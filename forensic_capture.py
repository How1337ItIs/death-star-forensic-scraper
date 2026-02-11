#!/usr/bin/env python3
"""
Forensic Capture Module
=======================

Complete forensic capture capabilities for the Death Star scraper.
Captures EVERYTHING for reverse engineering and analysis.

Features:
---------
1. WARC generation (Web ARChive format - archival standard)
2. HAR capture (HTTP Archive - network forensics)
3. Complete asset downloading
4. Full header preservation
5. Browser storage extraction
6. Metadata extraction
7. Certificate/DNS capture
8. Screenshot and PDF generation

Usage:
------
    from forensic_capture import ForensicCapture
    
    capture = ForensicCapture(output_dir="data/forensic")
    result = await capture.capture_page(url, browser_page)
"""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import re
import shutil
import socket
import ssl
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
import logging
import sys

logger = logging.getLogger("forensic_capture")


def safe_path_component(value: str) -> str:
    """Make a string safe for cross-platform file and directory names."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


@dataclass
class NetworkRequest:
    """Captured network request."""
    url: str
    method: str
    headers: Dict[str, str]
    post_data: Optional[str]
    resource_type: str
    timestamp: float


@dataclass 
class NetworkResponse:
    """Captured network response."""
    url: str
    status: int
    status_text: str
    headers: Dict[str, str]
    body: bytes
    body_hash: str
    mime_type: str
    timestamp: float
    from_cache: bool


@dataclass
class ForensicResult:
    """Complete forensic capture result."""
    url: str
    final_url: str
    timestamp: str
    
    # Page content
    raw_html: str
    dom_snapshot: str  # Post-JS execution
    clean_text: str
    
    # Network
    requests: List[NetworkRequest]
    responses: List[NetworkResponse]
    har_data: Dict
    
    # Assets
    assets: Dict[str, bytes]  # url -> content
    asset_hashes: Dict[str, str]  # url -> hash
    
    # Metadata
    metadata: Dict[str, Any]
    headers: Dict[str, str]
    cookies: List[Dict]
    
    # Browser storage
    local_storage: Dict[str, str]
    session_storage: Dict[str, str]
    indexed_db: Dict[str, Any]
    
    # Security
    certificate: Dict[str, Any]
    dns_records: Dict[str, Any]
    security_headers: Dict[str, str]
    
    # Visual
    screenshot_path: Optional[str]
    pdf_path: Optional[str]
    mhtml_path: Optional[str]
    favicon_path: Optional[str]
    
    # Links & Structure
    internal_links: List[str]
    external_links: List[str]
    resource_links: List[str]
    
    # Hashes for integrity
    content_hash: str
    warc_path: Optional[str]
    wacz_path: Optional[str]


class ForensicCapture:
    """
    Complete forensic web page capture.
    
    Captures every trace of a web page for forensic analysis
    and reverse engineering.
    """
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/forensic")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.output_dir / "warc").mkdir(exist_ok=True)
        (self.output_dir / "har").mkdir(exist_ok=True)
        (self.output_dir / "assets").mkdir(exist_ok=True)
        (self.output_dir / "screenshots").mkdir(exist_ok=True)
        (self.output_dir / "pdfs").mkdir(exist_ok=True)
        (self.output_dir / "singlefile").mkdir(exist_ok=True)
        (self.output_dir / "favicons").mkdir(exist_ok=True)
        (self.output_dir / "wacz").mkdir(exist_ok=True)
        (self.output_dir / "metadata").mkdir(exist_ok=True)
        (self.output_dir / "certificates").mkdir(exist_ok=True)
        
        self._requests: List[NetworkRequest] = []
        self._responses: List[NetworkResponse] = []
    
    async def capture_page(
        self,
        url: str,
        page = None,  # Playwright page object
        capture_assets: bool = True,
        capture_storage: bool = True,
        capture_screenshot: bool = True,
        capture_pdf: bool = True,
        capture_mhtml: bool = True,
        capture_favicon: bool = True,
        capture_certificate: bool = True,
        generate_warc: bool = True,
        generate_har: bool = True,
        generate_wacz: bool = False,
    ) -> ForensicResult:
        """
        Capture complete forensic data for a page.
        
        Args:
            url: URL to capture
            page: Playwright page object (if None, creates new browser)
            capture_assets: Download all assets
            capture_storage: Capture browser storage
            capture_screenshot: Take screenshot
            capture_pdf: Generate PDF
            capture_mhtml: Generate MHTML single-file snapshot
            capture_favicon: Download and save site favicon
            capture_certificate: Capture SSL certificate
            generate_warc: Generate WARC archive
            generate_har: Generate HAR file
            generate_wacz: Convert generated WARC into WACZ (requires `wacz` CLI)
        
        Returns:
            ForensicResult with all captured data
        """
        parsed_target = urlparse(url)
        domain = (parsed_target.hostname or parsed_target.netloc).replace("www.", "")
        domain_fs = safe_path_component(domain)
        timestamp = datetime.now().isoformat()
        
        # Reset capture state
        self._requests = []
        self._responses = []
        
        # Create browser if needed
        own_browser = False
        if page is None:
            page, own_browser = await self._create_browser()
        
        try:
            # Set up network interception
            await self._setup_network_capture(page)
            
            # Navigate and wait for full load
            response = await page.goto(url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(2)  # Extra wait for dynamic content
            
            # Get final URL after redirects
            final_url = page.url
            
            # Capture raw HTML
            raw_html = await page.content()
            
            # Capture DOM snapshot (post-JS)
            dom_snapshot = await self._capture_dom_snapshot(page)
            
            # Extract text
            clean_text = await page.evaluate('''
                () => {
                    const clone = document.body.cloneNode(true);
                    const scripts = clone.querySelectorAll('script, style, noscript');
                    scripts.forEach(s => s.remove());
                    return clone.innerText;
                }
            ''')
            
            # Capture metadata
            metadata = await self._extract_metadata(page, raw_html, url)

            # Capture favicon
            favicon_path = None
            if capture_favicon:
                favicon_path = await self._capture_favicon(
                    url=url,
                    domain=domain_fs,
                    timestamp=timestamp,
                    metadata=metadata,
                )
                if favicon_path:
                    metadata["favicon_path"] = favicon_path
            
            # Capture headers
            headers = {}
            if response:
                headers = dict(response.headers)
            
            # Capture cookies
            cookies = await page.context.cookies()
            
            # Capture browser storage
            local_storage = {}
            session_storage = {}
            indexed_db = {}
            if capture_storage:
                local_storage, session_storage, indexed_db = await self._capture_storage(page)
            
            # Extract links
            internal_links, external_links, resource_links = await self._extract_links(
                page, raw_html, url
            )
            
            # Capture assets
            assets = {}
            asset_hashes = {}
            if capture_assets:
                assets, asset_hashes = await self._capture_assets(
                    page, resource_links, domain_fs
                )
            
            # Capture certificate
            certificate = {}
            if capture_certificate:
                certificate = self._capture_certificate(url)
            
            # Capture DNS
            dns_records = self._capture_dns(domain)
            
            # Extract security headers
            security_headers = self._extract_security_headers(headers)
            
            # Screenshot
            screenshot_path = None
            if capture_screenshot:
                screenshot_path = await self._capture_screenshot(page, domain_fs, timestamp)
            
            # PDF
            pdf_path = None
            if capture_pdf:
                pdf_path = await self._capture_pdf(page, domain_fs, timestamp)

            # Single-file (MHTML) snapshot
            mhtml_path = None
            if capture_mhtml:
                mhtml_path = await self._capture_mhtml(page, domain_fs, timestamp)
            
            # Generate HAR
            har_data = {}
            if generate_har:
                har_data = self._generate_har(url, self._requests, self._responses)
                har_path = self.output_dir / "har" / f"{domain_fs}_{timestamp.replace(':', '-')}.har"
                with open(har_path, 'w') as f:
                    json.dump(har_data, f, indent=2)
            
            # Generate WARC
            warc_path = None
            if generate_warc:
                warc_path = await self._generate_warc(
                    url, raw_html, self._requests, self._responses, domain_fs, timestamp
                )

            # Generate WACZ from WARC if requested
            wacz_path = None
            if generate_wacz and warc_path:
                wacz_path = await self._generate_wacz(
                    warc_path=warc_path,
                    source_url=url,
                    domain=domain_fs,
                    timestamp=timestamp,
                )
            
            # Calculate content hash
            content_hash = hashlib.sha256(raw_html.encode()).hexdigest()
            
            return ForensicResult(
                url=url,
                final_url=final_url,
                timestamp=timestamp,
                raw_html=raw_html,
                dom_snapshot=dom_snapshot,
                clean_text=clean_text,
                requests=self._requests,
                responses=self._responses,
                har_data=har_data,
                assets=assets,
                asset_hashes=asset_hashes,
                metadata=metadata,
                headers=headers,
                cookies=cookies,
                local_storage=local_storage,
                session_storage=session_storage,
                indexed_db=indexed_db,
                certificate=certificate,
                dns_records=dns_records,
                security_headers=security_headers,
                screenshot_path=screenshot_path,
                pdf_path=pdf_path,
                mhtml_path=mhtml_path,
                favicon_path=favicon_path,
                internal_links=internal_links,
                external_links=external_links,
                resource_links=resource_links,
                content_hash=content_hash,
                warc_path=warc_path,
                wacz_path=wacz_path,
            )
            
        finally:
            if own_browser:
                await page.context.browser.close()
    
    async def _create_browser(self):
        """Create a new browser instance."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("Playwright required: pip install playwright && playwright install chromium")
        
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = await context.new_page()
        return page, True
    
    async def _setup_network_capture(self, page):
        """Set up network request/response capture."""
        
        async def handle_request(request):
            self._requests.append(NetworkRequest(
                url=request.url,
                method=request.method,
                headers=dict(request.headers),
                post_data=request.post_data,
                resource_type=request.resource_type,
                timestamp=time.time()
            ))
        
        async def handle_response(response):
            try:
                body = await response.body()
            except Exception:
                body = b""
            
            self._responses.append(NetworkResponse(
                url=response.url,
                status=response.status,
                status_text=response.status_text,
                headers=dict(response.headers),
                body=body,
                body_hash=hashlib.sha256(body).hexdigest()[:16],
                mime_type=response.headers.get('content-type', ''),
                timestamp=time.time(),
                from_cache=response.from_cache if hasattr(response, 'from_cache') else False
            ))
        
        page.on("request", handle_request)
        page.on("response", handle_response)
    
    async def _capture_dom_snapshot(self, page) -> str:
        """Capture DOM after JavaScript execution."""
        return await page.evaluate('''
            () => {
                const serializer = new XMLSerializer();
                return serializer.serializeToString(document);
            }
        ''')
    
    async def _extract_metadata(self, page, html: str, url: str) -> Dict[str, Any]:
        """Extract all metadata from page."""
        metadata = {
            "url": url,
            "extracted_at": datetime.now().isoformat(),
        }
        
        # Title
        try:
            metadata["title"] = await page.title()
        except Exception:
            metadata["title"] = ""
        
        # Meta tags
        meta_tags = await page.evaluate('''
            () => {
                const metas = {};
                document.querySelectorAll('meta').forEach(meta => {
                    const name = meta.getAttribute('name') || meta.getAttribute('property') || meta.getAttribute('http-equiv');
                    const content = meta.getAttribute('content');
                    if (name && content) {
                        metas[name] = content;
                    }
                });
                return metas;
            }
        ''')
        metadata["meta_tags"] = meta_tags
        
        # Open Graph
        metadata["open_graph"] = {
            k.replace('og:', ''): v 
            for k, v in meta_tags.items() 
            if k.startswith('og:')
        }
        
        # Twitter Card
        metadata["twitter_card"] = {
            k.replace('twitter:', ''): v 
            for k, v in meta_tags.items() 
            if k.startswith('twitter:')
        }
        
        # Schema.org / JSON-LD
        jsonld = await page.evaluate('''
            () => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                return Array.from(scripts).map(s => {
                    try { return JSON.parse(s.textContent); }
                    catch { return null; }
                }).filter(x => x);
            }
        ''')
        metadata["json_ld"] = jsonld
        
        # Canonical URL
        canonical = await page.evaluate('''
            () => {
                const link = document.querySelector('link[rel="canonical"]');
                return link ? link.href : null;
            }
        ''')
        metadata["canonical_url"] = canonical
        
        # Alternate languages
        alternates = await page.evaluate('''
            () => {
                const links = document.querySelectorAll('link[rel="alternate"][hreflang]');
                return Array.from(links).map(l => ({
                    hreflang: l.getAttribute('hreflang'),
                    href: l.href
                }));
            }
        ''')
        metadata["alternate_languages"] = alternates
        
        # RSS/Atom feeds
        feeds = await page.evaluate('''
            () => {
                const links = document.querySelectorAll('link[type*="rss"], link[type*="atom"]');
                return Array.from(links).map(l => ({
                    type: l.type,
                    href: l.href,
                    title: l.title
                }));
            }
        ''')
        metadata["feeds"] = feeds
        
        # Favicon
        favicon = await page.evaluate('''
            () => {
                const link = document.querySelector('link[rel*="icon"]');
                return link ? link.href : null;
            }
        ''')
        metadata["favicon"] = favicon
        
        return metadata
    
    async def _capture_storage(self, page) -> tuple:
        """Capture browser storage."""
        # localStorage
        local_storage = await page.evaluate('''
            () => {
                const storage = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    storage[key] = localStorage.getItem(key);
                }
                return storage;
            }
        ''')
        
        # sessionStorage
        session_storage = await page.evaluate('''
            () => {
                const storage = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    storage[key] = sessionStorage.getItem(key);
                }
                return storage;
            }
        ''')
        
        # IndexedDB (list databases)
        indexed_db = await page.evaluate('''
            async () => {
                try {
                    const dbs = await indexedDB.databases();
                    return dbs.map(db => ({ name: db.name, version: db.version }));
                } catch {
                    return [];
                }
            }
        ''')
        
        return local_storage, session_storage, {"databases": indexed_db}
    
    async def _extract_links(self, page, html: str, base_url: str) -> tuple:
        """Extract all links from page."""
        base_domain = urlparse(base_url).netloc
        
        all_links = await page.evaluate('''
            () => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
        ''')
        
        internal_links = []
        external_links = []
        
        for link in all_links:
            if not link or link.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            
            parsed = urlparse(link)
            if parsed.netloc == base_domain or parsed.netloc == '':
                internal_links.append(link)
            else:
                external_links.append(link)
        
        # Resource links (CSS, JS, images, etc.)
        resource_links = await page.evaluate('''
            () => {
                const resources = [];
                // CSS
                document.querySelectorAll('link[rel="stylesheet"]').forEach(l => resources.push(l.href));
                // JS
                document.querySelectorAll('script[src]').forEach(s => resources.push(s.src));
                // Images
                document.querySelectorAll('img[src]').forEach(i => resources.push(i.src));
                // Videos
                document.querySelectorAll('video source[src]').forEach(v => resources.push(v.src));
                // Audio
                document.querySelectorAll('audio source[src]').forEach(a => resources.push(a.src));
                // Fonts (from CSS - limited)
                document.querySelectorAll('link[rel="preload"][as="font"]').forEach(f => resources.push(f.href));
                return [...new Set(resources)];
            }
        ''')
        
        return internal_links, external_links, resource_links
    
    async def _capture_assets(self, page, resource_links: List[str], domain: str) -> tuple:
        """Download all assets."""
        assets = {}
        asset_hashes = {}
        
        asset_dir = self.output_dir / "assets" / domain
        asset_dir.mkdir(parents=True, exist_ok=True)
        
        for url in resource_links:
            if not url or not url.startswith(('http://', 'https://')):
                continue
            
            try:
                # Check if we already captured it in network responses
                for resp in self._responses:
                    if resp.url == url and resp.body:
                        assets[url] = resp.body
                        asset_hashes[url] = resp.body_hash
                        
                        # Save to disk
                        filename = self._url_to_filename(url)
                        filepath = asset_dir / filename
                        with open(filepath, 'wb') as f:
                            f.write(resp.body)
                        break
                        
            except Exception as e:
                logger.debug(f"Failed to save asset {url}: {e}")
        
        return assets, asset_hashes
    
    def _url_to_filename(self, url: str) -> str:
        """Convert URL to safe filename."""
        parsed = urlparse(url)
        path = parsed.path.strip('/').replace('/', '_') or 'index'
        # Add hash for uniqueness
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        # Get extension
        ext = Path(path).suffix
        if not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext or ""):
            ext = '.bin'
        name = safe_path_component(Path(path).stem)[:50]
        return f"{name}_{url_hash}{ext}"
    
    def _capture_certificate(self, url: str) -> Dict[str, Any]:
        """Capture SSL certificate information."""
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return {}
        
        try:
            hostname = parsed.netloc.split(':')[0]
            port = int(parsed.netloc.split(':')[1]) if ':' in parsed.netloc else 443
            
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    cert_binary = ssock.getpeercert(binary_form=True)
                    
                    return {
                        "subject": dict(x[0] for x in cert.get('subject', [])),
                        "issuer": dict(x[0] for x in cert.get('issuer', [])),
                        "version": cert.get('version'),
                        "serial_number": cert.get('serialNumber'),
                        "not_before": cert.get('notBefore'),
                        "not_after": cert.get('notAfter'),
                        "subject_alt_names": cert.get('subjectAltName', []),
                        "ocsp": cert.get('OCSP', []),
                        "fingerprint_sha256": hashlib.sha256(cert_binary).hexdigest(),
                    }
        except Exception as e:
            logger.debug(f"Certificate capture failed: {e}")
            return {"error": str(e)}
    
    def _capture_dns(self, domain: str) -> Dict[str, Any]:
        """Capture DNS records."""
        records = {}
        
        try:
            # A records
            import socket
            records["A"] = socket.gethostbyname_ex(domain)[2]
        except Exception:
            records["A"] = []
        
        try:
            # Try to get more records if dnspython is available
            import dns.resolver
            
            for record_type in ['AAAA', 'MX', 'TXT', 'NS', 'CNAME']:
                try:
                    answers = dns.resolver.resolve(domain, record_type)
                    records[record_type] = [str(r) for r in answers]
                except Exception:
                    records[record_type] = []
                    
        except ImportError:
            pass
        
        return records
    
    def _extract_security_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Extract security-related headers."""
        security_headers = {}
        
        security_header_names = [
            'content-security-policy',
            'x-content-type-options',
            'x-frame-options',
            'x-xss-protection',
            'strict-transport-security',
            'referrer-policy',
            'permissions-policy',
            'cross-origin-opener-policy',
            'cross-origin-embedder-policy',
            'cross-origin-resource-policy',
        ]
        
        for name in security_header_names:
            value = headers.get(name) or headers.get(name.title())
            if value:
                security_headers[name] = value
        
        return security_headers
    
    async def _capture_screenshot(self, page, domain: str, timestamp: str) -> str:
        """Capture full-page screenshot."""
        filename = f"{domain}_{timestamp.replace(':', '-')}.png"
        filepath = self.output_dir / "screenshots" / filename
        
        await page.screenshot(path=str(filepath), full_page=True)
        return str(filepath)
    
    async def _capture_pdf(self, page, domain: str, timestamp: str) -> str:
        """Generate PDF of page."""
        filename = f"{domain}_{timestamp.replace(':', '-')}.pdf"
        filepath = self.output_dir / "pdfs" / filename
        
        try:
            await page.pdf(path=str(filepath), format='A4', print_background=True)
            return str(filepath)
        except Exception as e:
            logger.debug(f"PDF generation failed: {e}")
            return None

    async def _capture_mhtml(self, page, domain: str, timestamp: str) -> Optional[str]:
        """Capture a single-file MHTML snapshot via CDP."""
        filename = f"{domain}_{timestamp.replace(':', '-')}.mhtml"
        filepath = self.output_dir / "singlefile" / filename

        try:
            cdp_session = await page.context.new_cdp_session(page)
            snapshot = await cdp_session.send("Page.captureSnapshot", {"format": "mhtml"})
            mhtml_data = snapshot.get("data", "")
            if not mhtml_data:
                return None

            with open(filepath, "w", encoding="utf-8", errors="ignore") as f:
                f.write(mhtml_data)
            return str(filepath)
        except Exception as e:
            logger.debug(f"MHTML capture failed: {e}")
            return None

    async def _capture_favicon(
        self,
        url: str,
        domain: str,
        timestamp: str,
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        """Download favicon referenced by page metadata or common default paths."""
        try:
            import requests
        except ImportError:
            return None

        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        candidates: List[str] = []

        favicon_hint = metadata.get("favicon")
        if favicon_hint:
            candidates.append(urljoin(url, favicon_hint))

        candidates.extend([
            urljoin(base_url, "/favicon.ico"),
            urljoin(base_url, "/favicon.png"),
            urljoin(base_url, "/apple-touch-icon.png"),
        ])

        seen = set()
        ordered_candidates = []
        for candidate in candidates:
            if candidate and candidate not in seen:
                ordered_candidates.append(candidate)
                seen.add(candidate)

        for favicon_url in ordered_candidates:
            try:
                response = requests.get(favicon_url, timeout=15)
                if response.status_code != 200 or not response.content:
                    continue

                ext = Path(urlparse(favicon_url).path).suffix.lower()
                if not re.fullmatch(r"\.[a-z0-9]{1,8}", ext or ""):
                    content_type = response.headers.get("content-type", "").lower()
                    ext = ".png" if "png" in content_type else ".ico"

                filename = f"{domain}_{timestamp.replace(':', '-')}{ext}"
                filepath = self.output_dir / "favicons" / filename
                with open(filepath, "wb") as f:
                    f.write(response.content)

                return str(filepath)
            except Exception:
                continue

        return None

    async def _generate_wacz(
        self,
        warc_path: str,
        source_url: str,
        domain: str,
        timestamp: str,
    ) -> Optional[str]:
        """Generate a WACZ package from a WARC file using py-wacz CLI."""
        if not warc_path or not warc_path.endswith((".warc", ".warc.gz")):
            return None

        if shutil.which("wacz") is None:
            logger.warning("wacz CLI not found; skipping WACZ generation")
            return None

        output_path = self.output_dir / "wacz" / f"{domain}_{timestamp.replace(':', '-')}.wacz"
        cmd = [
            "wacz",
            "create",
            warc_path,
            "-o",
            str(output_path),
            "--detect-pages",
            "--url",
            source_url,
            "--title",
            domain,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0 and output_path.exists():
                return str(output_path)

            logger.warning(f"WACZ generation failed (exit={result.returncode}): {result.stderr[:300]}")
            return None
        except Exception as e:
            logger.warning(f"WACZ generation failed: {e}")
            return None
    
    def _generate_har(
        self,
        url: str,
        requests: List[NetworkRequest],
        responses: List[NetworkResponse]
    ) -> Dict:
        """Generate HAR (HTTP Archive) format data."""
        entries = []
        
        # Match requests with responses
        response_map = {r.url: r for r in responses}
        
        for req in requests:
            resp = response_map.get(req.url)
            
            entry = {
                "startedDateTime": datetime.fromtimestamp(req.timestamp).isoformat(),
                "time": 0,
                "request": {
                    "method": req.method,
                    "url": req.url,
                    "httpVersion": "HTTP/1.1",
                    "headers": [{"name": k, "value": v} for k, v in req.headers.items()],
                    "queryString": [],
                    "cookies": [],
                    "headersSize": -1,
                    "bodySize": len(req.post_data) if req.post_data else 0,
                    "postData": {
                        "mimeType": req.headers.get('content-type', ''),
                        "text": req.post_data or ""
                    } if req.post_data else None
                },
                "response": {
                    "status": resp.status if resp else 0,
                    "statusText": resp.status_text if resp else "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [{"name": k, "value": v} for k, v in (resp.headers if resp else {}).items()],
                    "cookies": [],
                    "content": {
                        "size": len(resp.body) if resp else 0,
                        "mimeType": resp.mime_type if resp else "",
                        "text": base64.b64encode(resp.body).decode() if resp and resp.body else ""
                    },
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": len(resp.body) if resp else 0
                },
                "cache": {},
                "timings": {
                    "send": 0,
                    "wait": 0,
                    "receive": 0
                }
            }
            
            if resp:
                entry["time"] = (resp.timestamp - req.timestamp) * 1000
            
            entries.append(entry)
        
        return {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "DeathStar Forensic Capture",
                    "version": "2.0"
                },
                "entries": entries,
                "pages": [{
                    "startedDateTime": datetime.now().isoformat(),
                    "id": "page_1",
                    "title": url,
                    "pageTimings": {}
                }]
            }
        }
    
    async def _generate_warc(
        self,
        url: str,
        html: str,
        requests: List[NetworkRequest],
        responses: List[NetworkResponse],
        domain: str,
        timestamp: str
    ) -> Optional[str]:
        """Generate WARC archive file."""
        try:
            from warcio.warcwriter import WARCWriter
            from warcio.statusandheaders import StatusAndHeaders
        except ImportError:
            logger.warning("warcio not installed. Run: pip install warcio")
            # Fallback: save as WARC-like JSON
            return await self._generate_warc_fallback(url, html, requests, responses, domain, timestamp)
        
        filename = f"{domain}_{timestamp.replace(':', '-')}.warc.gz"
        filepath = self.output_dir / "warc" / filename
        
        with open(filepath, 'wb') as fh:
            writer = WARCWriter(fh, gzip=True)
            
            # Write warcinfo record
            warcinfo = writer.create_warcinfo_record(filepath.name, {
                'software': 'DeathStar Forensic Capture v2.0',
                'format': 'WARC File Format 1.1',
                'conformsTo': 'http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1-1_latestdraft.pdf'
            })
            writer.write_record(warcinfo)
            
            # Write response records
            response_map = {r.url: r for r in responses}
            
            for req in requests:
                resp = response_map.get(req.url)
                if not resp or not resp.body:
                    continue
                
                # Build HTTP response header
                http_headers = StatusAndHeaders(
                    f'{resp.status} {resp.status_text}',
                    list(resp.headers.items()),
                    protocol='HTTP/1.1'
                )
                
                # Create response record (warcio expects file-like with .read(), not raw bytes)
                record = writer.create_warc_record(
                    req.url,
                    'response',
                    payload=io.BytesIO(resp.body),
                    http_headers=http_headers
                )
                writer.write_record(record)
        
        return str(filepath)
    
    async def _generate_warc_fallback(
        self,
        url: str,
        html: str,
        requests: List[NetworkRequest],
        responses: List[NetworkResponse],
        domain: str,
        timestamp: str
    ) -> str:
        """Fallback WARC-like format when warcio not available."""
        filename = f"{domain}_{timestamp.replace(':', '-')}.warc.json"
        filepath = self.output_dir / "warc" / filename
        
        data = {
            "warc_version": "1.1-fallback",
            "software": "DeathStar Forensic Capture v2.0",
            "timestamp": timestamp,
            "target_uri": url,
            "records": []
        }
        
        response_map = {r.url: r for r in responses}
        
        for req in requests:
            resp = response_map.get(req.url)
            
            record = {
                "type": "request",
                "url": req.url,
                "method": req.method,
                "headers": req.headers,
                "timestamp": req.timestamp
            }
            data["records"].append(record)
            
            if resp:
                response_record = {
                    "type": "response",
                    "url": resp.url,
                    "status": resp.status,
                    "headers": resp.headers,
                    "body_hash": resp.body_hash,
                    "body_size": len(resp.body),
                    "body_base64": base64.b64encode(resp.body[:10000]).decode() if resp.body else "",  # First 10KB
                    "timestamp": resp.timestamp
                }
                data["records"].append(response_record)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        return str(filepath)


def extract_article_content(html: str) -> Dict[str, Optional[str]]:
    """Extract readable article-oriented content using optional extractors."""
    result = {
        "method": None,
        "title": None,
        "html": None,
        "text": None,
    }

    # 1) Prefer readability-lxml when installed.
    try:
        from readability import Document

        doc = Document(html)
        article_html = doc.summary(html_partial=True)
        article_title = (doc.short_title() or "").strip() or None
        article_text = re.sub(r"<[^>]+>", " ", article_html)
        article_text = re.sub(r"\s+", " ", article_text).strip()

        if article_html and article_text:
            result.update({
                "method": "readability-lxml",
                "title": article_title,
                "html": article_html,
                "text": article_text,
            })
            return result
    except Exception:
        pass

    # 2) Fallback to trafilatura when available.
    try:
        import trafilatura

        article_text = trafilatura.extract(
            html,
            include_links=False,
            include_images=False,
            include_tables=True,
        )
        article_html = trafilatura.extract(
            html,
            output_format="html",
            include_links=True,
            include_images=False,
        )
        if article_text:
            result.update({
                "method": "trafilatura",
                "html": article_html,
                "text": article_text,
            })
            return result
    except Exception:
        pass

    return result


# =============================================================================
# STANDALONE FUNCTIONS
# =============================================================================

async def capture_url_forensically(
    url: str,
    output_dir: str = "data/forensic",
    generate_wacz: bool = False,
) -> ForensicResult:
    """
    Convenience function to forensically capture a URL.
    
    Args:
        url: URL to capture
        output_dir: Output directory
    
    Returns:
        ForensicResult with all captured data
    """
    capture = ForensicCapture(output_dir=Path(output_dir))
    return await capture.capture_page(url, generate_wacz=generate_wacz)


def save_forensic_result(result: ForensicResult, output_dir: Path):
    """Save forensic result to disk."""
    parsed = urlparse(result.url)
    domain = (parsed.hostname or parsed.netloc).replace("www.", "")
    domain = safe_path_component(domain)
    timestamp = result.timestamp.replace(":", "-")
    
    # Create output directory
    result_dir = output_dir / "results" / f"{domain}_{timestamp}"
    result_dir.mkdir(parents=True, exist_ok=True)
    
    article = extract_article_content(result.raw_html)
    article_html_path = None
    article_text_path = None
    if article.get("html"):
        article_html_path = str(result_dir / "article.html")
        with open(result_dir / "article.html", "w", encoding="utf-8") as f:
            f.write(article["html"])
    if article.get("text"):
        article_text_path = str(result_dir / "article.txt")
        with open(result_dir / "article.txt", "w", encoding="utf-8") as f:
            f.write(article["text"])

    # Save metadata
    metadata = {
        "url": result.url,
        "final_url": result.final_url,
        "timestamp": result.timestamp,
        "content_hash": result.content_hash,
        "metadata": result.metadata,
        "headers": result.headers,
        "cookies": result.cookies,
        "local_storage": result.local_storage,
        "session_storage": result.session_storage,
        "certificate": result.certificate,
        "dns_records": result.dns_records,
        "security_headers": result.security_headers,
        "internal_links_count": len(result.internal_links),
        "external_links_count": len(result.external_links),
        "assets_count": len(result.assets),
        "requests_count": len(result.requests),
        "screenshot_path": result.screenshot_path,
        "pdf_path": result.pdf_path,
        "mhtml_path": result.mhtml_path,
        "favicon_path": result.favicon_path,
        "warc_path": result.warc_path,
        "wacz_path": result.wacz_path,
        "article_extraction_method": article.get("method"),
        "article_title": article.get("title"),
        "article_html_path": article_html_path,
        "article_text_path": article_text_path,
    }
    
    with open(result_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    # Save HTML
    with open(result_dir / "raw.html", "w", encoding="utf-8") as f:
        f.write(result.raw_html)
    
    with open(result_dir / "dom_snapshot.html", "w", encoding="utf-8") as f:
        f.write(result.dom_snapshot)
    
    # Save text
    with open(result_dir / "clean_text.txt", "w", encoding="utf-8") as f:
        f.write(result.clean_text)
    
    # Save links
    with open(result_dir / "internal_links.txt", "w") as f:
        f.write("\n".join(result.internal_links))
    
    with open(result_dir / "external_links.txt", "w") as f:
        f.write("\n".join(result.external_links))
    
    with open(result_dir / "resource_links.txt", "w") as f:
        f.write("\n".join(result.resource_links))
    
    # Save HAR
    if result.har_data:
        with open(result_dir / "network.har", "w") as f:
            json.dump(result.har_data, f, indent=2)
    
    logger.info(f"Forensic result saved to: {result_dir}")
    return result_dir


if __name__ == "__main__":
    def _is_http_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    parser = argparse.ArgumentParser(
        description="Run a standalone forensic capture for a single URL."
    )
    parser.add_argument("url", help="Target URL (must include http:// or https://)")
    parser.add_argument(
        "--output",
        "-o",
        default="data/forensic",
        help="Output directory (default: data/forensic)",
    )
    parser.add_argument(
        "--wacz",
        action="store_true",
        help="Generate WACZ package when warc and wacz CLI are available",
    )
    args = parser.parse_args()

    if not _is_http_url(args.url):
        parser.error("url must include a valid http:// or https:// scheme")

    async def main():
        result = await capture_url_forensically(
            args.url,
            output_dir=args.output,
            generate_wacz=args.wacz,
        )
        result_dir = save_forensic_result(result, Path(args.output))
        print("\nForensic capture complete")
        print(f"   URL: {result.url}")
        print(f"   Requests captured: {len(result.requests)}")
        print(f"   Assets captured: {len(result.assets)}")
        print(f"   Screenshot: {result.screenshot_path}")
        print(f"   WARC: {result.warc_path}")
        if result.wacz_path:
            print(f"   WACZ: {result.wacz_path}")
        if result.mhtml_path:
            print(f"   MHTML: {result.mhtml_path}")
        print(f"   Output: {result_dir}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
