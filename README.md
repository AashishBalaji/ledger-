# Ledger

An inventory optimization engine — EOQ, safety stock / reorder points under
demand and lead-time variability, and multi-echelon safety stock placement
across a DC/warehouse network — built around a validated, benchmarked test
harness, a containerized deployment, and an agentic CI-triage bot.

This project was built to demonstrate the specific combination of skills a
software-developer role on an "Advanced Inventory Optimization" team asks
for: Python software engineering, Python-based test automation and
benchmarking, Docker/Kubernetes, and agentic AI tooling in CI — not just
one of those in isolation.

## What's actually in here

- **`ledger/policies/eoq.py`** — classic EOQ and EOQ under quantity
  discounts (all-units price breaks).
- **`ledger/policies/safety_stock.py`** — reorder point and safety stock
  under combined demand and lead-time variability (the general
  `sigma_DL = sqrt(L*sigma_D^2 + D^2*sigma_L^2)` formula, which collapses
  to the simpler deterministic-lead-time case when `sigma_L = 0`).
- **`ledger/network/multi_echelon.py`** — safety stock placement across a
  DC -> warehouse(s) -> store(s) tree, using demand pooling (variances add
  across independent children, not standard deviations) to compute each
  node's own safety stock from its own aggregated demand and lead time.
  The modeling assumption behind this — that an internal node's incoming
  order stream has the same mean/variance as the demand it ultimately
  serves — is stated explicitly in the module docstring, not hidden. It
  ignores bullwhip-style variance amplification from order batching; that
  is a real simplification, not an oversight.
- **`ledger/forecasting/simple.py`** — moving average and exponential
  smoothing, feeding mean/variance estimates into the policy layer.
- **`ledger/api/`** — a FastAPI service (SKUs, demand history, EOQ/safety
  stock/network endpoints, Postgres via SQLAlchemy) wrapping the engine.
- **`ledger/agents/triage.py`** — a small agent (Claude API) that parses a
  failed pytest/benchmark CI run and writes a root-cause triage note. It
  only ever sees the pytest/benchmark text output, never the source tree,
  and makes no API call at all on a run with nothing to triage.

## Validation approach

Every policy formula is checked against textbook closed-form worked
examples (Silver/Pyke/Peterson; Chopra & Meindl) *and* against
property-based tests (Hypothesis) that sweep the whole valid input space —
so correctness isn't just "matches the two examples I hand-picked."
`tests/unit` (51 tests) covers this with no network or database required.

`tests/integration` (15 tests) runs the full FastAPI -> SQLAlchemy ->
Postgres stack against a real Postgres instance — not mocked — including
confirming that every policy computation is persisted as an audit record.

`tests/benchmarks` tracks solve-time for the multi-echelon propagation as
network size scales (10 to 1000 leaf nodes, flat and two-tier topologies).
`scripts/compare_benchmarks.py` compares a fresh run against the committed
baseline (`benchmarks/baseline.json`) and fails the CI job if any
benchmark's median regresses beyond 50% — this was verified to actually
catch an injected 3x regression, not just to exist as a step in a YAML
file.

## Running it

```bash
# unit + integration tests (needs a local Postgres)
pip install -e ".[dev]"
createuser ledger && createdb -O ledger ledger   # or use docker-compose below
export DATABASE_URL=postgresql+psycopg2://ledger:ledger@localhost:5432/ledger
pytest tests/unit tests/integration

# benchmarks
pytest tests/benchmarks --benchmark-only

# full stack via Docker
docker compose up --build
curl http://localhost:8000/health
```

## Kubernetes

`k8s/` has a namespace, a Postgres StatefulSet, and a Deployment+Service
for the app, with readiness/liveness probes on both, a Secret for
credentials, and a ConfigMap for non-secret connection details only (the
app resolves its full `DATABASE_URL` in-process from the two — see
`ledger/api/db.py` — so no password is ever written into a non-secret
object). These validate cleanly against the real Kubernetes API schemas
(`kubeconform -strict`, all 7 resources pass).

I made two attempts at a live cluster in the sandboxed environment these
were built in. `kind` failed outright: its kubeadm-based control-plane
node needs cgroup delegation the sandbox's cgroup v1 setup doesn't
support. `k3d` got further — its lighter-weight control-plane node does
start, and I used it to actually import the built image and `kubectl
apply` these exact manifests — but every real pod still fails at sandbox
creation with `runc create failed: ... can't get final child's PID from
pipe`, the same underlying cgroup v1 nested-delegation gap, just hit one
layer deeper (control plane vs. workload sandboxes). So, stating this
plainly rather than claiming a deploy that didn't happen: these manifests
are schema-valid, have been applied against a real (if partially
functional) cluster, and are ready to actually run end-to-end with `kind`,
`k3d`, or `minikube` on a machine with normal cgroup v2 support — they
just haven't been exercised to a fully Ready pod in this sandbox.

## CI/CD

`.github/workflows/ci.yml`: lint (ruff) -> unit + integration tests
against a real Postgres service container -> benchmark regression check
-> Docker build + a live container smoke test against a real Postgres
container. The triage agent runs automatically (and only) when the test or
benchmark job fails, given an `ANTHROPIC_API_KEY` repo secret; without that
secret configured, CI still runs and still fails loudly on a real failure,
it just skips the triage step.
