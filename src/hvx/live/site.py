"""
Site files: a small YAML description of a portfolio and its live points.

.. code-block:: yaml

    name: Head office
    country: DK
    timezone: Europe/Copenhagen
    sources:
      default:
        type: homeassistant
        url: http://homeassistant.local:8123
        token_env: HA_TOKEN          # never put the token itself in the file
    buildings:
      - id: hq
        name: HQ
        building_type: office
        floors:
          - id: hq-0
            name: Ground floor
            floor_number: 0
            rooms:
              - id: r-101
                name: Meeting 1.01
                room_type: meeting_room
                area_m2: 24
                ifc_guid: 2O2Fr$t4X7Zf8NOew3FLOH     # optional
                requirements: {target_category: I, co2_max_ppm: 950}
                sensors:
                  temperature: sensor.meeting_101_temperature
                  co2: sensor.meeting_101_co2
                  humidity: {point: sensor.meeting_101_humidity, source: default}

LoRaWAN rooms through ChirpStack bind whole devices by DevEUI:

.. code-block:: yaml

    sources:
      lorawan:
        type: chirpstack-mqtt          # or chirpstack-api, chirpstack-http (webhook, API server only)
        host: chirpstack.local
        port: 1883
        application_id: 4e1c...        # optional, default: all applications
        username: hvx
        password_env: CHIRPSTACK_MQTT_PASSWORD
        backfill: {server: chirpstack.local:8080, token_env: CHIRPSTACK_API_TOKEN}
    ...
              rooms:
                - id: r-102
                  name: Office 1.02
                  devices: [{source: lorawan, dev_eui: a84041000181c061}]
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

import yaml

from hvx.core.entities import Building, Floor, Portfolio, Room
from hvx.core.enums import SpatialEntityType
from hvx.core.semantics.ieq import IEQRequirements

from .base import TimeSeriesSource
from .bindings import DEFAULT_SOURCE, bind
from .sources import HomeAssistantSource, InMemorySource

DEVICE_PARAMETERS = ("temperature", "co2", "humidity")


@dataclass
class Site:
    portfolio: Portfolio
    buildings: Dict[str, Building]
    floors: Dict[str, Floor]
    rooms: Dict[str, Room]
    timezone: str = "UTC"
    source_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def entities(self):
        return self.portfolio, self.buildings, self.floors, self.rooms

    def build_sources(self, overrides: Optional[Mapping[str, TimeSeriesSource]] = None) -> Dict[str, TimeSeriesSource]:
        sources: Dict[str, TimeSeriesSource] = dict(overrides or {})
        for name, cfg in self.source_configs.items():
            if name not in sources:
                sources[name] = build_source(cfg)
        return sources


def _secret(cfg: Mapping[str, Any], key: str, default_env: str) -> str:
    return str(cfg.get(key) or os.environ.get(str(cfg.get(f"{key}_env", default_env)), ""))


def build_source(cfg: Mapping[str, Any]) -> TimeSeriesSource:
    kind = str(cfg.get("type", "")).lower()
    if kind.startswith("chirpstack"):
        from .chirpstack import ChirpStackAPISource, ChirpStackMQTTSource

        if kind == "chirpstack-api":
            return ChirpStackAPISource(
                server=str(cfg.get("server", "localhost:8080")),
                token=_secret(cfg, "token", "CHIRPSTACK_API_TOKEN"),
                tls=bool(cfg.get("tls", False)),
                aggregation=str(cfg.get("aggregation", "HOUR")),
            )
        if kind == "chirpstack-mqtt":
            backfill = cfg.get("backfill")
            return ChirpStackMQTTSource(
                host=str(cfg.get("host", "localhost")),
                port=int(cfg.get("port", 1883)),
                application_id=str(cfg.get("application_id", "+")),
                username=cfg.get("username"),
                password=_secret(cfg, "password", "CHIRPSTACK_MQTT_PASSWORD") or None,
                tls=bool(cfg.get("tls", False)),
                topic=cfg.get("topic"),
                backfill=build_source({**backfill, "type": "chirpstack-api"}) if backfill else None,  # type: ignore[arg-type]
            )
        if kind == "chirpstack-http":
            return InMemorySource()  # filled by POST /api/integrations/chirpstack
        raise ValueError(f"Unknown ChirpStack source type {kind!r}")
    if kind == "homeassistant":
        token = cfg.get("token") or os.environ.get(str(cfg.get("token_env", "HA_TOKEN")), "")
        return HomeAssistantSource(
            url=str(cfg.get("url", "http://homeassistant.local:8123")),
            token=token,
            verify_ssl=bool(cfg.get("verify_ssl", True)),
        )
    if kind == "memory":
        return InMemorySource()
    raise ValueError(
        f"Unknown source type {kind!r} (expected homeassistant, memory, chirpstack-mqtt, chirpstack-api or chirpstack-http)"
    )


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-") or "item"


def load_site(source: Union[str, Path, Mapping[str, Any]]) -> Site:
    data: Mapping[str, Any] = source if isinstance(source, Mapping) else yaml.safe_load(Path(source).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("Site file must be a mapping")
    country = data.get("country")
    portfolio = Portfolio(
        id=str(data.get("id") or _slug(str(data.get("name", "site")))),
        name=str(data.get("name", "Site")),
        type=SpatialEntityType.PORTFOLIO,
        country=country,
        region=data.get("region"),
    )
    buildings: Dict[str, Building] = {}
    floors: Dict[str, Floor] = {}
    rooms: Dict[str, Room] = {}

    def add_room(spec: Mapping[str, Any], building: Building, floor: Optional[Floor]) -> None:
        rid = str(spec.get("id") or f"{(floor or building).id}-{_slug(str(spec['name']))}")
        if rid in rooms:
            raise ValueError(f"Duplicate room id {rid!r}")
        req = spec.get("requirements")
        room = Room(
            id=rid,
            name=str(spec.get("name", rid)),
            building_id=building.id,
            floor_id=floor.id if floor else None,
            parent_ids=[(floor or building).id],
            room_type=spec.get("room_type"),
            area_m2=spec.get("area_m2"),
            volume_m3=spec.get("volume_m3"),
            design_occupancy=spec.get("design_occupancy"),
            ifc_guid=spec.get("ifc_guid"),
            brick_class=spec.get("brick_class"),
            ieq_requirements=IEQRequirements(**req) if req else None,
        )
        for device in spec.get("devices") or []:
            from .chirpstack import device_points

            dev = device if isinstance(device, Mapping) else {"dev_eui": device}
            params = dev.get("parameters") or DEVICE_PARAMETERS
            for parameter, point in device_points(str(dev["dev_eui"]), params).items():
                bind(room, parameter, point, str(dev.get("source", DEFAULT_SOURCE)))
        for parameter, point in (spec.get("sensors") or {}).items():
            if isinstance(point, Mapping):
                bind(room, parameter, str(point["point"]), str(point.get("source", DEFAULT_SOURCE)), point.get("unit"))
            elif point:
                bind(room, parameter, str(point))
        rooms[rid] = room
        (floor or building).add_room(rid)
        if floor:
            building.add_room(rid)

    for b_spec in data.get("buildings") or []:
        bid = str(b_spec.get("id") or _slug(str(b_spec["name"])))
        building = Building(
            id=bid,
            name=str(b_spec.get("name", bid)),
            parent_ids=[portfolio.id],
            building_type=b_spec.get("building_type"),
            country=b_spec.get("country") or country,
            city=b_spec.get("city"),
            area_m2=b_spec.get("area_m2"),
            year_built=b_spec.get("year_built"),
            ifc_guid=b_spec.get("ifc_guid"),
        )
        buildings[bid] = building
        portfolio.add_building(bid)
        for f_spec in b_spec.get("floors") or []:
            fid = str(f_spec.get("id") or f"{bid}-{_slug(str(f_spec['name']))}")
            floor = Floor(
                id=fid,
                name=str(f_spec.get("name", fid)),
                building_id=bid,
                parent_ids=[bid],
                floor_number=f_spec.get("floor_number"),
                ifc_guid=f_spec.get("ifc_guid"),
            )
            floors[fid] = floor
            building.add_floor(fid)
            for r_spec in f_spec.get("rooms") or []:
                add_room(r_spec, building, floor)
        for r_spec in b_spec.get("rooms") or []:
            add_room(r_spec, building, None)

    return Site(
        portfolio=portfolio,
        buildings=buildings,
        floors=floors,
        rooms=rooms,
        timezone=str(data.get("timezone", "UTC")),
        source_configs=dict(data.get("sources") or {}),
    )


def site_skeleton(portfolio: Portfolio, buildings, floors, rooms, source_type: str = "homeassistant") -> Dict[str, Any]:
    """A site-file dict from existing entities (e.g. an IFC import) with empty sensor slots to fill in."""
    def room_spec(r: Room) -> Dict[str, Any]:
        spec: Dict[str, Any] = {"id": r.id, "name": r.name}
        for key in ("room_type", "area_m2", "volume_m3", "design_occupancy", "ifc_guid"):
            if getattr(r, key) is not None:
                spec[key] = getattr(r, key)
        if r.ieq_requirements:
            spec["requirements"] = r.ieq_requirements.model_dump(mode="json", exclude_none=True)
        spec["sensors"] = {"temperature": None, "co2": None, "humidity": None}
        return spec

    out_buildings = []
    for b in buildings.values():
        b_floors = [f for f in floors.values() if f.building_id == b.id]
        b_floors.sort(key=lambda f: (f.floor_number is None, f.floor_number or 0))
        out_buildings.append(
            {
                "id": b.id,
                "name": b.name,
                **({"building_type": b.building_type} if b.building_type else {}),
                **({"ifc_guid": b.ifc_guid} if b.ifc_guid else {}),
                "floors": [
                    {
                        "id": f.id,
                        "name": f.name,
                        "floor_number": f.floor_number,
                        **({"ifc_guid": f.ifc_guid} if f.ifc_guid else {}),
                        "rooms": [room_spec(r) for r in rooms.values() if r.floor_id == f.id],
                    }
                    for f in b_floors
                ],
                "rooms": [room_spec(r) for r in rooms.values() if r.building_id == b.id and not r.floor_id],
            }
        )
    return {
        "name": portfolio.name,
        "country": portfolio.country or "DK",
        "timezone": "Europe/Copenhagen",
        "sources": {"default": {"type": source_type, "url": "http://homeassistant.local:8123", "token_env": "HA_TOKEN"}},
        "buildings": out_buildings,
    }


__all__ = ["Site", "load_site", "build_source", "site_skeleton"]
