# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

import copy
import csv
import io
import json

import pytest

from hvx.reporting import ReportBuilder, ReportConfig, render
from hvx.reporting.aggregate import group_category
from hvx.reporting.frames import climate_frame, room_frame
from hvx.reporting.model import SCHEMA_VERSION
from hvx.simulations.models.reporting import HTMLReportService
from tests.conftest import make_portfolio

FAST = dict(parallel_backend="serial", include_simulations=False)


def _snapshot(rooms):
    return {k: (list(r.timestamps), copy.deepcopy(r.timeseries_data), dict(r.computed_metrics), dict(r.metadata)) for k, r in rooms.items()}


def test_report_does_not_mutate_inputs(portfolio):
    p, b, f, r = portfolio
    before = _snapshot(r)
    ReportBuilder(ReportConfig(parallel_backend="serial")).build(p, b, f, r)
    assert _snapshot(r) == before


def test_room_results_are_consistent_with_en16798(portfolio):
    report = ReportBuilder(ReportConfig(**FAST)).build(*portfolio)
    assert report.schema_version == SCHEMA_VERSION
    analysed = [r for r in report.rooms if r.analysed]
    assert len(analysed) == 6
    for room in analysed:
        assert room.achieved_category in {"I", "II", "III", "IV", None}
        assert set(room.compliance) == {"temperature", "co2", "humidity"}
        assert 0 <= room.ieq_score <= 100
        # target compliance comes from the same EN 16798 run as the category
        en = room.assessments[0]
        assert room.compliance["co2"] == pytest.approx(en["parameters"]["co2"]["compliance_pct"], abs=0.05)
    # Room r2 has the worst CO2 by construction
    by_name = {r.room_name: r for r in analysed}
    assert by_name["Room 0.0.2"].compliance["co2"] < by_name["Room 0.0.0"].compliance["co2"]
    assert any("CO₂" in issue for issue in by_name["Room 0.0.2"].issues)


def test_full_year_assesses_each_season_separately():
    p, b, f, r = make_portfolio(n_buildings=1, n_rooms=1, start="2025-01-01", days=365, freq="1h", summer_overheating=4.0)
    room = next(iter(r.values()))
    report = ReportBuilder(ReportConfig(seasons=("winter", "summer"), **FAST)).build(p, b, f, r)
    result = report.rooms[0]
    seasons = {s.season: s for s in result.seasons}
    assert set(seasons) == {"winter", "summer"}
    # DK heating/cooling months partition the year: each sample lands in exactly one season.
    assert seasons["winter"].samples + seasons["summer"].samples == len(room.timestamps)
    assert seasons["summer"].period_start.startswith("2025-05")
    # Summer (+4 °C) must assess differently from winter (no stale cache reuse)...
    assert seasons["winter"].achieved_category != seasons["summer"].achieved_category
    # ...and the room's category is the worse of the two.
    assert result.achieved_category == max(seasons["winter"].achieved_category, seasons["summer"].achieved_category, key=["I", "II", "III", "IV"].index)
    assert result.parameters["temperature"].maximum > 27


def test_rooms_without_data_and_failures_are_isolated(portfolio, monkeypatch):
    p, b, f, r = portfolio
    r["b1_f0_r2"].timeseries_data = {}
    r["b1_f0_r1"].timestamps = ["not a date"] * len(r["b1_f0_r1"].timestamps)

    report = ReportBuilder(ReportConfig(**FAST)).build(p, b, f, r)
    status = {x.room_id: x.status for x in report.rooms}
    assert status["b1_f0_r2"] == "no_data"
    assert status["b1_f0_r1"] == "no_data"
    assert report.summary.rooms_total == 6
    assert report.summary.rooms_analysed == 4
    assert report.summary.coverage_pct == pytest.approx(66.7)


def test_error_in_one_room_does_not_abort(portfolio, monkeypatch):
    import hvx.reporting.analysis as analysis
    original = analysis._combine

    def flaky(report, *args, **kwargs):
        if report.room_id == "b0_f0_r1":
            raise RuntimeError("boom")
        return original(report, *args, **kwargs)

    monkeypatch.setattr(analysis, "_combine", flaky)
    report = ReportBuilder(ReportConfig(**FAST)).build(*portfolio)
    bad = report.room("b0_f0_r1")
    assert bad.status == "error" and "boom" in bad.message
    assert report.summary.rooms_failed == 1 and report.summary.rooms_analysed == 5
    assert any("boom" in w for w in report.warnings)


def test_parallel_matches_serial(portfolio):
    serial = ReportBuilder(ReportConfig(**FAST)).build(*portfolio)
    threaded = ReportBuilder(ReportConfig(parallel_backend="thread", max_workers=3, include_simulations=False)).build(*portfolio)
    key = lambda rep: [(r.room_id, r.achieved_category, r.ieq_score, r.compliance) for r in rep.rooms]  # noqa: E731
    assert key(serial) == key(threaded)


def test_process_pool(portfolio):
    report = ReportBuilder(ReportConfig(parallel_backend="process", max_workers=2, include_simulations=False)).build(*portfolio)
    assert report.summary.rooms_analysed == 6


def test_progress_callback(portfolio):
    calls = []
    ReportBuilder(ReportConfig(**FAST), progress=lambda done, total: calls.append((done, total))).build(*portfolio)
    assert calls[-1] == (6, 6) and len(calls) == 6


def test_building_filter_and_aggregation(portfolio):
    report = ReportBuilder(ReportConfig(**FAST)).build(*portfolio, building_ids=["b1"])
    assert [b.building_id for b in report.buildings] == ["b1"]
    assert {r.building_id for r in report.rooms} == {"b1"}
    building = report.buildings[0]
    assert building.summary.rooms_total == 3
    assert len(building.floors) == 1
    assert sum(building.summary.category_counts.values()) == 3


def test_group_category_threshold():
    assert group_category({"I": 7, "II": 3}, 0.7) == "I"
    assert group_category({"I": 6, "II": 4}, 0.7) == "II"
    assert group_category({"III": 1, "IV": 1}, 0.7) == "IV"
    assert group_category({}, 0.7) is None


def test_actions_are_grouped_across_rooms(portfolio):
    report = ReportBuilder(ReportConfig(parallel_backend="serial")).build(*portfolio)
    titles = [a.title for a in report.actions]
    assert len(titles) == len(set(titles))
    for action in report.actions:
        assert not any(name in action.title for name in action.room_names)


def test_climate_is_aligned_by_timestamp_not_position():
    stamps = [t.isoformat() for t in __import__("pandas").date_range("2025-01-01", periods=8, freq="15min")]
    hourly = {"outdoor_temperature": {"timestamps": ["2025-01-01T00:00:00", "2025-01-01T01:00:00", "2025-01-01T02:00:00"], "values": [1.0, 2.0, 3.0]}}
    ts = {"temperature": [21.0] * 8, "outdoor_temperature": [1.0, 2.0, 3.0]}
    df, warnings = room_frame(ts, stamps, climate_frame(hourly))
    out = df["outdoor_temperature"]
    # nearest hourly value per 15-min sample (positional truncation would give 1, 2, 3, NaN...)
    assert out.iloc[0] == 1.0 and out.iloc[1] == 1.0 and out.iloc[4] == 2.0 and out.iloc[7] == 3.0
    df2, warnings2 = room_frame(ts, stamps, None)
    assert "outdoor_temperature" not in df2.columns and any("ignored" in w for w in warnings2)


def test_renderers(portfolio):
    p, b, f, r = portfolio
    r["b0_f0_r0"].name = "<script>alert('x')</script>"
    report = ReportBuilder(ReportConfig(parallel_backend="serial")).build(p, b, f, r)

    html = render(report, "html")
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "cdn." not in html  # self-contained
    assert "Rooms needing attention" in html

    data = json.loads(render(report, "json"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["rooms"]) == 6 and "room_count" in data["actions"][0]

    rows = list(csv.DictReader(io.StringIO(render(report, "csv"))))
    assert len(rows) == 6 and rows[0]["brick_class"].startswith(("brick:", "ieq:"))

    with pytest.raises(ValueError):
        render(report, "pdf")


def test_legacy_html_service(tmp_path, portfolio):
    p, b, f, r = portfolio
    service = HTMLReportService(season="winter", analyze_full_year=True, parallel_backend="serial", include_simulations=False)
    assert service.seasons == ["winter", "summer"]
    out = service.generate_report(p, b, f, r, tmp_path / "r.html")
    assert out.exists() and "Test Portfolio" in out.read_text(encoding="utf-8")


def test_config_validation():
    with pytest.raises(ValueError):
        ReportConfig(seasons=("spring",))
    with pytest.raises(ValueError):
        ReportConfig(target_category="V")
    assert ReportConfig.from_legacy(season="heating").seasons == ("winter",)
    assert ReportConfig(parallel_backend="auto", parallel_threshold=10, max_workers=4).resolve_workers(100) == ("process", 4)
    assert ReportConfig(parallel_backend="auto").resolve_workers(3)[0] == "serial"


def test_room_standards_cache_is_per_season(portfolio):
    """Regression: a second compute_standards call with another season returned the first season's result."""
    room = portfolio[3]["b0_f0_r0"]
    winter = room.compute_standards(country="DK", building_type="office", season="winter")
    summer = room.compute_standards(country="DK", building_type="office", season="summer")
    assert winter["en16798_1"]["season"] == "winter"
    assert summer["en16798_1"]["season"] == "summer"
    assert room.compute_standards(country="DK", building_type="office", season="winter") is winter
