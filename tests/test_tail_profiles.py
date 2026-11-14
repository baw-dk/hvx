# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""TAIL profiles: offices and hotels (Wargocki et al. 2021, tail.R) and schools (Tran 2024)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hvx.standards.tail.calculator import TAILCalculator

IDX = pd.date_range("2024-03-04 08:00", periods=200, freq="h")


def rate(building_type, room_type=None, **series):
    data = {k: (v if isinstance(v, pd.Series) else pd.Series(v, index=IDX[: len(v)] if np.ndim(v) else IDX))
            for k, v in series.items()}
    meta = {"building_type": building_type, "room_type": room_type}
    return TAILCalculator.assess_timeseries(data, metadata=meta, occupancy_filtered=True)


def label(result, parameter):
    return next((p.rating_label for p in result.parameter_results if p.parameter == parameter), None)


def test_profile_selection():
    assert TAILCalculator.profile_for("school")[0] == "school"
    assert TAILCalculator.profile_for("Hotel")[0] == "hotel"
    assert TAILCalculator.profile_for("office")[0] == "office"
    assert TAILCalculator.profile_for(None)[0] == "office"
    assert rate("school", co2=[600.0]).profile == "school"


def test_classroom_noise_limits():
    """Thesis Table 7: classrooms <= 30 / 34 / 38 dB(A); small office <= 30 / 35 / 40 (TAIL Table 3)."""
    assert label(rate("school", noise=[35.0] * 200), "noise") == "III"
    assert label(rate("office", "small office", noise=[35.0] * 200), "noise") == "II"
    assert label(rate("school", noise=[39.0] * 200), "noise") == "IV"


def test_school_pm25_and_no2():
    """Thesis Table 8: PM2.5 I < 5, II >= 5, IV >= 15; NO2 I < 10, II < 20, IV >= 20 (ug/m3)."""
    school = rate("school", pm25=[8.0] * 10, no2=[12.0] * 10)
    assert label(school, "pm25") == "II" and label(school, "no2") == "II"
    office = rate("office", pm25=[8.0] * 10, no2=[12.0] * 10)
    assert label(office, "pm25") == "I"  # office limit < 10
    assert label(office, "no2") is None and "no2" in {e.parameter for e in office.extensions}
    assert label(rate("school", no2=[25.0] * 10), "no2") == "IV"


def test_school_co2_by_time_share():
    """3 % of school hours above outdoor + 1350 ppm: schools rate by time shares (III); offices by P95 (I)."""
    co2 = np.full(200, 600.0)
    co2[:6] = 1900.0
    assert label(rate("school", co2=co2), "co2") == "III"
    assert label(rate("office", co2=co2), "co2") == "I"


@pytest.mark.parametrize("rt,expected", [(0.5, "I"), (0.7, "II"), (1.0, "IV"), (0.3, "IV")])
def test_reverberation_time_by_volume(rt, expected):
    result = TAILCalculator.assess_timeseries({"reverberation_time": pd.Series([rt])},
                                              metadata={"building_type": "school", "volume_m3": 180},
                                              occupancy_filtered=True)
    assert label(result, "reverberation_time") == expected


def test_reverberation_time_needs_volume_and_school():
    no_volume = TAILCalculator.assess_timeseries({"rt": pd.Series([0.5])}, metadata={"building_type": "school"},
                                                 occupancy_filtered=True)
    assert "volume" in no_volume.not_rated["reverberation_time"]
    office = TAILCalculator.assess_timeseries({"rt": pd.Series([0.5])}, metadata={"building_type": "office",
                                              "volume_m3": 100}, occupancy_filtered=True)
    assert "schools only" in office.not_rated["reverberation_time"]


def test_school_illuminance_minimums():
    """Thesis Table 9: >= 500 / 300 / 200 lx; offices: share of time within 300-500 lx."""
    lux = np.full(200, 650.0)
    assert label(rate("school", illuminance=lux), "illuminance") == "I"
    assert label(rate("office", illuminance=lux), "illuminance") == "IV"  # never within 300-500 lx
    lux[:30] = 250.0  # 15 % between 200 and 300 lx
    assert label(rate("school", illuminance=lux), "illuminance") == "III"  # 100 % >= 200 lx, 15 % below 300


def test_adaptive_bands_without_mechanical_cooling():
    """TAIL Table 2: outside the heating season, buildings without cooling use 0.33*theta_rm + 18.8.
    27 °C with theta_rm = 20 °C: Green (upper 27.4 °C). With cooling (fixed 23.5-25.5 °C): not Green."""
    idx = pd.date_range("2024-07-01 08:00", "2024-07-31 16:00", freq="h")
    temp = pd.Series(27.0, index=idx)
    daily = {d.strftime("%Y-%m-%d"): 20.0 for d in pd.date_range("2024-06-01", "2024-07-31")}
    free = TAILCalculator.assess_timeseries({"temperature": temp}, occupancy_filtered=True,
                                            metadata={"mechanical_cooling": False, "outdoor_daily_mean_temperature": daily})
    assert label(free, "temperature") == "I"
    assert free.parameter_results[0].metadata["adaptive"] is True
    cooled = TAILCalculator.assess_timeseries({"temperature": temp}, occupancy_filtered=True,
                                              metadata={"outdoor_daily_mean_temperature": daily})
    assert label(cooled, "temperature") == "III"  # 27 °C: Orange band 22-27 °C


def test_building_aggregation_differs_by_profile():
    """Offices/hotels: mean of the rooms' parameter ratings (TAIL Eq. 1); schools: mean of the
    classrooms' domain ratings (Tran 2024, Fig. 10)."""
    from hvx.reporting.aggregate import interim_label, typical_tail

    a = {"domains": {"iaq": "IV"}, "parameters": {"co2": "IV", "relative_humidity": "I"}, "overall": "IV"}
    b = {"domains": {"iaq": "IV"}, "parameters": {"co2": "I", "relative_humidity": "IV"}, "overall": "IV"}
    office = typical_tail([{**a, "profile": "office"}, {**b, "profile": "office"}])
    school = typical_tail([{**a, "profile": "school"}, {**b, "profile": "school"}])
    assert office["domains"]["iaq"] == "III"  # co2 (4+1)/2 = 2.5 -> III, RH 2.5 -> III
    assert school["domains"]["iaq"] == "IV"   # (4+4)/2 = 4 -> IV
    assert [interim_label(r) for r in ([1, 1, 2], [1, 2], [2, 3], [3, 4])] == ["I", "II", "III", "IV"]
