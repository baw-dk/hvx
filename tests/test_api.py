# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import hvx.app.api as api  # noqa: E402
from tests.conftest import make_portfolio  # noqa: E402


@pytest.fixture
def client():
    p, b, f, r = make_portfolio(n_buildings=1, n_rooms=2)
    store = api._store
    store.portfolio, store.buildings, store.floors, store.rooms = p, b, f, r
    yield TestClient(api.app)
    store.portfolio, store.buildings, store.floors, store.rooms = None, {}, {}, {}


def test_report_json(client):
    res = client.post("/api/reports", json={"format": "json", "seasons": ["heating"], "include_simulations": False})
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["rooms_analysed"] == 2 and data["config"]["seasons"] == ["winter"]


def test_report_html_and_csv(client):
    html = client.post("/api/reports", json={"format": "html", "include_simulations": False})
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
    csv = client.post("/api/reports", json={"format": "csv", "include_simulations": False})
    assert csv.status_code == 200 and csv.text.count("\n") == 3
    assert "attachment" in csv.headers["content-disposition"]


def test_report_validation(client):
    assert client.post("/api/reports", json={"format": "docx"}).status_code == 422
    assert client.post("/api/reports", json={"seasons": ["spring"]}).status_code == 422


def test_brick_export_and_import(client):
    pytest.importorskip("rdflib")
    res = client.get("/api/semantics/brick", params={"with_assessments": True})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/turtle")
    assert "ieq:IEQAssessment" in res.text and "brick:CO2_Level_Sensor" in res.text
    imported = client.post("/api/semantics/brick/import", files={"file": ("model.ttl", res.content, "text/turtle")})
    assert imported.status_code == 200
    assert imported.json()["rooms"] == 2 and imported.json()["sensors"] == 6


def test_report_requires_portfolio():
    api._store.portfolio = None
    assert TestClient(api.app).post("/api/reports", json={}).status_code == 400
