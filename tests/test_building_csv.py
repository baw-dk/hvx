# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""A building from one CSV per room: room and building TAIL labels, and the report (synthetic data)."""
import numpy as np
import pandas as pd
import pytest

from hvx import building_csv


def room_csv(seed: int, co2_extra: float, days: int = 60) -> str:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=days * 24, freq="h")
    occupied = ((idx.hour >= 8) & (idx.hour < 15) & (idx.day_of_week < 5)).astype(float)
    frame = pd.DataFrame({
        "timestamp": idx.strftime("%Y-%m-%d %H:%M"),
        "temperature": (21.8 + occupied + rng.normal(0, 0.3, len(idx))).round(1),
        "co2": (430 + occupied * (350 + co2_extra) + rng.normal(0, 20, len(idx))).round(),
        "humidity": (38 + rng.normal(0, 3, len(idx))).round(),
        "outdoor_temperature": (3 + rng.normal(0, 2, len(idx))).round(1),
    })
    return frame.to_csv(index=False)


ROOMS = [{"name": f"Room {i}", "csv": room_csv(i, 300 * i)} for i in range(3)]


def test_room_and_building_labels_follow_tail_eq1():
    out = building_csv.labels(ROOMS, "Synthetic office", building_type="office")
    ratings = [r["parameters"]["co2"]["rating"] for r in out["rooms"]]
    assert len(out["rooms"]) == 3 and out["building"]["kind"] == "building"
    ranks = ["I", "II", "III", "IV"]
    mean = round(sum(ranks.index(r) + 1 for r in ratings) / 3 + 1e-9, 1)
    expected = "I" if mean <= 1.4 else "II" if mean <= 2.4 else "III" if mean <= 3.4 else "IV"
    assert out["building"]["parameters"]["co2"]["rating"] == expected
    assert sum(out["building"]["parameters"]["co2"]["distribution"].values()) == 3
    assert [r["name"] for r in out["building"]["rooms"]] == ["Room 0", "Room 1", "Room 2"]
    assert "Eq. 1" in out["building"]["basis"]


def test_one_room_has_no_building_label():
    assert building_csv.labels(ROOMS[:1])["building"] is None


def test_shared_advanced_schedule_reaches_labels():
    schedule = {"periods": [{"day": d, "start": "08:00", "end": "12:00"} for d in range(5)], "public_holidays": True}
    out = building_csv.labels(ROOMS, schedule=schedule)
    assert out["rooms"][0]["occupied"]["groups"] == [{"days": [0, 1, 2, 3, 4], "hours": [["08:00", "12:00"]]}]


def test_bad_file_names_the_room():
    with pytest.raises(ValueError, match="Room X"):
        building_csv.labels([{"name": "Room X", "csv": "a,b\n1,2\n"}])


def test_report_uses_the_label_hours_and_outdoor_column():
    result = building_csv.report(ROOMS, "Synthetic school", building_type="school", mechanical_cooling=False,
                                 seasons=("winter",))
    assert "<html" in result["html"].lower() and "Synthetic school" in result["html"]
    rooms = result["data"]["rooms"]
    assert len(rooms) == 3 and rooms[0]["occupancy"].startswith("Mon–Fri 08:00–17:00")
    assert rooms[0]["tail"]["profile"] == "school"
