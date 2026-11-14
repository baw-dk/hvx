# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Danish weather data from DMI's open data API (no API key).

Uses the quality-controlled *climate data* collection (hourly or daily station
values such as ``mean_temp`` and ``mean_radiation``) and writes the long CSV format
that :func:`hvx.connectors.climify.read_dmi_csv` reads, so a fetched file can be
given to a building as its ``climate_file``::

    from hvx.connectors.dmi import fetch_climate_data, nearest_stations, write_dmi_csv

    nearest_stations(55.66, 12.27, parameter="mean_temp")[:3]
    data = fetch_climate_data("06170", ["mean_temp", "mean_radiation"], "2024-01-01", "2024-12-31")
    write_dmi_csv(data, "climate_roskilde_2024.csv")

or ``hvx dmi fetch --station 06170 --param mean_temp --from 2024-01-01 --to 2024-12-31 -o x.csv``.

Data: DMI (Danish Meteorological Institute), free for any use with attribution.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import pandas as pd

API = "https://opendataapi.dmi.dk/v2/climateData"
PAGE = 10000
USER_AGENT = "hvx-ieq (python)"


def _get(url: str, timeout: float = 60.0) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        return json.load(response)


def _paged(url: str) -> Iterable[dict]:
    while url:
        page = _get(url)
        yield from page.get("features") or []
        url = next((link["href"] for link in page.get("links") or [] if link.get("rel") == "next"), None)


def stations(parameter: Optional[str] = None) -> pd.DataFrame:
    """Active climate stations: id, name, latitude, longitude, (optionally) offering ``parameter``."""
    rows = []
    for feature in _paged(f"{API}/collections/station/items?limit={PAGE}"):
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        if props.get("validTo"):  # superseded station record
            continue
        if parameter and parameter not in (props.get("parameterId") or []):
            continue
        rows.append({"station_id": props.get("stationId"), "name": props.get("name"),
                     "latitude": coords[1], "longitude": coords[0], "type": props.get("type")})
    return pd.DataFrame(rows).drop_duplicates("station_id")


def nearest_stations(latitude: float, longitude: float, parameter: str = "mean_temp", n: int = 5) -> pd.DataFrame:
    """The ``n`` stations closest to a point that report ``parameter``, with distance in km."""
    table = stations(parameter)
    lat0, lon0 = math.radians(latitude), math.radians(longitude)

    def km(row) -> float:
        lat, lon = math.radians(row.latitude), math.radians(row.longitude)
        a = math.sin((lat - lat0) / 2) ** 2 + math.cos(lat0) * math.cos(lat) * math.sin((lon - lon0) / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(a))

    table["distance_km"] = table.apply(km, axis=1).round(1)
    return table.sort_values("distance_km").head(n).reset_index(drop=True)


def fetch_climate_data(
    station_id: str,
    parameters: Iterable[str],
    start: str,
    end: str,
    time_resolution: str = "hour",
) -> pd.DataFrame:
    """Station values between ``start`` and ``end`` (dates or ISO times, UTC), long format:
    timestamp (UTC, start of the interval), parameter, value, unit, station_id."""
    start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start)
    end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end)
    if len(str(end)) <= 10:  # a date: include the whole day
        end_ts += pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    rows: List[Dict] = []
    for parameter in parameters:
        query = urllib.parse.urlencode({
            "stationId": station_id, "parameterId": parameter, "timeResolution": time_resolution,
            "datetime": f"{start_ts:%Y-%m-%dT%H:%M:%SZ}/{end_ts:%Y-%m-%dT%H:%M:%SZ}", "limit": PAGE,
        })
        for feature in _paged(f"{API}/collections/stationValue/items?{query}"):
            props = feature.get("properties") or {}
            if props.get("value") is None:
                continue
            rows.append({"timestamp": props["from"], "parameter": parameter, "value": float(props["value"]),
                         "unit": parameter, "station_id": station_id, "qc_status": props.get("qcStatus")})
    frame = pd.DataFrame(rows, columns=["timestamp", "parameter", "value", "unit", "station_id", "qc_status"])
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.sort_values(["parameter", "timestamp"]).reset_index(drop=True)
    return frame


def write_dmi_csv(data: pd.DataFrame, path: Union[str, Path], station_name: Optional[str] = None) -> Path:
    """Write :func:`fetch_climate_data` output in the long format ``read_dmi_csv`` reads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = data.copy()
    out["station_name"] = station_name or ""
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True).dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    out[["timestamp", "parameter", "value", "unit", "station_name", "station_id"]].to_csv(path, index=False)
    return path


__all__ = ["fetch_climate_data", "nearest_stations", "stations", "write_dmi_csv", "API"]
