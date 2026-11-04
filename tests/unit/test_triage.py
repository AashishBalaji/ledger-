"""Triage agent tests. No network calls: the Claude client is a fake
stand-in (TriageClient protocol) so parsing/prompt-construction logic is
tested in isolation from the real API."""
from ledger.agents.triage import (
    FailureSummary,
    build_triage_prompt,
    parse_pytest_failures,
    run_triage,
)

SAMPLE_PYTEST_OUTPUT = """\
============================= test session starts ==============================
collected 3 items

tests/unit/test_eoq.py F..                                                 [100%]

=================================== FAILURES ====================================
______________________ test_classic_textbook_example ____________________________

    def test_classic_textbook_example():
        inputs = EOQInputs(annual_demand=1000, order_cost=50, holding_cost_per_unit=2)
        result = classic_eoq(inputs)
>       assert result.order_quantity == pytest.approx(999.0, rel=1e-4)
E       assert 223.60679774997897 == 999.0 ± 1.0e-04

tests/unit/test_eoq.py:15: AssertionError
=========================== short test summary info =============================
FAILED tests/unit/test_eoq.py::test_classic_textbook_example - assert 223.60679774997897 == 999.0 ± 1.0e-04
======================== 1 failed, 2 passed in 0.12s ==============================
"""

SAMPLE_PASSING_OUTPUT = """\
============================= test session starts ==============================
collected 42 items
42 passed in 1.23s
"""


class FakeTriageClient:
    def __init__(self, response: str = "fake triage response"):
        self.response = response
        self.last_prompt: str | None = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def test_parse_pytest_failures_extracts_test_id_and_message():
    failures = parse_pytest_failures(SAMPLE_PYTEST_OUTPUT)
    assert len(failures) == 1
    f = failures[0]
    assert f.test_id == "tests/unit/test_eoq.py::test_classic_textbook_example"
    assert "223.60679774997897 == 999.0" in f.short_message


def test_parse_pytest_failures_extracts_traceback_excerpt():
    failures = parse_pytest_failures(SAMPLE_PYTEST_OUTPUT)
    f = failures[0]
    assert "pytest.approx(999.0" in f.traceback_excerpt
    assert "AssertionError" in f.traceback_excerpt


def test_parse_pytest_failures_empty_on_all_pass():
    failures = parse_pytest_failures(SAMPLE_PASSING_OUTPUT)
    assert failures == []


def test_build_triage_prompt_includes_test_id_and_traceback():
    failures = [
        FailureSummary(
            test_id="tests/x.py::test_y",
            short_message="assert 1 == 2",
            traceback_excerpt="some traceback text here",
        )
    ]
    prompt = build_triage_prompt(failures)
    assert "tests/x.py::test_y" in prompt
    assert "assert 1 == 2" in prompt
    assert "some traceback text here" in prompt
    # Instructs the model not to speculate beyond the given traceback:
    assert "never guess" in prompt.lower() or "not invent" in prompt.lower() or "speculate" in prompt.lower()


def test_build_triage_prompt_includes_benchmark_section_when_given():
    failures = []
    prompt = build_triage_prompt(failures, benchmark_regression_output="REGRESSION: foo +120%")
    assert "REGRESSION: foo" in prompt
    assert "Benchmark regression" in prompt


def test_run_triage_no_failures_no_benchmark_skips_api_call():
    client = FakeTriageClient()
    report = run_triage(SAMPLE_PASSING_OUTPUT, client)
    assert "No failures found" in report
    assert client.last_prompt is None  # API must not be called when there's nothing to triage


def test_run_triage_with_failure_calls_client_and_wraps_response():
    client = FakeTriageClient(response="## test_classic_textbook_example\nThe expected value in the test was wrong.")
    report = run_triage(SAMPLE_PYTEST_OUTPUT, client)
    assert client.last_prompt is not None
    assert "test_classic_textbook_example" in client.last_prompt
    assert "# CI Triage Report" in report
    assert "The expected value in the test was wrong." in report


def test_run_triage_benchmark_only_regression_builds_dedicated_prompt():
    client = FakeTriageClient(response="network_1000 regressed 3x due to...")
    report = run_triage(
        SAMPLE_PASSING_OUTPUT, client, benchmark_regression_output="REGRESSION: test_benchmark_flat_network_1000"
    )
    assert client.last_prompt is not None
    assert "REGRESSION: test_benchmark_flat_network_1000" in client.last_prompt
    assert "network_1000 regressed 3x due to..." in report


def test_parse_pytest_failures_handles_error_lines_too():
    output = (
        "=========================== short test summary info =============================\n"
        "ERROR tests/integration/test_x.py::test_y - ConnectionRefusedError\n"
    )
    failures = parse_pytest_failures(output)
    assert len(failures) == 1
    assert failures[0].test_id == "tests/integration/test_x.py::test_y"
    assert "ConnectionRefusedError" in failures[0].short_message
