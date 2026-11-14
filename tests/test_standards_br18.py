# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""BR18 indicators: hours from sample durations, one allowance per year of use."""

from __future__ import annotations

import pandas as pd
import pytest

from hvx.core.schedules import OccupancySchedule
from hvx.reporting import ReportBuilder, ReportConfig
from hvx.standards.br18.analysis import _evaluate_rule

RULE_26 = {"id": "t26", "metric": "temperature", "operator": "<=", "target_value": 26.0, "tolerance_hours": 100}


def test_hours_come_from_sample_durations():
    """50 hourly samples above 27 °C followed by 15-minute samples: 50 h, not 200 h."""
    hourly = pd.date_range("2024-06-03 00:00", periods=50, freq="h")
    quarter = pd.date_range(hourly[-1] + pd.Timedelta("1h"), periods=400, freq="15min")
    series = pd.Series([28.0] * 50 + [22.0] * 400, index=hourly.append(quarter))
    result = _evaluate_rule(series, RULE_26)
    assert result["non_compliant_hours"] == pytest.approx(50.0)
    assert result["passed"] is True


def _room_with_hot_hours(hot_winter: int, hot_summer: int):
    from tests.conftest import make_portfolio

    p, b, f, rooms = make_portfolio(n_buildings=1, n_rooms=1)
    building = next(iter(b.values()))
    building.country = "DK"
    building.building_type = "school"
    p.country = "DK"
    idx = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h")
    temp = pd.Series(22.0, index=idx)
    occupied = OccupancySchedule(start="08:00", end="16:00").mask(idx, "DK")
    winter_hours = idx[occupied & (idx.month == 2)][:hot_winter]
    summer_hours = idx[occupied & (idx.month == 6)][:hot_summer]
    temp[winter_hours.append(summer_hours)] = 26.5
    room = next(iter(rooms.values()))
    room.timestamps = [t.isoformat() for t in idx]
    room.timeseries_data = {"temperature": temp.tolist(), "co2": [600.0] * len(idx)}
    return p, b, f, rooms


def test_br18_allowance_is_per_year_not_per_season():
    """80 h above 26 °C in winter + 80 h in summer = 160 h: fails the 100 h value even when the
    report is split into seasons (each season used to get its own 100 h)."""
    entities = _room_with_hot_hours(80, 80)
    config = ReportConfig(seasons=("winter", "summer"), occupancy=OccupancySchedule(start="08:00", end="16:00"),
                          parallel_backend="serial", include_simulations=False)
    room = ReportBuilder(config).build(*entities).rooms[0]
    assert room.br18_pass is False
    assert any("26 °C" in name for name in room.br18_failed)
    assert room.exceedance_hours["temperature>26"] == pytest.approx(160.0)


def test_hours_consistent_between_issues_br18_and_recommendations():
    """Occupied-only data must not give each day's last sample the gap to the next morning."""
    entities = _room_with_hot_hours(0, 150)
    config = ReportConfig(seasons=("winter", "summer"), occupancy=OccupancySchedule(start="08:00", end="16:00"),
                          parallel_backend="serial")
    room = ReportBuilder(config).build(*entities).rooms[0]
    assert room.exceedance_hours["temperature>26"] == pytest.approx(150.0)
    rec = next(r for r in room.recommendations if r["key"] in ("summer_overheating", "solar_shading"))
    assert rec["evidence"]["hours_above_26"] == pytest.approx(150.0)
    assert room.br18_pass is False
