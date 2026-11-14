# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
TAIL against the authors' reference script tail.R (TAILRatingScheme, commit
c71b8b5; Wargocki et al. 2021). Every expected label below is derived by hand
from the script's rules ("l.NN" = line in tail.R). Synthetic data only.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from hvx.standards.tail.calculator import TAILCalculator, TAILCategory, TAILRating, load_config

JAN = "2024-01-15 09:00"  # heating season (October-May)
JUL = "2024-07-15 09:00"  # non-heating season (June-September)


def _series(values, start=JAN, freq="min") -> pd.Series:
    return pd.Series(list(values), index=pd.date_range(start, periods=len(values), freq=freq), dtype=object)


def _rate(data, thresholds=None, occupancy_filtered=True, **metadata):
    series = {k: v if isinstance(v, pd.Series) else _series(v) for k, v in data.items()}
    return TAILCalculator.assess_timeseries(series, thresholds, metadata=metadata, occupancy_filtered=occupancy_filtered)


def _param(result, name):
    found = {p.parameter: p for p in result.parameter_results + result.extensions}
    return found[name]


def _label(data, name=None, **metadata) -> str:
    result = _rate(data, **metadata)
    return _param(result, name or next(iter(data))).rating_label


def _mix(green=0, yellow=0, orange=0, red=0, nan=0, start=JAN):
    """Heating-season temperatures with the given number of Green/Yellow/Orange/Red/missing samples."""
    values = [22.0] * green + [20.5] * yellow + [19.5] * orange + [18.0] * red + [np.nan] * nan
    return _series(values, start=start)


# --------------------------------------------------------------------------- temperature
def test_temperature_heating_bands_l89_94():
    values = [21.0, 23.0, 20.0, 24.0, 19.0, 25.0, 18.9, 25.1]
    p = _param(_rate({"temperature": values}), "temperature")
    assert p.distribution == {"green": 25.0, "yellow": 25.0, "orange": 25.0, "red": 25.0}


def test_temperature_non_heating_bands_l95_100():
    values = [23.5, 25.5, 23.0, 26.0, 22.0, 27.0, 21.9, 27.1]
    p = _param(_rate({"temperature": _series(values, start=JUL)}), "temperature")
    assert p.distribution == {"green": 25.0, "yellow": 25.0, "orange": 25.0, "red": 25.0}


def test_temperature_rounded_to_one_decimal_like_r():
    # l.84 round(Value, 1): 23.04 -> 23.0 (Green), 23.05 -> 23.1 (Yellow; numpy would give 23.0)
    assert _label({"temperature": [23.04] * 10}) == "I"
    assert _label({"temperature": [23.05] * 10}) == "II"  # 100 % Yellow, no Orange/Red


def test_temperature_season_is_per_sample_by_month():
    # l.85-87: heating = October-May. 22.0 °C is Green in May (heating), Orange in June (non-heating).
    def dist(stamp, value):
        s = pd.Series([value], index=pd.DatetimeIndex([stamp]))
        return _param(_rate({"temperature": s}), "temperature").distribution

    assert dist("2024-05-31 10:00", 22.0)["green"] == 100
    assert dist("2024-06-03 10:00", 22.0)["orange"] == 100
    assert dist("2024-09-30 10:00", 24.0)["green"] == 100  # non-heating 23.5-25.5
    assert dist("2024-10-01 10:00", 24.0)["yellow"] == 100  # heating 23-24 is Yellow

    # One series across the season change: each sample uses its own month's bands.
    s = pd.Series([22.0, 22.0], index=pd.DatetimeIndex(["2024-05-30 10:00", "2024-06-03 10:00"]))
    p = _param(_rate({"temperature": s}), "temperature")
    assert p.distribution["green"] == 50 and p.distribution["orange"] == 50
    assert p.metadata["heating_samples"] == 1 and p.metadata["non_heating_samples"] == 1


def test_temperature_season_hint_ignored_with_timestamps_and_used_without():
    july_22 = _series([22.0] * 10, start=JUL)  # Orange in non-heating season
    result = _rate({"temperature": july_22}, season_hint="winter")
    assert _param(result, "temperature").distribution["orange"] == 100
    no_index = pd.Series([22.0] * 10)
    assert _param(_rate({"temperature": no_index}, season_hint="winter"), "temperature").rating_label == "I"
    assert _param(_rate({"temperature": no_index}, season_hint="summer"), "temperature").distribution["orange"] == 100
    unknown = _rate({"temperature": no_index})
    assert "temperature" in unknown.not_rated and unknown.overall_rating is None


@pytest.mark.parametrize(
    "counts, label",
    [
        (dict(green=100), "I"),
        (dict(green=94, yellow=5, orange=1), "I"),  # G >= 94 %, O <= 1 %, R = 0
        (dict(green=93, yellow=7), "II"),  # tail.R II: Y > 5 %
        (dict(green=94, yellow=5, red=1), "II"),  # R > 0 -> not I; O <= 5 %, R <= 1 %
        (dict(green=94, orange=6), "III"),  # tail.R III: O > 5 %, R <= 5 %
        (dict(green=90, yellow=5, red=5), "III"),  # R <= 5 %
        (dict(green=90, yellow=4, red=6), "IV"),  # R > 5 %
        (dict(green=40, orange=60), "III"),
        # Gaps of the literal tail.R rule (all fall through to IV there):
        (dict(green=199, red=1), "II"),  # 99.5 % G + 0.5 % R
        (dict(green=93, yellow=2, orange=5), "II"),  # 93 % G + 2 % Y + 5 % O
        (dict(green=90, yellow=4, orange=4, red=2), "III"),  # R 2 % with O <= 5 %
        (dict(green=97, red=3), "III"),
    ],
)
def test_temperature_time_share_rule_cumulative(counts, label):
    assert _label({"temperature": _mix(**counts)}) == label


def test_missing_samples_are_excluded_from_the_shares():
    # 94 Green + 6 missing: 100 % Green of the samples with a value -> I
    result = _rate({"temperature": _mix(green=94, nan=6)})
    p = _param(result, "temperature")
    assert p.rating_label == "I" and p.sample_count == 94


def _literal_tail_r(g, y, o, r):
    """tail.R l.357-369 exactly as written."""
    if g >= 0.94 and o <= 0.01 and r == 0:
        return 1
    if y > 0.05 and o <= 0.05 and r <= 0.01:
        return 2
    if o > 0.05 and r <= 0.05:
        return 3
    return 4


def test_cumulative_rule_keeps_every_label_tail_r_gives():
    rule = load_config()["time_share_rule"]
    gaps = 0
    for g, y, o in itertools.product(range(0, 101), range(0, 21), range(0, 21)):
        r = 100 - g - y - o
        if r < 0 or r > 20:
            continue
        counts = dict(green=g, yellow=y, orange=o, red=r)
        literal = _literal_tail_r(g / 100, y / 100, o / 100, r / 100)
        ours = TAILCalculator._time_share_rating(counts, rule).value
        if literal < 4:
            assert ours == literal, counts
        else:
            gaps += ours < 4
    assert gaps > 0  # and some IV cases of the literal rule are the gaps being closed


# --------------------------------------------------------------------------- relative humidity
def test_rh_office_bands_l113_118():
    values = [30, 50, 25, 29, 51, 60, 20, 24, 61, 70, 19, 71]
    p = _param(_rate({"humidity": values}, building_type="office"), "relative_humidity")
    assert p.distribution == {"green": 16.67, "yellow": 33.33, "orange": 33.33, "red": 16.67}


def test_rh_clamping_and_integer_rounding_l108_111():
    def colors(values, **meta):
        return _param(_rate({"rh": values}, **meta), "relative_humidity").distribution

    assert colors([0.5])["red"] == 100  # < 1 % -> 1 % -> Red
    assert colors([100.5])["red"] == 100  # > 100 % -> 95 % -> Red
    assert colors([50.5])["green"] == 100  # round half to even: 50
    assert colors([29.5])["green"] == 100  # -> 30
    assert colors([24.5])["orange"] == 100  # -> 24


def test_rh_hotel_bands_l119_123():
    def color(value, building_type):
        dist = _param(_rate({"humidity": [value]}, building_type=building_type), "relative_humidity").distribution
        return max(dist, key=dist.get)

    assert color(65, "office") == "orange"
    assert color(65, "hotel") == "red"  # hotels: > 60 % is Red
    assert color(22, "hotel") == "orange"
    assert color(55, "Hotel") == "yellow"
    assert color(65, "school") == "orange"  # other building types use the office bands
    assert color(65, "hospitality") == "red"


def test_rh_label_uses_the_time_share_rule_and_belongs_to_indoor_air():
    result = _rate({"temperature": [22.0] * 100, "humidity": [40] * 99 + [80]})  # 1 % Red RH
    assert _param(result, "relative_humidity").rating_label == "II"
    assert result.categories[TAILCategory.THERMAL].rating_label == "I"
    assert result.categories[TAILCategory.IAQ].rating_label == "II"
    assert result.overall_rating_label == "II"


# --------------------------------------------------------------------------- CO2
@pytest.mark.parametrize("value, label", [(970, "I"), (971, "II"), (1220, "II"), (1221, "III"), (1770, "III"), (1771, "IV")])
def test_co2_p95_limits_l163_166(value, label):
    assert _label({"co2": [value] * 20}) == label


def test_co2_p95_interpolation_and_outdoor_clamp():
    # 21 values: P95 (R type 7) is at sorted position 0.95 * 20 = 19 -> 1000 ppm -> Yellow, though one sample is 2000.
    p = _param(_rate({"co2": [500] * 19 + [1000, 2000]}), "co2")
    assert p.summary_value == 1000 and p.rating_label == "II"
    # Values below outdoor (420 ppm) are raised to 420 (l.153).
    p = _param(_rate({"co2": [300] * 20}), "co2")
    assert p.summary_value == 420 and p.rating_label == "I"
    assert p.metadata["limits_ppm"] == {"green": 970.0, "yellow": 1220.0, "orange": 1770.0}


def test_co2_outdoor_level_is_a_parameter():
    data = {"co2": [960] * 20}
    assert _label(data) == "I"  # 960 <= 420 + 550
    assert _label(data, outdoor_co2_ppm=400) == "II"  # 960 > 400 + 550
    result = _rate(data, thresholds={"co2": {"outdoor_ppm": 400}})
    assert _param(result, "co2").metadata["limits_ppm"] == {"green": 950.0, "yellow": 1200.0, "orange": 1750.0}
    assert _param(result, "co2").rating_label == "II"


# --------------------------------------------------------------------------- Green/Yellow/Red pollutants
@pytest.mark.parametrize(
    "parameter, values, label",
    [
        ("pm25", [5] * 10, "I"),
        ("pm25", [5] * 9 + [10], "II"),  # any Yellow -> II
        ("pm25", [5] * 9 + [25], "IV"),  # any Red -> IV (there is no Orange)
        ("pm25", [9.4], "I"),  # rounded to 9
        ("pm25", [9.5], "II"),  # round half to even -> 10
        ("pm25", [24.5], "II"),  # -> 24
        ("pm2.5", [0.8, 3], "I"),
        ("formaldehyde", [29], "I"),
        ("formaldehyde", [30], "II"),
        ("formaldehyde", [99], "II"),
        ("formaldehyde", [100], "IV"),
        ("benzene", [1.4], "I"),  # -> 1
        ("benzene", [1.6], "II"),  # -> 2
        ("benzene", [4], "II"),
        ("benzene", [5], "IV"),
        ("radon", [99], "I"),
        ("radon", [100], "II"),
        ("radon", [299], "II"),
        ("radon", [300], "IV"),
    ],
)
def test_pollutants_worst_sample_without_orange(parameter, values, label):
    result = _rate({parameter: values})
    assert len(result.parameter_results) == 1
    assert result.parameter_results[0].rating_label == label


def test_negative_pollutant_values_are_dropped():
    p = _param(_rate({"pm25": [-5, 3]}), "pm25")
    assert p.sample_count == 1 and p.rating_label == "I"


# --------------------------------------------------------------------------- noise
@pytest.mark.parametrize(
    "room_type, value, label",
    [
        ("Small office", 30, "I"),
        ("small_office", 20, "I"),  # raised to 30 dB (l.261)
        ("small-office", 31, "II"),
        ("private_office", 35, "II"),
        ("small_office", 36, "III"),
        ("small_office", 40, "III"),
        ("small_office", 41, "IV"),
        ("Open office", 35, "I"),
        ("open_office", 36, "II"),
        ("open_office", 40, "II"),
        ("open_office", 45, "III"),
        ("open_office", 46, "IV"),
        ("hotel_room", 20, "II"),  # P5 >= 30 after the clamp: hotel Green (<= 25) is unreachable
        ("Hotel", 33, "III"),
        ("hotel", 35, "III"),  # tail.R leaves exactly 35 dB without category; hvx: Orange
        ("hotel", 36, "IV"),
    ],
)
def test_noise_p5_by_room_type_l271_282(room_type, value, label):
    assert _label({"noise": [value] * 20}, room_type=room_type) == label


def test_noise_p5_interpolation():
    # 21 values: P5 at sorted position 0.05 * 20 = 1 -> 31 dB -> small office Yellow
    p = _param(_rate({"noise": [30, 31] + [50] * 19}, room_type="small_office"), "noise")
    assert p.summary_value == 31 and p.rating_label == "II"


def test_noise_room_type_resolution():
    assert _label({"noise": [33] * 5}, building_type="hotel") == "III"  # no room type in a hotel -> hotel limits
    result = _rate({"noise": [33] * 5}, room_type="classroom")
    assert "noise" in result.not_rated and "room type" in result.not_rated["noise"]
    assert TAILCategory.ACOUSTIC not in result.categories


# --------------------------------------------------------------------------- illuminance
@pytest.mark.parametrize("inside, label", [(61, "I"), (60, "II"), (40, "II"), (39, "III"), (10, "III"), (9, "IV")])
def test_illuminance_office_share_within_300_500_lx(inside, label):
    values = [400] * inside + [100] * (100 - inside)
    assert _label({"illuminance": values}, building_type="office") == label


def test_illuminance_office_range_is_inclusive():
    p = _param(_rate({"lux": [300, 500, 299, 501]}), "illuminance")
    assert p.summary_value == 50.0 and p.rating_label == "II"  # 50 % within 300-500 lx


@pytest.mark.parametrize("bright, label", [(0, "I"), (1, "II"), (50, "II"), (51, "III"), (90, "III"), (91, "IV")])
def test_illuminance_hotel_share_at_or_above_100_lx(bright, label):
    values = [100] * bright + [50] * (100 - bright)
    assert _label({"illuminance": values}, building_type="hotel") == label


# --------------------------------------------------------------------------- daylight factor
@pytest.mark.parametrize("values, label", [([5.0], "I"), ([4.9], "II"), ([3.3], "II"), ([3.29], "III"), ([2.0], "III"),
                                            ([1.99], "IV"), ([6.0, 2.5], "III")])
def test_daylight_factor_l328_333(values, label):
    assert _label({"daylight_factor": values}) == label


# --------------------------------------------------------------------------- ventilation
@pytest.mark.parametrize("value, label", [(60.0, "I"), (59.96, "I"), (59.9, "II"), (42.0, "II"), (41.9, "III"),
                                          (24.0, "III"), (23.9, "IV")])
def test_ventilation_limits_from_persons_and_floor_area(value, label):
    # 2 persons, 20 m²: Green 10*2 + 2*20 = 60, Yellow 7*2 + 1.4*20 = 42, Orange 4*2 + 0.8*20 = 24 l/s (l.58-60)
    assert _label({"ventilation": [value]}, design_occupancy=2, area_m2=20.0) == label


def test_ventilation_worst_sample_and_unknown_inputs():
    assert _label({"ventilation": [80.0, 30.0]}, design_occupancy=2, area_m2=20.0) == "III"
    no_people = _rate({"ventilation": [80.0]}, area_m2=20.0)
    assert "number of persons" in no_people.not_rated["ventilation"] and not no_people.parameter_results
    no_area = _rate({"ventilation": [80.0]}, design_occupancy=2)
    assert "floor area" in no_area.not_rated["ventilation"]


# --------------------------------------------------------------------------- mould
@pytest.mark.parametrize(
    "observations, label",
    [
        (["No visible mold"], "I"),
        (["No visible mold", "Small areas visible mold, <400 cm2"], "II"),
        (["slightly larger areas visible mold, < 2500 cm2"], "III"),  # case and spacing normalised
        (["Large areas visible mold, > 2500 cm2", "No visible mold"], "IV"),
        (["none"], "I"),
        (["large"], "IV"),
        ([0], "I"),
        ([399], "II"),
        ([400], "III"),
        ([2500], "IV"),
    ],
)
def test_mould_four_visible_area_classes(observations, label):
    assert _label({"mould": observations}, "mold") == label


def test_unrecognised_mould_observation_is_not_rated():
    result = _rate({"mold": ["a bit"]})
    assert "mold" in result.not_rated and result.overall_rating is None


# --------------------------------------------------------------------------- domains and overall
def test_domain_is_worst_parameter_and_overall_worst_domain():
    result = _rate(
        {
            "temperature": [22.0] * 100,  # I
            "co2": [1000] * 20,  # II
            "pm25": [30],  # IV
            "noise": [33] * 20,  # small office II
            "illuminance": [400] * 100,  # I
            "daylight_factor": [2.5],  # III
        },
        room_type="small_office",
    )
    labels = {c.value: r.rating_label for c, r in result.categories.items()}
    assert labels == {"thermal": "I", "iaq": "IV", "acoustic": "II", "luminous": "III"}
    assert result.overall_rating_label == "IV"


def test_unmeasured_domains_stay_out():
    result = _rate({"temperature": [22.0] * 10})
    assert set(result.categories) == {TAILCategory.THERMAL}
    assert result.overall_rating_label == "I"


def test_pm10_and_voc_are_hvx_extensions_outside_the_rating():
    result = _rate({"co2": [600] * 20, "pm10": [500] * 5, "tvoc": [5000] * 5})
    assert result.overall_rating_label == "I"
    assert result.categories[TAILCategory.IAQ].parameter_count == 1
    assert {p.parameter for p in result.extensions} == {"pm10", "voc"}
    assert all(p.extension and p.rating_label == "IV" for p in result.extensions)
    assert "pm10" in result.visualization["extensions"]
    assert "pm10" not in result.visualization["domains"]["iaq"]["parameters"]


# --------------------------------------------------------------------------- opening hours and time zones
def _day_and_night(day=22.0, night=30.0):
    idx = pd.date_range("2024-01-15", periods=7 * 24, freq="h")  # Monday-Sunday, January
    office = (idx.day_of_week < 5) & (idx.hour >= 8) & (idx.hour < 19)  # covers 08:00-18:00 with either end rule
    return pd.Series(np.where(office, day, night), index=idx)


def test_no_second_opening_hours_filter_when_data_is_already_filtered():
    series = _day_and_night()
    filtered_here = _rate({"temperature": series}, occupancy_filtered=False, building_type="office")
    assert filtered_here.overall_rating_label == "I"  # standalone use: office hours only
    already_filtered = _rate({"temperature": series}, occupancy_filtered=True, building_type="office")
    assert already_filtered.overall_rating_label == "IV"  # caller's choice (here 24/7) is kept


def test_tz_aware_timestamps_use_local_time_not_utc():
    # 2024-05-31 23:30 UTC is 1 June 01:30 in Copenhagen: non-heating, so 22.0 °C is Orange.
    utc = pd.Series([22.0], index=pd.DatetimeIndex(["2024-05-31 23:30"]).tz_localize("UTC"))
    local = _param(_rate({"temperature": utc}, timezone="Europe/Copenhagen"), "temperature")
    assert local.distribution["orange"] == 100
    # Without a building time zone the stamps' own offset is kept (wall-clock time), not UTC.
    own = pd.Series([22.0], index=pd.DatetimeIndex(["2024-06-01 01:30"]).tz_localize("Europe/Copenhagen"))
    assert _param(_rate({"temperature": own}), "temperature").distribution["orange"] == 100
    # Opening hours are local too: Monday 08:30 local (07:30 UTC) is within office hours.
    morning = pd.Series([22.0], index=pd.DatetimeIndex(["2024-01-15 08:30"]).tz_localize("Europe/Copenhagen"))
    result = _rate({"temperature": morning}, occupancy_filtered=False, building_type="office")
    assert _param(result, "temperature").sample_count == 1


def test_analysis_run_parses_offsets_to_local_time_and_respects_occupancy_flag():
    from hvx.core.entities import Room
    from hvx.standards.tail.analysis import run

    room = Room(id="r", name="R", building_id="b", floor_id="f", building_type="office")
    stamps = ["2024-06-01T01:30:00+02:00", "2024-06-01T02:30:00+02:00"]
    summary = run(room, {"temperature": [22.0, 22.0]}, stamps, occupancy_filtered=True).summary_results
    assert summary["parameters"]["temperature"]["distribution"]["orange"] == 100  # June, not May (UTC)
    assert summary["occupancy_filtered"] is True
    filtered = run(room, {"temperature": [22.0, 22.0]}, stamps).summary_results  # Saturday night: unoccupied
    assert filtered["overall_rating"] is None and "temperature" not in filtered["parameters"]


def test_report_pipeline_does_not_filter_opening_hours_twice():
    from hvx.reporting import ReportBuilder, ReportConfig
    from tests.conftest import make_portfolio

    p, b, f, rooms = make_portfolio(n_buildings=1, n_rooms=1, start="2024-01-15", days=7, freq="1h")
    room = next(iter(rooms.values()))
    temps = _day_and_night()
    room.timestamps = [t.isoformat() for t in temps.index]
    room.timeseries_data = {"temperature": temps.tolist(), "co2": [600.0] * len(temps), "humidity": [40.0] * len(temps)}
    fast = dict(parallel_backend="serial", include_simulations=False, min_samples_per_season=1)
    occupied = ReportBuilder(ReportConfig(**fast)).build(p, b, f, rooms).rooms[0]
    assert occupied.tail["parameters"]["temperature"] == "I"
    all_hours = ReportBuilder(ReportConfig(occupied_only=False, **fast)).build(p, b, f, rooms).rooms[0]
    assert all_hours.tail["parameters"]["temperature"] == "IV"  # the report's 24/7 choice reaches TAIL


# --------------------------------------------------------------------------- configuration and aggregation
def test_thresholds_come_from_config_yaml():
    cfg = load_config()
    assert "default_thresholds" not in cfg and "building_type_thresholds" not in cfg
    params = cfg["parameters"]
    assert params["temperature"]["bands"]["heating"]["green"] == [21.0, 23.0]
    assert params["co2"]["outdoor_ppm"] == 420
    assert params["noise"]["limits"]["open_office"] == {"green": 35, "yellow": 40, "orange": 45}
    for name in ("TEMPERATURE_THRESHOLDS", "RH_THRESHOLDS", "POLLUTANT_THRESHOLDS", "NOISE_THRESHOLDS"):
        assert not hasattr(TAILCalculator, name)
    # Overrides go through the same config structure.
    assert _label({"radon": [150]}, thresholds={"radon": {"limits": {"green_below": 200}}}) == "I"


def test_instant_values_and_rating_enum():
    result = TAILCalculator.assess_instant_values({"co2": 800, "pm25": 12}, metadata={})
    assert result.overall_rating == TAILRating.GOOD
    assert TAILRating.from_label("III") is TAILRating.FAIR


def test_typical_tail_is_an_hvx_summary_and_ignores_extensions():
    from hvx.reporting.aggregate import typical_tail
    from hvx.reporting.analysis import combine_tail

    rooms = [
        {"overall": "II", "domains": {"iaq": "II"}, "parameters": {"co2": "II", "pm10": "IV"}, "extensions": {"pm10": "IV"}},
        {"overall": "I", "domains": {"iaq": "I"}, "parameters": {"co2": "I"}},
    ]
    group = typical_tail(rooms)
    assert group["parameters"] == {"co2": "II"} and group["overall"] == "II"
    assert "hvx summary" in group["basis"]
    assert "not* a TAIL building" in typical_tail.__doc__
    seasons = combine_tail([
        {"overall": "I", "domains": {"iaq": "I"}, "parameters": {"co2": "I"}, "extensions": {"pm10": "II"}},
        {"overall": "III", "domains": {"iaq": "III"}, "parameters": {"co2": "III"}, "extensions": {"pm10": "I"}},
    ])
    assert seasons["overall"] == "III" and seasons["extensions"] == {"pm10": "II"}
    assert "pm10" not in seasons["parameters"]


def test_report_caption_calls_the_group_rating_an_hvx_summary(portfolio):
    from hvx.reporting import ReportBuilder, ReportConfig, render

    html = render(ReportBuilder(ReportConfig(parallel_backend="serial", include_simulations=False)).build(*portfolio), "html")
    assert "Typical room (hvx summary)" in html
    assert "not a TAIL building rating" in html


def test_single_winter_season_report_still_uses_bands_per_month():
    from hvx.reporting import ReportBuilder, ReportConfig
    from tests.conftest import make_portfolio

    p, b, f, rooms = make_portfolio(n_buildings=1, n_rooms=1, start="2024-07-01", days=7, freq="1h")
    room = next(iter(rooms.values()))
    n = len(room.timestamps)
    room.timeseries_data = {"temperature": [22.0] * n, "co2": [600.0] * n, "humidity": [40.0] * n}
    config = ReportConfig(seasons=("winter",), parallel_backend="serial", include_simulations=False)
    result = ReportBuilder(config).build(p, b, f, rooms).rooms[0]
    # 22.0 °C is Green in the heating season but Orange in July (non-heating 22-<23 °C): III, not I.
    assert result.tail["parameters"]["temperature"] == "III"
