"""CI triage agent: parses a failed pytest run (and optional benchmark
regression output), asks Claude for a root-cause note per failure, and
writes a markdown report. Wired into CI (.github/workflows/ci.yml) to run
only when the test or benchmark job actually fails, so it costs nothing on
green runs.

Design choices, stated plainly:
- The agent is handed only the pytest/benchmark TEXT output, never the
  repository's source. It reasons from the traceback the way a human
  triager glancing at a CI failure notification would, not from reading
  the codebase — keeping the agent's blast radius (and the CI permissions
  it needs) small.
- Parsing is based on pytest's own `-rf` / short-summary output format
  (`FAILED <test_id> - <message>`) plus the `___ test name ___` traceback
  section headers, both of which are part of pytest's documented default
  output, not an ad hoc scrape of something undocumented.
- The Claude client is injected (TriageClient protocol) so the parsing and
  prompt-construction logic is fully unit-testable without any network
  call or API key; only the thin ClaudeTriageClient wrapper touches the
  real API.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_MODEL = "claude-haiku-5-5"  # fast/cheap model is the right fit for a CI triage note

_FAILED_LINE_RE = re.compile(r"^FAILED (?P<test_id>\S+)(?: - (?P<message>.*))?$", re.MULTILINE)
_ERROR_LINE_RE = re.compile(r"^ERROR (?P<test_id>\S+)(?: - (?P<message>.*))?$", re.MULTILINE)
_SECTION_HEADER_RE = re.compile(r"^_{3,} (?P<name>.+?) _{3,}$", re.MULTILINE)

_TRACEBACK_EXCERPT_CHARS = 2000


@dataclass(frozen=True)
class FailureSummary:
    test_id: str
    short_message: str
    traceback_excerpt: str


def parse_pytest_failures(output: str) -> list[FailureSummary]:
    """Extract failing/erroring test IDs and their traceback context from
    pytest's standard text output (short summary line + traceback section)."""
    messages: dict[str, str] = {}
    for pattern in (_FAILED_LINE_RE, _ERROR_LINE_RE):
        for m in pattern.finditer(output):
            messages.setdefault(m.group("test_id"), m.group("message") or "")

    sections = list(_SECTION_HEADER_RE.finditer(output))
    tracebacks: dict[str, str] = {}
    for i, sec in enumerate(sections):
        name = sec.group("name").strip()
        start = sec.end()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(output)
        tracebacks[name] = output[start:end].strip()

    results: list[FailureSummary] = []
    for test_id, message in messages.items():
        short_name = test_id.split("::")[-1]
        excerpt = ""
        for name, tb in tracebacks.items():
            if short_name in name:
                excerpt = tb[:_TRACEBACK_EXCERPT_CHARS]
                break
        results.append(FailureSummary(test_id=test_id, short_message=message, traceback_excerpt=excerpt))
    return results


def build_triage_prompt(
    failures: list[FailureSummary], benchmark_regression_output: str | None = None
) -> str:
    """Builds the prompt sent to Claude: the raw failure data plus
    instructions to stay grounded in what's shown, not to speculate about
    code the agent was never given."""
    instructions = (
        "You are a CI triage assistant. You are given failing pytest test "
        "IDs, their short failure messages, and traceback excerpts from a "
        "single CI run. For EACH failure, write a short root-cause note: "
        "(1) what broke, in one sentence, grounded only in the traceback "
        "shown -- never guess at application code you have not been shown; "
        "(2) which kind of fix it likely needs (test bug, implementation "
        "bug, environment/dependency issue, or flaky/non-deterministic), "
        "with one sentence of reasoning; (3) if the traceback is too thin "
        "to tell, say so plainly instead of inventing a cause. "
        "Output markdown with one '## <test_id>' section per failure. Be "
        "concise -- a few sentences per failure, not a full analysis."
    )
    parts = [instructions, "", "## Failures"]
    for f in failures:
        parts.append(f"\n### {f.test_id}")
        parts.append(f"Message: {f.short_message or '(none)'}")
        if f.traceback_excerpt:
            parts.append(f"Traceback excerpt:\n```\n{f.traceback_excerpt}\n```")
        else:
            parts.append("Traceback excerpt: (not found in output)")

    if benchmark_regression_output:
        parts.append("\n## Benchmark regression check output")
        parts.append(f"```\n{benchmark_regression_output.strip()}\n```")
        parts.append(
            "\nAlso write one short '## Benchmark regressions' section "
            "summarizing which benchmarks regressed and by how much, "
            "grounded only in the output above."
        )

    return "\n".join(parts)


class TriageClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class ClaudeTriageClient:
    """Thin wrapper around the Anthropic Messages API. Reads
    ANTHROPIC_API_KEY from the environment (the SDK's own default)."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        import anthropic  # imported lazily so the rest of this module has no hard dependency

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1536,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


def run_triage(
    pytest_output: str,
    client: TriageClient,
    benchmark_regression_output: str | None = None,
) -> str:
    """Parses failures out of pytest_output and returns a markdown triage
    report. Returns a short "nothing to triage" note (no API call made) if
    there were no failures and no benchmark regression text supplied."""
    failures = parse_pytest_failures(pytest_output)

    if not failures and not benchmark_regression_output:
        return "# CI Triage Report\n\nNo failures found in the supplied pytest output. Nothing to triage.\n"

    if not failures and benchmark_regression_output:
        prompt = (
            "You are a CI triage assistant. All tests passed, but the "
            "benchmark regression check below reported a problem. Summarize "
            "which benchmark(s) regressed and by how much, grounded only in "
            "the output shown, in a few sentences.\n\n"
            f"```\n{benchmark_regression_output.strip()}\n```"
        )
    else:
        prompt = build_triage_prompt(failures, benchmark_regression_output)

    body = client.complete(prompt)
    return f"# CI Triage Report\n\n{body.strip()}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pytest-output",
        type=Path,
        default=None,
        help="path to captured pytest output; omit if this run has no test failures to triage "
        "(e.g. a benchmark-only regression)",
    )
    parser.add_argument("--benchmark-output", type=Path, default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    pytest_output = args.pytest_output.read_text() if args.pytest_output else ""
    benchmark_output = args.benchmark_output.read_text() if args.benchmark_output else None

    client = ClaudeTriageClient(model=args.model)
    report = run_triage(pytest_output, client, benchmark_output)

    args.output.write_text(report)
    print(f"Triage report written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
