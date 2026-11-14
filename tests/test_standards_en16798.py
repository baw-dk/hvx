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
    assert result.time_out_of_all_categories_pct == pytest.approx(50.0)


def test_legacy_timeseries_compliance_runs_and_ignores_gaps():
    """Used by app.analysis_runner; previously raised UnboundLocalError on every call."""
    humidity = pd.Series([40.0] * 8 + [np.nan] * 32, index=IDX)
    result = EN16798Calculator.assess_timeseries_compliance(
        temperature=pd.Series(22.0, index=IDX), humidity=humidity, season="heating"
    )
    assert result["I"]["compliance_rate"] == pytest.approx(100.0)
    assert result["II"]["compliance_rate"] == pytest.approx(100.0)
