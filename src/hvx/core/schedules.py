# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Opening hours and occupancy scheduling utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Dict, Iterable, List, Optional, Tuple

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


@dataclass(frozen=True)
class OccupancySchedule:
    """
    When a space counts as occupied, for assessments that apply "during use".

    ``start``/``end`` are local clock times (end exclusive); ``weekdays`` uses
    Monday=0. ``holiday_periods`` are inclusive ``(first_day, last_day)`` ISO date
    pairs (e.g. school holidays); ``public_holidays`` excludes the country's
    statutory holidays.
    """

    start: str = "08:00"
    end: str = "16:00"
    weekdays: Tuple[int, ...] = (0, 1, 2, 3, 4)
    holiday_periods: Tuple[Tuple[str, str], ...] = ()
    public_holidays: bool = True
    always: bool = False  # 24/7 spaces (residential, hospitals)

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

    def with_holidays(self, periods: Iterable[Iterable[str]]) -> "OccupancySchedule":
        extra = tuple((str(a), str(b)) for a, b in periods)
        if not extra:
            return self
        return OccupancySchedule(self.start, self.end, self.weekdays, self.holiday_periods + extra, self.public_holidays, self.always)

    def mask(self, index: pd.DatetimeIndex, country: Optional[str] = None) -> pd.Series:
        """Boolean mask over a local, timezone-naive DatetimeIndex (vectorised)."""
        if self.always:
            return pd.Series(True, index=index)
        minutes = index.hour * 60 + index.minute
        start, end = (_minutes(self.start), _minutes(self.end))
        occupied = (minutes >= start) & (minutes < end) & index.day_of_week.isin(self.weekdays)
        days = index.normalize()
        if self.public_holidays and country and len(index):
            import holidays as holidays_lib

            try:
                years = range(int(index.year.min()), int(index.year.max()) + 1)
                public = holidays_lib.country_holidays(country.upper(), years=years)
                occupied &= ~days.isin(pd.to_datetime(list(public.keys())))
            except (NotImplementedError, KeyError):
                pass
        for first, last in self.holiday_periods:
            occupied &= ~((days >= pd.Timestamp(first)) & (days <= pd.Timestamp(last)))
        return pd.Series(occupied, index=index)

    def describe(self) -> str:
        if self.always:
            return "all hours (24/7 occupancy)"
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = ", ".join(names[d] for d in self.weekdays)
        text = f"{days} {self.start}–{self.end}"
        if self.public_holidays:
            text += ", excluding public holidays"
        if self.holiday_periods:
            text += f" and {len(self.holiday_periods)} holiday period(s)"
        return text


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


__all__ = [
    "PROFILE_DEFINITIONS",
    "OccupancySchedule",
    "get_opening_profile_for_building_type",
    "generate_occupancy_mask",
]
