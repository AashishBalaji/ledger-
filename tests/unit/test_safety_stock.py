"""Safety stock / reorder point validated against textbook worked examples
(Chopra & Meindl style), plus the collapse-to-simple-case check."""
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import norm

from ledger.policies.safety_stock import (
    DemandLeadTimeInputs,
    safety_stock_and_reorder_point,
    z_score_for_service_level,
)


def test_z_score_matches_scipy_directly():
    assert z_score_for_service_level(0.95) == pytest.approx(1.6449, rel=1e-4)
    assert z_score_for_service_level(0.90) == pytest.approx(1.2816, rel=1e-4)


def test_deterministic_lead_time_worked_example():
    """D=2500 units/week, sigma_D=500, L=2 weeks (deterministic), CSL=0.90.
    sigma_DL = sigma_D * sqrt(L) = 500 * sqrt(2) = 707.107
    SS = z * sigma_DL = 1.2816 * 707.107 = 906.3
    ROP = D*L + SS = 5000 + 906.3 = 5906.3
    (Chopra & Meindl, Supply Chain Management, standard worked example)."""
    inputs = DemandLeadTimeInputs(
        mean_demand_per_period=2500,
        std_demand_per_period=500,
        mean_lead_time_periods=2,
        std_lead_time_periods=0.0,
        service_level=0.90,
    )
    result = safety_stock_and_reorder_point(inputs)

    expected_sigma_dl = 500 * math.sqrt(2)
    assert result.std_dev_during_lead_time == pytest.approx(expected_sigma_dl, rel=1e-4)
    assert result.safety_stock == pytest.approx(1.2816 * expected_sigma_dl, rel=1e-3)
    assert result.reorder_point == pytest.approx(5000 + result.safety_stock, rel=1e-6)


def test_variable_lead_time_worked_example():
    """D=2500/week, sigma_D=500, L=2 weeks, sigma_L=1 week, CSL=0.90.
    sigma_DL = sqrt(L*sigma_D^2 + D^2*sigma_L^2)
             = sqrt(2*500^2 + 2500^2*1^2) = sqrt(500000 + 6250000) = sqrt(6750000) = 2598.08
    SS = 1.2816 * 2598.08 = 3329.7
    ROP = 5000 + 3329.7 = 8329.7"""
    inputs = DemandLeadTimeInputs(
        mean_demand_per_period=2500,
        std_demand_per_period=500,
        mean_lead_time_periods=2,
        std_lead_time_periods=1,
        service_level=0.90,
    )
    result = safety_stock_and_reorder_point(inputs)

    expected_sigma_dl = math.sqrt(2 * 500**2 + 2500**2 * 1**2)
    assert expected_sigma_dl == pytest.approx(2598.08, rel=1e-4)
    assert result.std_dev_during_lead_time == pytest.approx(expected_sigma_dl, rel=1e-4)
    assert result.safety_stock == pytest.approx(1.2816 * expected_sigma_dl, rel=1e-3)


def test_deterministic_lead_time_is_special_case_of_general_formula():
    """With std_lead_time_periods=0, the general sigma_DL formula must
    collapse exactly to sigma_D * sqrt(L) — i.e. the two formulas are not
    independently implemented, one is a special case of the other."""
    general = DemandLeadTimeInputs(
        mean_demand_per_period=800,
        std_demand_per_period=120,
        mean_lead_time_periods=5,
        std_lead_time_periods=0.0,
        service_level=0.95,
    )
    result = safety_stock_and_reorder_point(general)
    simple_expected = 120 * math.sqrt(5)
    assert result.std_dev_during_lead_time == pytest.approx(simple_expected, rel=1e-9)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mean_demand_per_period", -1),
        ("std_demand_per_period", -1),
        ("mean_lead_time_periods", 0),
        ("mean_lead_time_periods", -1),
        ("std_lead_time_periods", -1),
    ],
)
def test_invalid_inputs_raise(field, value):
    kwargs = {
        "mean_demand_per_period": 100,
        "std_demand_per_period": 10,
        "mean_lead_time_periods": 2,
        "std_lead_time_periods": 0.0,
        "service_level": 0.95,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        DemandLeadTimeInputs(**kwargs)


@pytest.mark.parametrize("service_level", [0.0, 1.0, -0.1, 1.1])
def test_invalid_service_level_raises(service_level):
    with pytest.raises(ValueError):
        DemandLeadTimeInputs(
            mean_demand_per_period=100,
            std_demand_per_period=10,
            mean_lead_time_periods=2,
            std_lead_time_periods=0.0,
            service_level=service_level,
        )


@given(
    d=st.floats(min_value=0, max_value=100_000, allow_nan=False),
    sigma_d=st.floats(min_value=0, max_value=10_000, allow_nan=False),
    l=st.floats(min_value=0.01, max_value=365, allow_nan=False),
    sigma_l=st.floats(min_value=0, max_value=50, allow_nan=False),
    service_level=st.floats(min_value=0.5, max_value=0.999, allow_nan=False),
)
@settings(max_examples=200)
def test_matches_closed_form_for_arbitrary_valid_inputs(d, sigma_d, l, sigma_l, service_level):
    """Property-based: implementation must equal the closed-form formula
    across the whole valid input space, not just the worked examples."""
    inputs = DemandLeadTimeInputs(d, sigma_d, l, sigma_l, service_level)
    result = safety_stock_and_reorder_point(inputs)

    expected_z = norm.ppf(service_level)
    expected_variance = l * sigma_d**2 + d**2 * sigma_l**2
    expected_sigma_dl = math.sqrt(expected_variance)
    expected_ss = expected_z * expected_sigma_dl
    expected_rop = d * l + expected_ss

    assert result.z_score == pytest.approx(expected_z, rel=1e-9)
    assert result.std_dev_during_lead_time == pytest.approx(expected_sigma_dl, rel=1e-9)
    assert result.safety_stock == pytest.approx(expected_ss, rel=1e-9)
    assert result.reorder_point == pytest.approx(expected_rop, rel=1e-9)


@given(
    d=st.floats(min_value=1, max_value=100_000, allow_nan=False),
    sigma_d=st.floats(min_value=0, max_value=10_000, allow_nan=False),
    l=st.floats(min_value=0.01, max_value=365, allow_nan=False),
    service_level=st.floats(min_value=0.5, max_value=0.999, allow_nan=False),
)
@settings(max_examples=100)
def test_higher_service_level_never_decreases_safety_stock(d, sigma_d, l, service_level):
    """Monotonicity property: raising the target service level must never
    lower the computed safety stock, for any fixed demand/lead-time inputs."""
    lower = DemandLeadTimeInputs(d, sigma_d, l, 0.0, service_level)
    higher_level = min(service_level + 0.0005, 0.9999)
    higher = DemandLeadTimeInputs(d, sigma_d, l, 0.0, higher_level)

    r_lower = safety_stock_and_reorder_point(lower)
    r_higher = safety_stock_and_reorder_point(higher)

    assert r_higher.safety_stock >= r_lower.safety_stock - 1e-9
