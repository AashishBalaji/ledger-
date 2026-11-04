"""Multi-echelon safety stock placement: validates the variance-pooling
aggregation and that per-node safety stock matches the single-node formula
once aggregated demand is known."""
import math

import pytest

from ledger.network.multi_echelon import (
    EchelonNode,
    propagate_safety_stock,
    total_network_safety_stock,
)
from ledger.policies.safety_stock import DemandLeadTimeInputs, safety_stock_and_reorder_point


def test_leaf_node_matches_single_node_safety_stock():
    """A tree of exactly one leaf node must reduce to the plain single-node
    safety stock calculation — no pooling effect with nothing to pool."""
    leaf = EchelonNode(
        node_id="store-1",
        mean_lead_time_periods=3,
        std_lead_time_periods=0.0,
        service_level=0.95,
        mean_demand_per_period=200,
        std_demand_per_period=40,
    )
    reports = propagate_safety_stock(leaf)
    expected = safety_stock_and_reorder_point(
        DemandLeadTimeInputs(200, 40, 3, 0.0, 0.95)
    )
    assert reports["store-1"].safety_stock.safety_stock == pytest.approx(
        expected.safety_stock, rel=1e-9
    )


def test_two_leaf_aggregation_pools_variance_not_std():
    """Two independent children with demand (mean=100, std=20) each: the
    parent's aggregated variance must be the SUM of the children's
    variances (risk pooling), not a sum of standard deviations."""
    child_a = EchelonNode(
        node_id="wh-a", mean_lead_time_periods=1, std_lead_time_periods=0.0,
        service_level=0.95, mean_demand_per_period=100, std_demand_per_period=20,
    )
    child_b = EchelonNode(
        node_id="wh-b", mean_lead_time_periods=1, std_lead_time_periods=0.0,
        service_level=0.95, mean_demand_per_period=100, std_demand_per_period=20,
    )
    dc = EchelonNode(
        node_id="dc", mean_lead_time_periods=5, std_lead_time_periods=0.0,
        service_level=0.95, children=[child_a, child_b],
    )

    reports = propagate_safety_stock(dc)

    expected_mean = 200  # 100 + 100
    expected_variance = 400 + 400  # 20^2 + 20^2
    expected_std = math.sqrt(expected_variance)

    assert reports["dc"].aggregated_mean_demand == pytest.approx(expected_mean)
    assert reports["dc"].aggregated_std_demand == pytest.approx(expected_std)

    # Explicitly confirm this is NOT std-summed (a common implementation bug):
    wrong_std_sum = 20 + 20
    assert reports["dc"].aggregated_std_demand < wrong_std_sum


def test_pooling_reduces_coefficient_of_variation():
    """The core economic justification for centralization: pooling N
    independent, identically-distributed demand streams reduces the
    coefficient of variation (std/mean) of the pooled stream by sqrt(N)
    relative to a single stream, for streams with equal mean and std."""
    n = 4
    children = [
        EchelonNode(
            node_id=f"store-{i}", mean_lead_time_periods=1, std_lead_time_periods=0.0,
            service_level=0.95, mean_demand_per_period=50, std_demand_per_period=15,
        )
        for i in range(n)
    ]
    dc = EchelonNode(
        node_id="dc", mean_lead_time_periods=1, std_lead_time_periods=0.0,
        service_level=0.95, children=children,
    )
    reports = propagate_safety_stock(dc)

    single_cv = 15 / 50
    pooled_cv = reports["dc"].aggregated_std_demand / reports["dc"].aggregated_mean_demand
    assert pooled_cv == pytest.approx(single_cv / math.sqrt(n), rel=1e-6)


def test_three_tier_tree_propagates_bottom_up():
    """DC -> 2 regional warehouses -> each with 2 stores. Confirms
    aggregation is correct across more than one level of the tree."""
    stores_a = [
        EchelonNode(f"store-a{i}", 1, 0.0, 0.95, mean_demand_per_period=30, std_demand_per_period=8)
        for i in range(2)
    ]
    stores_b = [
        EchelonNode(f"store-b{i}", 1, 0.0, 0.95, mean_demand_per_period=40, std_demand_per_period=10)
        for i in range(2)
    ]
    wh_a = EchelonNode("wh-a", 2, 0.0, 0.95, children=stores_a)
    wh_b = EchelonNode("wh-b", 2, 0.0, 0.95, children=stores_b)
    dc = EchelonNode("dc", 5, 0.0, 0.95, children=[wh_a, wh_b])

    reports = propagate_safety_stock(dc)

    assert reports["wh-a"].aggregated_mean_demand == pytest.approx(60)
    assert reports["wh-b"].aggregated_mean_demand == pytest.approx(80)
    assert reports["dc"].aggregated_mean_demand == pytest.approx(140)

    expected_dc_variance = (64 + 64) + (100 + 100)  # sum of all 4 store variances
    assert reports["dc"].aggregated_std_demand == pytest.approx(math.sqrt(expected_dc_variance))

    # Every node in the tree must appear in the flat report map.
    assert set(reports.keys()) == {"dc", "wh-a", "wh-b", "store-a0", "store-a1", "store-b0", "store-b1"}


def test_total_network_safety_stock_sums_all_nodes():
    child = EchelonNode("a", 1, 0.0, 0.95, mean_demand_per_period=50, std_demand_per_period=10)
    root = EchelonNode("root", 2, 0.0, 0.95, children=[child])
    reports = propagate_safety_stock(root)

    expected_total = sum(r.safety_stock.safety_stock for r in reports.values())
    assert total_network_safety_stock(reports) == pytest.approx(expected_total)
    assert total_network_safety_stock(reports) == pytest.approx(
        reports["root"].safety_stock.safety_stock + reports["a"].safety_stock.safety_stock
    )
