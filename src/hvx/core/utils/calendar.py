# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Calendar helpers for holidays and operating periods.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

import pandas as pd
import holidays

from hvx.core.config import load_holiday_config


def _expand_custom_holidays(entries: Iterable[dict]) -> Set[pd.Timestamp]:
    dates: Set[pd.Timestamp] = set()
    for entry in entries or []:
        start = entry.get("start_date")
        end = entry.get("end_date", start)
        if not start:
            continue
        start_ts = pd.to_datetime(start)
        if end is None:
            end_ts = start_ts
        else:
            end_ts = pd.to_datetime(end)
        for ts in pd.date_range(start_ts, end_ts, freq="D"):
            dates.add(ts.normalize())
    return dates


def get_holiday_dates(country_code: Optional[str]) -> List[pd.Timestamp]:
    """
    Build a combined list of statutory + custom holidays for a country.
    """
    if not country_code:
        return []

    normalized_dates: Set[pd.Timestamp] = set()
    try:
        # Without explicit years the calendar stays empty until queried by date.
        this_year = pd.Timestamp.now().year
        cal = holidays.country_holidays(country_code.upper(), years=range(this_year - 10, this_year + 2))
        normalized_dates.update(pd.to_datetime(list(cal.keys())))
    except Exception:
        pass

    config = load_holiday_config(country_code)
    custom = _expand_custom_holidays(config.get("custom_holidays", []))
    normalized_dates.update(custom)

    return sorted(ts.normalize() for ts in normalized_dates)
