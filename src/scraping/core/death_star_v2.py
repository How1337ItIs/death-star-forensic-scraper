#!/usr/bin/env python3
"""
DEATH STAR V2 - "Nuke From Orbit" Web Scraper
==============================================

The ultimate all-purpose web scraper. Leave no stone unturned.

Features:
---------
1. MULTI-TOOL ARSENAL:
   - wget recursive (fast, reliable baseline)
   - ArchiveBox (full archival: HTML, PDF, WARC, screenshots)
   - Playwright stealth (JS rendering, anti-bot evasion)
   - Trafilatura (LLM-ready content extraction)
   - Direct HTTP (fast static pages)

2. ANTI-BOT EVASION:
   - User-Agent rotation
   - Proxy rotation with session management
   - Human-like delays and behavior
   - Stealth browser fingerprinting
   - Cloudflare/bot detection bypass

3. RESILIENCE:
   - SQLite WAL checkpoint/resume (crash-proof)
   - Exponential backoff with jitter
   - Domain-aware rate limiting
   - Graceful shutdown handling

4. INTELLIGENCE:
   - Adaptive routing (static vs JS rendering)
   - robots.txt compliance (optional)
   - Content deduplication
   - Metadata extraction

5. OUTPUT FLEXIBILITY:
   - Raw HTML preservation
   - Clean markdown for LLM
   - JSON/JSONL structured data
   - Full WARC archives

Usage:
------
    # Destroy a single site with all weapons
    python death_star_v2.py --target https://example.com --mode full

    # Quick static scrape (fastest)
    python death_star_v2.py --target https://example.com --mode quick

    # JS-heavy site with stealth browser
    python death_star_v2.py --target https://example.com --mode stealth

    # Resume interrupted scrape
    python death_star_v2.py --target https://example.com --resume

    # Respect robots.txt (polite mode)
    python death_star_v2.py --target https://example.com --polite

    # Multiple targets from file
    python death_star_v2.py --targets urls.txt --mode full --depth 5

Author: Deadhead-LLM Project
License: MIT
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication: lowercase scheme+host, strip fragments, normalize trailing slashes."""
    parsed = urlparse(url)
    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # Strip fragment
    # Normalize path: remove trailing slash except for root
    path = parsed.path
    if path != '/' and path.endswith('/'):
        path = path.rstrip('/')
    # Reassemble without fragment
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ''))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("death_star_v2")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Output directory
DEFAULT_OUTPUT_DIR = Path("data/scraped_sites")

# User agents pool (realistic 2025-2026 browser fingerprints)
USER_AGENTS = [
    # Chrome 134 on Windows (March 2026)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    # Chrome 133 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    # Chrome 134 on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    # Firefox 135 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    # Firefox 135 on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    # Safari 18.3 on Mac (Sonoma)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    # Edge 134 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
    # Chrome 134 on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
]

# Accept headers to rotate
ACCEPT_HEADERS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
]

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
]


@dataclass
class ScrapeConfig:
    """Configuration for scrape behavior."""
    # Rate limiting
    min_delay: float = 1.0
    max_delay: float = 3.0
    requests_per_minute: int = 30
    concurrent_per_domain: int = 2
    
    # Retry behavior
    max_retries: int = 3
    backoff_factor: float = 2.0
    
    # Depth and scope
    max_depth: int = 5
    max_pages: int = 10000
    follow_external: bool = False
    
    # Features
    respect_robots: bool = False
    extract_content: bool = True
    save_raw_html: bool = True
    save_screenshots: bool = False
    deduplicate: bool = True
    
    # Browser settings
    headless: bool = True
    browser_timeout: int = 30000  # ms
    browser_engine: str = "playwright"  # playwright, patchright, camoufox, nodriver
    cdp_endpoint: Optional[str] = None  # e.g. "http://localhost:9222" to attach to running Chrome

    # Proxy settings
    proxy_list: List[str] = field(default_factory=list)
    rotate_proxies: bool = False
    proxy_pool_file: Optional[str] = None  # File with proxy list

    # Session/Cookie settings
    cookie_file: Optional[str] = None  # Path to cookies.json (Netscape or JSON format)
    session_data: Dict[str, Any] = field(default_factory=dict)  # Custom session data

    # Authentication
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    auth_type: str = "basic"  # basic, digest, form


@dataclass
class ScrapedPage:
    """Result of scraping a single page."""
    url: str
    final_url: str
    status_code: int
    content_type: str
    raw_html: str
    clean_text: str
    markdown: str
    title: str
    links: List[str]
    media: List[str]
    metadata: Dict[str, Any]
    scraped_at: str
    method: str  # "http", "playwright", "wget", etc.
    content_hash: str


# =============================================================================
# PROXY POOL MANAGER
# =============================================================================

class ProxyPool:
    """
    Intelligent proxy rotation with health tracking.
    
    Features:
    - Load proxies from file or list
    - Track proxy health/failures
    - Automatic rotation with cooldown
    - Geographic selection (if tagged)
    """
    
    def __init__(self, proxies: List[str] = None, proxy_file: str = None):
        self.proxies: List[Dict[str, Any]] = []
        self._current_index = 0
        self._failures: Dict[str, int] = {}
        self._cooldowns: Dict[str, float] = {}
        
        if proxy_file:
            self._load_from_file(proxy_file)
        elif proxies:
            self.proxies = [self._parse_proxy(p) for p in proxies]
    
    def _load_from_file(self, filepath: str):
        """Load proxies from file (one per line)."""
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"Proxy file not found: {filepath}")
            return
        
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    self.proxies.append(self._parse_proxy(line))
                except Exception as e:
                    logger.debug(f"Invalid proxy line: {line} - {e}")
    
    def _parse_proxy(self, proxy_str: str) -> Dict[str, Any]:
        """Parse proxy string into structured format."""
        # Format: protocol://[user:pass@]host:port[@location]
        proxy = {
            'url': proxy_str,
            'protocol': 'http',
            'host': '',
            'port': 8080,
            'auth': None,
            'location': None,
        }
        
        if '://' in proxy_str:
            proxy['protocol'], rest = proxy_str.split('://', 1)
        else:
            rest = proxy_str
        
        # Check for location tag
        if '@' in rest and rest.count('@') > 1:
            rest, proxy['location'] = rest.rsplit('@', 1)
        
        # Check for auth
        if '@' in rest:
            auth, hostport = rest.rsplit('@', 1)
            if ':' in auth:
                user, passwd = auth.split(':', 1)
                proxy['auth'] = (user, passwd)
        else:
            hostport = rest
        
        # Parse host:port
        if ':' in hostport:
            proxy['host'], port = hostport.rsplit(':', 1)
            proxy['port'] = int(port)
        else:
            proxy['host'] = hostport
        
        return proxy
    
    def get_proxy(self, location: str = None) -> Optional[Dict[str, Any]]:
        """Get next available proxy."""
        if not self.proxies:
            return None
        
        now = time.time()
        available = []
        
        for proxy in self.proxies:
            url = proxy['url']
            
            # Check cooldown
            if url in self._cooldowns and self._cooldowns[url] > now:
                continue
            
            # Check failure count
            if self._failures.get(url, 0) >= 5:
                continue
            
            # Check location filter
            if location and proxy.get('location') != location:
                continue
            
            available.append(proxy)
        
        if not available:
            return None
        
        # Round-robin
        proxy = available[self._current_index % len(available)]
        self._current_index += 1
        
        return proxy
    
    def report_failure(self, proxy_url: str):
        """Report a proxy failure."""
        self._failures[proxy_url] = self._failures.get(proxy_url, 0) + 1
        # Cooldown for 60 seconds after failure
        self._cooldowns[proxy_url] = time.time() + 60
    
    def report_success(self, proxy_url: str):
        """Report successful use."""
        self._failures[proxy_url] = 0
    
    def get_playwright_proxy(self, location: str = None) -> Optional[Dict]:
        """Get proxy in Playwright format."""
        proxy = self.get_proxy(location)
        if not proxy:
            return None
        
        result = {
            'server': f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"
        }
        if proxy.get('auth'):
            result['username'], result['password'] = proxy['auth']
        
        return result
    
    def get_httpx_proxy(self, location: str = None) -> Optional[str]:
        """Get proxy URL for httpx/requests."""
        proxy = self.get_proxy(location)
        if not proxy:
            return None
        
        if proxy.get('auth'):
            return f"{proxy['protocol']}://{proxy['auth'][0]}:{proxy['auth'][1]}@{proxy['host']}:{proxy['port']}"
        return f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"


# =============================================================================
# COOKIE/SESSION MANAGER
# =============================================================================

class SessionManager:
    """
    Manage cookies and session data for authenticated scraping.
    
    Supports:
    - Netscape cookie format (from browser export)
    - JSON cookie format
    - Raw cookie strings
    """
    
    def __init__(self, cookie_file: str = None):
        self.cookies: List[Dict] = []
        self.headers: Dict[str, str] = {}
        
        if cookie_file:
            self._load_cookies(cookie_file)
    
    def _load_cookies(self, filepath: str):
        """Load cookies from file."""
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"Cookie file not found: {filepath}")
            return
        
        content = path.read_text()
        
        # Try JSON format first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                self.cookies = data
            elif isinstance(data, dict):
                self.cookies = [data]
            logger.info(f"Loaded {len(self.cookies)} cookies from JSON")
            return
        except json.JSONDecodeError:
            pass
        
        # Try Netscape format
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('\t')
            if len(parts) >= 7:
                self.cookies.append({
                    'domain': parts[0],
                    'httpOnly': parts[1].lower() == 'true',
                    'path': parts[2],
                    'secure': parts[3].lower() == 'true',
                    'expires': int(parts[4]) if parts[4].isdigit() else 0,
                    'name': parts[5],
                    'value': parts[6],
                })
        
        logger.info(f"Loaded {len(self.cookies)} cookies from Netscape format")
    
    def get_cookies_for_domain(self, domain: str) -> List[Dict]:
        """Get cookies applicable to a domain."""
        result = []
        for cookie in self.cookies:
            cookie_domain = cookie.get('domain', '')
            if domain.endswith(cookie_domain.lstrip('.')):
                result.append(cookie)
        return result
    
    def get_cookie_header(self, domain: str) -> str:
        """Get Cookie header value for a domain."""
        cookies = self.get_cookies_for_domain(domain)
        return '; '.join(f"{c['name']}={c['value']}" for c in cookies)
    
    def get_playwright_cookies(self, domain: str = None) -> List[Dict]:
        """Get cookies in Playwright format."""
        cookies = self.cookies if not domain else self.get_cookies_for_domain(domain)
        
        result = []
        for c in cookies:
            cookie = {
                'name': c.get('name', ''),
                'value': c.get('value', ''),
                'domain': c.get('domain', ''),
                'path': c.get('path', '/'),
            }
            if 'expires' in c and c['expires']:
                cookie['expires'] = c['expires']
            if 'httpOnly' in c:
                cookie['httpOnly'] = c['httpOnly']
            if 'secure' in c:
                cookie['secure'] = c['secure']
            result.append(cookie)
        
        return result
    
    def add_auth_headers(self, username: str, password: str, auth_type: str = 'basic'):
        """Add authentication headers."""
        import base64
        
        if auth_type == 'basic':
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.headers['Authorization'] = f"Basic {credentials}"


# =============================================================================
# CHECKPOINT MANAGER (Enhanced)
# =============================================================================

class EnhancedCheckpoint:
    """
    Enhanced checkpoint manager with domain-aware state tracking.
    
    Tracks:
    - URLs queued, completed, failed
    - Content hashes for deduplication
    - Domain rate limit state
    - Session metadata
    """
    
    def __init__(self, name: str, db_dir: str = "data/scraping_state"):
        self.name = name
        self.db_path = Path(db_dir) / f"{name}_v2.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        import sqlite3
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')
        self._init_schema()
        
    def _init_schema(self):
        """Initialize database schema."""
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                domain TEXT,
                depth INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                method TEXT,
                content_hash TEXT,
                error TEXT,
                added_at TEXT,
                completed_at TEXT
            );
            
            CREATE TABLE IF NOT EXISTS content_hashes (
                hash TEXT PRIMARY KEY,
                url TEXT,
                added_at TEXT
            );
            
            CREATE TABLE IF NOT EXISTS domain_state (
                domain TEXT PRIMARY KEY,
                last_request_at TEXT,
                request_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                robots_parsed INTEGER DEFAULT 0,
                robots_rules TEXT
            );
            
            CREATE TABLE IF NOT EXISTS session (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);
            CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain);
        ''')
        self.conn.commit()
    
    def add_url(self, url: str, depth: int = 0) -> bool:
        """Add URL to queue if not already present."""
        url = normalize_url(url)
        domain = urlparse(url).netloc
        try:
            self.conn.execute('''
                INSERT OR IGNORE INTO urls (url, domain, depth, added_at)
                VALUES (?, ?, ?, ?)
            ''', (url, domain, depth, datetime.now().isoformat()))
            self.conn.commit()
            return True
        except Exception as e:
            logger.debug(f"Failed to add URL {url}: {e}")
            return False

    def add_urls(self, urls: List[str], depth: int = 0):
        """Batch add URLs."""
        for url in urls:
            self.add_url(url, depth)
    
    def get_pending(self, limit: int = 100) -> List[Dict]:
        """Get pending URLs, ordered by depth (breadth-first)."""
        cursor = self.conn.execute('''
            SELECT url, domain, depth FROM urls
            WHERE status = 'pending'
            ORDER BY depth ASC, added_at ASC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in cursor]
    
    def mark_complete(self, url: str, method: str, content_hash: str = None):
        """Mark URL as completed."""
        self.conn.execute('''
            UPDATE urls SET
                status = 'complete',
                method = ?,
                content_hash = ?,
                completed_at = ?
            WHERE url = ?
        ''', (method, content_hash, datetime.now().isoformat(), url))
        self.conn.commit()
    
    def mark_failed(self, url: str, error: str):
        """Mark URL as failed."""
        self.conn.execute('''
            UPDATE urls SET status = 'failed', error = ? WHERE url = ?
        ''', (error, url))
        self.conn.commit()
    
    def is_duplicate_content(self, content_hash: str) -> bool:
        """Check if content hash already exists."""
        row = self.conn.execute(
            'SELECT 1 FROM content_hashes WHERE hash = ?', (content_hash,)
        ).fetchone()
        return row is not None
    
    def add_content_hash(self, content_hash: str, url: str):
        """Register content hash."""
        self.conn.execute('''
            INSERT OR IGNORE INTO content_hashes (hash, url, added_at)
            VALUES (?, ?, ?)
        ''', (content_hash, url, datetime.now().isoformat()))
        self.conn.commit()
    
    def get_domain_state(self, domain: str) -> Dict:
        """Get rate limiting state for domain."""
        row = self.conn.execute(
            'SELECT * FROM domain_state WHERE domain = ?', (domain,)
        ).fetchone()
        if row:
            return dict(row)
        return {'domain': domain, 'last_request_at': None, 'request_count': 0}
    
    def update_domain_state(self, domain: str, last_request_at: str = None):
        """Update domain state after request."""
        now = last_request_at or datetime.now().isoformat()
        self.conn.execute('''
            INSERT INTO domain_state (domain, last_request_at, request_count)
            VALUES (?, ?, 1)
            ON CONFLICT(domain) DO UPDATE SET
                last_request_at = ?,
                request_count = request_count + 1
        ''', (domain, now, now))
        self.conn.commit()
    
    def stats(self) -> Dict:
        """Get scraping statistics."""
        rows = self.conn.execute('''
            SELECT status, COUNT(*) as count FROM urls GROUP BY status
        ''').fetchall()
        stats = {row['status']: row['count'] for row in rows}
        stats['total'] = sum(stats.values())
        return stats
    
    def close(self):
        """Close database connection."""
        self.conn.close()


# =============================================================================
# ROBOTS.TXT HANDLER
# =============================================================================

class RobotsHandler:
    """Handles robots.txt parsing and compliance."""
    
    def __init__(self):
        self._parsers: Dict[str, RobotFileParser] = {}
        self._user_agent = "DeadheadLLM-Research/2.0"
    
    def can_fetch(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        if domain not in self._parsers:
            self._load_robots(parsed.scheme, domain)
        
        parser = self._parsers.get(domain)
        if parser:
            return parser.can_fetch(self._user_agent, url)
        return True  # Allow if we couldn't fetch robots.txt
    
    def get_crawl_delay(self, domain: str) -> Optional[float]:
        """Get crawl delay from robots.txt."""
        parser = self._parsers.get(domain)
        if parser:
            delay = parser.crawl_delay(self._user_agent)
            return delay
        return None
    
    def _load_robots(self, scheme: str, domain: str):
        """Load and parse robots.txt for domain."""
        robots_url = f"{scheme}://{domain}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            self._parsers[domain] = parser
            logger.debug(f"Loaded robots.txt for {domain}")
        except Exception as e:
            logger.debug(f"Could not load robots.txt for {domain}: {e}")
            self._parsers[domain] = None


# =============================================================================
# HTTP FETCHER (Static pages)
# =============================================================================

class HTTPFetcher:
    """Fast HTTP fetcher for static pages."""
    
    def __init__(self, config: ScrapeConfig):
        self.config = config
        self._session = None
    
    def _get_session(self):
        """Get or create requests session."""
        if self._session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            self._session = requests.Session()
            
            # Configure retries
            retry = Retry(
                total=self.config.max_retries,
                backoff_factor=self.config.backoff_factor,
                status_forcelist=[429, 500, 502, 503, 504]
            )
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)
        
        return self._session
    
    def _get_headers(self) -> Dict[str, str]:
        """Get randomized request headers."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": random.choice(ACCEPT_HEADERS),
            "Accept-Language": random.choice(ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    def _fetch_curl_cffi(self, url: str, headers: Dict[str, str]):
        """Try fetching with curl_cffi for TLS/JA3/HTTP2 fingerprint impersonation."""
        from curl_cffi.requests import Session as CffiSession
        timeout = self.config.browser_timeout / 1000
        session = CffiSession(impersonate="chrome131")
        try:
            return session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        except Exception:
            # Retry without SSL verification
            return session.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)

    def _fetch_httpx(self, url: str, headers: Dict[str, str]):
        """Try fetching with httpx (HTTP/2 support)."""
        import httpx
        timeout = self.config.browser_timeout / 1000
        try:
            with httpx.Client(http2=True, follow_redirects=True, timeout=timeout) as client:
                return client.get(url, headers=headers)
        except Exception:
            # Retry without SSL verification
            with httpx.Client(http2=True, follow_redirects=True, timeout=timeout, verify=False) as client:
                return client.get(url, headers=headers)

    def fetch(self, url: str) -> Optional[ScrapedPage]:
        """Fetch a page via HTTP.

        Tries engines in order for best TLS fingerprint impersonation:
        1. curl_cffi (Chrome TLS/JA3/HTTP2 fingerprint impersonation)
        2. httpx (HTTP/2 support)
        3. requests (fallback)
        """
        headers = self._get_headers()
        response = None
        method = "http"

        # Try curl_cffi first (best TLS fingerprint impersonation)
        try:
            response = self._fetch_curl_cffi(url, headers)
            method = "http-curl_cffi"
            logger.debug(f"Using curl_cffi for {url}")
        except ImportError:
            logger.debug("curl_cffi not installed, trying httpx")
        except Exception as e:
            logger.debug(f"curl_cffi failed for {url}: {e}, trying httpx")

        # Try httpx next (HTTP/2 support)
        if response is None:
            try:
                response = self._fetch_httpx(url, headers)
                method = "http-httpx"
                logger.debug(f"Using httpx for {url}")
            except ImportError:
                logger.debug("httpx not installed, falling back to requests")
            except Exception as e:
                logger.debug(f"httpx failed for {url}: {e}, falling back to requests")

        # Fall back to requests
        if response is None:
            try:
                session = self._get_session()
                response = session.get(
                    url,
                    headers=headers,
                    timeout=self.config.browser_timeout / 1000,
                    allow_redirects=True
                )
                method = "http-requests"
            except Exception as e:
                logger.warning(f"HTTP fetch failed for {url}: {e}")
                return None

        try:
            content_type = response.headers.get('Content-Type', '')

            # Only process HTML
            if 'text/html' not in content_type.lower():
                return None

            raw_html = response.text
            final_url = str(response.url) if hasattr(response, 'url') else url

            # Extract content
            title, clean_text, markdown, links, media = self._extract_content(
                raw_html, final_url
            )

            content_hash = hashlib.sha256(clean_text.encode()).hexdigest()[:16]

            # Extract elapsed time (differs by library)
            elapsed_ms = (
                response.elapsed.total_seconds() * 1000
                if hasattr(response, 'elapsed') and response.elapsed
                else 0
            )

            return ScrapedPage(
                url=url,
                final_url=final_url,
                status_code=response.status_code,
                content_type=content_type,
                raw_html=raw_html,
                clean_text=clean_text,
                markdown=markdown,
                title=title,
                links=links,
                media=media,
                metadata={
                    "headers": dict(response.headers),
                    "elapsed_ms": elapsed_ms,
                    "http_engine": method
                },
                scraped_at=datetime.now().isoformat(),
                method=method,
                content_hash=content_hash
            )

        except Exception as e:
            logger.warning(f"HTTP fetch failed for {url}: {e}")
            return None
    
    def _extract_content(self, html: str, base_url: str) -> tuple:
        """Extract content from HTML."""
        try:
            # Try trafilatura first (best for article extraction)
            import trafilatura
            
            clean_text = trafilatura.extract(
                html,
                include_links=False,
                include_images=False,
                include_tables=True
            ) or ""
            
            # Get markdown version
            markdown = trafilatura.extract(
                html,
                output_format='markdown',
                include_links=True,
                include_images=True
            ) or clean_text
            
        except ImportError:
            # Fallback to basic extraction
            from html.parser import HTMLParser
            
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self._skip = False
                    
                def handle_starttag(self, tag, attrs):
                    if tag in ('script', 'style', 'noscript'):
                        self._skip = True
                        
                def handle_endtag(self, tag):
                    if tag in ('script', 'style', 'noscript'):
                        self._skip = False
                        
                def handle_data(self, data):
                    if not self._skip:
                        self.text.append(data.strip())
            
            extractor = TextExtractor()
            extractor.feed(html)
            clean_text = ' '.join(t for t in extractor.text if t)
            markdown = clean_text
        
        # Extract title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract links
        links = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            href = match.group(1)
            if href.startswith(('http://', 'https://', '/')):
                full_url = urljoin(base_url, href)
                links.append(full_url)
        
        # Extract media
        media = []
        for match in re.finditer(r'src=["\']([^"\']+)["\']', html, re.I):
            src = match.group(1)
            if any(ext in src.lower() for ext in ['.jpg', '.png', '.gif', '.webp', '.mp4', '.mp3']):
                media.append(urljoin(base_url, src))
        
        return title, clean_text, markdown, links, media


# =============================================================================
# PLAYWRIGHT FETCHER (JS-heavy sites with stealth)
# =============================================================================

class PlaywrightFetcher:
    """
    Stealth browser fetcher for JS-heavy sites.

    Features:
    - CDP connection mode (attach to running Chrome)
    - Cookie injection from SessionManager
    - Proxy injection from ProxyPool
    - Browser engine escalation (playwright -> rebrowser -> patchright -> camoufox -> nodriver)
    - __NEXT_DATA__ extraction for Next.js sites
    - GraphQL response interception
    - In-browser fetch() for anti-bot evasion
    """

    # Browser engines in escalation order (most compatible -> most stealthy)
    BROWSER_ENGINES = ["playwright", "rebrowser", "patchright", "camoufox", "nodriver"]

    def __init__(
        self,
        config: ScrapeConfig,
        session_manager: Optional['SessionManager'] = None,
        proxy_pool: Optional['ProxyPool'] = None,
    ):
        self.config = config
        self.session_manager = session_manager
        self.proxy_pool = proxy_pool
        self._browser = None
        self._context = None
        self._playwright = None
        self._is_cdp = False  # True when connected via CDP
        self._captured_graphql: List[Dict] = []  # Intercepted GraphQL responses

    def _get_async_playwright(self):
        """Import the right async_playwright based on config.browser_engine."""
        engine = self.config.browser_engine
        if engine == "rebrowser":
            try:
                from rebrowser_playwright.async_api import async_playwright
                logger.info("Using rebrowser-playwright (stealth Playwright fork)")
                return async_playwright
            except ImportError:
                logger.warning("rebrowser-playwright not installed, falling back to playwright")
        elif engine == "patchright":
            try:
                from patchright.async_api import async_playwright
                logger.info("Using patchright (stealth-patched Playwright)")
                return async_playwright
            except ImportError:
                logger.warning("patchright not installed, falling back to playwright")
        elif engine == "camoufox":
            try:
                from camoufox.async_api import AsyncCamoufox
                logger.info("Using camoufox (Firefox-based stealth)")
                return AsyncCamoufox
            except ImportError:
                logger.warning("camoufox not installed, falling back to playwright")

        # Default: standard playwright
        from playwright.async_api import async_playwright
        return async_playwright

    async def _ensure_browser(self):
        """Ensure browser is running. Supports CDP, launch, and engine selection."""
        if self._browser is not None:
            return True

        # --- CDP connection mode: attach to an already-running Chrome ---
        if self.config.cdp_endpoint:
            return await self._connect_cdp()

        # --- Standard launch mode ---
        return await self._launch_browser()

    async def _connect_cdp(self) -> bool:
        """Connect to a running Chrome instance via CDP."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False

        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.config.cdp_endpoint, timeout=15000
            )
            self._is_cdp = True

            # Use the existing browser context (the user's real session)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()

            logger.info(f"Connected to Chrome via CDP at {self.config.cdp_endpoint}")
            logger.info(f"  Pages open: {len(self._context.pages)}")
            return True
        except Exception as e:
            logger.error(f"CDP connection failed: {e}")
            return False

    async def _launch_browser(self) -> bool:
        """Launch a new browser instance with stealth, cookies, and proxy."""
        try:
            async_pw = self._get_async_playwright()
        except ImportError:
            logger.error("No browser engine available. Install: pip install playwright && playwright install chromium")
            return False

        try:
            self._playwright = await async_pw().start()

            # Build launch args
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--disable-gpu',
            ]

            # Proxy from pool
            proxy_config = None
            if self.proxy_pool:
                proxy_config = self.proxy_pool.get_playwright_proxy()
                if proxy_config:
                    logger.info(f"Using proxy: {proxy_config['server']}")

            launch_kwargs = dict(
                headless=self.config.headless,
                args=launch_args,
            )
            if proxy_config:
                launch_kwargs['proxy'] = proxy_config

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)

            # Context with realistic viewport
            context_kwargs = dict(
                viewport={'width': 1920, 'height': 1080},
                user_agent=random.choice(USER_AGENTS),
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                java_script_enabled=True,
            )
            if proxy_config:
                context_kwargs['proxy'] = proxy_config

            self._context = await self._browser.new_context(**context_kwargs)

            # Inject cookies from SessionManager
            if self.session_manager and self.session_manager.cookies:
                pw_cookies = self.session_manager.get_playwright_cookies()
                if pw_cookies:
                    await self._context.add_cookies(pw_cookies)
                    logger.info(f"Injected {len(pw_cookies)} cookies into browser context")

            # Apply stealth scripts
            await self._apply_stealth()

            return True
        except Exception as e:
            logger.error(f"Browser launch failed: {e}")
            return False

    async def _apply_stealth(self):
        """Apply stealth modifications to evade detection."""
        stealth_js = """
        // Pass webdriver check
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Pass chrome check
        window.chrome = { runtime: {} };

        // Pass permissions check
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Pass plugins check
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Pass languages check
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });

        // Remove automation indicators
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """

        await self._context.add_init_script(stealth_js)

    # ------------------------------------------------------------------
    # In-browser fetch (bypasses anti-bot by executing inside the page)
    # ------------------------------------------------------------------

    async def in_browser_fetch(self, page, path: str, parse_next_data: bool = True) -> Optional[Dict]:
        """
        Use the page's own fetch() to request a URL, carrying all cookies/tokens.
        This is the key anti-bot pattern: PerimeterX and similar systems allow
        requests that originate from the page's own JavaScript context.

        Args:
            page: Playwright page object
            path: URL path (e.g. "/orders?dateFilter=year-2")
            parse_next_data: If True, parse __NEXT_DATA__ from HTML response

        Returns:
            Dict with response data, or None on failure
        """
        js = """async (path, parseNextData) => {
            try {
                const resp = await fetch(path, {
                    credentials: "include",
                    headers: { "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" }
                });
                const html = await resp.text();
                const result = { status: resp.status, url: resp.url, htmlLength: html.length };

                if (parseNextData) {
                    const match = html.match(/<script id="__NEXT_DATA__"[^>]*>(.*?)<\\/script>/s);
                    if (match) {
                        try {
                            result.nextData = JSON.parse(match[1]);
                        } catch(e) {
                            result.nextDataError = e.message;
                        }
                    }
                }
                result.html = html;
                return result;
            } catch(e) {
                return { error: e.message };
            }
        }"""
        try:
            return await page.evaluate(js, [path, parse_next_data])
        except Exception as e:
            logger.warning(f"In-browser fetch failed for {path}: {e}")
            return None

    # ------------------------------------------------------------------
    # __NEXT_DATA__ extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_next_data(html: str) -> Optional[Dict]:
        """Extract __NEXT_DATA__ JSON from a Next.js page's HTML."""
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------------
    # GraphQL response interception
    # ------------------------------------------------------------------

    async def install_graphql_interceptor(self, page, url_pattern: str = "graphql"):
        """
        Install a response listener that captures GraphQL responses.
        Captured responses are stored in self._captured_graphql.
        """
        async def _on_response(response):
            if url_pattern in response.url:
                try:
                    body = await response.json()
                    self._captured_graphql.append({
                        "url": response.url,
                        "status": response.status,
                        "data": body,
                        "timestamp": time.time(),
                    })
                    logger.debug(f"Captured GraphQL response: {response.url[:120]}")
                except Exception as e:
                    logger.debug(f"Failed to capture GraphQL response: {e}")

        page.on("response", _on_response)

    def get_captured_graphql(self, clear: bool = True) -> List[Dict]:
        """Return captured GraphQL responses, optionally clearing the buffer."""
        result = list(self._captured_graphql)
        if clear:
            self._captured_graphql.clear()
        return result

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    async def fetch(self, url: str) -> Optional[ScrapedPage]:
        """Fetch page with stealth browser."""
        if not await self._ensure_browser():
            return None

        page = None
        try:
            page = await self._context.new_page()

            # Install GraphQL interceptor
            await self.install_graphql_interceptor(page)

            # Navigate with human-like behavior
            # Try networkidle first, fall back to domcontentloaded on timeout
            try:
                response = await page.goto(
                    url,
                    wait_until='networkidle',
                    timeout=self.config.browser_timeout
                )
            except Exception:
                logger.debug(f"networkidle timeout, retrying with domcontentloaded: {url}")
                response = await page.goto(
                    url,
                    wait_until='domcontentloaded',
                    timeout=self.config.browser_timeout
                )
                # Give a bit more time for JS to render
                await asyncio.sleep(2.0)

            if not response:
                return None

            # Random scroll to trigger lazy loading
            await self._human_scroll(page)

            # Wait a bit for any dynamic content
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Get content
            raw_html = await page.content()

            # Also capture Shadow DOM content if present
            try:
                shadow_content = await self._extract_with_shadow_dom(page)
                if shadow_content and len(shadow_content) > len(raw_html):
                    metadata["has_shadow_dom"] = True
                    metadata["shadow_dom_html"] = shadow_content
            except Exception as e:
                logger.debug(f"Shadow DOM extraction failed: {e}")

            title = await page.title()
            final_url = page.url

            # Extract __NEXT_DATA__ if present (structured JSON from Next.js)
            next_data = self.extract_next_data(raw_html)

            # Extract text content (guard: document.body null for SVG/non-HTML)
            clean_text = await page.evaluate('''
                () => {
                    if (!document.body) return '';
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(s => s.remove());
                    return document.body.innerText || '';
                }
            ''')

            # Extract links
            links = await page.evaluate('''
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(href => href.startsWith('http'))
            ''')

            # Extract media
            media = await page.evaluate('''
                () => Array.from(document.querySelectorAll('img[src], video[src], audio[src]'))
                    .map(el => el.src)
                    .filter(src => src.startsWith('http'))
            ''')

            content_hash = hashlib.sha256(clean_text.encode()).hexdigest()[:16]

            # Optional screenshot
            screenshot_data = None
            if self.config.save_screenshots:
                screenshot_data = await page.screenshot(full_page=True)

            metadata = {
                "screenshot": screenshot_data is not None,
                "js_rendered": True,
                "browser_engine": self.config.browser_engine,
                "cdp_mode": self._is_cdp,
            }
            if next_data:
                metadata["has_next_data"] = True
                metadata["next_data"] = next_data
            graphql_captures = self.get_captured_graphql()
            if graphql_captures:
                metadata["graphql_responses"] = graphql_captures

            return ScrapedPage(
                url=url,
                final_url=final_url,
                status_code=response.status,
                content_type=response.headers.get('content-type', ''),
                raw_html=raw_html,
                clean_text=clean_text,
                markdown=clean_text,
                title=title,
                links=links,
                media=media,
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
                method="playwright" if not self._is_cdp else "playwright-cdp",
                content_hash=content_hash
            )

        except Exception as e:
            logger.warning(f"Playwright fetch failed for {url}: {e}")
            return None
        finally:
            if page and not self._is_cdp:
                await page.close()

    async def fetch_with_escalation(self, url: str) -> Optional[ScrapedPage]:
        """
        Try fetching with the configured engine; on anti-bot block, escalate
        through stealthier engines: playwright -> rebrowser -> patchright -> camoufox -> nodriver.
        """
        engines = self.BROWSER_ENGINES
        start_idx = engines.index(self.config.browser_engine) if self.config.browser_engine in engines else 0

        for engine in engines[start_idx:]:
            self.config.browser_engine = engine
            await self.close()  # Reset browser for new engine

            logger.info(f"Attempting fetch with engine: {engine}")
            result = await self.fetch(url)

            if result and result.status_code not in (403, 418, 429, 503):
                return result

            logger.warning(f"Engine {engine} blocked (status={result.status_code if result else 'N/A'}), escalating...")

        return None

    async def get_page_for_domain(self, domain: str):
        """
        In CDP mode, find an existing page/tab for the given domain.
        Useful for reusing an already-authenticated session.
        """
        if not self._context:
            return None
        for page in self._context.pages:
            if domain in page.url:
                return page
        return None

    async def _human_scroll(self, page, max_scrolls: int = 30):
        """Scroll page to trigger infinite scroll and lazy loading."""
        try:
            previous_height = 0
            idle_count = 0

            for i in range(max_scrolls):
                current_height = await page.evaluate('document.body.scrollHeight')
                if current_height == previous_height:
                    idle_count += 1
                    if idle_count >= 3:
                        break
                else:
                    idle_count = 0
                previous_height = current_height

                # Scroll to bottom with random offset
                scroll_to = current_height - random.randint(0, 200)
                await page.evaluate(f'window.scrollTo(0, {scroll_to})')

                # Wait for potential content loading
                try:
                    await page.wait_for_load_state('networkidle', timeout=3000)
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.5, 1.5))

            # Scroll back to top
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.debug(f"Human scroll failed: {e}")

    async def _extract_with_shadow_dom(self, page) -> str:
        """Extract full page HTML including Shadow DOM content."""
        return await page.evaluate('''() => {
            function getFullHTML(root) {
                let html = '';
                const walker = document.createTreeWalker(
                    root, NodeFilter.SHOW_ELEMENT, null, false
                );
                let node = walker.currentNode;
                while (node) {
                    if (node.shadowRoot) {
                        html += node.shadowRoot.innerHTML;
                        // Recurse into shadow root
                        const shadowWalker = document.createTreeWalker(
                            node.shadowRoot, NodeFilter.SHOW_ELEMENT, null, false
                        );
                        let shadowNode = shadowWalker.nextNode();
                        while (shadowNode) {
                            if (shadowNode.shadowRoot) {
                                html += shadowNode.shadowRoot.innerHTML;
                            }
                            shadowNode = shadowWalker.nextNode();
                        }
                    }
                    node = walker.nextNode();
                }
                return html;
            }
            const mainHTML = document.documentElement.outerHTML;
            const shadowHTML = getFullHTML(document);
            return mainHTML + '\\n<!-- Shadow DOM Content -->\\n' + shadowHTML;
        }''')

    async def close(self):
        """Close browser (skip actual close in CDP mode to preserve user session)."""
        if self._is_cdp:
            # Don't close the user's real browser — just disconnect
            self._browser = None
            self._context = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            self._is_cdp = False
        else:
            if self._browser:
                await self._browser.close()
                self._browser = None
                self._context = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None


# =============================================================================
# WGET FETCHER (Classic recursive download)
# =============================================================================

class WgetFetcher:
    """Classic wget recursive download for bulk archival."""
    
    def __init__(self, config: ScrapeConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self._wget_available = self._check_wget()
    
    def _check_wget(self) -> bool:
        """Check if wget is available."""
        import shutil
        return shutil.which("wget") is not None
    
    def fetch_site(self, url: str) -> Optional[Path]:
        """Recursively download entire site."""
        if not self._wget_available:
            logger.warning("wget not available, skipping")
            return None
        
        domain = urlparse(url).netloc.replace("www.", "")
        output_path = self.output_dir / "wget" / domain
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🌐 WGET: Downloading {url} (depth={self.config.max_depth})")
        
        cmd = [
            "wget",
            "--recursive",
            "--level", str(self.config.max_depth),
            "--page-requisites",
            "--convert-links",
            "-E",  # --adjust-extension (use short flag for Windows wget compat)
            "--no-parent",
            "--wait", str(self.config.min_delay),
            "--random-wait",
            "--limit-rate", "1M",
            "--user-agent", random.choice(USER_AGENTS),
            "--directory-prefix", str(output_path),
            "--no-clobber",
            "--timeout", "30",
            "--tries", str(self.config.max_retries),
            "--execute", "robots=off" if not self.config.respect_robots else "robots=on",
            url
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour max
            )
            
            if result.returncode in [0, 8]:  # 8 = some errors but mostly success
                logger.info(f"✅ WGET complete: {output_path}")
                return output_path
            else:
                logger.warning(f"WGET returned {result.returncode}: {result.stderr[:200]}")
                return output_path if output_path.exists() else None
                
        except subprocess.TimeoutExpired:
            logger.warning("WGET timed out after 1 hour")
            return output_path if output_path.exists() else None
        except Exception as e:
            logger.error(f"WGET failed: {e}")
            return None


# =============================================================================
# ARCHIVEBOX FETCHER (Full archival)
# =============================================================================

class ArchiveBoxFetcher:
    """Full archival using ArchiveBox (HTML, PDF, screenshots, WARC)."""
    
    def __init__(self, config: ScrapeConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self._available = self._check_archivebox()
    
    def _check_archivebox(self) -> bool:
        """Check if archivebox is available."""
        import shutil
        return shutil.which("archivebox") is not None
    
    def archive_url(self, url: str) -> Optional[Path]:
        """Archive a URL with all formats."""
        if not self._available:
            logger.warning("archivebox not available. Install: pip install archivebox")
            return None
        
        domain = urlparse(url).netloc.replace("www.", "")
        output_path = self.output_dir / "archivebox" / domain
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"📦 ARCHIVEBOX: Archiving {url}")
        
        # Initialize if needed
        init_cmd = ["archivebox", "init", "--setup"]
        subprocess.run(init_cmd, cwd=output_path, capture_output=True)
        
        # Add URL with depth
        add_cmd = [
            "archivebox", "add",
            url,
            f"--depth={min(self.config.max_depth, 3)}",
            "--parser=auto"
        ]
        
        try:
            result = subprocess.run(
                add_cmd,
                cwd=output_path,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours max
            )
            
            if result.returncode == 0:
                logger.info(f"✅ ARCHIVEBOX complete: {output_path}")
                return output_path
            else:
                logger.warning(f"ARCHIVEBOX issues: {result.stderr[:200]}")
                return output_path if output_path.exists() else None
                
        except Exception as e:
            logger.error(f"ARCHIVEBOX failed: {e}")
            return None


# =============================================================================
# RATE LIMITER
# =============================================================================

class DomainRateLimiter:
    """Per-domain rate limiting with adaptive delays."""
    
    def __init__(self, config: ScrapeConfig):
        self.config = config
        self._last_request: Dict[str, float] = {}
        self._error_counts: Dict[str, int] = {}
    
    async def wait_for_domain(self, domain: str):
        """Wait appropriate time before next request to domain."""
        last_time = self._last_request.get(domain, 0)
        error_count = self._error_counts.get(domain, 0)
        
        # Base delay
        min_delay = self.config.min_delay
        max_delay = self.config.max_delay
        
        # Increase delay based on errors (adaptive)
        if error_count > 0:
            multiplier = min(error_count, 5)  # Cap at 5x
            min_delay *= multiplier
            max_delay *= multiplier
        
        delay = random.uniform(min_delay, max_delay)
        
        elapsed = time.time() - last_time
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        
        self._last_request[domain] = time.time()
    
    def record_error(self, domain: str):
        """Record error for adaptive rate limiting."""
        self._error_counts[domain] = self._error_counts.get(domain, 0) + 1
    
    def record_success(self, domain: str):
        """Record success - reduce error count."""
        if domain in self._error_counts:
            self._error_counts[domain] = max(0, self._error_counts[domain] - 1)


# =============================================================================
# MAIN DEATH STAR V2 CLASS
# =============================================================================

class DeathStarV2:
    """
    The all-consuming "nuke from orbit" web scraper.
    
    Orchestrates multiple scraping tools with intelligent routing,
    anti-bot evasion, and crash-proof checkpointing.
    """
    
    def __init__(
        self,
        config: Optional[ScrapeConfig] = None,
        output_dir: Optional[Path] = None
    ):
        self.config = config or ScrapeConfig()
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.checkpoint = None
        self.robots = RobotsHandler()
        self.rate_limiter = DomainRateLimiter(self.config)
        
        # Proxy pool (if configured)
        self.proxy_pool = None
        if self.config.proxy_pool_file:
            self.proxy_pool = ProxyPool(proxy_file=self.config.proxy_pool_file)
            logger.info(f"Loaded {len(self.proxy_pool.proxies)} proxies")
        elif self.config.proxy_list:
            self.proxy_pool = ProxyPool(proxies=self.config.proxy_list)
            logger.info(f"Using {len(self.proxy_pool.proxies)} proxies")
        
        # Session manager (if configured)
        self.session_manager = None
        if self.config.cookie_file:
            self.session_manager = SessionManager(cookie_file=self.config.cookie_file)
            logger.info(f"Loaded {len(self.session_manager.cookies)} cookies")
        
        # Add auth headers if configured
        if self.config.auth_username and self.config.auth_password:
            if not self.session_manager:
                self.session_manager = SessionManager()
            self.session_manager.add_auth_headers(
                self.config.auth_username,
                self.config.auth_password,
                self.config.auth_type
            )
            logger.info(f"Added {self.config.auth_type} authentication")
        
        # Fetchers (lazy initialized)
        self._http_fetcher = None
        self._playwright_fetcher = None
        self._wget_fetcher = None
        self._archivebox_fetcher = None

        # Circuit breaker, CAPTCHA handler, structured data, session pool
        from .circuit_breaker import CircuitBreaker
        from .captcha_handler import CAPTCHADetector, CAPTCHASolver, load_env_file
        from .structured_data import StructuredDataExtractor
        from .session_pool import SessionPool

        load_env_file()  # Load .env for API keys
        self.circuit_breaker = CircuitBreaker()
        self.captcha_detector = CAPTCHADetector()
        self.captcha_solver = CAPTCHASolver()
        self.structured_data = StructuredDataExtractor()
        self.session_pool = SessionPool(
            proxy_list=self.config.proxy_list or [],
        )

        # State
        self._shutdown_requested = False
        self._pages_scraped = 0
        self._errors = 0
        
        # Signal handlers
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)
        
        self._check_tools()
    
    def _check_tools(self):
        """Check available tools and log status."""
        import shutil
        
        tools = {
            "wget": shutil.which("wget") is not None,
            "archivebox": shutil.which("archivebox") is not None,
            "playwright": self._check_module("playwright"),
            "trafilatura": self._check_module("trafilatura"),
            "requests": self._check_module("requests"),
        }

        # Check enhanced modules
        enhanced = {
            "curl_cffi": self._check_module("curl_cffi"),
            "browserforge": self._check_module("browserforge"),
            "extruct": self._check_module("extruct"),
            "capsolver": bool(self.captcha_solver.capsolver_key),
            "browser_cookie3": self._check_module("browser_cookie3"),
            "patchright": self._check_module("patchright"),
            "camoufox": self._check_module("camoufox"),
            "nodriver": self._check_module("nodriver"),
        }

        logger.info("=== DEATH STAR V2 WEAPONS SYSTEMS ===")
        for tool, available in tools.items():
            status = "ARMED" if available else "OFFLINE"
            logger.info(f"  {tool}: {status}")

        armed_enhanced = [k for k, v in enhanced.items() if v]
        if armed_enhanced:
            logger.info(f"  Enhanced: {', '.join(armed_enhanced)}")
        offline_enhanced = [k for k, v in enhanced.items() if not v]
        if offline_enhanced:
            logger.debug(f"  Optional (not installed): {', '.join(offline_enhanced)}")

        self._tools = tools
        self._enhanced_tools = enhanced
    
    def _check_module(self, module: str) -> bool:
        """Check if Python module is available."""
        try:
            __import__(module)
            return True
        except ImportError:
            return False
    
    @staticmethod
    def _should_crawl_url(url: str) -> bool:
        """Return False for obvious non-HTML assets (fonts, images, etc.) to avoid Playwright failures."""
        if not url or not url.strip():
            return False
        path = urlparse(url).path.lower().split("?")[0]
        skip_extensions = (
            ".woff2", ".woff", ".ttf", ".otf", ".eot",
            ".svg", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif",
            ".css", ".js", ".mjs", ".map",
            ".pdf", ".zip", ".mp4", ".webm", ".mp3", ".wav",
        )
        if any(path.endswith(ext) for ext in skip_extensions):
            return False
        if "_next/static/media/" in url or "/static/media/" in path:
            return False
        return True
    
    def _shutdown_handler(self, sig, frame):
        """Handle graceful shutdown."""
        logger.info(f"Shutdown signal received ({sig}). Finishing current page...")
        self._shutdown_requested = True
    
    @property
    def http_fetcher(self) -> HTTPFetcher:
        """Lazy-initialize HTTP fetcher."""
        if self._http_fetcher is None:
            self._http_fetcher = HTTPFetcher(self.config)
        return self._http_fetcher
    
    @property
    def wget_fetcher(self) -> WgetFetcher:
        """Lazy-initialize wget fetcher."""
        if self._wget_fetcher is None:
            self._wget_fetcher = WgetFetcher(self.config, self.output_dir)
        return self._wget_fetcher
    
    @property
    def archivebox_fetcher(self) -> ArchiveBoxFetcher:
        """Lazy-initialize archivebox fetcher."""
        if self._archivebox_fetcher is None:
            self._archivebox_fetcher = ArchiveBoxFetcher(self.config, self.output_dir)
        return self._archivebox_fetcher
    
    async def _get_playwright_fetcher(self) -> PlaywrightFetcher:
        """Lazy-initialize playwright fetcher with session and proxy support."""
        if self._playwright_fetcher is None:
            self._playwright_fetcher = PlaywrightFetcher(
                self.config,
                session_manager=self.session_manager,
                proxy_pool=self.proxy_pool,
            )
        return self._playwright_fetcher
    
    def _should_use_browser(self, url: str, html: str = None) -> bool:
        """Determine if URL needs browser rendering."""
        # Patterns that suggest JS rendering needed
        js_patterns = [
            'react', 'angular', 'vue', 'ember',
            'spa', 'single-page',
            'cloudflare', 'ddos-guard',
            '__NEXT_DATA__', '__NUXT__',
        ]
        
        # Check URL patterns
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Known JS-heavy sites
        js_domains = [
            'twitter.com', 'x.com', 'instagram.com', 'facebook.com',
            'reddit.com', 'discord.com', 'slack.com',
        ]
        
        if any(d in domain for d in js_domains):
            return True
        
        # Check HTML content if available
        if html:
            html_lower = html.lower()
            if any(p in html_lower for p in js_patterns):
                return True
            
            # Check if content is suspiciously small
            if len(html) < 1000 and 'javascript' in html_lower:
                return True
        
        return False
    
    async def scrape_page(self, url: str, use_browser: bool = False) -> Optional[ScrapedPage]:
        """Scrape a single page with appropriate method."""
        url = normalize_url(url)
        domain = urlparse(url).netloc

        # Circuit breaker check
        if not self.circuit_breaker.can_request(domain):
            logger.debug(f"Circuit breaker OPEN for {domain}, skipping: {url}")
            return None

        # Check robots.txt
        if self.config.respect_robots and not self.robots.can_fetch(url):
            logger.debug(f"Blocked by robots.txt: {url}")
            return None

        # Rate limiting
        await self.rate_limiter.wait_for_domain(domain)

        result = None

        # Try HTTP first unless browser requested
        http_fallback = None
        if not use_browser:
            result = self.http_fetcher.fetch(url)

            # If content seems JS-heavy, try browser but keep HTTP as fallback
            if result and self._should_use_browser(url, result.raw_html):
                logger.debug(f"Detected JS content, trying browser: {url}")
                use_browser = True
                http_fallback = result
                result = None

        # Use Playwright for JS content
        if use_browser and self._tools.get('playwright'):
            fetcher = await self._get_playwright_fetcher()
            result = await fetcher.fetch(url)

        # Fall back to HTTP result if browser failed
        if result is None and http_fallback is not None:
            logger.debug(f"Browser failed, using HTTP fallback for: {url}")
            result = http_fallback

        # Post-fetch processing
        if result:
            # Check for CAPTCHA in response
            detection = self.captcha_detector.detect(
                result.raw_html, url=url
            )
            if detection.detected:
                logger.warning(
                    f"CAPTCHA detected ({detection.captcha_type.value}) at {url}"
                )
                # Attempt to solve
                solution = await self.captcha_solver.solve(detection)
                if solution.solved:
                    logger.info(
                        f"CAPTCHA solved via {solution.method} "
                        f"in {solution.solve_time:.1f}s"
                    )
                    # If we got cookies (e.g. cf_clearance), inject and retry
                    if solution.cookies:
                        session = self.session_pool.get_session(domain)
                        session.add_cookies(solution.cookies)
                        if solution.user_agent:
                            session.set_cf_clearance(
                                solution.cookies.get("cf_clearance", ""),
                                solution.user_agent,
                            )
                        # Retry the request with new cookies
                        result = self.http_fetcher.fetch(url)
                else:
                    logger.warning(f"CAPTCHA not solved: {solution.error}")
                    self.circuit_breaker.record_failure(domain, reason="captcha_unsolved")
                    self.rate_limiter.record_error(domain)
                    return None

            # Extract structured data and add to metadata
            try:
                sd = self.structured_data.extract(result.raw_html, url=url)
                if any(sd.values()):
                    result.metadata["structured_data"] = sd
                    summary = self.structured_data.extract_summary(sd)
                    if summary.get("schema_types"):
                        logger.debug(f"Structured data: {summary['schema_types']}")
            except Exception as e:
                logger.debug(f"Structured data extraction failed: {e}")

            self.circuit_breaker.record_success(domain)
            self.rate_limiter.record_success(domain)
        else:
            self.circuit_breaker.record_failure(domain, reason="fetch_failed")
            self.rate_limiter.record_error(domain)

        return result
    
    async def destroy(
        self,
        url: str,
        mode: str = "smart",
        depth: int = None,
        resume: bool = False
    ) -> Dict:
        """
        FIRE THE DEATH STAR.
        
        Modes:
            - "quick": HTTP/wget only (fastest)
            - "smart": Adaptive routing (recommended)
            - "stealth": Browser with anti-bot evasion
            - "full": All weapons (most comprehensive)
            - "archive": Full archival with ArchiveBox
            - "forensic": Complete forensic capture (WARC, HAR, assets, storage)
            - "planetary": MAXIMUM DESTRUCTION - all modes combined
        
        Args:
            url: Target URL to destroy
            mode: Scraping mode
            depth: Override max depth
            resume: Resume from checkpoint
        
        Returns:
            Dict with results and statistics
        """
        if depth:
            self.config.max_depth = depth
        
        domain = urlparse(url).netloc.replace("www.", "")
        logger.info(f"💥💥💥 DEATH STAR V2 FIRING ON: {url} (mode={mode}) 💥💥💥")
        
        # Initialize checkpoint
        self.checkpoint = EnhancedCheckpoint(domain)

        # Add seed URL if not resuming or empty
        stats = self.checkpoint.stats()
        if not resume or stats.get('total', 0) == 0:
            # Reset any previously failed URLs so we retry them
            try:
                self.checkpoint.conn.execute(
                    "UPDATE urls SET status = 'pending' WHERE status = 'failed'"
                )
                self.checkpoint.conn.commit()
            except Exception:
                pass
            self.checkpoint.add_url(url, depth=0)
        
        results = {
            "target": url,
            "mode": mode,
            "depth": self.config.max_depth,
            "started_at": datetime.now().isoformat(),
            "weapons_fired": [],
            "pages_scraped": 0,
            "errors": 0,
            "outputs": {}
        }
        
        # Mode-specific scraping
        if mode == "quick":
            # Just wget
            wget_path = self.wget_fetcher.fetch_site(url)
            if wget_path:
                results["weapons_fired"].append("wget")
                results["outputs"]["wget"] = str(wget_path)
        
        elif mode == "archive":
            # Full archival
            ab_path = self.archivebox_fetcher.archive_url(url)
            if ab_path:
                results["weapons_fired"].append("archivebox")
                results["outputs"]["archivebox"] = str(ab_path)
        
        elif mode in ("smart", "stealth", "full"):
            # Crawl and scrape
            use_browser = mode == "stealth"
            
            results["weapons_fired"].append("http" if not use_browser else "playwright")
            
            # Process queue
            output_path = self.output_dir / "pages" / domain
            output_path.mkdir(parents=True, exist_ok=True)
            
            while not self._shutdown_requested:
                pending = self.checkpoint.get_pending(limit=10)
                if not pending:
                    break
                
                for item in pending:
                    if self._shutdown_requested:
                        break
                    
                    if self._pages_scraped >= self.config.max_pages:
                        logger.info(f"Reached max pages limit: {self.config.max_pages}")
                        break
                    
                    page_url = item['url']
                    page_depth = item['depth']
                    
                    try:
                        page = await self.scrape_page(page_url, use_browser=use_browser)
                        
                        if page:
                            # Check for duplicate content
                            if self.config.deduplicate:
                                if self.checkpoint.is_duplicate_content(page.content_hash):
                                    logger.debug(f"Duplicate content: {page_url}")
                                    self.checkpoint.mark_complete(page_url, page.method, page.content_hash)
                                    continue
                                self.checkpoint.add_content_hash(page.content_hash, page_url)
                            
                            # Save page data
                            self._save_page(page, output_path)
                            self.checkpoint.mark_complete(page_url, page.method, page.content_hash)
                            self._pages_scraped += 1
                            
                            # Follow links if within depth
                            if page_depth < self.config.max_depth:
                                for link in page.links:
                                    if not self._should_crawl_url(link):
                                        continue
                                    link_domain = urlparse(link).netloc
                                    if link_domain == urlparse(url).netloc or self.config.follow_external:
                                        self.checkpoint.add_url(link, depth=page_depth + 1)
                            
                            if self._pages_scraped % 10 == 0:
                                logger.info(f"Progress: {self._pages_scraped} pages scraped")
                        else:
                            self.checkpoint.mark_failed(page_url, "fetch_failed")
                            self._errors += 1
                            
                    except Exception as e:
                        logger.error(f"Error scraping {page_url}: {e}")
                        self.checkpoint.mark_failed(page_url, str(e))
                        self._errors += 1
            
            results["outputs"]["pages"] = str(output_path)
            
            # Also run wget in full mode
            if mode == "full" and self._tools.get('wget'):
                wget_path = self.wget_fetcher.fetch_site(url)
                if wget_path:
                    results["weapons_fired"].append("wget")
                    results["outputs"]["wget"] = str(wget_path)
        
        elif mode == "forensic":
            # Complete forensic capture
            results["weapons_fired"].append("forensic_capture")
            
            try:
                from .forensic_capture import ForensicCapture, save_forensic_result
                
                forensic = ForensicCapture(output_dir=self.output_dir / "forensic")
                forensic_result = await forensic.capture_page(
                    url,
                    capture_assets=True,
                    capture_storage=True,
                    capture_screenshot=True,
                    capture_pdf=True,
                    capture_certificate=True,
                    generate_warc=True,
                    generate_har=True,
                )
                
                result_dir = save_forensic_result(forensic_result, self.output_dir / "forensic")
                results["outputs"]["forensic"] = str(result_dir)
                results["outputs"]["warc"] = forensic_result.warc_path
                results["outputs"]["screenshot"] = forensic_result.screenshot_path
                results["forensic_stats"] = {
                    "requests_captured": len(forensic_result.requests),
                    "assets_captured": len(forensic_result.assets),
                    "cookies": len(forensic_result.cookies),
                    "local_storage_keys": len(forensic_result.local_storage),
                }
                self._pages_scraped = 1
                
            except ImportError as e:
                logger.error(f"Forensic capture requires additional modules: {e}")
                results["errors"] = 1
        
        elif mode == "planetary":
            # MAXIMUM DESTRUCTION - everything!
            logger.info("🌍💥 PLANETARY DESTRUCTION MODE - ALL WEAPONS FIRING!")
            
            # 1. Site discovery first
            try:
                from .site_discovery import SiteDiscovery
                
                discovery = SiteDiscovery(output_dir=self.output_dir / "discovery")
                discovery_result = await discovery.discover_site(url, max_depth=2)
                results["weapons_fired"].append("site_discovery")
                results["outputs"]["discovery"] = str(self.output_dir / "discovery" / domain)
                results["discovery_stats"] = discovery_result.stats
                
                # Add discovered URLs to queue
                for discovered_url in list(discovery_result.html_pages)[:self.config.max_pages]:
                    self.checkpoint.add_url(discovered_url, depth=1)
                    
            except Exception as e:
                logger.warning(f"Site discovery failed: {e}")
            
            # 2. Forensic capture of main page
            forensic_result = None
            try:
                from .forensic_capture import ForensicCapture, save_forensic_result

                forensic = ForensicCapture(output_dir=self.output_dir / "forensic")
                forensic_result = await forensic.capture_page(url)
                save_forensic_result(forensic_result, self.output_dir / "forensic")
                results["weapons_fired"].append("forensic_capture")
                results["outputs"]["forensic"] = str(self.output_dir / "forensic")

            except Exception as e:
                logger.warning(f"Forensic capture failed: {e}")

            # 3. Media extraction
            try:
                from .media_extractor import MediaExtractor

                extractor = MediaExtractor(output_dir=self.output_dir / "media")
                # Get HTML from forensic result or fetch
                html = forensic_result.raw_html if forensic_result is not None else ""
                if not html:
                    page = await self.scrape_page(url)
                    html = page.raw_html if page else ""
                
                if html:
                    media_result = await extractor.extract_all(url, html)
                    results["weapons_fired"].append("media_extractor")
                    results["outputs"]["media"] = str(self.output_dir / "media")
                    results["media_stats"] = {
                        "videos": len(media_result.videos),
                        "audio": len(media_result.audios),
                        "images": len(media_result.images),
                        "documents": len(media_result.documents),
                    }
                    
            except Exception as e:
                logger.warning(f"Media extraction failed: {e}")
            
            # 4. Full crawl with stealth
            output_path = self.output_dir / "pages" / domain
            output_path.mkdir(parents=True, exist_ok=True)
            
            while not self._shutdown_requested:
                pending = self.checkpoint.get_pending(limit=10)
                if not pending:
                    break
                
                if self._pages_scraped >= self.config.max_pages:
                    break
                
                for item in pending:
                    if self._shutdown_requested or self._pages_scraped >= self.config.max_pages:
                        break
                    
                    page_url = item['url']
                    page_depth = item['depth']
                    
                    try:
                        page = await self.scrape_page(page_url, use_browser=True)
                        
                        if page:
                            if self.config.deduplicate and self.checkpoint.is_duplicate_content(page.content_hash):
                                self.checkpoint.mark_complete(page_url, page.method, page.content_hash)
                                continue
                            
                            self.checkpoint.add_content_hash(page.content_hash, page_url)
                            self._save_page(page, output_path)
                            self.checkpoint.mark_complete(page_url, page.method, page.content_hash)
                            self._pages_scraped += 1
                            
                            if page_depth < self.config.max_depth:
                                for link in page.links:
                                    if not self._should_crawl_url(link):
                                        continue
                                    link_domain = urlparse(link).netloc
                                    if link_domain == urlparse(url).netloc:
                                        self.checkpoint.add_url(link, depth=page_depth + 1)
                        else:
                            self.checkpoint.mark_failed(page_url, "fetch_failed")
                            self._errors += 1
                            
                    except Exception as e:
                        self.checkpoint.mark_failed(page_url, str(e))
                        self._errors += 1
            
            results["weapons_fired"].append("stealth_crawl")
            results["outputs"]["pages"] = str(output_path)
            
            # 5. wget mirror
            if self._tools.get('wget'):
                wget_path = self.wget_fetcher.fetch_site(url)
                if wget_path:
                    results["weapons_fired"].append("wget")
                    results["outputs"]["wget"] = str(wget_path)
            
            # 6. ArchiveBox
            if self._tools.get('archivebox'):
                ab_path = self.archivebox_fetcher.archive_url(url)
                if ab_path:
                    results["weapons_fired"].append("archivebox")
                    results["outputs"]["archivebox"] = str(ab_path)
        
        elif mode == "ultimate":
            # ULTIMATE MODE - Absolutely everything
            logger.info("🌌⚡ ULTIMATE DESTRUCTION MODE - LEAVING NOTHING BEHIND! ⚡🌌")
            
            # Initialize browser for advanced capture
            playwright_fetcher = await self._get_playwright_fetcher()
            await playwright_fetcher._ensure_browser()
            browser_page = await playwright_fetcher._context.new_page()
            
            try:
                # Navigate to page
                response = await browser_page.goto(url, wait_until='networkidle', timeout=60000)
                await asyncio.sleep(2)
                
                # 1. Advanced capture (WebSocket, forms, tech stack, source maps)
                try:
                    from .advanced_capture import AdvancedCapture
                    
                    advanced = AdvancedCapture(output_dir=self.output_dir / "advanced")
                    headers = dict(response.headers) if response else {}
                    advanced_result = await advanced.capture_advanced(
                        browser_page,
                        url,
                        headers=headers,
                        capture_iframes=True,
                        capture_source_maps=True
                    )
                    advanced.save_result(advanced_result, domain)
                    results["weapons_fired"].append("advanced_capture")
                    results["outputs"]["advanced"] = str(self.output_dir / "advanced" / domain)
                    results["advanced_stats"] = {
                        "websocket_connections": len(advanced_result.websocket_connections),
                        "websocket_messages": len(advanced_result.websocket_messages),
                        "forms_found": len(advanced_result.forms),
                        "iframes_found": len(advanced_result.iframes),
                        "source_maps_found": len(advanced_result.source_maps),
                        "third_party_scripts": len(advanced_result.third_party_scripts),
                        "api_endpoints_found": len(advanced_result.api_endpoints),
                        "tech_stack": {
                            "cms": advanced_result.tech_stack.cms,
                            "frameworks": advanced_result.tech_stack.frameworks,
                            "analytics": advanced_result.tech_stack.analytics,
                        },
                        "contact_info": {
                            "emails": len(advanced_result.contact_info.emails),
                            "phones": len(advanced_result.contact_info.phones),
                            "social_platforms": list(advanced_result.contact_info.social_links.keys())
                        }
                    }
                except Exception as e:
                    logger.warning(f"Advanced capture failed: {e}")
                
                # 2. Forensic capture
                try:
                    from .forensic_capture import ForensicCapture, save_forensic_result
                    
                    forensic = ForensicCapture(output_dir=self.output_dir / "forensic")
                    forensic_result = await forensic.capture_page(
                        url,
                        page=browser_page,
                        capture_assets=True,
                        capture_storage=True,
                        capture_screenshot=True,
                        capture_pdf=True,
                        capture_certificate=True,
                        generate_warc=True,
                        generate_har=True
                    )
                    save_forensic_result(forensic_result, self.output_dir / "forensic")
                    results["weapons_fired"].append("forensic_capture")
                    results["outputs"]["forensic"] = str(self.output_dir / "forensic")
                    results["outputs"]["warc"] = forensic_result.warc_path
                    results["outputs"]["har"] = str(self.output_dir / "forensic" / "har")
                    results["forensic_stats"] = {
                        "requests_captured": len(forensic_result.requests),
                        "responses_captured": len(forensic_result.responses),
                        "assets_captured": len(forensic_result.assets),
                        "cookies": len(forensic_result.cookies),
                        "local_storage_keys": len(forensic_result.local_storage),
                        "session_storage_keys": len(forensic_result.session_storage),
                        "internal_links": len(forensic_result.internal_links),
                        "external_links": len(forensic_result.external_links),
                    }
                except Exception as e:
                    logger.warning(f"Forensic capture failed: {e}")
                
                # 3. Wayback Machine integration
                try:
                    from .wayback_integration import WaybackMachine
                    
                    wayback = WaybackMachine(output_dir=self.output_dir / "wayback")
                    
                    # Get historical snapshots
                    snapshots = await wayback.get_snapshots(url, limit=100)
                    wayback.save_snapshots_index(url, snapshots, domain)
                    results["weapons_fired"].append("wayback_integration")
                    results["outputs"]["wayback"] = str(self.output_dir / "wayback" / domain)
                    results["wayback_stats"] = {
                        "snapshots_found": len(snapshots),
                        "oldest": snapshots[-1].datetime.isoformat() if snapshots else None,
                        "newest": snapshots[0].datetime.isoformat() if snapshots else None,
                    }
                    
                    # Submit current page for archival
                    archived_url = await wayback.save_url(url)
                    if archived_url:
                        results["wayback_stats"]["archived_to"] = archived_url
                        
                except Exception as e:
                    logger.warning(f"Wayback integration failed: {e}")
                
                # 4. Site discovery
                try:
                    from .site_discovery import SiteDiscovery
                    
                    discovery = SiteDiscovery(output_dir=self.output_dir / "discovery")
                    discovery_result = await discovery.discover_site(url, max_depth=2)
                    results["weapons_fired"].append("site_discovery")
                    results["outputs"]["discovery"] = str(self.output_dir / "discovery" / domain)
                    results["discovery_stats"] = discovery_result.stats
                    
                    # Add discovered URLs to queue (skip non-HTML assets)
                    for discovered_url in list(discovery_result.html_pages)[:self.config.max_pages]:
                        if self._should_crawl_url(discovered_url):
                            self.checkpoint.add_url(discovered_url, depth=1)
                        
                except Exception as e:
                    logger.warning(f"Site discovery failed: {e}")
                
                # 5. Media extraction
                try:
                    from .media_extractor import MediaExtractor
                    
                    extractor = MediaExtractor(output_dir=self.output_dir / "media")
                    html = await browser_page.content()
                    media_result = await extractor.extract_all(url, html)
                    results["weapons_fired"].append("media_extractor")
                    results["outputs"]["media"] = str(self.output_dir / "media")
                    results["media_stats"] = {
                        "videos": len(media_result.videos),
                        "audio": len(media_result.audios),
                        "images": len(media_result.images),
                        "documents": len(media_result.documents),
                        "embedded_players": len(media_result.embedded_players),
                        "total_size_mb": media_result.total_size / 1024 / 1024,
                    }
                except Exception as e:
                    logger.warning(f"Media extraction failed: {e}")
                
            finally:
                await browser_page.close()
            
            # 6. Full stealth crawl
            output_path = self.output_dir / "pages" / domain
            output_path.mkdir(parents=True, exist_ok=True)
            
            while not self._shutdown_requested:
                pending = self.checkpoint.get_pending(limit=10)
                if not pending:
                    break
                
                if self._pages_scraped >= self.config.max_pages:
                    break
                
                for item in pending:
                    if self._shutdown_requested or self._pages_scraped >= self.config.max_pages:
                        break
                    
                    page_url = item['url']
                    page_depth = item['depth']
                    
                    try:
                        page = await self.scrape_page(page_url, use_browser=True)
                        
                        if page:
                            if self.config.deduplicate and self.checkpoint.is_duplicate_content(page.content_hash):
                                self.checkpoint.mark_complete(page_url, page.method, page.content_hash)
                                continue
                            
                            self.checkpoint.add_content_hash(page.content_hash, page_url)
                            self._save_page(page, output_path)
                            self.checkpoint.mark_complete(page_url, page.method, page.content_hash)
                            self._pages_scraped += 1
                            
                            if page_depth < self.config.max_depth:
                                for link in page.links:
                                    if not self._should_crawl_url(link):
                                        continue
                                    link_domain = urlparse(link).netloc
                                    if link_domain == urlparse(url).netloc:
                                        self.checkpoint.add_url(link, depth=page_depth + 1)
                        else:
                            self.checkpoint.mark_failed(page_url, "fetch_failed")
                            self._errors += 1
                            
                    except Exception as e:
                        self.checkpoint.mark_failed(page_url, str(e))
                        self._errors += 1
            
            results["weapons_fired"].append("stealth_crawl")
            results["outputs"]["pages"] = str(output_path)
            
            # 7. wget mirror
            if self._tools.get('wget'):
                wget_path = self.wget_fetcher.fetch_site(url)
                if wget_path:
                    results["weapons_fired"].append("wget")
                    results["outputs"]["wget"] = str(wget_path)
            
            # 8. ArchiveBox
            if self._tools.get('archivebox'):
                ab_path = self.archivebox_fetcher.archive_url(url)
                if ab_path:
                    results["weapons_fired"].append("archivebox")
                    results["outputs"]["archivebox"] = str(ab_path)
            
            logger.info("🌌 ULTIMATE DESTRUCTION COMPLETE - NOTHING REMAINS 🌌")
        
        # Finalize results
        results["pages_scraped"] = self._pages_scraped
        results["errors"] = self._errors
        results["completed_at"] = datetime.now().isoformat()
        results["checkpoint_stats"] = self.checkpoint.stats()
        
        # Save manifest
        manifest_path = self.output_dir / f"{domain}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(results, f, indent=2)
        
        results["manifest"] = str(manifest_path)
        
        logger.info(f"💥 DESTRUCTION COMPLETE: {self._pages_scraped} pages, {self._errors} errors")
        
        return results
    
    def _save_page(self, page: ScrapedPage, output_dir: Path):
        """Save scraped page to disk."""
        # Create filename from URL
        parsed = urlparse(page.url)
        path_parts = parsed.path.strip('/').replace('/', '_') or 'index'
        filename = f"{path_parts}_{page.content_hash}"
        
        # Save JSON metadata + content
        page_data = {
            "url": page.url,
            "final_url": page.final_url,
            "title": page.title,
            "scraped_at": page.scraped_at,
            "method": page.method,
            "content_hash": page.content_hash,
            "status_code": page.status_code,
            "content_type": page.content_type,
            "links_count": len(page.links),
            "media_count": len(page.media),
        }
        
        # Save metadata
        meta_path = output_dir / f"{filename}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(page_data, f, indent=2)
        
        # Save markdown (for LLM)
        md_path = output_dir / f"{filename}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {page.title}\n\n")
            f.write(f"URL: {page.url}\n")
            f.write(f"Scraped: {page.scraped_at}\n\n")
            f.write("---\n\n")
            f.write(page.markdown or page.clean_text)
        
        # Optionally save raw HTML
        if self.config.save_raw_html:
            html_path = output_dir / f"{filename}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.raw_html)
    
    async def close(self):
        """Clean up resources."""
        if self._playwright_fetcher:
            await self._playwright_fetcher.close()
        if self.checkpoint:
            self.checkpoint.close()


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="💥 DEATH STAR V2 - Nuke From Orbit Web Scraper 💥",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  quick      Fast wget-only download
  smart      Adaptive routing (HTTP + browser fallback) [DEFAULT]
  stealth    Browser-only with anti-bot evasion
  full       All weapons (smart crawl + wget + archivebox)
  archive    Full archival via ArchiveBox only
  forensic   Complete forensic capture (WARC, HAR, assets, storage) ⭐
  planetary  MAXIMUM DESTRUCTION - all modes combined ⭐
  x_community  X/Twitter community scraper (requires --cookies) 🐦

Examples:
  # Smart crawl a site
  python death_star_v2.py --target https://example.com

  # Deep stealth scrape
  python death_star_v2.py --target https://example.com --mode stealth --depth 10

  # Complete forensic capture
  python death_star_v2.py --target https://example.com --mode forensic

  # PLANETARY DESTRUCTION (everything!)
  python death_star_v2.py --target https://example.com --mode planetary

  # X COMMUNITY SCRAPE (requires cookies!)
  python death_star_v2.py --target https://x.com/i/communities/123 --mode x_community --cookies x_cookies.json

  # Attach to running Chrome via CDP (reuse authenticated session)
  python death_star_v2.py --target https://example.com --cdp http://localhost:9222

  # Use patchright stealth engine
  python death_star_v2.py --target https://example.com --engine patchright --mode stealth

  # Resume interrupted scrape
  python death_star_v2.py --target https://example.com --resume

  # Full archival
  python death_star_v2.py --target https://example.com --mode full

  # Multiple targets
  python death_star_v2.py --targets urls.txt --mode smart
        """
    )
    
    parser.add_argument("--target", "-t", help="Target URL to scrape")
    parser.add_argument("--targets", "-T", help="File with URLs (one per line)")
    parser.add_argument("--mode", "-m", default="smart",
                       choices=["quick", "smart", "stealth", "full", "archive", "forensic", "planetary", "ultimate", "x_community"],
                       help="Scraping mode (default: smart)")
    parser.add_argument("--depth", "-d", type=int, default=5,
                       help="Max crawl depth (default: 5)")
    parser.add_argument("--max-pages", type=int, default=10000,
                       help="Max pages to scrape (default: 10000)")
    parser.add_argument("--resume", "-r", action="store_true",
                       help="Resume from checkpoint")
    parser.add_argument("--polite", "-p", action="store_true",
                       help="Respect robots.txt")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--delay", type=float, default=1.0,
                       help="Min delay between requests (default: 1.0)")
    parser.add_argument("--no-dedup", action="store_true",
                       help="Disable content deduplication")
    
    # Browser engine and CDP
    parser.add_argument("--cdp", help="CDP endpoint to attach to running Chrome (e.g. http://localhost:9222)")
    parser.add_argument("--engine", default="playwright",
                       choices=["playwright", "patchright", "camoufox", "nodriver"],
                       help="Browser engine (default: playwright)")
    parser.add_argument("--headed", action="store_true",
                       help="Run browser in headed (visible) mode")

    # Proxy and authentication
    parser.add_argument("--proxy", help="Single proxy URL (http://host:port)")
    parser.add_argument("--proxy-file", help="File with proxy list (one per line)")
    parser.add_argument("--cookies", help="Cookie file (JSON or Netscape format)")
    parser.add_argument("--auth-user", help="Username for HTTP authentication")
    parser.add_argument("--auth-pass", help="Password for HTTP authentication")
    parser.add_argument("--auth-type", default="basic",
                       choices=["basic", "digest"],
                       help="Authentication type (default: basic)")
    
    parser.add_argument("--install", action="store_true",
                       help="Show installation instructions")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.install:
        print_installation_guide()
        return
    
    if not args.target and not args.targets:
        parser.print_help()
        print("\n💥 Example: python death_star_v2.py --target https://example.com --mode smart")
        return
    
    # Build config
    proxy_list = [args.proxy] if args.proxy else []
    
    config = ScrapeConfig(
        max_depth=args.depth,
        max_pages=args.max_pages,
        min_delay=args.delay,
        max_delay=args.delay * 2,
        respect_robots=args.polite,
        deduplicate=not args.no_dedup,
        headless=not args.headed,
        browser_engine=args.engine,
        cdp_endpoint=args.cdp,
        proxy_list=proxy_list,
        proxy_pool_file=args.proxy_file,
        cookie_file=args.cookies,
        auth_username=args.auth_user,
        auth_password=args.auth_pass,
        auth_type=args.auth_type,
    )
    
    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR
    
    # Run scraper
    async def run():
        # Special handling for X community mode
        if args.mode == "x_community":
            from ..x_community_scraper import XCommunityScraper
            
            if not args.cookies:
                logger.error("X community scraping requires --cookies flag!")
                logger.info("See: src/scraping/HOWTO_X_COOKIES.md")
                return
            
            scraper = XCommunityScraper(
                output_dir=output_dir / "x_communities",
                cookies_file=args.cookies,
            )
            
            result = await scraper.scrape_community(
                url=args.target,
                max_posts=args.max_pages,
                max_scrolls=args.depth * 4,  # Use depth to control scrolling
            )
            
            if result:
                print(f"\n🎯 X COMMUNITY SCRAPED: {result.name}")
                print(f"   ID: {result.id}")
                print(f"   Members: {result.member_count:,}")
                print(f"   Posts captured: {len(result.posts)}")
            return
        
        death_star = DeathStarV2(config=config, output_dir=output_dir)
        
        try:
            if args.target:
                result = await death_star.destroy(
                    args.target,
                    mode=args.mode,
                    depth=args.depth,
                    resume=args.resume
                )
                print(json.dumps(result, indent=2))
                
            elif args.targets:
                with open(args.targets) as f:
                    urls = [line.strip() for line in f if line.strip()]
                
                results = []
                for url in urls:
                    result = await death_star.destroy(
                        url,
                        mode=args.mode,
                        depth=args.depth,
                        resume=args.resume
                    )
                    results.append(result)
                
                print(json.dumps(results, indent=2))
        finally:
            await death_star.close()
    
    asyncio.run(run())


def print_installation_guide():
    """Print installation guide for all weapons."""
    print("""
=== DEATH STAR V2 INSTALLATION GUIDE ===

Core Requirements (pip install):
--------------------------------
pip install requests trafilatura playwright

Browser Setup:
--------------
playwright install chromium

Stealth Browser Engines (optional escalation):
-----------------------------------------------
pip install patchright   # Stealth-patched Playwright (bypasses most anti-bot)
pip install camoufox     # Firefox-based stealth (separate fingerprint)
pip install nodriver     # Undetectable Chrome via raw DevTools Protocol

Optional Tools:
---------------
# ArchiveBox (full archival)
pip install archivebox
archivebox init --setup

# wget (usually pre-installed on Linux)
sudo apt install wget  # Ubuntu/Debian
brew install wget      # macOS

Full Installation (one-liner):
------------------------------
pip install requests trafilatura playwright patchright archivebox && playwright install chromium

Verify Installation:
--------------------
python death_star_v2.py --install

=== READY TO NUKE FROM ORBIT ===
""")


if __name__ == "__main__":
    main()
