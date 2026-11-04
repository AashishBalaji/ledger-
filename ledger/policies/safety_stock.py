"""Safety stock and reorder point under demand and lead-time variability.

Standard formulas (Silver/Pyke/Peterson; also Chopra & Meindl "Supply Chain
Management"), used as the closed-form ground truth in tests.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True)
class DemandLeadTimeInputs:
    """Period demand and lead time, both potentially stochastic.

    mean_demand_per_period: average demand per period (e.g. per day)
    std_demand_per_period: std dev of demand per period
    mean_lead_time_periods: average lead time, in the same period units
    std_lead_time_periods: std dev of lead time (0.0 for deterministic lead time)
    service_level: target cycle service level, e.g. 0.95 for 95%
    """

    mean_demand_per_period: float
    std_demand_per_period: float
    mean_lead_time_periods: float
    std_lead_time_periods: float
    service_level: float

    def __post_init__(self) -> None:
        if self.mean_demand_per_period < 0:
            raise ValueError("mean_demand_per_period must be >= 0")
        if self.std_demand_per_period < 0:
            raise ValueError("std_demand_per_period must be >= 0")
        if self.mean_lead_time_periods <= 0:
            raise ValueError("mean_lead_time_periods must be > 0")
        if self.std_lead_time_periods < 0:
            raise ValueError("std_lead_time_periods must be >= 0")
        if not (0.0 < self.service_level < 1.0):
            raise ValueError("service_level must be in (0, 1)")


@dataclass(frozen=True)
class SafetyStockResult:
    z_score: float
    demand_during_lead_time: float
    std_dev_during_lead_time: float
    safety_stock: float
    reorder_point: float


def z_score_for_service_level(service_level: float) -> float:
    """Inverse standard-normal CDF: the z used throughout inventory theory."""
    return float(norm.ppf(service_level))


def safety_stock_and_reorder_point(inputs: DemandLeadTimeInputs) -> SafetyStockResult:
    """Reorder point under combined demand and lead-time variability.

    sigma_DL = sqrt(L * sigma_D^2 + D^2 * sigma_L^2)
    SS = z * sigma_DL
    ROP = D * L + SS

    When std_lead_time_periods == 0, this reduces to the simpler
    SS = z * sigma_D * sqrt(L) textbook case — exercised directly by a
    dedicated test to confirm the general formula collapses correctly.
    """
    d = inputs.mean_demand_per_period
    sigma_d = inputs.std_demand_per_period
    l = inputs.mean_lead_time_periods
    sigma_l = inputs.std_lead_time_periods
    z = z_score_for_service_level(inputs.service_level)

    demand_during_lead_time = d * l
    variance_during_lead_time = l * (sigma_d ** 2) + (d ** 2) * (sigma_l ** 2)
    std_dev_during_lead_time = math.sqrt(variance_during_lead_time)

    safety_stock = z * std_dev_during_lead_time
    reorder_point = demand_during_lead_time + safety_stock

    return SafetyStockResult(
        z_score=z,
        demand_during_lead_time=demand_during_lead_time,
        std_dev_during_lead_time=std_dev_during_lead_time,
        safety_stock=safety_stock,
        reorder_point=reorder_point,
    )
