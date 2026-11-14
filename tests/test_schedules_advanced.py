# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Advanced occupancy schedules: hours per weekday, breaks, closed days, school holidays."""
import pandas as pd
import pytest

from hvx.core.schedules import OccupancySchedule, danish_school_holidays
from hvx.reporting.i18n import Translator, describe_schedule

IDX = pd.date_range("2024-01-01", "2024-12-31 23:30", freq="30min")


def test_simple_form_is_unchanged_and_equals_its_periods():
    simple = OccupancySchedule(start="08:00", end="16:00")
    periods = OccupancySchedule(periods=tuple((d, "08:00", "16:00") for d in range(5)))
    assert simple.mask(IDX, "DK").equals(periods.mask(IDX, "DK"))
    assert simple.describe() == "Mon–Fri 08:00–16:00, excluding public holidays"


def test_hours_per_day_and_a_lunch_break():
    s = OccupancySchedule(periods=((0, "08:00", "11:30"), (0, "12:00", "15:00"), (4, "08:00", "12:00")),
                          public_holidays=False)
    m = s.mask(IDX)
    monday = m["2024-01-08"]
    assert monday["2024-01-08 11:00"] and not monday["2024-01-08 11:30"] and monday["2024-01-08 12:00"]
    assert not monday["2024-01-08 15:00"]
    assert m["2024-01-12"].sum() == 8  # Friday 08-12, half-hourly
    assert not m["2024-01-09"].any()  # Tuesday has no periods
    assert s.weekly_hours() == pytest.approx(6.5 + 4)
    assert s.describe() == "Mon 08:00–11:30, 12:00–15:00; Fri 08:00–12:00"


def test_overnight_period_belongs_to_the_evening_and_its_days_off():
    s = OccupancySchedule(periods=((4, "22:00", "06:00"),), closed_days=("2024-03-08",), public_holidays=False)
    m = s.mask(IDX)
    assert m["2024-01-05 22:00"] and m["2024-01-06 05:30"] and not m["2024-01-06 06:00"]
    assert not m["2024-03-08 23:00"] and not m["2024-03-09 02:00"]  # the night of a closed Friday


def test_holidays_closed_days_and_round_trip():
    s = OccupancySchedule(holiday_periods=(("2024-06-29", "2024-08-11"),), closed_days=("2024-05-10",))
    m = s.mask(IDX, "DK")
    assert not m["2024-07-15"].any() and not m["2024-05-10"].any() and not m["2024-01-01"].any()
    assert m["2024-05-13"].any()
    assert OccupancySchedule.from_dict(s.to_dict()).mask(IDX, "DK").equals(m)
    assert "1 closed day(s)" in s.describe()
    assert describe_schedule(s, Translator("da")).startswith("man–fre kl. 08:00–16:00")


def test_invalid_times_and_days_are_refused():
    with pytest.raises(ValueError):
        OccupancySchedule(periods=((7, "08:00", "16:00"),))
    with pytest.raises(ValueError):
        OccupancySchedule(start="8 o'clock")


def test_danish_school_holidays():
    by_name = {h["name"]: h for h in danish_school_holidays([2024])}
    assert by_name["Summer"] == {"name": "Summer", "first": "2024-06-29", "last": "2024-08-11"}
    assert by_name["Winter"]["first"] == "2024-02-12" and by_name["Autumn"]["first"] == "2024-10-14"
    assert by_name["Easter"] == {"name": "Easter", "first": "2024-03-23", "last": "2024-04-01"}
    assert by_name["Christmas"]["first"] == "2023-12-21"
