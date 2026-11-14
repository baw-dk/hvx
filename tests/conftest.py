from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.entities import Building, Floor, Portfolio, Room  # noqa: E402
from core.enums import SpatialEntityType  # noqa: E402

Hierarchy = Tuple[Portfolio, Dict[str, Building], Dict[str, Floor], Dict[str, Room]]


def make_portfolio(
    n_buildings: int = 2,
    n_floors: int = 1,
    n_rooms: int = 3,
    start: str = "2025-01-06",
    days: int = 7,
    freq: str = "15min",
    seed: int = 0,
    summer_overheating: float = 0.0,
) -> Hierarchy:
    """Synthetic office portfolio; room index r makes CO2 and temperature progressively worse."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=int(pd.Timedelta(days=days) / pd.Timedelta(freq)), freq=freq)
    hour = idx.hour.to_numpy()
    occupied = ((hour >= 8) & (hour < 17) & (idx.day_of_week.to_numpy() < 5)).astype(float)
    summer = idx.month.isin([5, 6, 7, 8, 9]).astype(float)

    portfolio = Portfolio(id="p1", name="Test Portfolio", type=SpatialEntityType.PORTFOLIO, country="DK")
    buildings: Dict[str, Building] = {}
    floors: Dict[str, Floor] = {}
    rooms: Dict[str, Room] = {}
    for b in range(n_buildings):
        bid = f"b{b}"
        building = Building(id=bid, name=f"Building {b}", parent_ids=[portfolio.id], building_type="office", country="DK")
        portfolio.add_building(bid)
        buildings[bid] = building
        for f in range(n_floors):
            fid = f"{bid}_f{f}"
            floor = Floor(id=fid, name=f"Floor {f}", building_id=bid, parent_ids=[bid], floor_number=f)
            building.add_floor(fid)
            floors[fid] = floor
            for r in range(n_rooms):
                rid = f"{fid}_r{r}"
                temp = 21.5 + 1.2 * np.sin(2 * np.pi * hour / 24) + rng.normal(0, 0.4, len(idx)) + 0.8 * r
                temp = temp + summer * summer_overheating
                co2 = 430 + occupied * (300 + 350 * r) + rng.normal(0, 30, len(idx))
                rh = 42 + rng.normal(0, 4, len(idx))
                room = Room(
                    id=rid, name=f"Room {b}.{f}.{r}", floor_id=fid, building_id=bid, parent_ids=[fid],
                    room_type="meeting_room" if r == 0 else "open_office", area_m2=20.0 + 5 * r, volume_m3=60.0 + 15 * r,
                )
                room.timestamps = [t.isoformat() for t in idx]
                room.timeseries_data = {"temperature": temp.tolist(), "co2": co2.tolist(), "humidity": rh.tolist()}
                floor.add_room(rid)
                building.add_room(rid)
                rooms[rid] = room
    return portfolio, buildings, floors, rooms


@pytest.fixture
def portfolio() -> Hierarchy:
    return make_portfolio()
