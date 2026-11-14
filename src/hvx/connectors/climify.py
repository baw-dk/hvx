# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Load Climify room exports and DMI weather files into HVX entities.

Climify exports one CSV per room with Danish column names (``DateTime``,
``Temperatur``, ``Fugtighed``, ``CO2``, ``Lys``, ``Tilstedeværelse`` plus
interval/average columns) and local, timezone-naive timestamps. File names
encode building, floor and room, e.g. ``<Building>_<Floor>_<Room>_processed.csv``.

DMI files (as produced by the DMI open-data API) are long-format:
``timestamp, parameter, value`` with UTC timestamps. They are converted to the
building's local time so they line up with the room data.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import pandas as pd

from hvx.core.entities import Building, Floor, Portfolio, Room
from hvx.core.enums import SpatialEntityType

CLIMIFY_COLUMNS: Dict[str, str] = {
    "Temperatur": "temperature",
    "Fugtighed": "humidity",
    "CO2": "co2",
    "Lys": "illuminance",
    "Tilstedeværelse": "occupancy",
}
DMI_PARAMETERS: Dict[str, str] = {
    "mean_temp": "outdoor_temperature",
    "mean_relative_hum": "outdoor_humidity",
    "mean_radiation": "solar_irradiance",
}
# Floor tokens in Climify room names: "0._sal", "1._Sal", "Stueplan", "Stue", "Kælder"
FLOOR_PATTERN = re.compile(r"^(?P<floor>(?:\d+\._[Ss]al)|Stueplan|Stue|K[æa]lder)_(?P<room>.+)$")


@dataclass
class BuildingSpec:
    """How to recognise one building in the export file names."""

    prefix: str  # file-name prefix, e.g. "Ole_Rømer-Skolen"
    name: str
    building_type: str = "school"
    id: Optional[str] = None
    climate_file: Optional[Union[str, Path]] = None
    room_type: Optional[str] = "classroom"


@dataclass
class ClimifyLoadResult:
    portfolio: Portfolio
    buildings: Dict[str, Building]
    floors: Dict[str, Floor]
    rooms: Dict[str, Room]
    skipped: List[str] = field(default_factory=list)

    @property
    def entities(self):
        return self.portfolio, self.buildings, self.floors, self.rooms


_DANISH = str.maketrans({"æ": "ae", "ø": "oe", "å": "aa", "Æ": "Ae", "Ø": "Oe", "Å": "Aa"})


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.translate(_DANISH)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def _floor_info(token: str) -> tuple[str, Optional[int]]:
    """'0._sal' -> ('0. sal', 0); 'Stueplan'/'Stue' -> ('Stueplan', 0)."""
    m = re.match(r"(\d+)\._[Ss]al", token)
    if m:
        return f"{m.group(1)}. sal", int(m.group(1))
    if token.lower().startswith("stue"):
        return "Stueplan", 0
    return token.replace("_", " "), -1


def read_climify_csv(path: Union[str, Path]) -> pd.DataFrame:
    """One room export -> DataFrame with canonical columns and a local DatetimeIndex."""
    header = pd.read_csv(path, nrows=0).columns
    usecols = ["DateTime"] + [c for c in CLIMIFY_COLUMNS if c in header]
    df = pd.read_csv(path, usecols=usecols)
    df.index = pd.to_datetime(df.pop("DateTime"), errors="coerce")
    df = df[~df.index.isna()]
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df = df.rename(columns=CLIMIFY_COLUMNS).apply(pd.to_numeric, errors="coerce")
    return df.dropna(how="all")


def read_dmi_csv(path: Union[str, Path], timezone: str = "Europe/Copenhagen") -> Dict[str, Dict[str, list]]:
    """Long-format DMI file -> ``{parameter: {"timestamps": [...], "values": [...]}}`` in local time."""
    raw = pd.read_csv(path, usecols=["timestamp", "parameter", "value"])
    raw = raw[raw["parameter"].isin(DMI_PARAMETERS)]
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True).dt.tz_convert(timezone).dt.tz_localize(None)
    wide = raw.pivot_table(index="timestamp", columns="parameter", values="value", aggfunc="mean").sort_index()
    return {
        DMI_PARAMETERS[col]: {
            "timestamps": [t.isoformat() for t in wide.index[wide[col].notna()]],
            "values": wide[col].dropna().astype(float).tolist(),
        }
        for col in wide.columns
    }


def load_climify_folder(
    folder: Union[str, Path],
    buildings: Iterable[BuildingSpec],
    portfolio_name: str = "Portfolio",
    country: str = "DK",
    timezone: str = "Europe/Copenhagen",
    pattern: str = "*.csv",
    parameters: Optional[Iterable[str]] = None,
) -> ClimifyLoadResult:
    """``parameters`` limits what is loaded, e.g. ``("temperature", "co2", "humidity")``
    to leave out light readings that do not represent the work plane."""
    keep = set(parameters) if parameters is not None else None
    specs = sorted(buildings, key=lambda b: len(b.prefix), reverse=True)  # longest prefix wins
    portfolio = Portfolio(id=slug(portfolio_name), name=portfolio_name, type=SpatialEntityType.PORTFOLIO, country=country)
    out_buildings: Dict[str, Building] = {}
    floors: Dict[str, Floor] = {}
    rooms: Dict[str, Room] = {}
    skipped: List[str] = []

    for spec in specs:
        bid = spec.id or slug(spec.name)
        building = Building(id=bid, name=spec.name, parent_ids=[portfolio.id], building_type=spec.building_type, country=country)
        if spec.climate_file:
            building.metadata["climate_data"] = read_dmi_csv(spec.climate_file, timezone)
        out_buildings[bid] = building
        portfolio.add_building(bid)

    for path in sorted(Path(folder).glob(pattern)):
        stem = re.sub(r"_processed$", "", path.stem)
        spec = next((s for s in specs if stem.startswith(s.prefix + "_")), None)
        if spec is None:
            skipped.append(path.name)
            continue
        building = out_buildings[spec.id or slug(spec.name)]
        rest = stem[len(spec.prefix) + 1 :]
        m = FLOOR_PATTERN.match(rest)
        floor = None
        room_label = rest
        if m:
            floor_name, number = _floor_info(m.group("floor"))
            fid = f"{building.id}-{slug(floor_name)}"
            floor = floors.get(fid)
            if floor is None:
                floor = Floor(id=fid, name=floor_name, building_id=building.id, parent_ids=[building.id], floor_number=number)
                floors[fid] = floor
                building.add_floor(fid)
            room_label = m.group("room")
        room_name = room_label.replace("_", " ")
        rid = f"{(floor or building).id}-{slug(room_name)}"
        df = read_climify_csv(path)
        if df.empty:
            skipped.append(path.name)
            continue
        room = Room(
            id=rid,
            name=room_name,
            building_id=building.id,
            floor_id=floor.id if floor else None,
            parent_ids=[(floor or building).id],
            room_type=spec.room_type,
            metadata={"source_file": path.name},
        )
        room.timestamps = [t.isoformat() for t in df.index]
        room.timeseries_data = {c: df[c].astype(float).tolist() for c in df.columns if keep is None or c in keep}
        rooms[rid] = room
        (floor or building).add_room(rid)
        if floor:
            building.add_room(rid)

    return ClimifyLoadResult(portfolio, out_buildings, floors, rooms, skipped)


__all__ = ["BuildingSpec", "ClimifyLoadResult", "load_climify_folder", "read_climify_csv", "read_dmi_csv", "CLIMIFY_COLUMNS", "DMI_PARAMETERS"]
