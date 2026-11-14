"""
ChirpStack (LoRaWAN network server, v4) as a live source.

Three ways in, all producing points named ``<devEui>/<field>``:

* :class:`ChirpStackMQTTSource` – subscribes to the MQTT integration
  (``application/<app>/device/<devEui>/event/up``). Needs ``paho-mqtt``.
* :class:`ChirpStackAPISource` – reads stored device metrics through the gRPC
  API (``DeviceService.GetMetrics``) for history/backfill. Needs
  ``chirpstack-api``. ChirpStack keeps metrics only for the *measurements*
  configured in the device profile.
* :func:`handle_http_event` – for the HTTP integration (webhook); the FastAPI
  app exposes it at ``POST /api/integrations/chirpstack``.

Field names come from each device's payload codec and differ per vendor
(Elsys ``co2``, Milesight ``co2``, Dragino ``TempC_SHT``...). Every numeric leaf of
the decoded ``object`` becomes ``<devEui>/<path>``; recognised IEQ fields are
*also* published under a canonical name (``<devEui>/temperature``, ``/co2``,
``/humidity``...), so a room can bind a whole device without knowing its codec.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .base import TimeSeriesSource, as_utc, to_series, utcnow
from .sources import InMemorySource

logger = logging.getLogger(__name__)

DEFAULT_TOPIC = "application/{application_id}/device/+/event/up"

# Codec field names seen in common LoRaWAN IEQ sensors -> canonical hvx metric.
# Matching is case-insensitive on the last path component.
FIELD_ALIASES: Dict[str, str] = {
    "temperature": "temperature",
    "temp": "temperature",
    "tempc": "temperature",
    "temperature_c": "temperature",
    "tempc_sht": "temperature",
    "air_temperature": "temperature",
    "airtemperature": "temperature",
    "humidity": "humidity",
    "hum": "humidity",
    "rh": "humidity",
    "relative_humidity": "humidity",
    "hum_sht": "humidity",
    "air_humidity": "humidity",
    "airhumidity": "humidity",
    "co2": "co2",
    "co2_ppm": "co2",
    "carbon_dioxide": "co2",
    "co2level": "co2",
    "light": "illuminance",
    "lux": "illuminance",
    "illuminance": "illuminance",
    "tvoc": "voc",
    "voc": "voc",
    "pm2_5": "pm2_5",
    "pm25": "pm2_5",
    "pm10": "pm10",
    "noise": "noise",
    "sound": "noise",
    "laeq": "noise",
    "sound_level": "noise",
    "occupancy": "occupancy",
    "people_count": "occupancy",
}

_DEV_EUI = re.compile(r"^[0-9a-fA-F]{16}$")


def _flatten(obj: Any, prefix: str = "") -> Iterator[Tuple[str, float]]:
    if isinstance(obj, bool):
        yield prefix, float(obj)
    elif isinstance(obj, (int, float)):
        yield prefix, float(obj)
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            yield from _flatten(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            yield from _flatten(value, f"{prefix}.{i}" if prefix else str(i))
    # strings and nulls are not measurements


def canonical_field(path: str) -> Optional[str]:
    leaf = path.rsplit(".", 1)[-1].lower()
    return FIELD_ALIASES.get(leaf)


def decode_event(payload: Any, content_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Turn a ChirpStack event payload (JSON bytes/str/dict, or Protobuf bytes) into
    the JSON-mapped dict ChirpStack emits (camelCase field names).
    """
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, (bytes, bytearray)):
        is_proto = content_type is not None and "json" not in content_type.lower()
        if not is_proto:
            try:
                return json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                is_proto = True
        if is_proto:
            try:
                from chirpstack_api import integration
                from google.protobuf.json_format import MessageToDict
            except ImportError as exc:
                raise ValueError("Protobuf-encoded ChirpStack events need: pip install 'hvx[chirpstack]'") from exc
            event = integration.UplinkEvent()
            event.ParseFromString(bytes(payload))
            return MessageToDict(event)
    if isinstance(payload, str):
        return json.loads(payload)
    raise ValueError(f"Unsupported ChirpStack payload type {type(payload).__name__}")


def parse_uplink(event: Mapping[str, Any]) -> List[Tuple[str, float, datetime]]:
    """``(point, value, timestamp)`` triples from one uplink event dict."""
    info = event.get("deviceInfo") or {}
    dev_eui = str(info.get("devEui") or "").lower()
    if not dev_eui:
        return []
    obj = event.get("object")
    if not isinstance(obj, Mapping):
        return []  # no codec configured: raw bytes only
    stamp = event.get("time")
    try:
        ts = as_utc(datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))) if stamp else utcnow()
    except ValueError:
        ts = utcnow()
    out: List[Tuple[str, float, datetime]] = []
    canonical_seen: set = set()
    for path, value in _flatten(obj):
        if not path:
            continue
        out.append((f"{dev_eui}/{path}", value, ts))
        canonical = canonical_field(path)
        if canonical and canonical != path and canonical not in canonical_seen:
            canonical_seen.add(canonical)
            out.append((f"{dev_eui}/{canonical}", value, ts))
    return out


def device_points(dev_eui: str, parameters: Sequence[str] = ("temperature", "co2", "humidity")) -> Dict[str, str]:
    """Canonical point ids for binding a whole device to a room."""
    dev = dev_eui.lower()
    if not _DEV_EUI.match(dev):
        raise ValueError(f"Not a LoRaWAN DevEUI (16 hex digits): {dev_eui!r}")
    return {p: f"{dev}/{p}" for p in parameters}


def handle_http_event(
    source: InMemorySource,
    event_type: str,
    body: bytes,
    content_type: Optional[str] = None,
) -> int:
    """Ingest one HTTP-integration delivery (``POST ...?event=up``). Returns readings stored."""
    if event_type != "up":
        return 0  # join, status, ack, log... carry no measurements
    readings = parse_uplink(decode_event(body, content_type))
    for point, value, ts in readings:
        source.push(point, value, ts)
    return len(readings)


class ChirpStackMQTTSource(InMemorySource):
    """
    Subscribe to ChirpStack's MQTT integration and buffer uplinks.

    LoRaWAN devices report periodically, so silence means missing data
    (``hold_values=False``). Optionally backfills history from the gRPC API on
    the first request (``backfill=ChirpStackAPISource(...)``).
    """

    name = "chirpstack-mqtt"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        application_id: str = "+",
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = False,
        topic: Optional[str] = None,
        client_id: Optional[str] = None,
        backfill: Optional["ChirpStackAPISource"] = None,
        keepalive: int = 60,
    ) -> None:
        super().__init__(hold_values=False)
        self.host, self.port, self.tls = host, int(port), tls
        self.topic = topic or DEFAULT_TOPIC.format(application_id=application_id or "+")
        self.username, self.password = username, password
        self.client_id = client_id or "hvx-live"
        self.keepalive = keepalive
        self.backfill = backfill
        self._backfilled: set = set()
        self._client = None
        self._connected = threading.Event()
        self.messages = 0
        self.errors = 0
        self.devices: Dict[str, Dict[str, Any]] = {}  # devEui -> deviceInfo + last fields seen

    # -- MQTT ---------------------------------------------------------------
    def start(self, wait: float = 10.0) -> "ChirpStackMQTTSource":
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise ImportError("ChirpStack MQTT needs paho-mqtt: pip install 'hvx[chirpstack]'") from exc
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        if self.username:
            client.username_pw_set(self.username, self.password)
        if self.tls:
            client.tls_set()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.connect(self.host, self.port, keepalive=self.keepalive)
        client.loop_start()
        self._client = client
        if wait and not self._connected.wait(wait):
            raise ConnectionError(f"No MQTT connection to {self.host}:{self.port} within {wait:g}s")
        return self

    def close(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            self._connected.clear()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.error("MQTT connection refused: %s", reason_code)
            return
        client.subscribe(self.topic, qos=1)
        self._connected.set()
        logger.info("Subscribed to %s on %s:%s", self.topic, self.host, self.port)

    def _on_message(self, client, userdata, message) -> None:
        self.ingest(message.payload, message.topic)

    def ingest(self, payload: Any, topic: Optional[str] = None) -> int:
        """Handle one uplink payload (also usable without a broker, e.g. from a bridge)."""
        try:
            event = decode_event(payload)
            readings = parse_uplink(event)
        except Exception as exc:  # malformed message: count it, keep listening
            self.errors += 1
            logger.warning("Bad ChirpStack message on %s: %s", topic, exc)
            return 0
        self.messages += 1
        info = event.get("deviceInfo") or {}
        if info.get("devEui"):
            entry = self.devices.setdefault(str(info["devEui"]).lower(), {})
            entry.update({k: info.get(k) for k in ("deviceName", "deviceProfileName", "applicationName", "tags")})
            entry["fields"] = sorted({p.split("/", 1)[1] for p, _, _ in readings})
            entry["last_seen"] = readings[0][2].isoformat() if readings else None
        for point, value, ts in readings:
            self.push(point, value, ts)
        return len(readings)

    # -- Source API ---------------------------------------------------------
    def history(self, points: Sequence[str], start: datetime, end: Optional[datetime] = None) -> Dict[str, pd.Series]:
        live = super().history(points, start, end)
        if self.backfill is None:
            return live
        missing = [p for p in points if p not in self._backfilled]
        if missing:
            self._backfilled.update(missing)
            try:
                old = self.backfill.history(missing, start, end)
            except Exception as exc:
                logger.warning("ChirpStack backfill failed: %s", exc)
                old = {}
            for point, series in old.items():
                self.extend(point, series)
            live = super().history(points, start, end)
        return live


class ChirpStackAPISource(TimeSeriesSource):
    """
    Device metrics through ChirpStack's gRPC API (``DeviceService.GetMetrics``).

    ``server`` is ``host:port`` of the ChirpStack API (default port 8080);
    ``token`` an API key from the ChirpStack UI. Aggregation ``HOUR`` (default) or
    ``MINUTE`` (ChirpStack ≥ 4.10).
    """

    name = "chirpstack-api"

    def __init__(self, server: str, token: str, tls: bool = False, aggregation: str = "HOUR", timeout: float = 30.0) -> None:
        if not token:
            raise ValueError("A ChirpStack API token is required")
        self.server, self.token, self.tls = server, token, tls
        self.aggregation = aggregation.upper()
        self.timeout = timeout
        self._channel = None
        self._stub = None

    def _connect(self):
        if self._stub is None:
            try:
                import grpc
                from chirpstack_api import api
            except ImportError as exc:
                raise ImportError("ChirpStack API needs chirpstack-api: pip install 'hvx[chirpstack]'") from exc
            self._channel = (
                grpc.secure_channel(self.server, grpc.ssl_channel_credentials()) if self.tls else grpc.insecure_channel(self.server)
            )
            self._stub = api.DeviceServiceStub(self._channel)
        return self._stub

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = self._stub = None

    def history(self, points: Sequence[str], start: datetime, end: Optional[datetime] = None) -> Dict[str, pd.Series]:
        from chirpstack_api import api, common
        from google.protobuf.timestamp_pb2 import Timestamp

        stub = self._connect()
        start, end = as_utc(start), as_utc(end or utcnow())
        by_device: Dict[str, set] = {}
        for point in points:
            dev, _, field = point.partition("/")
            if dev and field:
                by_device.setdefault(dev.lower(), set()).add(field)
        ts_start, ts_end = Timestamp(), Timestamp()
        ts_start.FromDatetime(start)
        ts_end.FromDatetime(end)
        out: Dict[str, pd.Series] = {}
        for dev, fields in by_device.items():
            request = api.GetDeviceMetricsRequest(
                dev_eui=dev, start=ts_start, end=ts_end, aggregation=common.Aggregation.Value(self.aggregation)
            )
            response = stub.GetMetrics(request, metadata=[("authorization", f"Bearer {self.token}")], timeout=self.timeout)
            for key, metric in response.metrics.items():
                if not metric.datasets:
                    continue
                stamps = [t.ToDatetime(tzinfo=timezone.utc) for t in metric.timestamps]
                series = to_series(zip(stamps, metric.datasets[0].data))
                for name in {key, canonical_field(key) or key}:
                    if name in fields:
                        out[f"{dev}/{name}"] = series
        return out


__all__ = [
    "ChirpStackMQTTSource",
    "ChirpStackAPISource",
    "FIELD_ALIASES",
    "canonical_field",
    "decode_event",
    "device_points",
    "handle_http_event",
    "parse_uplink",
]
