# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Climify room exports and DMI weather files (synthetic files in the real formats)."""

from __future__ import annotations

import pandas as pd
import pytest

from hvx.connectors.climify import BuildingSpec, load_climify_folder, read_dmi_csv, slug

HEADER = (
    "DateTime,Weekend Highlight,Temperatur,Temperatur Interval (low),Temperatur Interval (high),Temperatur Gennemsnit,"
    "Fugtighed,Fugtighed Interval (low),Fugtighed Interval (high),Fugtighed Gennemsnit,CO2,CO2 Interval (low),"
    "CO2 Interval (high),CO2 Gennemsnit,Lys,Lys Interval (low),Lys Interval (high),Lys Gennemsnit,source_file,hour\n"
)


def _room_file(path, rows):
    lines = [HEADER]
    for ts, t, rh, co2 in rows:
        lines.append(f"{ts},,{t},{t},{t},,{rh},{rh},{rh},,{co2},{co2},{co2},,0,0,0,,x.csv,0\n")
    path.write_text("".join(lines), encoding="utf-8")


@pytest.fixture
def export(tmp_path):
    rooms = tmp_path / "rooms"
    rooms.mkdir()
    hours = pd.date_range("2024-03-04 00:00", periods=48, freq="h")
    rows = [(t.strftime("%Y-%m-%d %H:%M:%S"), 21.5, 35.0, 450 + 600 * (8 <= t.hour < 16)) for t in hours]
    _room_file(rooms / "Nordskolen_0._sal_0.012_processed.csv", rows)
    _room_file(rooms / "Nordskolen_1._Sal_Klasse_7A_processed.csv", rows + [rows[-1]])  # duplicate row
    _room_file(rooms / "Lille_Nordskolen_Stue_Musik_processed.csv", rows)  # longer prefix must win
    _room_file(rooms / "Ukendt_Stue_1_processed.csv", rows)
    dmi = tmp_path / "dmi.csv"
    dmi.write_text(
        "timestamp,parameter,value,unit,school,school_key,station_name,station_id\n"
        "2024-03-04 11:00:00+00:00,mean_temp,5.0,mean_temp,N,n,S,1\n"
        "2024-03-04 12:00:00+00:00,mean_temp,6.0,mean_temp,N,n,S,1\n"
        "2024-03-04 12:00:00+00:00,mean_radiation,250.0,mean_radiation,N,n,S,1\n"
        "2024-03-04 12:00:00+00:00,acc_precip,0.1,acc_precip,N,n,S,1\n",
        encoding="utf-8",
    )
    return rooms, dmi


def test_load_folder_structure(export):
    rooms_dir, dmi = export
    result = load_climify_folder(
        rooms_dir,
        [BuildingSpec("Nordskolen", "Nordskolen", climate_file=dmi), BuildingSpec("Lille_Nordskolen", "Lille Nordskolen")],
        portfolio_name="Test kommune",
    )
    assert result.skipped == ["Ukendt_Stue_1_processed.csv"]
    assert set(result.buildings) == {"nordskolen", "lille-nordskolen"}
    nord = result.buildings["nordskolen"]
    assert sorted(result.floors[f].name for f in nord.floor_ids) == ["0. sal", "1. sal"]
    assert [result.floors[f].floor_number for f in sorted(nord.floor_ids)] == [0, 1]
    names = {r.name: r for r in result.rooms.values()}
    assert set(names) == {"0.012", "Klasse 7A", "Musik"}
    assert names["Musik"].building_id == "lille-nordskolen"
    room = names["Klasse 7A"]
    assert len(room.timestamps) == 48  # duplicate timestamp dropped
    assert set(room.timeseries_data) == {"temperature", "humidity", "co2", "illuminance"}
    assert room.room_type == "classroom" and room.timestamps[0] == "2024-03-04T00:00:00"


def test_dmi_is_converted_to_local_time(export):
    _, dmi = export
    climate = read_dmi_csv(dmi, "Europe/Copenhagen")
    assert set(climate) == {"outdoor_temperature", "solar_irradiance"}  # precipitation ignored
    # 11:00 UTC is 12:00 in Copenhagen (CET, winter)
    assert climate["outdoor_temperature"]["timestamps"][0] == "2024-03-04T12:00:00"
    assert climate["outdoor_temperature"]["values"] == [5.0, 6.0]


def test_report_end_to_end(export):
    from hvx.core.schedules import OccupancySchedule
    from hvx.reporting import ReportBuilder, ReportConfig

    rooms_dir, dmi = export
    result = load_climify_folder(rooms_dir, [BuildingSpec("Nordskolen", "Nordskolen", climate_file=dmi)])
    report = ReportBuilder(
        ReportConfig(occupancy=OccupancySchedule(start="08:00", end="16:00"), parallel_backend="serial", include_simulations=False)
    ).build(*result.entities)
    room = next(r for r in report.rooms if r.room_name == "0.012")
    assert room.status == "ok"
    assert room.exceedance_hours["co2>1000"] == pytest.approx(16.0)  # 2 school days x 8 h at 1050 ppm
    assert room.data_quality["occupied_hours"] == pytest.approx(16.0)


def test_slug_transliterates_danish():
    assert slug("Fløng Skole") == "floeng-skole"
    assert slug("Ole Rømer-Skolen / Kælder") == "ole-roemer-skolen-kaelder"
    assert slug("Åbyhøj") == "aabyhoej"
