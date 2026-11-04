"""Benchmark suite: tracks solve-time for the multi-echelon safety stock
propagation as network size (leaf/node count) scales. Run with:

    pytest tests/benchmarks --benchmark-only --benchmark-autosave

CI (see .github/workflows/ci.yml) compares each run against the last saved
baseline and fails if the median time regresses beyond a set threshold —
this is what "validate ... through testing, benchmarking, and data-driven
analysis" means in practice, not just a one-off timing print.
"""
from __future__ import annotations

from ledger.network.multi_echelon import EchelonNode, propagate_safety_stock
from ledger.policies.eoq import EOQInputs, classic_eoq


def _build_flat_network(n_leaves: int) -> EchelonNode:
    """One DC directly supplying n_leaves independent warehouses — the
    simplest shape that scales node count linearly."""
    children = [
        EchelonNode(
            node_id=f"wh-{i}",
            mean_lead_time_periods=2,
            std_lead_time_periods=0.5,
            service_level=0.95,
            mean_demand_per_period=100 + (i % 7),
            std_demand_per_period=20 + (i % 5),
        )
        for i in range(n_leaves)
    ]
    return EchelonNode(
        node_id="dc",
        mean_lead_time_periods=5,
        std_lead_time_periods=1.0,
        service_level=0.95,
        children=children,
    )


def _build_two_tier_network(n_warehouses: int, stores_per_warehouse: int) -> EchelonNode:
    """DC -> n_warehouses -> stores_per_warehouse stores each, exercising
    a deeper tree than the flat case."""
    warehouses = []
    for w in range(n_warehouses):
        stores = [
            EchelonNode(
                node_id=f"wh-{w}-store-{s}",
                mean_lead_time_periods=1,
                std_lead_time_periods=0.2,
                service_level=0.95,
                mean_demand_per_period=30 + (s % 4),
                std_demand_per_period=8 + (s % 3),
            )
            for s in range(stores_per_warehouse)
        ]
        warehouses.append(
            EchelonNode(
                node_id=f"wh-{w}",
                mean_lead_time_periods=2,
                std_lead_time_periods=0.5,
                service_level=0.95,
                children=stores,
            )
        )
    return EchelonNode(
        node_id="dc",
        mean_lead_time_periods=5,
        std_lead_time_periods=1.0,
        service_level=0.95,
        children=warehouses,
    )


def test_benchmark_flat_network_10(benchmark):
    network = _build_flat_network(10)
    benchmark(propagate_safety_stock, network)


def test_benchmark_flat_network_100(benchmark):
    network = _build_flat_network(100)
    benchmark(propagate_safety_stock, network)


def test_benchmark_flat_network_1000(benchmark):
    network = _build_flat_network(1000)
    benchmark(propagate_safety_stock, network)


def test_benchmark_two_tier_network_10x10(benchmark):
    """10 warehouses x 10 stores = 100 leaves + 10 internal nodes + root."""
    network = _build_two_tier_network(n_warehouses=10, stores_per_warehouse=10)
    benchmark(propagate_safety_stock, network)


def test_benchmark_two_tier_network_20x25(benchmark):
    """20 warehouses x 25 stores = 500 leaves — a realistic mid-size
    regional network, to catch any non-linear blowup before it reaches
    production scale."""
    network = _build_two_tier_network(n_warehouses=20, stores_per_warehouse=25)
    benchmark(propagate_safety_stock, network)


def test_benchmark_single_eoq_call(benchmark):
    inputs = EOQInputs(annual_demand=12000, order_cost=4000, holding_cost_per_unit=100)
    benchmark(classic_eoq, inputs)
