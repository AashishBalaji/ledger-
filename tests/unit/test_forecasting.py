"""Forecasting module: validated against hand-computed small examples."""

import pytest

from ledger.forecasting.simple import exponential_smoothing_forecast, moving_average_forecast


def test_moving_average_basic():
    history = [10, 20, 30, 40, 50]
    result = moving_average_forecast(history, window=3)
    # last 3: 30, 40, 50 -> mean = 40
    assert result.forecast_mean == pytest.approx(40.0)


def test_moving_average_insufficient_history_raises():
    with pytest.raises(ValueError):
        moving_average_forecast([1, 2], window=5)


def test_moving_average_invalid_window_raises():
    with pytest.raises(ValueError):
        moving_average_forecast([1, 2, 3], window=0)


def test_exponential_smoothing_hand_computed():
    """alpha=0.5, history=[10, 20]:
    level starts at 10 (first obs). error = 20 - 10 = 10.
    level = 0.5*20 + 0.5*10 = 15."""
    result = exponential_smoothing_forecast([10, 20], alpha=0.5)
    assert result.forecast_mean == pytest.approx(15.0)
    assert result.residual_std == pytest.approx(0.0)  # single error, zero variance by definition


def test_exponential_smoothing_three_points_hand_computed():
    """alpha=0.5, history=[10, 20, 10]:
    level_0 = 10
    error_1 = 20-10=10; level_1 = 0.5*20+0.5*10=15
    error_2 = 10-15=-5; level_2 = 0.5*10+0.5*15=12.5
    errors = [10, -5] -> mean=2.5, variance=((10-2.5)^2+(-5-2.5)^2)/2 = (56.25+56.25)/2=56.25
    residual_std = sqrt(56.25) = 7.5"""
    result = exponential_smoothing_forecast([10, 20, 10], alpha=0.5)
    assert result.forecast_mean == pytest.approx(12.5)
    assert result.residual_std == pytest.approx(7.5)


def test_exponential_smoothing_invalid_alpha_raises():
    with pytest.raises(ValueError):
        exponential_smoothing_forecast([1, 2, 3], alpha=0.0)
    with pytest.raises(ValueError):
        exponential_smoothing_forecast([1, 2, 3], alpha=1.5)


def test_exponential_smoothing_needs_two_points():
    with pytest.raises(ValueError):
        exponential_smoothing_forecast([5], alpha=0.5)


def test_exponential_smoothing_alpha_one_tracks_last_observation():
    """alpha=1 means the level jumps straight to the latest observation each
    step, so the final level equals the last observation exactly."""
    history = [10, 50, 5, 90, 33]
    result = exponential_smoothing_forecast(history, alpha=1.0)
    assert result.forecast_mean == pytest.approx(history[-1])
