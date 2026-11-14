# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""DMI connector against canned API pages (no network)."""

from __future__ import annotations

import urllib.parse

import pytest

import hvx.connectors.dmi as dmi
from hvx.connectors.climify import read_dmi_csv


def _value(t: str, v: float) -> dict:
    return {"properties": {"from": t, "value": v, "qcStatus": "manual"}}


@pytest.fixture
def fake_api(monkeypatch):
    calls = []

    def get(url, timeout=60.0):
        calls.append(url)
        if "collections/station/items" in url:
            return {"features": [
                {"properties": {"stationId": "06170", "name": "Near", "parameterId": ["mean_temp"]}, "geometry": {"coordinates": [12.14, 55.59]}},
                {"properties": {"stationId": "06180", "name": "Far", "parameterId": ["mean_temp"]}, "geometry": {"coordinates": [12.65, 55.61]}},
                {"properties": {"stationId": "09999", "name": "Old", "parameterId": ["mean_temp"], "validTo": "2001-01-01"}, "geometry": {"coordinates": [12.2, 55.66]}},
            ]}
        if "offset=" not in url:  # first page links to a second one
            return {"features": [_value("2024-01-15T10:00:00+00:00", 1.5)],
                    "links": [{"rel": "next", "href": url + "&offset=1"}]}
        return {"features": [_value("2024-07-15T10:00:00+00:00", 20.5), _value("2024-07-15T11:00:00+00:00", None)], "links": []}

    monkeypatch.setattr(dmi, "_get", get)
    return calls


def test_fetch_follows_pages_and_writes_readable_file(fake_api, tmp_path):
    data = dmi.fetch_climate_data("06170", ["mean_temp"], "2024-01-01", "2024-12-31")
    assert list(data.value) == [1.5, 20.5]  # missing values dropped, both pages read
    query = urllib.parse.parse_qs(urllib.parse.urlparse(fake_api[0]).query)
    assert query["datetime"] == ["2024-01-01T00:00:00Z/2024-12-31T23:59:59Z"] and query["timeResolution"] == ["hour"]
    path = dmi.write_dmi_csv(data, tmp_path / "x.csv", "Station")
    climate = read_dmi_csv(path, "Europe/Copenhagen")
    # UTC -> local: 10:00 UTC is 11:00 in winter, 12:00 in summer
    assert climate["outdoor_temperature"]["timestamps"] == ["2024-01-15T11:00:00", "2024-07-15T12:00:00"]


def test_nearest_stations_skips_closed_records(fake_api):
    near = dmi.nearest_stations(55.66, 12.19, "mean_temp", 5)
    assert list(near.station_id) == ["06170", "06180"]
    assert near.distance_km.iloc[0] == pytest.approx(8.4, abs=0.2)  # haversine
