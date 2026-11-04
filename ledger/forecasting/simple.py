"""Lightweight demand forecasting: moving average and simple exponential smoothing.

These feed mean/std demand estimates into the policy layer (EOQ, safety
stock). The point of this module is the pipeline — forecast -> policy
inputs -> policy output — not forecasting sophistication; a production
AIO-style system would plug in a far richer forecasting model behind the
same interface.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ForecastResult:
    forecast_mean: float
    residual_std: float  # std dev of (actual - forecast), used as demand variability


def moving_average_forecast(history: Sequence[float], window: int) -> ForecastResult:
    """Simple moving average over the last `window` periods, with the
    residual std dev of history vs. a rolling forecast as the variability
    estimate fed into safety stock calculations.
    """
    if window <= 0:
        raise ValueError("window must be > 0")
    if len(history) < window:
        raise ValueError(f"need at least {window} periods of history, got {len(history)}")

    forecast_mean = sum(history[-window:]) / window

    residuals = []
    for i in range(window, len(history)):
        rolling_mean = sum(history[i - window:i]) / window
        residuals.append(history[i] - rolling_mean)

    if residuals:
        mean_residual = sum(residuals) / len(residuals)
        variance = sum((r - mean_residual) ** 2 for r in residuals) / len(residuals)
        residual_std = math.sqrt(variance)
    else:
        # Not enough history for a rolling residual series; fall back to
        # the sample std dev of the window itself as a conservative estimate.
        variance = sum((x - forecast_mean) ** 2 for x in history[-window:]) / window
        residual_std = math.sqrt(variance)

    return ForecastResult(forecast_mean=forecast_mean, residual_std=residual_std)


def exponential_smoothing_forecast(
    history: Sequence[float], alpha: float
) -> ForecastResult:
    """Simple exponential smoothing: S_t = alpha * x_t + (1 - alpha) * S_{t-1}.

    Residual std dev is computed over one-step-ahead forecast errors across
    the whole history, which is the standard way to estimate forecast-error
    variability for this model (and is exactly what feeds the demand-side
    sigma_D term in the safety stock formula).
    """
    if not (0.0 < alpha <= 1.0):
        raise ValueError("alpha must be in (0, 1]")
    if len(history) < 2:
        raise ValueError("need at least 2 periods of history")

    level = history[0]
    errors: list[float] = []

    for actual in history[1:]:
        error = actual - level
        errors.append(error)
        level = alpha * actual + (1 - alpha) * level

    mean_error = sum(errors) / len(errors)
    variance = sum((e - mean_error) ** 2 for e in errors) / len(errors)
    residual_std = math.sqrt(variance)

    return ForecastResult(forecast_mean=level, residual_std=residual_std)
