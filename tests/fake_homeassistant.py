"""Minimal stand-in for Home Assistant's REST API (history + states), for tests."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, unquote, urlparse

TOKEN = "test-token"


class FakeHomeAssistant:
    """``states[entity_id] = [(utc datetime, state string), ...]`` plus units."""

    def __init__(self) -> None:
        self.states: Dict[str, List[Tuple[datetime, str]]] = {}
        self.units: Dict[str, str] = {}
        self.requests: List[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _json(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                fake.requests.append(self.path)
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._json(401, {"message": "401: Unauthorized"})
                url = urlparse(self.path)
                query = parse_qs(url.query, keep_blank_values=True)
                if url.path == "/api/":
                    return self._json(200, {"message": "API running."})
                if url.path.startswith("/api/history/period/"):
                    start = datetime.fromisoformat(unquote(url.path.rsplit("/", 1)[1]))
                    end = datetime.fromisoformat(query["end_time"][0])
                    minimal = "minimal_response" in query
                    out = []
                    for entity in query["filter_entity_id"][0].split(","):
                        rows = [(t, s) for t, s in fake.states.get(entity, []) if start <= t <= end]
                        if not rows:
                            continue
                        series = []
                        for i, (t, s) in enumerate(rows):
                            if i == 0 or not minimal:
                                series.append({"entity_id": entity, "state": s, "last_changed": t.isoformat(),
                                               "attributes": {"unit_of_measurement": fake.units.get(entity)}})
                            else:
                                series.append({"state": s, "last_changed": t.isoformat()})
                        out.append(series)
                    return self._json(200, out)
                if url.path.startswith("/api/states/"):
                    entity = unquote(url.path.rsplit("/", 1)[1])
                    rows = fake.states.get(entity)
                    if not rows:
                        return self._json(404, {"message": "Entity not found."})
                    t, s = rows[-1]
                    return self._json(200, {"entity_id": entity, "state": s, "last_changed": t.isoformat(),
                                            "last_updated": t.isoformat(), "attributes": {"unit_of_measurement": fake.units.get(entity)}})
                return self._json(404, {"message": "Not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
