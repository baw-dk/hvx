# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""TAIL label from one CSV (used by the web app through Pyodide)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hvx.tail_label import detected_columns, label_from_csv, parameter_for

IDX = pd.date_range("2024-01-01", "2024-12-31 23:00", freq="h")


def _csv(sep=",", decimal=".", **columns):
    frame = pd.DataFrame({"timestamp": IDX.strftime("%Y-%m-%d %H:%M"), **columns})
    return frame.to_csv(sep=sep, index=False, decimal=decimal)


def _good_temperature():
    heating = IDX.month.isin([10, 11, 12, 1, 2, 3, 4, 5])
    return np.where(heating, 22.0, 24.5)  # inside the green band of each season


def test_column_names_in_english_and_danish():
    assert parameter_for("Temperatur [°C]") == "temperature"
    assert parameter_for("CO2 (ppm)") == "co2"
    assert parameter_for("Luftfugtighed") == "relative_humidity"
    assert parameter_for("Støj") == "noise" and parameter_for("lux") == "illuminance"
    assert parameter_for("Weekend Highlight") is None
    text = _csv(sep=";", decimal=",", temperature=_good_temperature(), co2=600.0)
    assert detected_columns(text) == {"timestamp": "time", "temperature": "temperature", "co2": "co2"}


def test_good_year_rates_tail_i():
    out = label_from_csv(_csv(temperature=_good_temperature(), co2=600.0, humidity=40.0))
    assert out["overall"] == "I" and out["domains"] == {"thermal": "I", "iaq": "I"}
    assert out["coverage"]["days"] == pytest.approx(366, abs=1) and out["warnings"] == []
    weekday_hours = 8 * 253  # office 09-17 (predicTAIL) on 2024 working days, Danish public holidays excluded
    assert out["occupied"]["hours"] == pytest.approx(weekday_hours, rel=0.03)  # each sample counts 1 h
    assert out["profile"] == "office"


def test_semicolon_decimal_comma_and_bad_co2():
    co2 = np.where((IDX.hour >= 8) & (IDX.hour < 16), 1900.0, 450.0)  # P95 > 1770 ppm: Red -> IV
    out = label_from_csv(_csv(sep=";", decimal=",", temperature=_good_temperature(), co2=co2), building_type="school")
    assert out["parameters"]["co2"]["rating"] == "IV" and out["overall"] == "IV"
    assert out["occupied"]["building_type"] == "school"


def test_short_period_warns_and_column_override():
    frame = pd.DataFrame({"when": IDX[:24 * 30].strftime("%Y-%m-%d %H:%M"), "sensor_a": 22.0})
    out = label_from_csv(frame.to_csv(index=False), columns={"when": "time", "sensor_a": "temperature"})
    assert any("30" in w and "365" in w for w in out["warnings"])


def test_no_parameters_is_a_clear_error():
    with pytest.raises(ValueError, match="No TAIL parameter"):
        label_from_csv("timestamp,foo\n2024-01-01 00:00,1\n")


def test_hotel_rates_sleeping_hours():
    """Hotels: 22:00-06:00 every night (predicTAIL); a bright night light fails the hotel lux rule."""
    lux = np.where((IDX.hour >= 22) | (IDX.hour < 6), 150.0, 5.0)
    out = label_from_csv(_csv(temperature=_good_temperature(), lux=lux), building_type="hotel")
    assert out["occupied"]["hours"] == pytest.approx(8 * 366, rel=0.01)
    assert out["parameters"]["illuminance"]["rating"] == "IV" and out["profile"] == "hotel"


def test_school_profile_and_spot_values():
    out = label_from_csv(_csv(temperature=_good_temperature(), co2=600.0, noise=33.0), building_type="school",
                         volume_m3=180, spot_values={"reverberation_time": 0.7})
    assert out["profile"] == "school" and "Tran 2024" in out["standard"]
    assert out["parameters"]["noise"]["rating"] == "II"  # classroom <= 34 dB(A)
    assert out["parameters"]["reverberation_time"]["rating"] == "II"
    assert out["domains"]["acoustic"] == "II"


def test_adaptive_from_outdoor_column():
    summer = IDX.month.isin([6, 7, 8, 9])
    temp = np.where(summer, 27.0, 22.0)  # warm summer: Orange by the fixed bands, Green adaptively
    outdoor = np.where(IDX.month.isin([5, 6, 7, 8, 9]), 20.0, 5.0)  # warm from May, so theta_rm is ~20 by June
    text = _csv(temperature=temp, udetemperatur=outdoor)
    fixed = label_from_csv(text, building_type="school")
    adaptive = label_from_csv(text, building_type="school", mechanical_cooling=False)
    assert fixed["parameters"]["temperature"]["rating"] == "III"
    assert adaptive["parameters"]["temperature"]["rating"] == "I" and adaptive["parameters"]["temperature"]["adaptive"]
    assert "outdoor_temperature" not in adaptive["parameters"]
