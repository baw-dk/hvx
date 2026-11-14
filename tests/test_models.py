# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Estimation models against synthetic data with a known answer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hvx.simulations.models.scenario import ScenarioImpactModel
from hvx.simulations.models.ventilation import VentilationCalculator


def _decays(step_min: int, ach: float, background: float = 430.0, seed: int = 1):
    """Two weeks: 1400 ppm while occupied (weekdays 08-15), then decay at `ach`."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-03-04", periods=int(14 * 24 * 60 / step_min), freq=f"{step_min}min")
    hour = idx.hour + idx.minute / 60
    weekday = idx.day_of_week < 5
    occupied = weekday & (hour >= 8) & (hour < 15)
    after = weekday & (hour >= 15)
    values = np.full(len(idx), background)
    values[occupied] = 1400.0
    values[after] = background + (1400.0 - background) * np.exp(-ach * (hour[after] - 15))
    return pd.Series(values + rng.normal(0, 5, len(idx)), index=idx), pd.Series(~occupied, index=idx)


@pytest.mark.parametrize("step,ach", [(10, 0.5), (10, 2.0), (10, 5.0), (60, 0.3), (60, 0.5), (15, 1.0)])
def test_decay_rate_is_recovered(step, ach):
    co2, unoccupied = _decays(step, ach)
    result = VentilationCalculator().estimate_from_co2_decay(co2, unoccupied=unoccupied)
    assert result is not None and result.ach == pytest.approx(ach, rel=0.08)
    assert result.outdoor_co2 == pytest.approx(430, abs=15)  # background estimated, not assumed 400
    assert result.category == "after_hours"


def test_too_fast_for_hourly_data_is_not_reported_as_slow():
    co2, unoccupied = _decays(60, 2.0)
    assert VentilationCalculator().estimate_from_co2_decay(co2, unoccupied=unoccupied) is None


def test_decays_during_occupancy_are_ignored():
    co2, unoccupied = _decays(10, 1.0)
    assert VentilationCalculator().estimate_from_co2_decay(co2, unoccupied=pd.Series(False, index=co2.index)) is None


def _summer(solar_effect: float, seed: int = 2):
    """Occupied summer hours: T = 21 + 0.25 * (Tout - 15) + solar_effect * solar/100 + noise."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-06-03 08:00", "2024-08-30 15:00", freq="h")
    idx = idx[(idx.day_of_week < 5) & (idx.hour >= 8) & (idx.hour < 16)]
    day = np.arange(len(idx)) // 8
    tout = 15 + 6 * np.sin(day / 9.0) + rng.normal(0, 1.5, len(idx))
    solar = np.clip(500 * np.sin(np.pi * (idx.hour - 6) / 14) * rng.uniform(0.2, 1.0, len(idx)), 0, None)
    temp = 21 + 0.25 * (tout - 15) + solar_effect * solar / 100 + rng.normal(0, 0.3, len(idx))
    return pd.DataFrame({"temperature": temp, "outdoor_temperature": tout, "solar_irradiance": solar}, index=idx)


def test_solar_coefficient_is_recovered_at_equal_outdoor_temperature():
    result = ScenarioImpactModel().solar_shading_scenario(_summer(1.2))
    assert result.metrics["solar_k_per_100_w_m2"] == pytest.approx(1.2, abs=0.1)
    assert result.metrics["hours_avoided"] > 0


def test_no_solar_effect_means_no_shading_benefit():
    """The old fixed -1.5 °C rule credited shading to rooms with no solar response at all."""
    result = ScenarioImpactModel().solar_shading_scenario(_summer(0.0))
    assert abs(result.metrics["solar_k_per_100_w_m2"]) < 0.1
    assert result.metrics["hours_avoided"] == 0


def test_no_outdoor_temperature_no_solar_estimate():
    assert ScenarioImpactModel().solar_shading_scenario(_summer(1.2).drop(columns="outdoor_temperature")) is None


def test_airflow_factor_is_the_steady_state_ratio():
    idx = pd.date_range("2024-03-04 08:00", periods=200, freq="h")
    df = pd.DataFrame({"co2": np.linspace(600, 1800, 200)}, index=idx)
    p95 = float(np.percentile(df["co2"], 95))
    result = ScenarioImpactModel(co2_limit=1200).airflow_scenario(df, background=420)
    assert result.metrics["airflow_factor"] == pytest.approx((p95 - 420) / (1200 - 420), abs=0.01)


def test_perfect_room_gets_no_recommendations():
    """A room inside Category I all year, with sun and weather data, gets no advice
    (it used to get a high-priority 'reduce solar gains, ~2,000 kWh')."""
    from hvx.reporting import ReportBuilder, ReportConfig
    from tests.conftest import make_portfolio

    p, b, f, rooms = make_portfolio(n_buildings=1, n_rooms=1)
    idx = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h")
    room = next(iter(rooms.values()))
    room.timestamps = [t.isoformat() for t in idx]
    winter = idx.month.isin([1, 2, 3, 4, 10, 11, 12])
    room.timeseries_data = {"temperature": np.where(winter, 22.0, 24.5).tolist(), "co2": [650.0] * len(idx),
                            "humidity": [40.0] * len(idx)}
    building = next(iter(b.values()))
    stamps = [t.isoformat() for t in idx]
    solar = np.clip(600 * np.sin(np.pi * (idx.hour - 6) / 14), 0, None)
    building.metadata = {**(building.metadata or {}), "climate_data": {
        "outdoor_temperature": {"timestamps": stamps, "values": (8 + 10 * np.sin((idx.day_of_year - 100) / 58)).tolist()},
        "solar_irradiance": {"timestamps": stamps, "values": solar.tolist()},
    }}
    report = ReportBuilder(ReportConfig(seasons=("winter", "summer"), parallel_backend="serial")).build(p, b, f, rooms)
    r = report.rooms[0]
    assert r.achieved_category == "I"
    assert r.recommendations == []
