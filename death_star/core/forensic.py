"""
Forensic Capture Module
=======================

Complete forensic capture of web pages including:
- WARC generation
- HAR capture
- Asset downloading
- Browser storage
- SSL certificates
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("death_star.forensic")


@dataclass
class ForensicResult:
    """Result of forensic capture."""
    url: str
    timestamp: str
    
    # Network
    requests: List[Dict]
    responses: List[Dict]
    
    # Content
    html: str
    assets: List[Dict]
    
    # Browser storage
    cookies: List[Dict]
    local_storage: Dict[str, str]
    session_storage: Dict[str, str]
    
    # Links
    internal_links: List[str]
    external_links: List[str]
    
    # Files
    warc_path: Optional[str] = None
    har_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    pdf_path: Optional[str] = None


class ForensicCapture:
    """
    Complete forensic capture of web pages.
    
    Usage:
        capture = ForensicCapture(output_dir="data/forensic")
        result = await capture.capture_page("https://example.com")
    """
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/forensic")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def capture_page(
        self,
        url: str,
        page=None,  # Playwright page (optional)
        capture_assets: bool = True,
        capture_storage: bool = True,
        capture_screenshot: bool = True,
        capture_pdf: bool = False,
        capture_certificate: bool = True,
        generate_warc: bool = True,
        generate_har: bool = True,
    ) -> ForensicResult:
        """
        Capture a page forensically.
        
        Args:
            url: URL to capture
            page: Existing Playwright page (or creates new one)
            capture_assets: Download all assets
            capture_storage: Capture browser storage
            capture_screenshot: Take screenshot
            capture_pdf: Generate PDF
            capture_certificate: Capture SSL certificate
            generate_warc: Generate WARC file
            generate_har: Generate HAR file
        
        Returns:
            ForensicResult with all captured data
        """
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc
        output_dir = self.output_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        requests = []
        responses = []
        
        # Create browser if not provided
        own_browser = False
        if page is None:
            try:
                from playwright.async_api import async_playwright
                
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                own_browser = True
            except ImportError:
                logger.error("Playwright required for forensic capture")
                raise
        
        try:
            # Set up request/response capture
            async def capture_request(request):
                requests.append({
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "timestamp": datetime.now().isoformat(),
                })
            
            async def capture_response(response):
                resp_entry = {
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "timestamp": datetime.now().isoformat(),
                }
                try:
                    ct = response.headers.get("content-type", "") or ""
                    if "json" in ct or "application/json" in ct:
                        body = await response.body()
                        resp_entry["body"] = body.decode("utf-8", errors="replace")
                except Exception:
                    pass
                responses.append(resp_entry)
            
            page.on("request", capture_request)
            page.on("response", capture_response)
            
            # Navigate
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            
            # Get HTML
            html = await page.content()
            
            # Capture storage
            cookies = []
            local_storage = {}
            session_storage = {}
            
            if capture_storage:
                cookies = await page.context.cookies()
                
                local_storage = await page.evaluate("""
                    () => {
                        const items = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const key = localStorage.key(i);
                            items[key] = localStorage.getItem(key);
                        }
                        return items;
                    }
                """)
                
                session_storage = await page.evaluate("""
                    () => {
                        const items = {};
                        for (let i = 0; i < sessionStorage.length; i++) {
                            const key = sessionStorage.key(i);
                            items[key] = sessionStorage.getItem(key);
                        }
                        return items;
                    }
                """)
            
            # Extract links
            internal_links = []
            external_links = []
            
            links_data = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
            """)
            
            for link in links_data:
                if urlparse(link).netloc == domain:
                    internal_links.append(link)
                elif link.startswith("http"):
                    external_links.append(link)
            
            # Capture assets
            assets = []
            if capture_assets:
                assets = await self._capture_assets(page, url, output_dir)
            
            # Screenshot
            screenshot_path = None
            if capture_screenshot:
                screenshot_path = output_dir / "screenshot.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
            
            # PDF
            pdf_path = None
            if capture_pdf:
                pdf_path = output_dir / "page.pdf"
                await page.pdf(path=str(pdf_path))
            
            # WARC
            warc_path = None
            if generate_warc:
                warc_path = await self._generate_warc(url, html, responses, output_dir)
            
            # HAR
            har_path = None
            if generate_har:
                har_path = await self._generate_har(url, requests, responses, output_dir)
            
            # Save JSON response bodies (API data)
            api_dir = output_dir / "api_responses"
            api_dir.mkdir(exist_ok=True)
            for i, resp in enumerate(responses):
                body = resp.get("body")
                if not body:
                    continue
                safe_name = re.sub(r"[^\w\-.]", "_", urlparse(resp["url"]).path or "response")[:80]
                safe_name = safe_name or "response"
                ext = ".json" if body.strip().startswith("{") or body.strip().startswith("[") else ".txt"
                out_path = api_dir / f"{i:04d}_{safe_name}{ext}"
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(body)
                except Exception as e:
                    logger.debug(f"Could not save API response {out_path}: {e}")
            
            return ForensicResult(
                url=url,
                timestamp=datetime.now().isoformat(),
                requests=requests,
                responses=responses,
                html=html,
                assets=assets,
                cookies=cookies,
                local_storage=local_storage,
                session_storage=session_storage,
                internal_links=internal_links,
                external_links=external_links,
                warc_path=str(warc_path) if warc_path else None,
                har_path=str(har_path) if har_path else None,
                screenshot_path=str(screenshot_path) if screenshot_path else None,
                pdf_path=str(pdf_path) if pdf_path else None,
            )
            
        finally:
            if own_browser:
                await browser.close()
                await playwright.stop()
    
    async def _capture_assets(self, page, base_url: str, output_dir: Path) -> List[Dict]:
        """Download all page assets."""
        assets = []
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)
        
        # Get all resource URLs
        resources = await page.evaluate("""
            () => {
                const resources = [];
                
                // Images
                document.querySelectorAll('img[src]').forEach(img => {
                    resources.push({type: 'image', url: img.src});
                });
                
                // CSS
                document.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
                    resources.push({type: 'css', url: link.href});
                });
                
                // JS
                document.querySelectorAll('script[src]').forEach(script => {
                    resources.push({type: 'js', url: script.src});
                });
                
                return resources;
            }
        """)
        
        for resource in resources[:100]:  # Limit
            try:
                response = await page.request.get(resource["url"])
                if response.ok:
                    content = await response.body()
                    
                    # Generate filename
                    url_hash = hashlib.md5(resource["url"].encode()).hexdigest()[:8]
                    ext = Path(resource["url"]).suffix[:10] or ".bin"
                    filename = f"{resource['type']}_{url_hash}{ext}"
                    
                    filepath = assets_dir / filename
                    filepath.write_bytes(content)
                    
                    assets.append({
                        "url": resource["url"],
                        "type": resource["type"],
                        "path": str(filepath),
                        "size": len(content),
                    })
            except Exception:
                pass
        
        return assets
    
    async def _generate_warc(
        self,
        url: str,
        html: str,
        responses: List[Dict],
        output_dir: Path
    ) -> Optional[Path]:
        """Generate WARC file."""
        try:
            from io import BytesIO
            from warcio.warcwriter import WARCWriter
            from warcio.statusandheaders import StatusAndHeaders
            
            warc_path = output_dir / f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.warc.gz"
            
            with open(warc_path, "wb") as f:
                writer = WARCWriter(f, gzip=True)
                
                # Write main HTML response (payload must be file-like)
                headers = StatusAndHeaders(
                    "200 OK",
                    [("Content-Type", "text/html; charset=utf-8")],
                    protocol="HTTP/1.1"
                )
                
                record = writer.create_warc_record(
                    url,
                    "response",
                    payload=BytesIO(html.encode("utf-8")),
                    http_headers=headers
                )
                writer.write_record(record)
            
            return warc_path
            
        except ImportError:
            logger.warning("warcio not installed, skipping WARC generation")
            return None
    
    async def _generate_har(
        self,
        url: str,
        requests: List[Dict],
        responses: List[Dict],
        output_dir: Path
    ) -> Path:
        """Generate HAR file."""
        har = {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "Death Star Scraper",
                    "version": "2.0.0"
                },
                "entries": []
            }
        }
        
        # Match requests with responses
        for req in requests:
            entry = {
                "startedDateTime": req["timestamp"],
                "request": {
                    "method": req["method"],
                    "url": req["url"],
                    "headers": [{"name": k, "value": v} for k, v in req["headers"].items()],
                },
                "response": {
                    "status": 0,
                    "statusText": "",
                    "headers": [],
                }
            }
            
            # Find matching response
            for resp in responses:
                if resp["url"] == req["url"]:
                    entry["response"]["status"] = resp["status"]
                    entry["response"]["headers"] = [
                        {"name": k, "value": v} for k, v in resp["headers"].items()
                    ]
                    break
            
            har["log"]["entries"].append(entry)
        
        har_path = output_dir / "capture.har"
        with open(har_path, "w") as f:
            json.dump(har, f, indent=2)
        
        return har_path


def save_forensic_result(result: ForensicResult, output_dir: Path):
    """Save forensic result to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metadata
    meta = {
        "url": result.url,
        "timestamp": result.timestamp,
        "request_count": len(result.requests),
        "response_count": len(result.responses),
        "asset_count": len(result.assets),
        "cookie_count": len(result.cookies),
        "internal_links": len(result.internal_links),
        "external_links": len(result.external_links),
        "warc_path": result.warc_path,
        "har_path": result.har_path,
        "screenshot_path": result.screenshot_path,
    }
    
    with open(output_dir / "forensic_metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
    
    # Save HTML
    with open(output_dir / "page.html", "w", encoding="utf-8") as f:
        f.write(result.html)
    
    # Save storage
    with open(output_dir / "cookies.json", "w") as f:
        json.dump(result.cookies, f, indent=2)
    
    with open(output_dir / "local_storage.json", "w") as f:
        json.dump(result.local_storage, f, indent=2)
    
    # Save links
    with open(output_dir / "links.json", "w") as f:
        json.dump({
            "internal": result.internal_links,
            "external": result.external_links,
        }, f, indent=2)
