"""Multi-echelon safety stock placement across a DC -> warehouse(s) tree.

Modeling approach
------------------
Each leaf node faces independent, normally-distributed end-customer demand
(mean, std per period). Each internal node's incoming replenishment demand
is modeled as the sum of its children's demand streams: under the standard
independence assumption, the aggregated mean is the sum of child means and
the aggregated variance is the sum of child variances (demand pooling /
risk pooling). This is the same mechanism that makes centralized inventory
cheaper than fully decentralized inventory — pooled variance grows with the
*sum* of variances, not with the square of the sum, so pooled coefficient
of variation falls as more independent demand streams are combined.

Simplifying assumption (stated explicitly, not hidden): an internal node's
incoming order stream is approximated as having the same mean and variance
as the aggregate downstream customer demand it ultimately serves (the
"demand pass-through" approximation, standard in pooled safety-stock
placement for tractability). This ignores order-batching-induced variance
amplification (the bullwhip effect) — a real limitation worth stating
plainly, not engineering around, since representing it as exact would be
the wrong kind of polish for a portfolio piece meant to survive technical
questioning.

Each node also has its own lead time (mean, std) from its supplier (parent),
and its own target service level, so safety stock is computed per node via
ledger.policies.safety_stock using that node's own aggregated demand and
own lead time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ledger.policies.safety_stock import (
    DemandLeadTimeInputs,
    SafetyStockResult,
    safety_stock_and_reorder_point,
)


@dataclass
class EchelonNode:
    """One node in the inventory network (a DC or a warehouse/store).

    For a leaf node, set mean_demand_per_period / std_demand_per_period to
    the node's own end-customer demand. For an internal node, leave them
    at 0.0 — they are computed bottom-up from children during propagation
    and populated into `aggregated_mean_demand` / `aggregated_std_demand`.
    """

    node_id: str
    mean_lead_time_periods: float
    std_lead_time_periods: float
    service_level: float
    mean_demand_per_period: float = 0.0
    std_demand_per_period: float = 0.0
    children: list[EchelonNode] = field(default_factory=list)

    # Populated by propagate_safety_stock():
    aggregated_mean_demand: float = field(default=0.0, init=False)
    aggregated_variance_demand: float = field(default=0.0, init=False)
    safety_stock_result: SafetyStockResult | None = field(default=None, init=False)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0


@dataclass(frozen=True)
class NetworkSafetyStockReport:
    """Flat, per-node view of the propagation result, easiest to test and serialize."""

    node_id: str
    aggregated_mean_demand: float
    aggregated_std_demand: float
    safety_stock: SafetyStockResult


def propagate_safety_stock(root: EchelonNode) -> dict[str, NetworkSafetyStockReport]:
    """Bottom-up pass: aggregate demand from leaves to root, then compute
    each node's own safety stock from its aggregated demand and own lead
    time. Returns a flat map keyed by node_id for easy lookup/serialization.
    """
    reports: dict[str, NetworkSafetyStockReport] = {}

    def visit(node: EchelonNode) -> tuple[float, float]:
        """Returns (mean, variance) of this node's aggregated demand stream."""
        if node.is_leaf:
            mean = node.mean_demand_per_period
            variance = node.std_demand_per_period ** 2
        else:
            mean = 0.0
            variance = 0.0
            for child in node.children:
                child_mean, child_variance = visit(child)
                mean += child_mean
                variance += child_variance  # independence assumption

        node.aggregated_mean_demand = mean
        node.aggregated_variance_demand = variance
        std = math.sqrt(variance)

        ss_inputs = DemandLeadTimeInputs(
            mean_demand_per_period=mean,
            std_demand_per_period=std,
            mean_lead_time_periods=node.mean_lead_time_periods,
            std_lead_time_periods=node.std_lead_time_periods,
            service_level=node.service_level,
        )
        result = safety_stock_and_reorder_point(ss_inputs)
        node.safety_stock_result = result

        reports[node.node_id] = NetworkSafetyStockReport(
            node_id=node.node_id,
            aggregated_mean_demand=mean,
            aggregated_std_demand=std,
            safety_stock=result,
        )
        return mean, variance

    visit(root)
    return reports


def total_network_safety_stock(reports: dict[str, NetworkSafetyStockReport]) -> float:
    """Sum of safety stock held at every node in the network."""
    return sum(r.safety_stock.safety_stock for r in reports.values())
