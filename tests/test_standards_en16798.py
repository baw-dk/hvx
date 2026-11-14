# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Regression tests for EN 16798-1 assessment edge cases."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from hvx.standards.en16798.analysis import EN16798Calculator, EN16798Category

IDX = pd.date_range("2025-01-14 08:00", periods=40, freq="15min")


def _assess(**series):
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)  # the old code warned about int/Timestamp index unions
        return EN16798Calculator.assess_detailed_timeseries(season="heating", **series)


def test_single_parameter_room_gets_a_category():
    """A room with only a temperature sensor used to come out '200% outside all categories'."""
    result = _assess(temperature=pd.Series(22.0, index=IDX))
    assert result.achieved_category == EN16798Category.CATEGORY_I
    assert result.time_in_category_I_pct == pytest.approx(100.0)
    assert result.time_out_of_all_categories_pct == pytest.approx(0.0)


def test_missing_samples_are_not_violations():
    humidity = pd.Series([40.0] * 8 + [np.nan] * 32, index=IDX)
    result = _assess(temperature=pd.Series(22.0, index=IDX), humidity=humidity)
    assert result.humidity_metrics["category_II_compliance_rate"] == pytest.approx(100.0)
    assert result.time_in_category_I_pct == pytest.approx(100.0)


def test_rows_with_no_measurement_are_not_assessed():
    temperature = pd.Series([22.0] * 20 + [np.nan] * 20, index=IDX)
    co2 = pd.Series([700.0] * 10 + [1500.0] * 10 + [np.nan] * 20, index=IDX)
    result = _assess(temperature=temperature, co2=co2)
    assert result.co2_metrics["category_II_compliance_rate"] == pytest.approx(50.0)
    # 20 assessed rows, 10 within Cat I/II limits for CO2 -> 50 % in Cat I, not 25 %
    assert result.time_in_category_I_pct == pytest.approx(50.0)


def test_real_violations_still_count():
    result = _assess(temperature=pd.Series([22.0] * 20 + [27.5] * 20, index=IDX))
    assert result.temperature_metrics["category_II_compliance_rate"] == pytest.approx(50.0)
    # Category IV is everything outside Category III: there is no "below IV".
    assert result.achieved_category == EN16798Category.CATEGORY_IV
    assert result.time_in_category_IV_pct == pytest.approx(50.0)
    assert result.time_out_of_all_categories_pct == pytest.approx(0.0)


IDX100 = pd.date_range("2025-01-14 08:00", periods=100, freq="h")


def _co2(high_share: float, value: float = 1300.0) -> pd.Series:
    n = int(round(high_share * 100))
    return pd.Series([700.0] * (100 - n) + [value] * n, index=IDX100)


def test_pass_share_is_95_percent():
    """5 % deviation allowed: 5 % of hours at 1300 ppm still Cat I; 8 % is not (II limit 1200 ppm too)."""
    temp = pd.Series(22.0, index=IDX100)
    assert _assess(temperature=temp, co2=_co2(0.05)).achieved_category == EN16798Category.CATEGORY_I
    assert _assess(temperature=temp, co2=_co2(0.08)).achieved_category == EN16798Category.CATEGORY_III
    assert _assess(temperature=temp, co2=_co2(0.08, 1100.0)).achieved_category == EN16798Category.CATEGORY_II
    assert _assess(temperature=temp, co2=_co2(0.10, 2000.0)).achieved_category == EN16798Category.CATEGORY_IV


def test_each_parameter_rated_on_its_own():
    """Two parameters each within Cat I 96 % of the time, failing at different hours: Cat I
    (the old all-at-once rule gave 92 % and Cat II/III)."""
    temp = pd.Series([22.0] * 96 + [23.5] * 4, index=IDX100)
    co2 = pd.Series([1000.0] * 4 + [700.0] * 96, index=IDX100)
    result = _assess(temperature=temp, co2=co2)
    assert result.parameter_categories == {"temperature": "I", "co2": "I"}
    assert result.achieved_category == EN16798Category.CATEGORY_I
    assert result.category_compliance_rates["I"] == pytest.approx(92.0)  # informational, all at once


def test_missing_values_do_not_count_either_way():
    """40 % missing CO2 and 10 % of all hours at 1800 ppm (above Cat III's 1750) -> 1/6 of the
    measured hours: Cat IV. Counted over all rows (missing as compliant) it was 90 %."""
    co2 = pd.Series([700.0] * 50 + [1800.0] * 10 + [np.nan] * 40, index=IDX100)
    result = _assess(temperature=pd.Series(22.0, index=IDX100), co2=co2)
    assert result.co2_metrics["category_II_compliance_rate"] == pytest.approx(83.33, abs=0.01)
    assert result.parameter_categories["co2"] == "IV"


def test_humidity_counts_only_in_humidity_controlled_rooms():
    from tests.conftest import make_portfolio
    from hvx.standards.en16798.analysis import run

    _, _, _, rooms = make_portfolio(n_buildings=1, n_rooms=1)
    room = next(iter(rooms.values()))
    n = len(room.timestamps)
    series = {"temperature": [22.0] * n, "co2": [700.0] * n, "humidity": [18.0] * n}
    plain = run(room, dict(series), room.timestamps, season="winter").summary_results
    assert plain["achieved_category"] == "I" and plain["humidity_in_category"] is False
    assert plain["parameter_metrics"]["humidity"]["counts_for_category"] is False
    controlled = room.model_copy(update={"metadata": {**(room.metadata or {}), "humidity_controlled": True}})
    strict = run(controlled, dict(series), controlled.timestamps, season="winter").summary_results
    assert strict["achieved_category"] == "IV" and strict["parameter_categories"]["humidity"] == "IV"


def test_running_mean_weights_yesterday_most():
    """Ten days at 0 °C then ten at 20 °C: the running mean is close to 20, not 2."""
    value = EN16798Calculator.calculate_running_mean_outdoor_temp([0.0] * 10 + [20.0] * 10)
    assert value == pytest.approx(20.0 * (1 - 0.8 ** 10) / (1 - 0.8 ** 20), abs=0.01)


def test_legacy_timeseries_compliance_runs_and_ignores_gaps():
    """Used by app.analysis_runner; previously raised UnboundLocalError on every call."""
    humidity = pd.Series([40.0] * 8 + [np.nan] * 32, index=IDX)
    result = EN16798Calculator.assess_timeseries_compliance(
        temperature=pd.Series(22.0, index=IDX), humidity=humidity, season="heating"
    )
    assert result["I"]["compliance_rate"] == pytest.approx(100.0)
    assert result["II"]["compliance_rate"] == pytest.approx(100.0)
