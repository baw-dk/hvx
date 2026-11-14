# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""MCP server: tool functions on synthetic data, and a real stdio session."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

pytest.importorskip("mcp")

import hvx.mcp_server as srv  # noqa: E402
from tests.conftest import make_portfolio  # noqa: E402


@pytest.fixture
def loaded():
    srv._session.entities = make_portfolio(n_buildings=2, n_rooms=3)
    srv._session.source = "synthetic"
    yield
    srv._session.entities = None
    srv._session.reports.clear()


def test_requires_data():
    srv._session.entities = None
    with pytest.raises(ValueError, match="No data loaded"):
        srv.build_report()


def test_build_and_export(loaded, tmp_path):
    info = srv.describe_data()
    assert info["rooms"] == 6 and len(info["buildings"]) == 2
    assert info["buildings"][0]["rooms_per_parameter"]
    summary = srv.build_report(language="da", seasons=["winter"], occupied_from="08:00", occupied_to="16:00",
                               include_simulations=False)
    rid = summary["report_id"]
    assert summary["rooms_analysed"] == 6 and summary["key_findings"]
    assert len(srv.report_details(rid, "buildings")) == 2
    rooms = srv.report_details(rid, "rooms")
    detail = srv.report_details(rid, "room", room=rooms[0]["room_id"])
    assert detail[0]["compliance"] and detail[0]["seasons"]
    assert srv.report_details(rid, "config")["language"] == "da"
    out = srv.export_report(rid, str(tmp_path / "rapport"), format="html")
    assert out["path"].endswith("rapport.html") and "Hovedresultater" in (tmp_path / "rapport.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="exists"):
        srv.export_report(rid, str(tmp_path / "rapport.html"))
    srv.export_report(rid, str(tmp_path / "r.json"))
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["summary"]["rooms_analysed"] == 6
    with pytest.raises(ValueError, match="format"):
        srv.export_report(rid, str(tmp_path / "x.docx"))


def test_root_confinement(monkeypatch, tmp_path):
    monkeypatch.setenv("HVX_MCP_ROOT", str(tmp_path))
    assert srv._path("a/b.html", must_exist=False) == (tmp_path / "a" / "b.html").resolve()
    with pytest.raises(ValueError, match="outside HVX_MCP_ROOT"):
        srv._path("/etc/passwd")
    with pytest.raises(ValueError, match="outside HVX_MCP_ROOT"):
        srv._path("../escape.html", must_exist=False)


def test_brands_listed():
    brands = srv.list_brands()
    assert "baw" in brands["brands"] and "white_label" in brands


def test_stdio_session():
    """Spawn `hvx mcp` like a client would and talk MCP to it."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "hvx.cli", "mcp"])
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            prompts = {p.name for p in (await session.list_prompts()).prompts}
            brands = await session.call_tool("list_brands", {})
            missing = await session.call_tool("describe_data", {})
            return tools, prompts, brands, missing

    tools, prompts, brands, missing = asyncio.run(run())
    assert {"load_csv_folder", "load_climify_export", "build_report", "export_report", "report_details"} <= tools
    assert "ieq_report" in prompts
    def is_error(result):  # SDK 2.x: is_error, 1.x: isError
        return getattr(result, "is_error", None) if hasattr(result, "is_error") else result.isError

    assert not is_error(brands) and "baw" in brands.content[0].text
    assert is_error(missing) and "No data loaded" in missing.content[0].text
