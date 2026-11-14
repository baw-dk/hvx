# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Concrete sources.

* :class:`InMemorySource` – push readings in (MQTT callbacks, webhooks, tests,
  the Home Assistant integration).
* :class:`HomeAssistantSource` – pull from a Home Assistant instance over its
  REST API with a long-lived access token (no extra dependencies).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .base import Reading, TimeSeriesSource, as_utc, normalize_unit, to_series, utcnow

logger = logging.getLogger(__name__)


class InMemorySource(TimeSeriesSource):
    """Thread-safe push source."""

    name = "memory"

    def __init__(self, hold_values: bool = False) -> None:
        self.hold_values = hold_values
        self._data: Dict[str, List[tuple]] = {}
        self._lock = threading.Lock()

    def push(self, point: str, value: float, timestamp: Optional[datetime] = None, unit: Optional[str] = None) -> None:
        ts = as_utc(timestamp or utcnow())
        with self._lock:
            self._data.setdefault(point, []).append((ts, normalize_unit(float(value), unit)))

    def extend(self, point: str, series: pd.Series, unit: Optional[str] = None) -> None:
        index = series.index.tz_localize("UTC") if series.index.tz is None else series.index.tz_convert("UTC")
        with self._lock:
            bucket = self._data.setdefault(point, [])
            bucket.extend((ts.to_pydatetime(), normalize_unit(float(v), unit)) for ts, v in zip(index, series.to_numpy()))

    def history(self, points: Sequence[str], start: datetime, end: Optional[datetime] = None) -> Dict[str, pd.Series]:
        start, end = as_utc(start), as_utc(end or utcnow())
        with self._lock:
            snapshot = {p: list(self._data.get(p, [])) for p in points}
        return {p: to_series([x for x in rows if start <= x[0] <= end]) for p, rows in snapshot.items() if rows}

    def prune(self, before: datetime) -> None:
        before = as_utc(before)
        with self._lock:
            for point in list(self._data):
                self._data[point] = [x for x in self._data[point] if x[0] >= before]


class HomeAssistantError(RuntimeError):
    pass


class HomeAssistantSource(TimeSeriesSource):
    """
    Read sensor history from Home Assistant's REST API.

    ``points`` are entity ids such as ``sensor.meeting_room_co2``. Home Assistant
    stores a state only when it changes, so values are held until the next one;
    ``unavailable``/``unknown`` become NaN and end the hold. °F is converted to °C.
    """

    name = "homeassistant"
    hold_values = True  # HA records a state only when it changes

    def __init__(self, url: str, token: str, timeout: float = 30.0, verify_ssl: bool = True, chunk_size: int = 20) -> None:
        if not token:
            raise ValueError("A Home Assistant long-lived access token is required")
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.chunk_size = chunk_size
        self._ssl_context = None
        if not verify_ssl:
            import ssl

            self._ssl_context = ssl._create_unverified_context()  # noqa: S323 - explicit opt-in for self-signed HA

    # -- HTTP --------------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None):
        url = f"{self.url}{path}"
        if params:
            url += "?" + urlencode(params, safe=",:")
        request = Request(url, headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:  # noqa: S310 - user-configured URL
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 401:
                raise HomeAssistantError("Home Assistant rejected the access token (401)") from exc
            raise HomeAssistantError(f"Home Assistant returned HTTP {exc.code} for {path}") from exc
        except URLError as exc:
            raise HomeAssistantError(f"Cannot reach Home Assistant at {self.url}: {exc.reason}") from exc

    def check(self) -> str:
        """Return the API message, raising :class:`HomeAssistantError` on failure."""
        return str(self._get("/api/").get("message", "ok"))

    # -- Source API ----------------------------------------------------------
    def history(self, points: Sequence[str], start: datetime, end: Optional[datetime] = None) -> Dict[str, pd.Series]:
        start, end = as_utc(start), as_utc(end or utcnow())
        out: Dict[str, pd.Series] = {}
        points = list(dict.fromkeys(points))
        for i in range(0, len(points), self.chunk_size):
            chunk = points[i : i + self.chunk_size]
            payload = self._get(
                f"/api/history/period/{quote(start.isoformat())}",
                {
                    "filter_entity_id": ",".join(chunk),
                    "end_time": end.isoformat(),
                    "minimal_response": "",
                    "significant_changes_only": "0",
                },
            )
            for states in payload or []:
                if not states:
                    continue
                entity_id = states[0].get("entity_id")
                if entity_id is None:
                    continue
                unit = (states[0].get("attributes") or {}).get("unit_of_measurement")
                out[entity_id] = to_series(self._numeric(states, unit))
        return out

    def latest(self, points: Sequence[str]) -> Dict[str, Reading]:
        out: Dict[str, Reading] = {}
        for point in points:
            try:
                state = self._get(f"/api/states/{quote(point)}")
            except HomeAssistantError as exc:
                logger.warning("No state for %s: %s", point, exc)
                continue
            rows = [r for r in self._numeric([state], (state.get("attributes") or {}).get("unit_of_measurement")) if r[1] == r[1]]
            if rows:
                ts, value = rows[0]
                out[point] = Reading(point, value, ts, (state.get("attributes") or {}).get("unit_of_measurement"))
        return out

    @staticmethod
    def _numeric(states: list, unit: Optional[str]) -> List[tuple]:
        rows = []
        for state in states:
            raw = state.get("state")
            stamp = state.get("last_changed") or state.get("last_updated")
            if stamp is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = float("nan")  # unavailable / unknown: ends the previous value
            ts = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            rows.append((ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc), normalize_unit(value, unit)))
        return rows


__all__ = ["InMemorySource", "HomeAssistantSource", "HomeAssistantError"]
