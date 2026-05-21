"""Local HTTP fixtures for Death Star smoke and regression tests."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator


class DeathStarFixtureHandler(BaseHTTPRequestHandler):
    server_version = "DeathStarFixture/1.0"

    def log_message(self, format: str, *args):  # noqa: A002
        return

    def _send(self, body: bytes, status: int = 200, content_type: str = "text/html"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in {"/", "/static"}:
            self._send(
                b"""<!doctype html>
<html>
  <head>
    <title>Fixture Static Page</title>
    <meta property="og:title" content="Fixture Static Page">
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","name":"Fixture"}</script>
  </head>
  <body>
    <main>
      <h1>Fixture Static Page</h1>
      <p>This local page is stable and intentionally crawlable.</p>
      <a href="/duplicate-a">Duplicate A</a>
      <a href="/broken">Broken</a>
      <img src="/asset.txt" alt="fixture asset">
    </main>
  </body>
</html>"""
            )
            return
        if path == "/js":
            self._send(
                b"""<!doctype html>
<html><head><title>Fixture JS Page</title></head>
<body><div id="app"></div><script>document.getElementById('app').textContent = 'Rendered';</script></body></html>"""
            )
            return
        if path == "/sitemap.xml":
            self._send(
                b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>/static</loc></url>
  <url><loc>/duplicate-a</loc></url>
</urlset>""",
                content_type="application/xml",
            )
            return
        if path == "/robots.txt":
            self._send(b"User-agent: *\nAllow: /\nDisallow: /private\n", content_type="text/plain")
            return
        if path == "/api.json":
            self._send(json.dumps({"ok": True, "items": [1, 2, 3]}).encode(), content_type="application/json")
            return
        if path == "/graphql":
            self._send(json.dumps({"data": {"viewer": {"id": "fixture"}}}).encode(), content_type="application/json")
            return
        if path in {"/duplicate-a", "/duplicate-b"}:
            self._send(b"<html><title>Duplicate</title><body><h1>Same content</h1></body></html>")
            return
        if path == "/asset.txt":
            self._send(b"fixture asset text", content_type="text/plain")
            return
        if path == "/slow":
            time.sleep(0.25)
            self._send(b"<html><title>Slow</title><body>slow response</body></html>")
            return
        if path == "/broken":
            self._send(b"not found", status=404, content_type="text/plain")
            return
        self._send(b"not found", status=404, content_type="text/plain")

    def do_POST(self):  # noqa: N802
        if self.path.split("?", 1)[0] == "/graphql":
            self._send(json.dumps({"data": {"ok": True}}).encode(), content_type="application/json")
            return
        self._send(b"not found", status=404, content_type="text/plain")


class FixtureServer:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DeathStarFixtureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FixtureServer":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def fixture_server() -> Iterator[FixtureServer]:
    with FixtureServer() as server:
        yield server
