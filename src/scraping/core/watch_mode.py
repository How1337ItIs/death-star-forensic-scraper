#!/usr/bin/env python3
"""
DEATH STAR WATCH MODE - Passive Capture via CDP
================================================

Connect to a running Chrome instance and silently capture ALL network traffic,
page content, cookies, storage, and media URLs while the user browses manually.

This is the "sit back and watch" approach: the user drives the browser,
and the Death Star records everything.

Usage:
------
    # 1. Launch Chrome with debugging enabled
    chrome --remote-debugging-port=9222 --user-data-dir="C:\\path\\to\\profile"

    # 2. Browse normally, then start watching
    python watch_mode.py --cdp http://localhost:9222

    # Custom output dir and snapshot interval
    python watch_mode.py --cdp http://localhost:9222 -o data/my_capture --snapshot-interval 15

    # Runs until Ctrl+C, then saves summary

Author: Deadhead-LLM Project
License: MIT
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("death_star_v2.watch_mode")

# Media file extensions worth tracking for later download
MEDIA_EXTENSIONS = frozenset({
    '.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.m3u8', '.ts',
    '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.opus',
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip',
})

# URL patterns that indicate GraphQL endpoints
GRAPHQL_PATTERNS = ('graphql', '/gql', '/api/graphql', '/query')

# Content types that indicate JSON API responses
JSON_CONTENT_TYPES = ('application/json', 'application/graphql+json')


class WatchMode:
    """
    Passive capture mode: connect to Chrome via CDP and record everything
    the user does without interfering with their browsing.
    """

    def __init__(
        self,
        cdp_endpoint: str = "http://localhost:9222",
        output_dir: str = "data/watch_capture",
        snapshot_interval: int = 30,
    ):
        self.cdp_endpoint = cdp_endpoint
        self.snapshot_interval = snapshot_interval
        self._shutdown = False

        # Build timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(output_dir) / timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "api_responses").mkdir(exist_ok=True)
        (self.output_dir / "page_snapshots").mkdir(exist_ok=True)

        # Playwright handles
        self._playwright = None
        self._browser = None
        self._context = None

        # Capture state
        self._network_log_path = self.output_dir / "network_log.jsonl"
        self._network_count = 0
        self._graphql_captures: List[Dict] = []
        self._api_response_count = 0
        self._media_urls: Set[str] = set()
        self._snapshot_count = 0
        self._tracked_pages: Set[int] = set()  # page object ids we already instrumented
        self._start_time: float = 0.0

    # ------------------------------------------------------------------
    # CDP Connection
    # ------------------------------------------------------------------

    async def _connect(self) -> bool:
        """Connect to Chrome via CDP and attach to existing pages."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            return False

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.cdp_endpoint, timeout=15000
            )
        except Exception as e:
            logger.error(f"CDP connection failed: {e}")
            if self._playwright:
                await self._playwright.stop()
            return False

        # Grab the existing browser context (the user's real session)
        if self._browser.contexts:
            self._context = self._browser.contexts[0]
        else:
            logger.warning("No browser contexts found; creating a new one")
            self._context = await self._browser.new_context()

        pages = self._context.pages
        logger.info(f"Connected to Chrome via CDP at {self.cdp_endpoint}")
        logger.info(f"  Open tabs: {len(pages)}")
        for page in pages:
            logger.info(f"    - {page.url}")

        return True

    async def _disconnect(self):
        """Clean up Playwright resources."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Network Interception
    # ------------------------------------------------------------------

    def _is_graphql(self, url: str, content_type: str = "") -> bool:
        """Detect if a request/response is GraphQL."""
        url_lower = url.lower()
        return (
            any(pat in url_lower for pat in GRAPHQL_PATTERNS)
            or 'graphql' in content_type.lower()
        )

    def _is_media_url(self, url: str) -> bool:
        """Check if a URL points to a media/downloadable resource."""
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        return any(path_lower.endswith(ext) for ext in MEDIA_EXTENSIONS)

    async def _on_response(self, response):
        """Handle every HTTP response: log it, capture bodies for JSON/GraphQL."""
        try:
            url = response.url
            status = response.status
            headers = await response.all_headers()
            content_type = headers.get("content-type", "")
            timestamp = time.time()

            # Build the base log entry
            entry = {
                "timestamp": timestamp,
                "url": url,
                "status": status,
                "method": response.request.method,
                "request_url": response.request.url,
                "content_type": content_type,
                "headers": dict(headers),
            }

            # Track media URLs
            if self._is_media_url(url):
                self._media_urls.add(url)

            # Capture body for JSON/API responses
            body = None
            is_json = any(ct in content_type.lower() for ct in JSON_CONTENT_TYPES)
            is_gql = self._is_graphql(url, content_type)

            if is_json or is_gql:
                try:
                    body = await response.json()
                    entry["body"] = body
                except Exception:
                    # Body might not be decodable; try text fallback
                    try:
                        text_body = await response.text()
                        entry["body_text"] = text_body[:5000]
                    except Exception:
                        pass

            # GraphQL capture
            if is_gql and body is not None:
                gql_entry = {
                    "timestamp": timestamp,
                    "url": url,
                    "status": status,
                    "data": body,
                }
                self._graphql_captures.append(gql_entry)
                logger.debug(f"Captured GraphQL: {url[:120]}")

            # Save JSON API responses as individual files
            if is_json and body is not None:
                self._api_response_count += 1
                api_file = (
                    self.output_dir
                    / "api_responses"
                    / f"api_{self._api_response_count:06d}.json"
                )
                try:
                    api_file.write_text(
                        json.dumps(
                            {"url": url, "status": status, "timestamp": timestamp, "body": body},
                            indent=2,
                            default=str,
                        ),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.debug(f"Failed to save API response: {e}")

            # Append to JSONL network log (without large bodies to keep it manageable)
            log_entry = {k: v for k, v in entry.items() if k != "body"}
            if "body" in entry:
                log_entry["has_body"] = True
                log_entry["body_size"] = len(json.dumps(entry["body"], default=str))
            self._write_jsonl(log_entry)
            self._network_count += 1

            if self._network_count % 50 == 0:
                logger.info(f"Captured {self._network_count} network responses so far")

        except Exception as e:
            logger.debug(f"Response handler error: {e}")

    async def _on_request(self, request):
        """Log outgoing requests (lightweight, for URL tracking)."""
        try:
            url = request.url
            if self._is_media_url(url):
                self._media_urls.add(url)
        except Exception:
            pass

    async def _on_websocket(self, ws):
        """Track WebSocket connections and their messages."""
        ws_url = ws.url
        logger.info(f"WebSocket opened: {ws_url}")

        def on_frame_sent(payload):
            self._write_jsonl({
                "timestamp": time.time(),
                "type": "websocket_sent",
                "url": ws_url,
                "payload": payload[:2000] if isinstance(payload, str) else "<binary>",
            })

        def on_frame_received(payload):
            self._write_jsonl({
                "timestamp": time.time(),
                "type": "websocket_received",
                "url": ws_url,
                "payload": payload[:2000] if isinstance(payload, str) else "<binary>",
            })

        def on_close():
            self._write_jsonl({
                "timestamp": time.time(),
                "type": "websocket_closed",
                "url": ws_url,
            })

        ws.on("framesent", on_frame_sent)
        ws.on("framereceived", on_frame_received)
        ws.on("close", on_close)

    def _write_jsonl(self, entry: Dict):
        """Append a single JSON line to the network log."""
        try:
            with open(self._network_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.debug(f"Failed to write JSONL: {e}")

    # ------------------------------------------------------------------
    # Page Instrumentation
    # ------------------------------------------------------------------

    async def _instrument_page(self, page):
        """Attach listeners to a page for network capture."""
        page_id = id(page)
        if page_id in self._tracked_pages:
            return
        self._tracked_pages.add(page_id)

        page.on("response", self._on_response)
        page.on("request", self._on_request)
        page.on("websocket", self._on_websocket)

        try:
            title = await page.title()
        except Exception:
            title = "(unknown)"
        logger.info(f"Instrumented page: {page.url} [{title}]")

    async def _instrument_all_pages(self):
        """Instrument all currently open pages and listen for new ones."""
        if not self._context:
            return

        for page in self._context.pages:
            await self._instrument_page(page)

        # Listen for new tabs
        self._context.on("page", lambda page: asyncio.ensure_future(self._instrument_page(page)))

    # ------------------------------------------------------------------
    # Periodic Snapshots
    # ------------------------------------------------------------------

    async def _take_snapshots(self):
        """Snapshot HTML content of all open pages."""
        if not self._context:
            return

        for page in self._context.pages:
            try:
                url = page.url
                if not url or url == "about:blank":
                    continue

                title = await page.title()
                html = await page.content()

                self._snapshot_count += 1
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                domain = urlparse(url).netloc.replace(":", "_")
                filename = f"snapshot_{self._snapshot_count:04d}_{ts}_{domain}.html"
                filepath = self.output_dir / "page_snapshots" / filename

                filepath.write_text(html, encoding="utf-8")

                # Also write a metadata sidecar
                meta = {
                    "snapshot_id": self._snapshot_count,
                    "timestamp": time.time(),
                    "url": url,
                    "title": title,
                    "html_size": len(html),
                }
                meta_path = filepath.with_suffix(".json")
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

                logger.debug(f"Snapshot #{self._snapshot_count}: {url} ({len(html)} bytes)")

            except Exception as e:
                logger.debug(f"Snapshot failed for page: {e}")

    async def _snapshot_loop(self):
        """Periodically snapshot all pages until shutdown."""
        while not self._shutdown:
            await self._take_snapshots()
            # Sleep in small increments so we can respond to shutdown quickly
            for _ in range(self.snapshot_interval):
                if self._shutdown:
                    break
                await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Cookie & Storage Extraction
    # ------------------------------------------------------------------

    async def _extract_cookies(self) -> List[Dict]:
        """Extract all cookies from the browser context."""
        try:
            cookies = await self._context.cookies()
            return [dict(c) for c in cookies]
        except Exception as e:
            logger.warning(f"Failed to extract cookies: {e}")
            return []

    async def _extract_storage(self, page) -> Dict[str, Any]:
        """Extract localStorage and sessionStorage from a page."""
        result = {"url": page.url, "localStorage": {}, "sessionStorage": {}}

        try:
            result["localStorage"] = await page.evaluate("""
                () => {
                    const data = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        data[key] = localStorage.getItem(key);
                    }
                    return data;
                }
            """)
        except Exception as e:
            logger.debug(f"localStorage extraction failed: {e}")

        try:
            result["sessionStorage"] = await page.evaluate("""
                () => {
                    const data = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        data[key] = sessionStorage.getItem(key);
                    }
                    return data;
                }
            """)
        except Exception as e:
            logger.debug(f"sessionStorage extraction failed: {e}")

        return result

    async def _save_cookies_and_storage(self):
        """Save cookies and storage from all pages."""
        # Cookies
        cookies = await self._extract_cookies()
        cookies_path = self.output_dir / "cookies.json"
        cookies_path.write_text(
            json.dumps(cookies, indent=2, default=str), encoding="utf-8"
        )
        logger.info(f"Saved {len(cookies)} cookies")

        # Storage from each page
        all_storage = []
        for page in self._context.pages:
            try:
                if page.url and page.url != "about:blank":
                    storage = await self._extract_storage(page)
                    all_storage.append(storage)
            except Exception as e:
                logger.debug(f"Storage extraction failed for {page.url}: {e}")

        storage_path = self.output_dir / "storage.json"
        storage_path.write_text(
            json.dumps(all_storage, indent=2, default=str), encoding="utf-8"
        )
        logger.info(f"Saved storage from {len(all_storage)} pages")

    # ------------------------------------------------------------------
    # Summary & Finalization
    # ------------------------------------------------------------------

    async def _save_final_outputs(self):
        """Save all accumulated data before exit."""
        logger.info("Saving final outputs...")

        # GraphQL captures
        if self._graphql_captures:
            gql_path = self.output_dir / "graphql_captures.json"
            gql_path.write_text(
                json.dumps(self._graphql_captures, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(f"Saved {len(self._graphql_captures)} GraphQL captures")

        # Media URLs
        if self._media_urls:
            media_path = self.output_dir / "media_urls.txt"
            media_path.write_text(
                "\n".join(sorted(self._media_urls)), encoding="utf-8"
            )
            logger.info(f"Saved {len(self._media_urls)} media URLs")

        # Cookies and storage
        await self._save_cookies_and_storage()

        # Take one final snapshot
        await self._take_snapshots()

        # Summary
        elapsed = time.time() - self._start_time
        summary = {
            "cdp_endpoint": self.cdp_endpoint,
            "output_dir": str(self.output_dir),
            "start_time": datetime.fromtimestamp(self._start_time, tz=timezone.utc).isoformat(),
            "end_time": datetime.now(tz=timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "network_responses_captured": self._network_count,
            "graphql_captures": len(self._graphql_captures),
            "api_responses_saved": self._api_response_count,
            "page_snapshots": self._snapshot_count,
            "media_urls_discovered": len(self._media_urls),
        }
        summary_path = self.output_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        logger.info("=" * 60)
        logger.info("WATCH MODE CAPTURE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  Duration:            {elapsed:.0f}s")
        logger.info(f"  Network responses:   {self._network_count}")
        logger.info(f"  GraphQL captures:    {len(self._graphql_captures)}")
        logger.info(f"  API responses saved: {self._api_response_count}")
        logger.info(f"  Page snapshots:      {self._snapshot_count}")
        logger.info(f"  Media URLs found:    {len(self._media_urls)}")
        logger.info(f"  Output directory:    {self.output_dir}")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Main Run Loop
    # ------------------------------------------------------------------

    async def run(self):
        """
        Main entry point. Connect to Chrome, instrument pages, capture
        everything until Ctrl+C, then save and exit.
        """
        self._start_time = time.time()

        logger.info("=" * 60)
        logger.info("DEATH STAR WATCH MODE - Passive Capture")
        logger.info("=" * 60)
        logger.info(f"CDP endpoint:      {self.cdp_endpoint}")
        logger.info(f"Output directory:   {self.output_dir}")
        logger.info(f"Snapshot interval:  {self.snapshot_interval}s")
        logger.info("")

        # Connect via CDP
        if not await self._connect():
            logger.error("Failed to connect. Is Chrome running with --remote-debugging-port?")
            return

        # Set up signal handler for graceful shutdown
        loop = asyncio.get_running_loop()

        def _signal_handler():
            logger.info("\nShutdown signal received. Saving captures...")
            self._shutdown = True

        # Windows does not support add_signal_handler for SIGINT in asyncio,
        # so we fall back to the threaded signal module.
        if sys.platform == "win32":
            signal.signal(signal.SIGINT, lambda *_: _signal_handler())
            signal.signal(signal.SIGTERM, lambda *_: _signal_handler())
        else:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _signal_handler)

        # Instrument all open pages
        await self._instrument_all_pages()

        logger.info("")
        logger.info("Watching... Browse normally in Chrome. Press Ctrl+C to stop and save.")
        logger.info("")

        # Run snapshot loop until shutdown
        try:
            await self._snapshot_loop()
        except asyncio.CancelledError:
            pass

        # Final save
        await self._save_final_outputs()
        await self._disconnect()

        logger.info("Watch mode complete. Goodbye.")


# ======================================================================
# CLI Entry Point
# ======================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Death Star Watch Mode - Passive Capture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --cdp http://localhost:9222
  %(prog)s --cdp http://localhost:9222 -o data/my_capture --snapshot-interval 15

Launch Chrome first:
  chrome --remote-debugging-port=9222 --user-data-dir="C:\\path\\to\\profile"
        """,
    )
    parser.add_argument(
        "--cdp",
        default="http://localhost:9222",
        help="CDP endpoint URL (default: http://localhost:9222)",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/watch_capture",
        help="Output directory (default: data/watch_capture)",
    )
    parser.add_argument(
        "--snapshot-interval",
        type=int,
        default=30,
        help="Page snapshot interval in seconds (default: 30)",
    )
    args = parser.parse_args()

    asyncio.run(WatchMode(args.cdp, args.output, args.snapshot_interval).run())
