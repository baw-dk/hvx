# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""ChirpStack integration: event parsing, MQTT (real broker), gRPC metrics (real server), webhook."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from concurrent import futures
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("chirpstack_api")
from chirpstack_api import api, common, integration  # noqa: E402
from google.protobuf import json_format  # noqa: E402

from hvx.live import LiveMonitor, load_site  # noqa: E402
from hvx.live.chirpstack import (  # noqa: E402
    ChirpStackAPISource,
    ChirpStackMQTTSource,
    decode_event,
    device_points,
    handle_http_event,
    parse_uplink,
)
from hvx.live.sources import InMemorySource  # noqa: E402

NOW = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
ELSYS = "a81758fffe0312aa"
DRAGINO = "a84041000181c061"


def uplink(dev_eui: str, obj: dict, ts: datetime, name: str = "sensor") -> integration.UplinkEvent:
    """An UplinkEvent exactly as ChirpStack builds it (protobuf), decoded object included."""
    event = integration.UplinkEvent(
        deduplication_id="2d1f9c1e-0000-4000-8000-000000000001",
        device_info=integration.DeviceInfo(
            tenant_name="ChirpStack", application_id="app-1", application_name="IEQ",
            device_profile_name="Elsys ERS CO2", device_name=name, dev_eui=dev_eui, tags={"room": "r-101"},
        ),
        f_cnt=42, f_port=5, data=b"\x01\x00\xe2",
    )
    event.time.FromDatetime(ts)
    event.object.update(obj)
    return event


def as_json(event: integration.UplinkEvent) -> bytes:
    return json_format.MessageToJson(event).encode()  # ChirpStack's JSON encoding (protobuf JSON mapping)


def test_parse_uplink_json_shape_and_aliases():
    event = uplink(DRAGINO, {"TempC_SHT": 22.4, "Hum_SHT": 41.0, "BatV": 3.05, "Ext_sensor": "Temperature Sensor", "nested": {"co2": 812}}, NOW)
    data = decode_event(as_json(event))
    assert data["deviceInfo"]["devEui"] == DRAGINO and "object" in data and data["time"].endswith("Z")
    readings = {p: v for p, v, _ in parse_uplink(data)}
    assert readings[f"{DRAGINO}/TempC_SHT"] == pytest.approx(22.4)
    assert readings[f"{DRAGINO}/temperature"] == pytest.approx(22.4)  # canonical alias
    assert readings[f"{DRAGINO}/humidity"] == pytest.approx(41.0)
    assert readings[f"{DRAGINO}/nested.co2"] == 812 and readings[f"{DRAGINO}/co2"] == 812
    assert f"{DRAGINO}/Ext_sensor" not in readings  # strings are not measurements
    assert {ts for _, _, ts in parse_uplink(data)} == {NOW}


def test_protobuf_encoding_and_events_without_codec():
    event = uplink(ELSYS, {"co2": 950, "temperature": 21.0}, NOW)
    data = decode_event(event.SerializeToString(), "application/octet-stream")
    assert {p for p, _, _ in parse_uplink(data)} == {f"{ELSYS}/co2", f"{ELSYS}/temperature"}
    raw_only = integration.UplinkEvent(device_info=integration.DeviceInfo(dev_eui=ELSYS), data=b"\x01")
    assert parse_uplink(json_format.MessageToDict(raw_only)) == []


def test_http_event_handler_ignores_non_uplinks():
    source = InMemorySource()
    assert handle_http_event(source, "join", b"{}") == 0
    assert handle_http_event(source, "up", as_json(uplink(ELSYS, {"co2": 700}, NOW))) == 1
    assert list(source.history([f"{ELSYS}/co2"], NOW - timedelta(minutes=1), NOW)[f"{ELSYS}/co2"]) == [700.0]


def test_device_points_validation():
    assert device_points(ELSYS.upper())["co2"] == f"{ELSYS}/co2"
    with pytest.raises(ValueError):
        device_points("not-a-eui")


# --- real MQTT broker ---------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mqtt_broker():
    amqtt_broker = pytest.importorskip("amqtt.broker")
    port = _free_port()
    loop = asyncio.new_event_loop()
    config = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}}, "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}}
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    async def start():
        # Create the broker inside the loop that runs it: on Python 3.10 a broker built
        # outside its loop mixes futures from two loops and drops messages.
        broker = amqtt_broker.Broker(config)
        await broker.start()
        return broker

    try:
        broker = asyncio.run_coroutine_threadsafe(start(), loop).result(10)
    except Exception as exc:  # pragma: no cover - broker API drift
        loop.call_soon_threadsafe(loop.stop)
        pytest.skip(f"amqtt broker unavailable: {exc}")
    yield port
    asyncio.run_coroutine_threadsafe(broker.shutdown(), loop).result(10)
    loop.call_soon_threadsafe(loop.stop)


def test_mqtt_source_with_real_broker(mqtt_broker):
    import paho.mqtt.client as mqtt

    source = ChirpStackMQTTSource("127.0.0.1", mqtt_broker, application_id="app-1").start()
    try:
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        pub.connect("127.0.0.1", mqtt_broker)
        pub.loop_start()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for i in range(3):
            topic = f"application/app-1/device/{ELSYS}/event/up"
            pub.publish(topic, as_json(uplink(ELSYS, {"co2": 600 + 100 * i, "temperature": 21.5}, now - timedelta(minutes=10 * (2 - i)))), qos=1).wait_for_publish(5)
        pub.publish(f"application/other-app/device/{DRAGINO}/event/up", as_json(uplink(DRAGINO, {"co2": 5000}, now)), qos=1).wait_for_publish(5)
        pub.publish(f"application/app-1/device/{ELSYS}/event/up", b"not json {", qos=1).wait_for_publish(5)
        deadline = time.time() + 10
        while source.messages + source.errors < 4 and time.time() < deadline:
            time.sleep(0.05)
        pub.loop_stop()
        pub.disconnect()
    finally:
        source.close()
    history = source.history([f"{ELSYS}/co2", f"{DRAGINO}/co2"], now - timedelta(hours=1), now + timedelta(minutes=1))
    assert list(history[f"{ELSYS}/co2"]) == [600.0, 700.0, 800.0]
    assert f"{DRAGINO}/co2" not in history  # other application filtered by topic
    assert source.errors == 1
    assert source.devices[ELSYS]["deviceName"] == "sensor" and "co2" in source.devices[ELSYS]["fields"]


# --- real gRPC server ----------------------------------------------------------------


class FakeDeviceService(api.DeviceServiceServicer):
    def __init__(self):
        self.calls = []

    def GetMetrics(self, request, context):  # noqa: N802 - gRPC method name
        token = dict(context.invocation_metadata()).get("authorization")
        if token != "Bearer secret":
            import grpc

            context.abort(grpc.StatusCode.UNAUTHENTICATED, "bad token")
        self.calls.append((request.dev_eui, common.Aggregation.Name(request.aggregation)))
        start = request.start.ToDatetime(tzinfo=timezone.utc)
        hours = int((request.end.ToDatetime(tzinfo=timezone.utc) - start).total_seconds() // 3600)
        metric = common.Metric(name="CO2", kind=common.MetricKind.GAUGE)
        for h in range(hours):
            metric.timestamps.add().FromDatetime(start + timedelta(hours=h))
        metric.datasets.add(label="co2", data=[700.0 + h for h in range(hours)])
        response = api.GetDeviceMetricsResponse()
        response.metrics["co2"].CopyFrom(metric)
        return response


@pytest.fixture
def grpc_server():
    grpc = pytest.importorskip("grpc")
    servicer = FakeDeviceService()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    api.add_DeviceServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield f"127.0.0.1:{port}", servicer
    server.stop(0)


def test_api_source_reads_device_metrics(grpc_server):
    address, servicer = grpc_server
    source = ChirpStackAPISource(address, "secret")
    history = source.history([f"{ELSYS}/co2", f"{ELSYS}/humidity"], NOW - timedelta(hours=6), NOW)
    source.close()
    assert servicer.calls == [(ELSYS, "HOUR")]
    assert list(history) == [f"{ELSYS}/co2"] and len(history[f"{ELSYS}/co2"]) == 6
    with pytest.raises(Exception, match="bad token"):
        ChirpStackAPISource(address, "wrong").history([f"{ELSYS}/co2"], NOW - timedelta(hours=1), NOW)


def test_mqtt_backfill_from_api_then_live(grpc_server):
    address, servicer = grpc_server
    source = ChirpStackMQTTSource(backfill=ChirpStackAPISource(address, "secret"))
    source.ingest(as_json(uplink(ELSYS, {"co2": 1500}, NOW)))
    first = source.history([f"{ELSYS}/co2"], NOW - timedelta(hours=4), NOW)[f"{ELSYS}/co2"]
    assert len(first) == 5 and first.iloc[-1] == 1500.0  # 4 hourly backfilled + 1 live
    source.history([f"{ELSYS}/co2"], NOW - timedelta(hours=4), NOW)
    assert len(servicer.calls) == 1  # backfill happens once per point


# --- site files, monitor, webhook ---------------------------------------------------

SITE = {
    "name": "LoRaWAN office",
    "country": "DK",
    "timezone": "Europe/Copenhagen",
    "sources": {"lorawan": {"type": "chirpstack-http"}},
    "buildings": [{"id": "hq", "name": "HQ", "building_type": "office", "floors": [{"id": "f0", "name": "Ground", "rooms": [
        {"id": "r-101", "name": "Meeting 1.01", "devices": [{"source": "lorawan", "dev_eui": ELSYS}]},
        {"id": "r-102", "name": "Office 1.02", "devices": [{"source": "lorawan", "dev_eui": DRAGINO, "parameters": ["temperature", "humidity"]}]},
    ]}]}],
}


def test_site_devices_bind_and_monitor():
    site = load_site(SITE)
    source = site.build_sources()["lorawan"]
    assert {(b.room_id, b.parameter) for b in __import__("hvx.live", fromlist=["discover_bindings"]).discover_bindings(site.rooms.values())} == {
        ("r-101", "temperature"), ("r-101", "co2"), ("r-101", "humidity"), ("r-102", "temperature"), ("r-102", "humidity"),
    }
    for minutes in range(0, 240, 10):  # 4 h of 10-minute uplinks
        ts = NOW - timedelta(minutes=240 - minutes)
        handle_http_event(source, "up", as_json(uplink(ELSYS, {"temperature": 22.0, "humidity": 40, "co2": 1500}, ts)))
        handle_http_event(source, "up", as_json(uplink(DRAGINO, {"TempC_SHT": 21.5, "Hum_SHT": 45}, ts)))
    monitor = LiveMonitor(*site.entities, sources=site.build_sources({"lorawan": source}), window=timedelta(days=1), timezone=site.timezone)
    monitor.refresh(now=NOW)
    snap = monitor.snapshot(now=NOW)
    assert snap.rooms["r-101"].current["co2"].status == "high" and snap.rooms["r-101"].category_now == "III"
    assert snap.rooms["r-102"].category_now in ("I", "II") and not snap.rooms["r-102"].alerts
    assert snap.rooms["r-101"].window.compliance["co2"] == 0.0


def test_webhook_endpoint(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import hvx.app.api as app_api

    client = TestClient(app_api.app)
    monkeypatch.delenv("HVX_WEBHOOK_TOKEN", raising=False)
    assert client.post("/api/live/site", json=SITE).status_code == 200
    body = as_json(uplink(ELSYS, {"co2": 1300, "temperature": 22, "humidity": 40}, datetime.now(timezone.utc)))
    assert client.post("/api/integrations/chirpstack?event=up", content=body).status_code == 503  # no token configured

    monkeypatch.setenv("HVX_WEBHOOK_TOKEN", "s3cret")
    assert client.post("/api/integrations/chirpstack?event=up", content=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.post("/api/integrations/chirpstack?event=up", content=body, headers={"Authorization": "Bearer s3cret", "Content-Type": "application/json"})
    assert ok.status_code == 200 and ok.json()["readings"] == 3
    proto = client.post(
        "/api/integrations/chirpstack?event=up",
        content=uplink(DRAGINO, {"TempC_SHT": 21.0}, datetime.now(timezone.utc)).SerializeToString(),
        headers={"Authorization": "Bearer s3cret", "Content-Type": "application/octet-stream"},
    )
    assert proto.status_code == 200 and proto.json()["readings"] == 2
    status = client.post("/api/integrations/chirpstack?event=status", content=b"{}", headers={"Authorization": "Bearer s3cret"})
    assert status.json()["readings"] == 0

    snap = client.get("/api/live/snapshot").json()
    assert snap["rooms"]["r-101"]["current"]["co2"]["value"] == 1300.0
    assert any("co2" in a for a in snap["alerts"])
    report = client.post("/api/live/report", json={"format": "json", "include_simulations": False})
    assert report.status_code == 200 and report.json()["portfolio_name"] == "LoRaWAN office"
