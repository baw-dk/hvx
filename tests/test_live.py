# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import yaml
from click.testing import CliRunner

from hvx.cli import cli
from hvx.live import (
    HomeAssistantError,
    HomeAssistantSource,
    InMemorySource,
    LiveMonitor,
    category_now,
    discover_bindings,
    en16798_limits,
    load_site,
)
from tests.fake_homeassistant import TOKEN, FakeHomeAssistant

NOW = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

SITE = {
    "name": "Live Test Site",
    "country": "DK",
    "timezone": "Europe/Copenhagen",
    "sources": {"default": {"type": "homeassistant", "url": "http://placeholder", "token_env": "HVX_TEST_TOKEN"}},
    "buildings": [
        {
            "id": "hq",
            "name": "HQ",
            "building_type": "office",
            "floors": [
                {
                    "id": "hq-0",
                    "name": "Ground",
                    "floor_number": 0,
                    "rooms": [
                        {"id": "good", "name": "Good room", "room_type": "open_office", "area_m2": 30,
                         "sensors": {"temperature": "sensor.good_t", "co2": "sensor.good_co2", "humidity": "sensor.good_rh"}},
                        {"id": "stuffy", "name": "Stuffy room", "room_type": "meeting_room", "area_m2": 15,
                         "requirements": {"target_category": "II", "co2_max_ppm": 1000},
                         "sensors": {"temperature": "sensor.stuffy_t", "co2": "sensor.stuffy_co2", "humidity": "sensor.stuffy_rh"}},
                    ],
                }
            ],
        }
    ],
}


def _history(days: int = 3, freq: str = "10min"):
    """Synthetic sensor traces ending at NOW; the stuffy room peaks above 1500 ppm while occupied."""
    idx = pd.date_range(NOW - timedelta(days=days), NOW, freq=freq, tz="UTC")
    hour = idx.tz_convert("Europe/Copenhagen").hour.to_numpy()
    occupied = ((hour >= 8) & (hour < 17)).astype(float)
    rng = np.random.default_rng(1)
    return idx, {
        "sensor.good_t": 22 + rng.normal(0, 0.3, len(idx)),
        "sensor.good_co2": 450 + occupied * 300 + rng.normal(0, 20, len(idx)),
        "sensor.good_rh": 40 + rng.normal(0, 2, len(idx)),
        "sensor.stuffy_t": 71.6 + rng.normal(0, 0.5, len(idx)),  # reported in °F (= 22 °C)
        "sensor.stuffy_co2": 500 + occupied * 1100 + rng.normal(0, 30, len(idx)),
        "sensor.stuffy_rh": 45 + rng.normal(0, 2, len(idx)),
    }


@pytest.fixture
def fake_ha():
    idx, data = _history()
    with FakeHomeAssistant() as ha:
        for entity, values in data.items():
            ha.states[entity] = [(t.to_pydatetime(), f"{v:.2f}") for t, v in zip(idx, values)]
            ha.units[entity] = "ppm" if "co2" in entity else "%" if "rh" in entity else "°C"
        ha.units["sensor.stuffy_t"] = "°F"
        # an "unavailable" blip two hours before NOW
        blip = ha.states["sensor.good_rh"][-12][0] + timedelta(seconds=1)
        ha.states["sensor.good_rh"].insert(-11, (blip, "unavailable"))
        yield ha


def test_limits_come_from_en16798_config():
    winter = en16798_limits("winter")
    assert winter.bounds("II", "temperature") == (20.0, 24.0)
    assert winter.bounds("II", "co2") == (None, 1200)
    assert en16798_limits("summer").bounds("II", "temperature") == (23.0, 26.0)
    assert category_now({"temperature": 22.0, "co2": 800, "humidity": 40}, winter) == "I"
    assert category_now({"temperature": 22.0, "co2": 1100, "humidity": 40}, winter) == "II"
    assert category_now({"temperature": 30.0}, winter) is None


def test_home_assistant_source(fake_ha):
    source = HomeAssistantSource(fake_ha.url, TOKEN, chunk_size=4)
    assert source.check() == "API running."
    points = list(_history()[1])
    history = source.history(points, NOW - timedelta(days=1), NOW)
    assert set(history) == set(points)
    assert history["sensor.stuffy_t"].mean() == pytest.approx(22.0, abs=0.2)  # °F converted
    rh = history["sensor.good_rh"]
    assert rh.isna().sum() == 1 and rh.iloc[-1] == rh.iloc[-1]  # "unavailable" kept as an explicit gap marker
    assert sum("/api/history/period/" in r for r in fake_ha.requests) == 2  # chunked
    latest = source.latest(["sensor.good_co2", "sensor.missing"])
    assert set(latest) == {"sensor.good_co2"}
    with pytest.raises(HomeAssistantError, match="401"):
        HomeAssistantSource(fake_ha.url, "wrong").check()


def test_site_file_binds_points():
    site = load_site(SITE)
    bindings = discover_bindings(site.rooms.values())
    assert len(bindings) == 6
    assert {(b.room_id, b.parameter) for b in bindings} >= {("stuffy", "co2"), ("good", "temperature")}
    assert site.rooms["stuffy"].ieq_requirements.co2_max_ppm == 1000
    assert site.rooms["good"].semantic_brick_class() == "brick:Open_Office"


def test_monitor_end_to_end_with_home_assistant(fake_ha):
    site = load_site(SITE)
    source = HomeAssistantSource(fake_ha.url, TOKEN)
    monitor = LiveMonitor(*site.entities, sources=source, window=timedelta(days=2), timezone=site.timezone)
    added = monitor.refresh(now=NOW)
    assert added > 1000
    before = len(fake_ha.requests)
    assert monitor.refresh(now=NOW) <= 6  # incremental: only the newest sample(s) again
    assert len(fake_ha.requests) == before + 1

    snap = monitor.snapshot(now=NOW)
    assert snap.season == "winter"
    good, stuffy = snap.rooms["good"], snap.rooms["stuffy"]
    assert good.current["temperature"].status == "ok" and good.category_now in ("I", "II")
    # NOW = 13:00 local, occupied: stuffy CO2 ≈ 1600 ppm > its own 1000 ppm requirement
    assert stuffy.current["co2"].status == "high"
    assert any("co2" in a and "1000" in a for a in stuffy.alerts)
    assert stuffy.window.compliance["co2"] < good.window.compliance["co2"]
    assert snap.summary.rooms_analysed == 2

    rep = monitor.report()
    assert {r.room_id for r in rep.rooms} == {"good", "stuffy"}
    # window rooms are copies: the configured entities stay empty
    assert not site.rooms["good"].timeseries_data


def test_memory_source_and_staleness():
    site = load_site({**SITE, "sources": {}})
    source = InMemorySource()
    idx, data = _history(days=1)
    for point, values in data.items():
        if point.startswith("sensor.good"):
            source.extend(point, pd.Series(values, index=idx))
    monitor = LiveMonitor(*site.entities, sources=source, window=timedelta(days=1), timezone="Europe/Copenhagen")
    monitor.refresh(now=NOW + timedelta(hours=3))
    snap = monitor.snapshot(now=NOW + timedelta(hours=3))
    assert snap.rooms["good"].current["co2"].stale
    assert snap.rooms["stuffy"].current["co2"].status == "missing"
    assert snap.rooms["stuffy"].window.status == "no_data"


def test_dead_source_does_not_break_refresh():
    class Broken(InMemorySource):
        def history(self, *a, **k):
            raise ConnectionError("down")

    site = load_site({**SITE, "sources": {}})
    monitor = LiveMonitor(*site.entities, sources=Broken(), window=timedelta(days=1))
    assert monitor.refresh(now=NOW) == 0


def test_unknown_source_in_bindings_is_rejected():
    site = load_site({**SITE, "sources": {}})
    with pytest.raises(ValueError, match="unknown source"):
        LiveMonitor(*site.entities, sources={"other": InMemorySource()})


def test_cli_report_watch_check(fake_ha, tmp_path, monkeypatch):
    monkeypatch.setenv("HVX_TEST_TOKEN", TOKEN)
    site = {**SITE, "sources": {"default": {**SITE["sources"]["default"], "url": fake_ha.url}}}
    site_file = tmp_path / "site.yaml"
    site_file.write_text(yaml.safe_dump(site), encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(cli, ["check", "--site", str(site_file)])
    assert result.exit_code == 0, result.output
    assert "✓ sensor.stuffy_co2" in result.output

    out = tmp_path / "report.html"
    result = runner.invoke(cli, ["report", "--site", str(site_file), "--days", "400", "-o", str(out), "--no-simulations"])
    assert result.exit_code == 0, result.output
    assert out.exists() and "Live Test Site" in out.read_text(encoding="utf-8")

    result = runner.invoke(cli, ["watch", "--site", str(site_file), "--once", "--days", "400"])
    assert result.exit_code == 0, result.output
    assert "Stuffy room" in result.output

    result = runner.invoke(cli, ["report", "-o", str(out)])
    assert result.exit_code != 0 and "exactly one" in result.output


def test_cli_site_from_ifc(tmp_path, ifc_file):
    path, guid = ifc_file
    out = tmp_path / "site.yaml"
    result = CliRunner().invoke(cli, ["site", "from-ifc", str(path), "-o", str(out)])
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    room = data["buildings"][0]["floors"][1]["rooms"][0]
    assert room["ifc_guid"] == guid and room["sensors"] == {"temperature": None, "co2": None, "humidity": None}
    # the skeleton loads back as a site
    assert load_site(data).rooms[guid].ieq_requirements.target_category.value == "I"


def test_cli_version():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0 and "hvx" in result.output


def test_change_driven_values_are_held_until_next_change():
    """Home Assistant stores states on change only: a constant sensor has one sample, which stays valid."""
    site = load_site({**SITE, "sources": {}})
    source = InMemorySource(hold_values=True)
    start = NOW - timedelta(hours=8)
    for p, v in (("sensor.good_t", 22.0), ("sensor.good_co2", 600.0), ("sensor.good_rh", 40.0)):
        source.push(p, v, start)  # one sample each, 8 h ago
    source.push("sensor.stuffy_t", 22.0, start)
    source.push("sensor.stuffy_t", float("nan"), NOW - timedelta(hours=1))  # went unavailable
    monitor = LiveMonitor(*site.entities, sources=source, window=timedelta(days=1), timezone="Europe/Copenhagen")
    monitor.refresh(now=NOW)
    window = monitor.window_rooms(now=NOW)
    good = window["good"]
    assert len(good.timestamps) == 8 * 4 + 1 and all(v == 40.0 for v in good.timeseries_data["humidity"])
    stuffy = window["stuffy"]
    # held at 22 °C until it went unavailable 1 h before NOW; no rows afterwards
    assert set(stuffy.timeseries_data["temperature"]) == {22.0}
    assert stuffy.timestamps[-1] < good.timestamps[-1]
    assert len(good.timestamps) - len(stuffy.timestamps) == 5  # 11:00–12:00 UTC buckets

    snap = monitor.snapshot(now=NOW)
    assert not snap.rooms["good"].current["humidity"].stale  # 8 h unchanged is not stale
    assert snap.rooms["good"].window.compliance == {"temperature": 100.0, "co2": 100.0, "humidity": 100.0}
    assert snap.rooms["stuffy"].current["temperature"].status == "stale"
    assert any("unavailable" in a for a in snap.rooms["stuffy"].alerts)
