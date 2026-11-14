# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Opening hours and occupancy scheduling utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .enums import BuildingType, OpeningHoursProfile


def _time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


OpeningPeriod = Tuple[time, time]


PROFILE_DEFINITIONS: Dict[OpeningHoursProfile, Dict[int, List[OpeningPeriod]]] = {
    OpeningHoursProfile.OFFICE_STANDARD: {
        weekday: [(_time("08:00"), _time("18:00"))] for weekday in range(0, 5)
    },
    OpeningHoursProfile.RETAIL_STANDARD: {
        weekday: [(_time("09:00"), _time("20:00"))] for weekday in range(0, 6)
    },
    OpeningHoursProfile.EDUCATION_STANDARD: {
        weekday: [(_time("07:30"), _time("16:00"))] for weekday in range(0, 5)
    },
    OpeningHoursProfile.HOSPITALITY_STANDARD: {
        weekday: [(_time("06:00"), _time("23:00"))] for weekday in range(0, 7)
    },
    OpeningHoursProfile.INDUSTRIAL_STANDARD: {
        weekday: [(_time("06:00"), _time("22:00"))] for weekday in range(0, 6)
    },
    OpeningHoursProfile.TWENTY_FOUR_SEVEN: {
        weekday: [(_time("00:00"), _time("23:59"))] for weekday in range(0, 7)
    },
}


BUILDING_TYPE_OPENING_PROFILE: Dict[str, OpeningHoursProfile] = {
    BuildingType.OFFICE.value: OpeningHoursProfile.OFFICE_STANDARD,
    BuildingType.COMMERCIAL.value: OpeningHoursProfile.RETAIL_STANDARD,
    BuildingType.RETAIL.value: OpeningHoursProfile.RETAIL_STANDARD,
    BuildingType.EDUCATION.value: OpeningHoursProfile.EDUCATION_STANDARD,
    BuildingType.SCHOOL.value: OpeningHoursProfile.EDUCATION_STANDARD,
    BuildingType.HOSPITAL.value: OpeningHoursProfile.TWENTY_FOUR_SEVEN,
    BuildingType.HEALTHCARE.value: OpeningHoursProfile.TWENTY_FOUR_SEVEN,
    BuildingType.HOTEL.value: OpeningHoursProfile.TWENTY_FOUR_SEVEN,
    BuildingType.HOSPITALITY.value: OpeningHoursProfile.HOSPITALITY_STANDARD,
    BuildingType.INDUSTRIAL.value: OpeningHoursProfile.INDUSTRIAL_STANDARD,
    BuildingType.LOGISTICS.value: OpeningHoursProfile.INDUSTRIAL_STANDARD,
    BuildingType.DATA_CENTER.value: OpeningHoursProfile.TWENTY_FOUR_SEVEN,
    BuildingType.RESIDENTIAL.value: OpeningHoursProfile.TWENTY_FOUR_SEVEN,
    BuildingType.MULTIFAMILY.value: OpeningHoursProfile.TWENTY_FOUR_SEVEN,
}


def get_opening_profile_for_building_type(building_type: Optional[str]) -> OpeningHoursProfile:
    if building_type:
        profile = BUILDING_TYPE_OPENING_PROFILE.get(building_type.lower())
        if profile:
            return profile
    return OpeningHoursProfile.OFFICE_STANDARD


def generate_occupancy_mask(
    index: pd.DatetimeIndex,
    profile: OpeningHoursProfile,
    holiday_dates: Optional[Iterable[pd.Timestamp]] = None,
) -> pd.Series:
    """
    Generate boolean mask for occupied timestamps.
    """
    if index.tz is not None:
        local_index = index.tz_convert("UTC").tz_localize(None)
    else:
        local_index = index

    holidays_lookup = set(pd.to_datetime(list(holiday_dates or [])))
    profile_def = PROFILE_DEFINITIONS.get(profile) or PROFILE_DEFINITIONS[OpeningHoursProfile.OFFICE_STANDARD]

    mask_values: List[bool] = []
    for ts in local_index:
        day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        if day in holidays_lookup:
            mask_values.append(False)
            continue
        weekday = ts.weekday()
        periods = profile_def.get(weekday, [])
        in_period = False
        for start, end in periods:
            if start <= ts.time() <= end:
                in_period = True
                break
        mask_values.append(in_period)
    return pd.Series(mask_values, index=index)


DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# (weekday, start, end): Monday=0, local clock times, end exclusive ("24:00" = midnight);
# start > end is an overnight period that belongs to the evening's day.
SchedulePeriod = Tuple[int, str, str]


@dataclass(frozen=True)
class OccupancySchedule:
    """
    When a space counts as occupied, for assessments that apply "during use".

    Simple form: ``start``/``end`` local clock times (end exclusive) on ``weekdays``
    (Monday=0). Advanced form: ``periods``, a list of ``(weekday, start, end)`` that
    replaces the simple form, so days can have different hours and several periods
    (e.g. a lunch break: ``(0, "08:00", "11:30"), (0, "12:00", "15:00")``).

    Days off: ``holiday_periods`` are inclusive ``(first_day, last_day)`` ISO date pairs
    (e.g. school holidays), ``closed_days`` single ISO dates, and ``public_holidays``
    excludes the country's statutory holidays. ``always`` is 24/7 (residential, hospitals).
    """

    start: str = "08:00"
    end: str = "16:00"
    weekdays: Tuple[int, ...] = (0, 1, 2, 3, 4)
    holiday_periods: Tuple[Tuple[str, str], ...] = ()
    public_holidays: bool = True
    always: bool = False
    periods: Tuple[SchedulePeriod, ...] = ()
    closed_days: Tuple[str, ...] = ()

    def __post_init__(self):
        for day, first, last in self.periods:
            if not 0 <= int(day) <= 6:
                raise ValueError(f"Weekday {day} is not 0 (Monday) to 6 (Sunday)")
            _minutes(first), _minutes(last)  # validates "HH:MM"
        _minutes(self.start), _minutes(self.end)

    @classmethod
    def for_building_type(cls, building_type: Optional[str], **overrides) -> "OccupancySchedule":
        profile = get_opening_profile_for_building_type(building_type)
        if profile == OpeningHoursProfile.TWENTY_FOUR_SEVEN:
            return cls(always=True, public_holidays=False, **overrides)
        periods = PROFILE_DEFINITIONS[profile]
        weekdays = tuple(sorted(periods))
        first = periods[weekdays[0]][0]
        base = dict(start=first[0].strftime("%H:%M"), end=first[1].strftime("%H:%M"), weekdays=weekdays)
        return cls(**{**base, **overrides})

    @classmethod
    def from_dict(cls, data: Optional[Dict]) -> "OccupancySchedule":
        """From JSON-like data (as :meth:`to_dict`); periods may be ``{"day", "start", "end"}`` dicts."""
        data = dict(data or {})
        periods = []
        for item in data.pop("periods", None) or ():
            if isinstance(item, dict):
                item = (item["day"], item["start"], item["end"])
            periods.append((int(item[0]), str(item[1]), str(item[2])))
        holiday_periods = tuple((str(a), str(b)) for a, b in (data.pop("holiday_periods", None) or ()))
        closed = tuple(str(d) for d in (data.pop("closed_days", None) or ()))
        if "weekdays" in data:
            data["weekdays"] = tuple(int(d) for d in data["weekdays"])
        known = {"start", "end", "weekdays", "public_holidays", "always"}
        return cls(**{k: v for k, v in data.items() if k in known}, periods=tuple(periods),
                   holiday_periods=holiday_periods, closed_days=closed)

    def to_dict(self) -> Dict:
        return {"start": self.start, "end": self.end, "weekdays": list(self.weekdays),
                "periods": [{"day": d, "start": a, "end": b} for d, a, b in self.effective_periods()],
                "holiday_periods": [list(p) for p in self.holiday_periods], "closed_days": list(self.closed_days),
                "public_holidays": self.public_holidays, "always": self.always}

    def effective_periods(self) -> Tuple[SchedulePeriod, ...]:
        """The schedule as ``(weekday, start, end)`` periods, whichever form it was given in."""
        if self.periods:
            return tuple(sorted(self.periods, key=lambda p: (p[0], _minutes(p[1]))))
        return tuple((d, self.start, self.end) for d in sorted(self.weekdays))

    def with_holidays(self, periods: Iterable[Iterable[str]]) -> "OccupancySchedule":
        extra = tuple((str(a), str(b)) for a, b in periods)
        if not extra:
            return self
        return replace(self, holiday_periods=self.holiday_periods + extra)

    def mask(self, index: pd.DatetimeIndex, country: Optional[str] = None) -> pd.Series:
        """Boolean mask over a local, timezone-naive DatetimeIndex (vectorised)."""
        if self.always:
            return pd.Series(True, index=index)
        minutes = np.asarray(index.hour * 60 + index.minute)
        dates = index.normalize()
        weekday = np.asarray(index.day_of_week)
        days_off = self._days_off(dates, country)
        occupied = np.zeros(len(index), dtype=bool)
        for day, first, last in self.effective_periods():
            start, end = _minutes(first), _minutes(last)
            if start < end:
                part = (minutes >= start) & (minutes < end) & (weekday == day)
                occupied |= part & ~days_off(dates)
            elif start > end:
                # Overnight (e.g. hotel sleeping hours 22:00-06:00): the morning part belongs to
                # the night that started the previous evening, so weekday and days off refer to that day.
                evening = (minutes >= start) & (weekday == day)
                night_of = dates - pd.Timedelta(days=1)
                morning = (minutes < end) & (np.asarray(night_of.day_of_week) == day)
                occupied |= (evening & ~days_off(dates)) | (morning & ~days_off(night_of))
        return pd.Series(occupied, index=index)

    def _days_off(self, dates: pd.DatetimeIndex, country: Optional[str]):
        """Function: DatetimeIndex of days -> boolean array, True on public holidays and closed days."""
        off: List[pd.Timestamp] = [pd.Timestamp(d) for d in self.closed_days]
        if self.public_holidays and country and len(dates):
            import holidays as holidays_lib

            try:
                years = range(int(dates.year.min()) - 1, int(dates.year.max()) + 1)
                off += [pd.Timestamp(d) for d in holidays_lib.country_holidays(country.upper(), years=years)]
            except (NotImplementedError, KeyError):
                pass
        off_index = pd.DatetimeIndex(off)
        ranges = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in self.holiday_periods]

        def days_off(days: pd.DatetimeIndex) -> np.ndarray:
            result = np.asarray(days.isin(off_index))
            for first, last in ranges:
                result = result | np.asarray((days >= first) & (days <= last))
            return result

        return days_off

    def day_groups(self) -> List[Tuple[Tuple[int, ...], Tuple[Tuple[str, str], ...]]]:
        """Weekdays grouped by identical hours: ``[((0, 1, 2, 3), (("08:00", "15:00"),)), ((4,), ...)]``."""
        by_day: Dict[int, Tuple[Tuple[str, str], ...]] = {}
        for day, first, last in self.effective_periods():
            by_day[day] = by_day.get(day, ()) + ((first, last),)
        groups: List[Tuple[List[int], Tuple[Tuple[str, str], ...]]] = []
        for day in sorted(by_day):
            hours = by_day[day]
            if groups and groups[-1][1] == hours and groups[-1][0][-1] == day - 1:
                groups[-1][0].append(day)
            else:
                groups.append(([day], hours))
        return [(tuple(days), hours) for days, hours in groups]

    def describe(self, day_names: Sequence[str] = DAY_NAMES) -> str:
        if self.always:
            return "all hours (24/7 occupancy)"
        parts = []
        for days, hours in self.day_groups():
            span = day_names[days[0]] if len(days) == 1 else f"{day_names[days[0]]}–{day_names[days[-1]]}"
            parts.append(f"{span} " + ", ".join(f"{a}–{b}" for a, b in hours))
        text = "; ".join(parts) or "never"
        if self.public_holidays:
            text += ", excluding public holidays"
        if self.holiday_periods:
            text += f" and {len(self.holiday_periods)} holiday period(s)"
        if self.closed_days:
            text += f" and {len(self.closed_days)} closed day(s)"
        return text

    def weekly_hours(self) -> float:
        """Occupied hours in a normal week (no days off)."""
        total = 0
        for _, first, last in self.effective_periods():
            start, end = _minutes(first), _minutes(last)
            total += (end - start) if start <= end else (1440 - start + end)
        return total / 60.0


def danish_school_holidays(years: Iterable[int]) -> List[Dict[str, str]]:
    """
    Typical Danish school holidays, as ``{"name", "first", "last"}`` (inclusive ISO dates):
    winter (week 7), Easter (Saturday before Palm Sunday to Easter Monday), autumn (week 42),
    Christmas (21 December to 1 January) and summer (Saturday of week 26 to Sunday of week 32).
    Municipalities set their own dates, so check them against the school's calendar.
    """
    from datetime import date, timedelta

    from dateutil.easter import easter

    def day(year: int, week: int, weekday: int) -> str:
        return date.fromisocalendar(year, week, weekday).isoformat()

    out: List[Dict[str, str]] = []
    for year in sorted({int(y) for y in years}):
        e = easter(year)
        out += [
            {"name": "Christmas", "first": f"{year - 1}-12-21", "last": f"{year}-01-01"},
            {"name": "Winter", "first": day(year, 7, 1), "last": day(year, 7, 7)},
            {"name": "Easter", "first": (e - timedelta(days=8)).isoformat(), "last": (e + timedelta(days=1)).isoformat()},
            {"name": "Summer", "first": day(year, 26, 6), "last": day(year, 32, 7)},
            {"name": "Autumn", "first": day(year, 42, 1), "last": day(year, 42, 7)},
        ]
    return out


def _minutes(hhmm: str) -> int:
    try:
        hour, minute = str(hhmm).strip().replace(".", ":").split(":")
        value = int(hour) * 60 + int(minute)
    except ValueError:
        raise ValueError(f"Time {hhmm!r} is not HH:MM") from None
    if not 0 <= value <= 1440 or not 0 <= int(minute) < 60:
        raise ValueError(f"Time {hhmm!r} is not between 00:00 and 24:00")
    return value


__all__ = [
    "PROFILE_DEFINITIONS",
    "OccupancySchedule",
    "SchedulePeriod",
    "danish_school_holidays",
    "get_opening_profile_for_building_type",
    "generate_occupancy_mask",
]
