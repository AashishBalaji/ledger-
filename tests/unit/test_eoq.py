"""EOQ validated against textbook closed-form worked examples, plus
structural identities that must hold for any valid inputs."""
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ledger.policies.eoq import (
    EOQInputs,
    PriceBreak,
    classic_eoq,
    eoq_with_quantity_discounts,
)


def test_classic_textbook_example():
    """D=1000/yr, S=$50/order, H=$2/unit/yr -> Q* = sqrt(2*1000*50/2) = 223.6068...
    (standard EOQ worked example, e.g. Silver/Pyke/Peterson Ch. 5)."""
    inputs = EOQInputs(annual_demand=1000, order_cost=50, holding_cost_per_unit=2)
    result = classic_eoq(inputs)
    assert result.order_quantity == pytest.approx(223.6068, rel=1e-4)


def test_chopra_meindl_example():
    """D=12000/yr, S=$4000/order, H=0.2*500=$100/unit/yr -> Q*=sqrt(2*12000*4000/100)=979.80
    (Chopra & Meindl, Supply Chain Management, standard EOQ example)."""
    inputs = EOQInputs(annual_demand=12000, order_cost=4000, holding_cost_per_unit=100)
    result = classic_eoq(inputs)
    assert result.order_quantity == pytest.approx(979.7959, rel=1e-4)


def test_ordering_cost_equals_holding_cost_at_optimum():
    """Defining property of EOQ: at Q*, annual ordering cost == annual holding cost.
    This must hold for any valid (D, S, H), not just the worked examples above."""
    inputs = EOQInputs(annual_demand=5000, order_cost=120, holding_cost_per_unit=3.5)
    result = classic_eoq(inputs)
    assert result.annual_ordering_cost == pytest.approx(result.annual_holding_cost, rel=1e-9)


def test_total_cost_is_sum_of_components():
    inputs = EOQInputs(annual_demand=7300, order_cost=80, holding_cost_per_unit=1.5)
    result = classic_eoq(inputs)
    assert result.total_annual_cost == pytest.approx(
        result.annual_ordering_cost + result.annual_holding_cost
    )


def test_zero_demand_yields_zero_order_quantity():
    inputs = EOQInputs(annual_demand=0, order_cost=50, holding_cost_per_unit=2)
    result = classic_eoq(inputs)
    assert result.order_quantity == 0.0
    assert result.total_annual_cost == 0.0


@pytest.mark.parametrize(
    "order_cost,holding_cost",
    [(0, 2), (-1, 2), (50, 0), (50, -1)],
)
def test_invalid_cost_inputs_raise(order_cost, holding_cost):
    with pytest.raises(ValueError):
        EOQInputs(annual_demand=1000, order_cost=order_cost, holding_cost_per_unit=holding_cost)


def test_negative_demand_raises():
    with pytest.raises(ValueError):
        EOQInputs(annual_demand=-5, order_cost=50, holding_cost_per_unit=2)


@given(
    d=st.floats(min_value=1, max_value=1_000_000, allow_nan=False),
    s=st.floats(min_value=0.01, max_value=100_000, allow_nan=False),
    h=st.floats(min_value=0.01, max_value=100_000, allow_nan=False),
)
@settings(max_examples=200)
def test_eoq_matches_closed_form_for_arbitrary_valid_inputs(d, s, h):
    """Property-based: the implementation must equal the closed-form formula
    for ANY valid (D, S, H), not just the two worked examples above."""
    result = classic_eoq(EOQInputs(annual_demand=d, order_cost=s, holding_cost_per_unit=h))
    expected_q = math.sqrt(2 * d * s / h)
    assert result.order_quantity == pytest.approx(expected_q, rel=1e-9)


@given(
    d=st.floats(min_value=1, max_value=1_000_000, allow_nan=False),
    s=st.floats(min_value=0.01, max_value=100_000, allow_nan=False),
    h=st.floats(min_value=0.01, max_value=100_000, allow_nan=False),
)
@settings(max_examples=200)
def test_ordering_equals_holding_cost_property(d, s, h):
    """Same defining-property check as above, but swept across the input space."""
    result = classic_eoq(EOQInputs(annual_demand=d, order_cost=s, holding_cost_per_unit=h))
    assert result.annual_ordering_cost == pytest.approx(result.annual_holding_cost, rel=1e-6)


def test_quantity_discount_picks_lower_total_cost_tier():
    """Classic quantity-discount worked example (Silver/Pyke/Peterson style):
    a deep enough price break at a high enough minimum quantity should win
    over the unconstrained EOQ at the base price, when its total cost
    (incl. purchase cost) is actually lower."""
    price_breaks = [
        PriceBreak(min_quantity=0, unit_price=5.00),
        PriceBreak(min_quantity=1000, unit_price=4.50),
    ]
    _result, _chosen_price, total_cost = eoq_with_quantity_discounts(
        annual_demand=5000,
        order_cost=49,
        holding_cost_rate=0.2,
        price_breaks=price_breaks,
    )
    # Unconstrained EOQ at the base price:
    base_eoq = classic_eoq(EOQInputs(5000, 49, 0.2 * 5.00)).order_quantity
    assert base_eoq < 1000  # confirms the discount tier is NOT naturally reached

    # The discount should still be evaluated and chosen if cheaper overall.
    base_total = (
        (5000 / base_eoq) * 49 + (base_eoq / 2) * (0.2 * 5.00) + 5000 * 5.00
    )
    assert total_cost <= base_total


def test_quantity_discount_requires_nonempty_breaks():
    with pytest.raises(ValueError):
        eoq_with_quantity_discounts(
            annual_demand=1000, order_cost=50, holding_cost_rate=0.2, price_breaks=[]
        )
