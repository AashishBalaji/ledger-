"""Economic Order Quantity (EOQ) and variants.

Reference formulas follow standard operations-research texts (e.g. Silver,
Pyke & Peterson, "Inventory and Production Management in Supply Chains").
All formulas here are the textbook closed-form results, used in tests as
ground truth to validate the implementation against.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EOQInputs:
    """Inputs to the classic EOQ model.

    annual_demand: units/year (D)
    order_cost: fixed cost per order, currency (S)
    holding_cost_per_unit: annual holding cost per unit, currency (H)
    """

    annual_demand: float
    order_cost: float
    holding_cost_per_unit: float

    def __post_init__(self) -> None:
        if self.annual_demand < 0:
            raise ValueError("annual_demand must be >= 0")
        if self.order_cost <= 0:
            raise ValueError("order_cost must be > 0")
        if self.holding_cost_per_unit <= 0:
            raise ValueError("holding_cost_per_unit must be > 0")


@dataclass(frozen=True)
class EOQResult:
    order_quantity: float
    orders_per_year: float
    cycle_time_days: float
    annual_ordering_cost: float
    annual_holding_cost: float
    total_annual_cost: float


def classic_eoq(inputs: EOQInputs) -> EOQResult:
    """Classic EOQ: Q* = sqrt(2DS / H).

    At Q*, annual ordering cost equals annual holding cost — this identity
    is itself used as a validation check in the test suite (it must hold
    for any valid D, S, H, not just worked examples).
    """
    d, s, h = inputs.annual_demand, inputs.order_cost, inputs.holding_cost_per_unit

    if d == 0:
        return EOQResult(
            order_quantity=0.0,
            orders_per_year=0.0,
            cycle_time_days=float("inf"),
            annual_ordering_cost=0.0,
            annual_holding_cost=0.0,
            total_annual_cost=0.0,
        )

    q_star = math.sqrt(2 * d * s / h)
    orders_per_year = d / q_star
    cycle_time_days = 365.0 / orders_per_year
    annual_ordering_cost = orders_per_year * s
    annual_holding_cost = (q_star / 2) * h
    total_annual_cost = annual_ordering_cost + annual_holding_cost

    return EOQResult(
        order_quantity=q_star,
        orders_per_year=orders_per_year,
        cycle_time_days=cycle_time_days,
        annual_ordering_cost=annual_ordering_cost,
        annual_holding_cost=annual_holding_cost,
        total_annual_cost=total_annual_cost,
    )


@dataclass(frozen=True)
class PriceBreak:
    """A quantity discount tier: ordering >= min_quantity unlocks unit_price."""

    min_quantity: float
    unit_price: float


def eoq_with_quantity_discounts(
    annual_demand: float,
    order_cost: float,
    holding_cost_rate: float,
    price_breaks: Sequence[PriceBreak],
) -> tuple[EOQResult, float, float]:
    """EOQ under all-units quantity discounts (standard algorithm).

    holding_cost_rate is a fraction of unit price charged annually as
    holding cost (H = i * C), which is how discount-tier EOQ problems are
    conventionally posed, since holding cost scales with the price paid.

    Returns (result_at_chosen_quantity, unit_price, total_annual_cost_incl_purchase).

    Algorithm (Silver/Pyke/Peterson):
      1. Starting from the cheapest price tier, compute the EOQ using that
         tier's price for holding cost.
      2. If the computed EOQ lies in a quantity range that actually
         qualifies for that tier's price, it's feasible — evaluate it.
      3. Otherwise move up and also evaluate the cost at each tier's
         min_quantity breakpoint (since demand may be best served by
         exactly hitting a breakpoint).
      4. Choose the candidate with lowest total annual cost (ordering +
         holding + purchase).
    """
    if not price_breaks:
        raise ValueError("price_breaks must not be empty")

    sorted_breaks = sorted(price_breaks, key=lambda pb: pb.min_quantity)

    candidates: list[tuple[float, float]] = []  # (quantity, unit_price)

    for i, pb in enumerate(sorted_breaks):
        h = holding_cost_rate * pb.unit_price
        inputs = EOQInputs(annual_demand, order_cost, h)
        eoq_result = classic_eoq(inputs)
        q = eoq_result.order_quantity

        lower = pb.min_quantity
        upper = (
            sorted_breaks[i + 1].min_quantity
            if i + 1 < len(sorted_breaks)
            else float("inf")
        )

        if lower <= q < upper:
            candidates.append((q, pb.unit_price))
        else:
            # EOQ not feasible at this tier's price; the tier's own
            # breakpoint quantity is still a candidate to evaluate.
            candidates.append((lower, pb.unit_price))

    def total_cost(q: float, unit_price: float) -> float:
        h = holding_cost_rate * unit_price
        orders_per_year = annual_demand / q if q > 0 else 0.0
        ordering = orders_per_year * order_cost
        holding = (q / 2) * h
        purchase = annual_demand * unit_price
        return ordering + holding + purchase

    best_q, best_price = min(candidates, key=lambda c: total_cost(*c))
    best_h = holding_cost_rate * best_price

    result = classic_eoq(EOQInputs(annual_demand, order_cost, best_h))
    # Override quantity/derived fields with the actually-chosen (possibly
    # breakpoint-constrained) quantity rather than the unconstrained EOQ.
    orders_per_year = annual_demand / best_q if best_q > 0 else 0.0
    result = EOQResult(
        order_quantity=best_q,
        orders_per_year=orders_per_year,
        cycle_time_days=365.0 / orders_per_year if orders_per_year > 0 else float("inf"),
        annual_ordering_cost=orders_per_year * order_cost,
        annual_holding_cost=(best_q / 2) * best_h,
        total_annual_cost=total_cost(best_q, best_price),
    )
    return result, best_price, result.total_annual_cost
