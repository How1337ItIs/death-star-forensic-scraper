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
import ipaddress
import json
import logging
import random
import re
import shutil
import signal
import site
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

_JSON_SAFE = (str, int, float, bool, type(None))


def _to_serializable(obj):
    """Recursively convert Paths, sets, bytes, datetimes, and other objects to JSON-safe values."""
    if isinstance(obj, _JSON_SAFE):
        return obj
    if isinstance(obj, dict):
        return {str(k): _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(v) for v in obj]
    if isinstance(obj, set):
        return [_to_serializable(v) for v in sorted(obj, key=str)]
    if isinstance(obj, bytes):
        return f"<{len(obj)} bytes>"
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


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


def normalize_target_url(url: str) -> str:
    """Normalize target input to a valid HTTP(S) URL."""

    def _is_valid_netloc(netloc: str) -> bool:
        if not netloc or any(ch.isspace() for ch in netloc):
            return False

        host_port = netloc.rsplit("@", 1)[-1]
        if host_port.startswith("["):
            if "]" not in host_port:
                return False
            host = host_port[1:host_port.index("]")]
            remainder = host_port[host_port.index("]") + 1:]
            if remainder:
                if not remainder.startswith(":"):
                    return False
                port = remainder[1:]
                if not port.isdigit():
                    return False
            try:
                ipaddress.IPv6Address(host)
                return True
            except ValueError:
                return False

        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            if not port.isdigit():
                return False
        else:
            host = host_port

        if not host:
            return False
        try:
            ipaddress.IPv4Address(host)
            return True
        except ValueError:
            pass
        if host.lower() == "localhost":
            return True

        host = host.rstrip(".")
        if not host or len(host) > 253:
            return False
        for label in host.split("."):
            if not label or len(label) > 63:
                return False
            if label.startswith("-") or label.endswith("-"):
                return False
            if not re.fullmatch(r"[A-Za-z0-9-]+", label):
                return False
        return True

    raw = (url or "").strip()
    if not raw:
        raise ValueError("Target URL is empty")
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"}:
        if not _is_valid_netloc(parsed.netloc):
            raise ValueError("Target URL is missing a host")
        return raw
    if parsed.scheme and not parsed.netloc and "://" not in raw:
        normalized = f"https://{raw}"
        if not _is_valid_netloc(urlparse(normalized).netloc):
            raise ValueError("Target URL is invalid")
        return normalized
    if parsed.scheme:
        raise ValueError(f"Unsupported URL scheme '{parsed.scheme}'. Use http:// or https://")

    normalized = f"https://{raw}"
    if not _is_valid_netloc(urlparse(normalized).netloc):
        raise ValueError("Target URL is invalid")
    return normalized


def safe_path_component(value: str) -> str:
    """Make a string safe for cross-platform file and directory names."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


def resolve_cli(names: str | List[str]) -> Optional[str]:
    """Resolve a CLI from PATH or this Python installation's user scripts dir."""
    cli_names = [names] if isinstance(names, str) else names
    script_dirs = [sysconfig.get_path("scripts")]
    try:
        script_dirs.append(str(Path(site.getusersitepackages()).parent / "Scripts"))
    except Exception:
        pass
    script_dirs = [path for path in script_dirs if path]
    for cli_name in cli_names:
        found = shutil.which(cli_name)
        if found:
            return found
        for scripts_dir in script_dirs:
            candidates = [Path(scripts_dir) / cli_name]
            if not cli_name.lower().endswith(".exe"):
                candidates.append(Path(scripts_dir) / f"{cli_name}.exe")
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)
    return None

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

# Output directory (each scrape creates a timestamped run directory under this base)
DEFAULT_OUTPUT_DIR = Path("output")

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
    generate_wacz: bool = False
    block_ads: bool = False
    save_to_wayback: bool = False
    use_global_ignores: bool = True
    ignore_patterns_file: Optional[str] = None
    scope_include_regex: Optional[str] = None
    scope_exclude_regex: Optional[str] = None

    # Browser settings
    headless: bool = True
    browser_timeout: int = 30000  # ms
    browser_engine: str = "auto"  # auto, playwright, patchright, camoufox, nodriver
    cdp_endpoint: Optional[str] = None  # e.g. "http://localhost:9222" to attach to running Chrome
    wait_until: str = "load"  # domcontentloaded|load|networkidle|commit
    behavior_profile: str = "archive"  # minimal|archive|aggressive
    net_idle_wait: float = 2.0
    auto_click_selector: Optional[str] = None
    block_rules_file: Optional[str] = None
    discovery_max_pages: int = 200
    discovery_max_urls: int = 5000
    crawl_backend: str = "native"
    archive_backend: str = "native"
    extractors: str = "auto"
    asset_extractors: str = "auto"

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

    def reset(self):
        """Clear queued/completed URL state for a fresh non-resume run."""
        self.conn.execute("DELETE FROM urls")
        self.conn.execute("DELETE FROM content_hashes")
        self.conn.execute("DELETE FROM domain_state")
        self.conn.commit()

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

    DEFAULT_BLOCK_RULES = [
        r"doubleclick\.net",
        r"googletagmanager\.com",
        r"google-analytics\.com",
        r"adservice\.google\.com",
        r"adsystem",
        r"ads-twitter\.com",
        r"facebook\.net/tr",
        r"hotjar\.com",
        r"segment\.com",
        r"optimizely\.com",
        r"pixel\.redditmedia\.com",
        r"/collect\?",
    ]

    BEHAVIOR_PROFILES = {
        "minimal": {
            "scroll_passes": 0,
            "post_load_delay": 0.2,
            "run_cookie_clicks": False,
            "autoplay_media": False,
        },
        "archive": {
            "scroll_passes": 2,
            "post_load_delay": 1.0,
            "run_cookie_clicks": True,
            "autoplay_media": True,
        },
        "aggressive": {
            "scroll_passes": 4,
            "post_load_delay": 1.5,
            "run_cookie_clicks": True,
            "autoplay_media": True,
        },
    }

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
        self._is_camoufox = False
        self._captured_graphql: List[Dict] = []  # Intercepted GraphQL responses
        self._block_rules_installed = False
        self._blocked_request_count = 0
        self._compiled_block_rules = self._load_block_rules()

    def _get_async_playwright(self):
        """Import the right async_playwright based on config.browser_engine."""
        engine = "playwright" if self.config.browser_engine == "auto" else self.config.browser_engine
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
            logger.info("Using camoufox (Firefox-based stealth)")
            from camoufox.async_api import AsyncCamoufox  # noqa: F401
        elif engine == "nodriver":
            logger.warning("nodriver runtime adapter is not implemented in this pipeline; falling back to playwright")

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
            if self.config.browser_engine == "camoufox":
                from camoufox.async_api import AsyncCamoufox

                self._playwright = AsyncCamoufox(headless=self.config.headless)
                self._browser = await self._playwright.__aenter__()
                self._is_camoufox = True
                context_kwargs = dict(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent=random.choice(USER_AGENTS),
                    locale=random.choice(ACCEPT_LANGUAGES).split(',')[0],
                    timezone_id='America/New_York',
                    ignore_https_errors=True,
                    java_script_enabled=True,
                    bypass_csp=False,
                )
                if self.session_manager and self.session_manager.cookies:
                    context_kwargs['storage_state'] = self.session_manager.cookies
                self._context = await self._browser.new_context(**context_kwargs)
                await self._setup_block_rules()
                logger.info("Camoufox browser launched")
                return True

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
            await self._setup_block_rules()

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

    def _load_block_rules(self) -> List[re.Pattern]:
        """Load block rules from defaults + optional file."""
        patterns = list(self.DEFAULT_BLOCK_RULES)
        if self.config.block_rules_file:
            path = Path(self.config.block_rules_file)
            if path.exists():
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    candidate = line.strip()
                    if candidate and not candidate.startswith("#"):
                        patterns.append(candidate)
            else:
                logger.warning(f"Block rules file not found: {self.config.block_rules_file}")

        compiled: List[re.Pattern] = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                compiled.append(re.compile(re.escape(pattern), re.IGNORECASE))
        return compiled

    def _get_behavior_profile(self) -> Dict[str, Any]:
        profile_name = (self.config.behavior_profile or "archive").strip().lower()
        return dict(self.BEHAVIOR_PROFILES.get(profile_name, self.BEHAVIOR_PROFILES["archive"]))

    async def _setup_block_rules(self):
        """Optionally block known tracker/ad resources."""
        if self._block_rules_installed or not self.config.block_ads:
            return

        async def route_handler(route):
            request = route.request
            if any(rule.search(request.url) for rule in self._compiled_block_rules):
                self._blocked_request_count += 1
                await route.abort()
            else:
                await route.continue_()

        await self._context.route("**/*", route_handler)
        self._block_rules_installed = True

    async def _click_cookie_buttons(self, page):
        """Dismiss common cookie/privacy banners to expose page content."""
        selectors = [
            "button#onetrust-accept-btn-handler",
            "button:has-text('Accept')",
            "button:has-text('I agree')",
            "button:has-text('Accept all')",
            "[aria-label*='Accept' i]",
            "[data-testid*='accept']",
        ]
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0:
                    await button.click(timeout=1000)
                    await asyncio.sleep(0.1)
                    return
            except Exception:
                continue

    async def _run_page_behaviors(self, page):
        """Run post-load behaviors for higher-fidelity capture."""
        profile = self._get_behavior_profile()
        if profile.get("run_cookie_clicks"):
            await self._click_cookie_buttons(page)

        if self.config.auto_click_selector:
            try:
                elements = page.locator(self.config.auto_click_selector)
                click_count = min(await elements.count(), 8)
                for idx in range(click_count):
                    try:
                        await elements.nth(idx).click(timeout=1500)
                        await asyncio.sleep(0.15)
                    except Exception:
                        continue
            except Exception:
                pass

        if profile.get("autoplay_media"):
            try:
                await page.evaluate(
                    """
                    () => {
                        for (const el of document.querySelectorAll("video, audio")) {
                            try { el.muted = true; el.play(); } catch (_) {}
                        }
                    }
                    """
                )
            except Exception:
                pass

        scroll_passes = int(profile.get("scroll_passes", 0))
        if scroll_passes > 0:
            await self._human_scroll(page, max_scrolls=max(1, scroll_passes * 4))

        post_load_delay = float(profile.get("post_load_delay", 0))
        if post_load_delay > 0:
            await asyncio.sleep(post_load_delay)

        if self.config.net_idle_wait > 0:
            try:
                await page.wait_for_load_state("networkidle", timeout=int(self.config.net_idle_wait * 1000))
            except Exception:
                pass

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

            # Navigate with configured load behavior, falling back to domcontentloaded on timeout.
            wait_until = (self.config.wait_until or "load").strip().lower()
            if wait_until not in {"domcontentloaded", "load", "networkidle", "commit"}:
                wait_until = "load"
            try:
                response = await page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=self.config.browser_timeout
                )
            except Exception:
                logger.debug(f"{wait_until} timeout, retrying with domcontentloaded: {url}")
                response = await page.goto(
                    url,
                    wait_until='domcontentloaded',
                    timeout=self.config.browser_timeout
                )
                # Give a bit more time for JS to render
                await asyncio.sleep(2.0)

            if not response:
                return None

            blocked_start = self._blocked_request_count
            await self._run_page_behaviors(page)

            # Get content
            raw_html = await page.content()
            metadata = {
                "screenshot": False,
                "js_rendered": True,
                "browser_engine": self.config.browser_engine,
                "cdp_mode": self._is_cdp,
                "blocked_requests": self._blocked_request_count - blocked_start,
                "block_rules_enabled": self.config.block_ads,
                "wait_until": wait_until,
                "behavior_profile": self.config.behavior_profile,
            }

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
            if self.config.save_screenshots:
                await page.screenshot(full_page=True)
                metadata["screenshot"] = True
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
        elif self._is_camoufox:
            if self._playwright:
                await self._playwright.__aexit__(None, None, None)
                self._playwright = None
            self._browser = None
            self._context = None
            self._is_camoufox = False
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
        return resolve_cli("wget") is not None

    def fetch_site(self, url: str) -> Optional[Path]:
        """Recursively download entire site."""
        if not self._wget_available:
            logger.warning("wget not available, skipping")
            return None

        domain = urlparse(url).netloc.replace("www.", "")
        output_path = self.output_dir / "wget" / safe_path_component(domain)
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"WGET: Downloading {url} (depth={self.config.max_depth})")

        cmd = [
            resolve_cli("wget") or "wget",
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
                logger.info(f"WGET complete: {output_path}")
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
        return resolve_cli("archivebox") is not None

    def archive_url(self, url: str) -> Optional[Path]:
        """Archive a URL with all formats."""
        domain = urlparse(url).netloc.replace("www.", "")
        output_path = self.output_dir / "archivebox" / safe_path_component(domain)
        output_path.mkdir(parents=True, exist_ok=True)
        command_report = {
            "backend": "archivebox",
            "source_url": "https://github.com/ArchiveBox/ArchiveBox",
            "license": "MIT",
            "available": self._available,
            "url": url,
            "output_path": str(output_path),
            "commands": [],
        }

        if not self._available:
            command_report["error"] = "archivebox CLI missing; install with `pip install archivebox`"
            (output_path / "archivebox_command.json").write_text(
                json.dumps(command_report, indent=2, default=str),
                encoding="utf-8",
            )
            logger.warning("archivebox not available. Install: pip install archivebox")
            return None

        logger.info(f"ARCHIVEBOX: Archiving {url}")

        # Initialize if needed
        archivebox_cli = resolve_cli("archivebox") or "archivebox"
        init_cmd = [archivebox_cli, "init", "--setup"]
        command_report["commands"].append(init_cmd)
        subprocess.run(init_cmd, cwd=output_path, capture_output=True)

        # Add URL with depth
        add_cmd = [
            archivebox_cli, "add",
            url,
            f"--depth={min(self.config.max_depth, 3)}",
            "--parser=auto"
        ]
        command_report["commands"].append(add_cmd)

        try:
            result = subprocess.run(
                add_cmd,
                cwd=output_path,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours max
            )
            command_report.update(
                {
                    "returncode": result.returncode,
                    "stdout_tail": (result.stdout or "")[-4000:],
                    "stderr_tail": (result.stderr or "")[-4000:],
                }
            )
            (output_path / "archivebox_command.json").write_text(
                json.dumps(command_report, indent=2, default=str),
                encoding="utf-8",
            )

            if result.returncode == 0:
                logger.info(f"ARCHIVEBOX complete: {output_path}")
                return output_path
            else:
                logger.warning(f"ARCHIVEBOX issues: {result.stderr[:200]}")
                return None

        except Exception as e:
            command_report["error"] = str(e)
            (output_path / "archivebox_command.json").write_text(
                json.dumps(command_report, indent=2, default=str),
                encoding="utf-8",
            )
            logger.error(f"ARCHIVEBOX failed: {e}")
            return None


# =============================================================================
# BROWSERTRIX FETCHER (Docker/CLI boundary only)
# =============================================================================

class BrowsertrixFetcher:
    """High-fidelity Browsertrix archive through Docker, without vendoring AGPL code."""

    def __init__(self, config: ScrapeConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir
        self._docker = shutil.which("docker")

    def crawl_url(self, url: str) -> Optional[Dict[str, Any]]:
        domain = urlparse(url).netloc.replace("www.", "") or "site"
        collection = re.sub(r"[^A-Za-z0-9_-]+", "_", safe_path_component(domain)).strip("_-") or "site"
        output_path = self.output_dir / "browsertrix"
        output_path.mkdir(parents=True, exist_ok=True)
        scope = "page" if self.config.max_depth <= 0 else "prefix"
        command = [
            self._docker or "docker",
            "run",
            "--rm",
            "-v",
            f"{output_path.resolve()}:/crawls",
            "webrecorder/browsertrix-crawler",
            "crawl",
            "--url",
            url,
            "--generateWACZ",
            "--generateCDX",
            "--text",
            "to-pages",
            "--collection",
            collection,
            "--headless",
            "--workers",
            "1",
            "--scopeType",
            scope,
            "--depth",
            str(max(self.config.max_depth, 0)),
            "--limit",
            str(max(self.config.max_pages, 1)),
            "--saveState",
            "always",
        ]
        report = {
            "backend": "browsertrix",
            "source_url": "https://github.com/webrecorder/browsertrix-crawler",
            "license": "AGPL-3.0",
            "boundary": "Docker CLI invocation only; no Browsertrix source is vendored.",
            "available": bool(self._docker),
            "url": url,
            "collection": collection,
            "scope": scope,
            "output_path": str(output_path),
            "command": command,
        }
        report_path = output_path / "browsertrix_command.json"

        if not self._docker:
            report["error"] = "docker CLI missing; install Docker Desktop and rerun with --archive-backend browsertrix"
            report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            logger.warning(report["error"])
            return None

        try:
            result = subprocess.run(
                command,
                cwd=output_path,
                capture_output=True,
                text=True,
                timeout=7200,
            )
            collection_dir = output_path / "collections" / collection
            wacz_path = collection_dir / f"{collection}.wacz"
            pages_jsonl = collection_dir / "pages" / "pages.jsonl"
            report.update(
                {
                    "returncode": result.returncode,
                    "stdout_tail": (result.stdout or "")[-4000:],
                    "stderr_tail": (result.stderr or "")[-4000:],
                    "collection_dir": str(collection_dir),
                    "wacz_path": str(wacz_path) if wacz_path.exists() else None,
                    "pages_jsonl": str(pages_jsonl) if pages_jsonl.exists() else None,
                }
            )
            report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            if result.returncode == 0:
                logger.info(f"BROWSERTRIX complete: {collection_dir}")
                return report
            logger.warning(f"BROWSERTRIX returned {result.returncode}: {(result.stderr or '')[:200]}")
            return report if collection_dir.exists() else None
        except Exception as e:
            report["error"] = str(e)
            report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            logger.error(f"BROWSERTRIX failed: {e}")
            return None


# =============================================================================
# RUN ARTIFACTS
# =============================================================================

class EventWriter:
    """Append-only JSONL writer for run events."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, **payload: Any):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            **payload,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(_to_serializable(entry), default=str) + "\n")


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
        self.base_output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
        self.output_dir = self.base_output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.checkpoint = None
        self.robots = RobotsHandler()
        self.rate_limiter = DomainRateLimiter(self.config)
        self._target_url = ""
        self._target_netloc = ""
        self._normalized_final_url = None
        self._event_writer = None
        self._backend_report: Dict[str, Any] = {}
        self._run_warnings: List[str] = []

        try:
            from .archive_utils import CrawlPolicy

            self.crawl_policy = CrawlPolicy(
                include_regex=self.config.scope_include_regex,
                exclude_regex=self.config.scope_exclude_regex,
                ignore_patterns_file=self.config.ignore_patterns_file,
                use_default_ignore_set=self.config.use_global_ignores,
            )
        except Exception as e:
            logger.debug(f"Crawl policy disabled: {e}")
            self.crawl_policy = None

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
        self._browsertrix_fetcher = None

        # Circuit breaker, CAPTCHA handler, structured data, session pool
        from .captcha_handler import CAPTCHADetector, CAPTCHASolver, load_env_file
        from .circuit_breaker import CircuitBreaker
        from .session_pool import SessionPool
        from .structured_data import StructuredDataExtractor

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

        tools = {
            "wget": resolve_cli("wget") is not None,
            "archivebox": resolve_cli("archivebox") is not None,
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

    def _start_run(self, url: str, mode: str) -> Dict[str, Any]:
        """Create a timestamped run directory and write backend/tool reports."""
        started_at = datetime.now()
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "") or "watch"
        safe_domain = safe_path_component(domain)
        run_id = f"{safe_domain}_{started_at.strftime('%Y%m%d_%H%M%S')}"

        self.output_dir = self.base_output_dir / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_output_contract()

        # These fetchers carry output paths, so they must be run-scoped.
        self._wget_fetcher = None
        self._archivebox_fetcher = None
        self._browsertrix_fetcher = None

        self._event_writer = EventWriter(self.output_dir / "events.jsonl")
        self._event_writer.write("run_started", target=url, mode=mode, run_id=run_id)

        try:
            from .backends import get_backend_report, write_backend_reports

            self._backend_report = get_backend_report()
            write_backend_reports(self.output_dir, self._backend_report)
            if self.config.generate_wacz and not self._backend_available("wacz"):
                self._record_warning(
                    "WACZ requested but wacz CLI/module is missing; WARC/CDXJ outputs will still be kept"
                )
        except Exception as e:
            self._backend_report = {"schema_version": 1, "backends": [], "available": [], "missing": []}
            self._record_warning(f"backend report failed: {e}")

        return {
            "run_id": run_id,
            "run_dir": str(self.output_dir),
            "safe_domain": safe_domain,
            "started_at": started_at.isoformat(),
        }

    def _ensure_output_contract(self):
        for name in ("pages", "assets", "warc", "har", "wacz", "extract", "screenshots", "replay"):
            (self.output_dir / name).mkdir(parents=True, exist_ok=True)

    def _record_warning(self, message: str):
        self._run_warnings.append(message)
        if self._event_writer:
            self._event_writer.write("warning", message=message)

    def _write_event(self, event_type: str, **payload: Any):
        if self._event_writer:
            self._event_writer.write(event_type, **payload)

    def _backend_item(self, name: str) -> Optional[Dict[str, Any]]:
        target = name.lower()
        for item in self._backend_report.get("backends", []):
            if str(item.get("name", "")).lower() == target:
                return item
        return None

    def _backend_available(self, name: str) -> bool:
        item = self._backend_item(name)
        return bool(item and item.get("available"))

    def _relative_path(self, path_value: Any) -> Any:
        if not path_value:
            return path_value
        try:
            path = Path(path_value)
        except TypeError:
            return path_value
        try:
            return str(path.resolve().relative_to(self.output_dir.resolve()))
        except Exception:
            return str(path)

    def _manifest_copy(self, results: Dict[str, Any]) -> Dict[str, Any]:
        manifest = _to_serializable(dict(results))
        outputs = manifest.get("outputs", {})
        if isinstance(outputs, dict):
            manifest["outputs"] = {key: self._relative_path(value) for key, value in outputs.items()}
        manifest["output_paths"] = {
            "manifest": "manifest.json",
            "events": "events.jsonl",
            "tool_versions": "tool_versions.json",
            "backend_report": "backend_report.json",
            "pages": "pages",
            "assets": "assets",
            "warc": "warc",
            "har": "har",
            "wacz": "wacz",
            "extract": "extract",
            "screenshots": "screenshots",
            "replay": "replay",
        }
        manifest["backend_list"] = self._backend_report.get("backends", [])
        manifest["warnings"] = list(self._run_warnings)
        manifest["settings"] = {
            "robots_politeness": self.config.respect_robots,
            "depth": self.config.max_depth,
            "max_pages": self.config.max_pages,
            "engine": self.config.browser_engine,
            "crawl_backend": self.config.crawl_backend,
            "archive_backend": self.config.archive_backend,
            "extractors": self.config.extractors,
            "asset_extractors": self.config.asset_extractors,
        }
        manifest["secrets_present"] = {
            "cookies": bool(self.config.cookie_file),
            "proxy": bool(self.config.proxy_list or self.config.proxy_pool_file),
            "auth": bool(self.config.auth_username or self.config.auth_password),
        }
        return manifest

    def _write_manifest(self, results: Dict[str, Any], safe_domain: str) -> Path:
        manifest = self._manifest_copy(results)
        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

        # Compatibility with older dashboard/history scanners.
        legacy_path = self.output_dir / f"{safe_domain}_manifest.json"
        legacy_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        return manifest_path

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

    def _queue_url(self, candidate_url: str, depth: int, is_seed: bool = False) -> bool:
        """Apply configured scope rules before adding a URL to the checkpoint queue."""
        if not self.checkpoint:
            return False
        normalized = candidate_url
        if self.crawl_policy:
            allowed, normalized, reason = self.crawl_policy.evaluate_url(
                candidate_url,
                self._target_netloc,
                self.config.follow_external,
                is_seed=is_seed,
            )
            if not allowed or not normalized:
                logger.debug(f"Skipping URL ({reason}): {candidate_url}")
                return False
        ok = self.checkpoint.add_url(normalized, depth=depth)
        if ok:
            self._write_event("target_queued", url=normalized, depth=depth, is_seed=is_seed)
        return ok

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

    @property
    def browsertrix_fetcher(self) -> BrowsertrixFetcher:
        """Lazy-initialize Browsertrix Docker fetcher."""
        if self._browsertrix_fetcher is None:
            self._browsertrix_fetcher = BrowsertrixFetcher(self.config, self.output_dir)
        return self._browsertrix_fetcher

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
        self._write_event("fetch_started", url=url, browser_requested=use_browser)

        # Circuit breaker check
        if not self.circuit_breaker.can_request(domain):
            logger.debug(f"Circuit breaker OPEN for {domain}, skipping: {url}")
            self._write_event("fetch_finished", url=url, ok=False, skipped="circuit_open")
            return None

        # Check robots.txt
        if self.config.respect_robots and not self.robots.can_fetch(url):
            logger.debug(f"Blocked by robots.txt: {url}")
            self._write_event("fetch_finished", url=url, ok=False, skipped="robots")
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
                self._write_event("browser_escalation", url=url, reason="js_content_detected")
                use_browser = True
                http_fallback = result
                result = None

        # Use Playwright for JS content
        if use_browser and self._tools.get('playwright'):
            fetcher = await self._get_playwright_fetcher()
            result = await fetcher.fetch_with_escalation(url)
        elif use_browser:
            self._record_warning("browser requested but Playwright is missing")
            self._write_event("skipped_optional_backend", backend="playwright", reason="missing")

        # Fall back to HTTP result if browser failed
        if result is None and http_fallback is not None:
            logger.debug(f"Browser failed, using HTTP fallback for: {url}")
            result = http_fallback

        # Post-fetch processing
        if result:
            if not self._normalized_final_url:
                self._normalized_final_url = result.final_url
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
                    self._write_event("fetch_finished", url=url, ok=False, reason="captcha_unsolved")
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
            self._write_event(
                "fetch_finished",
                url=url,
                ok=True,
                status_code=result.status_code,
                method=result.method,
                final_url=result.final_url,
            )
        else:
            self.circuit_breaker.record_failure(domain, reason="fetch_failed")
            self.rate_limiter.record_error(domain)
            self._write_event("fetch_finished", url=url, ok=False, reason="fetch_failed")

        return result

    def _append_weapon(self, results: Dict[str, Any], weapon: str):
        if weapon not in results["weapons_fired"]:
            results["weapons_fired"].append(weapon)

    def _crawl_stats(self) -> Dict[str, Any]:
        checkpoint_stats = self.checkpoint.stats() if self.checkpoint else {}
        by_domain = []
        if self.checkpoint:
            try:
                rows = self.checkpoint.conn.execute(
                    """
                    SELECT domain, status, COUNT(*) AS count
                    FROM urls
                    GROUP BY domain, status
                    ORDER BY domain, status
                    """
                ).fetchall()
                by_domain = [dict(row) for row in rows]
            except Exception:
                by_domain = []
        return {
            "requested_backend": self.config.crawl_backend,
            "effective_backend": "native",
            "checkpoint": checkpoint_stats,
            "by_domain": by_domain,
            "rate_limiter_error_counts": dict(self.rate_limiter._error_counts),
            "pages_scraped": self._pages_scraped,
            "errors": self._errors,
            "resume_checkpoint": str(self.checkpoint.db_path) if self.checkpoint else None,
        }

    def _prepare_crawl_backend(self, results: Dict[str, Any]):
        if self.config.crawl_backend == "native":
            results["crawl_backend"] = {"requested": "native", "effective": "native"}
            return

        backend_name = "Crawlee Python" if self.config.crawl_backend == "crawlee" else self.config.crawl_backend
        backend = self._backend_item(backend_name)
        available = bool(backend and backend.get("available"))
        results["crawl_backend"] = {
            "requested": self.config.crawl_backend,
            "effective": "native",
            "available": available,
            "backend": backend,
        }
        if not available:
            self._record_warning(
                f"crawl backend '{self.config.crawl_backend}' is missing; using native crawler"
            )
            self._write_event(
                "skipped_optional_backend",
                backend=self.config.crawl_backend,
                reason="missing",
            )
        else:
            self._record_warning(
                f"crawl backend '{self.config.crawl_backend}' is installed but the native queue remains the execution pipeline for manifest/extraction consistency"
            )
            self._write_event(
                "skipped_optional_backend",
                backend=self.config.crawl_backend,
                reason="native_pipeline_selected",
            )

    async def _run_archive_backend(self, url: str, results: Dict[str, Any]) -> bool:
        backend = self.config.archive_backend
        if backend == "browsertrix":
            return self._run_browsertrix_backend(url, results)
        if backend == "archivebox":
            return self._run_archivebox_backend(url, results)
        return await self._run_native_archive_backend(url, results)

    async def _run_native_archive_backend(self, url: str, results: Dict[str, Any]) -> bool:
        self._write_event("archive_backend_started", backend="native", url=url)
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
                generate_wacz=self.config.generate_wacz,
            )
            result_dir = save_forensic_result(forensic_result, self.output_dir / "forensic")
            self._normalized_final_url = forensic_result.final_url
            self._append_weapon(results, "native_archive")
            results["outputs"]["forensic"] = str(result_dir)
            results["outputs"]["warc"] = forensic_result.warc_path
            if forensic_result.cdxj_path:
                results["outputs"]["cdxj"] = forensic_result.cdxj_path
            if forensic_result.wacz_path:
                results["outputs"]["wacz"] = forensic_result.wacz_path
            elif self.config.generate_wacz:
                self._record_warning("native WACZ generation failed; see forensic/wacz/*.wacz_error.json")
            if forensic_result.screenshot_path:
                results["outputs"]["screenshot"] = forensic_result.screenshot_path
            if forensic_result.pdf_path:
                results["outputs"]["pdf"] = forensic_result.pdf_path
            results["archive_backend"] = {
                "requested": "native",
                "effective": "forensic_capture",
                "ok": True,
            }
            results["forensic_stats"] = {
                "requests_captured": len(forensic_result.requests),
                "responses_captured": len(forensic_result.responses),
                "assets_captured": len(forensic_result.assets),
                "cookies": len(forensic_result.cookies),
                "local_storage_keys": len(forensic_result.local_storage),
            }
            self._run_asset_extractors_for_dir(self.output_dir / "forensic" / "assets")
            self._write_event("archive_backend_finished", backend="native", ok=True)
            self._pages_scraped = max(self._pages_scraped, 1)
            return True
        except Exception as e:
            self._record_warning(f"native archive backend failed: {e}")
            self._write_event("archive_backend_finished", backend="native", ok=False, error=str(e))
            results["archive_backend"] = {"requested": "native", "effective": "forensic_capture", "ok": False, "error": str(e)}
            return False

    def _run_archivebox_backend(self, url: str, results: Dict[str, Any]) -> bool:
        self._write_event("archive_backend_started", backend="archivebox", url=url)
        ab_path = self.archivebox_fetcher.archive_url(url)
        if ab_path:
            self._append_weapon(results, "archivebox")
            results["outputs"]["archivebox"] = str(ab_path)
            results["archive_backend"] = {
                "requested": "archivebox",
                "effective": "archivebox",
                "ok": True,
            }
            self._write_event("archive_backend_finished", backend="archivebox", ok=True)
            return True
        self._record_warning("ArchiveBox backend missing or failed; see backend_report.json")
        self._write_event("archive_backend_finished", backend="archivebox", ok=False)
        self._write_event("skipped_optional_backend", backend="archivebox", reason="missing_or_failed")
        results["archive_backend"] = {"requested": "archivebox", "effective": "archivebox", "ok": False}
        return False

    def _run_browsertrix_backend(self, url: str, results: Dict[str, Any]) -> bool:
        self._write_event("archive_backend_started", backend="browsertrix", url=url)
        report = self.browsertrix_fetcher.crawl_url(url)
        if report:
            self._append_weapon(results, "browsertrix")
            results["outputs"]["browsertrix"] = report.get("collection_dir") or report.get("output_path")
            if report.get("wacz_path"):
                results["outputs"]["browsertrix_wacz"] = report["wacz_path"]
            if report.get("pages_jsonl"):
                results["outputs"]["browsertrix_pages"] = report["pages_jsonl"]
            results["archive_backend"] = {
                "requested": "browsertrix",
                "effective": "browsertrix",
                "ok": report.get("returncode") == 0,
                "report": report,
            }
            self._write_event(
                "archive_backend_finished",
                backend="browsertrix",
                ok=report.get("returncode") == 0,
            )
            return report.get("returncode") == 0
        self._record_warning("Browsertrix backend missing or failed; see browsertrix/browsertrix_command.json")
        self._write_event("archive_backend_finished", backend="browsertrix", ok=False)
        self._write_event("skipped_optional_backend", backend="browsertrix", reason="missing_or_failed")
        results["archive_backend"] = {"requested": "browsertrix", "effective": "browsertrix", "ok": False}
        return False

    def _run_asset_extractors_for_dir(self, asset_root: Path):
        if not self.config.asset_extractors or self.config.asset_extractors.lower() == "none":
            return
        if not asset_root.exists():
            return
        candidates = [
            path for path in asset_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".html", ".htm", ".txt"}
        ]
        if not candidates:
            return
        try:
            from .extractors import run_asset_extractors
        except Exception as e:
            self._write_event("extraction_backend_finished", backend="asset_extractors", ok=False, error=str(e))
            return

        for asset_path in candidates:
            self._write_event(
                "extraction_backend_started",
                asset=str(asset_path),
                extractors=self.config.asset_extractors,
            )
            result = run_asset_extractors(
                asset_path,
                self.output_dir / "extract" / "assets",
                requested=self.config.asset_extractors,
            )
            self._write_event(
                "extraction_backend_finished",
                asset=str(asset_path),
                ok=bool(result.get("outputs")),
                extractors=self.config.asset_extractors,
            )

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
        url = normalize_target_url(url)

        if depth:
            self.config.max_depth = depth

        self._pages_scraped = 0
        self._errors = 0
        self._shutdown_requested = False
        self._run_warnings = []
        self._normalized_final_url = None

        domain = urlparse(url).netloc.replace("www.", "")
        safe_domain = safe_path_component(domain)
        self._target_url = url
        self._target_netloc = urlparse(url).netloc.lower()
        run_info = self._start_run(url, mode)
        logger.info(f"DEATH STAR V2 FIRING ON: {url} (mode={mode})")

        # Initialize checkpoint
        self.checkpoint = EnhancedCheckpoint(safe_domain)

        # Add seed URL if not resuming or empty
        if not resume:
            self.checkpoint.reset()
        stats = self.checkpoint.stats()
        if not resume or stats.get('total', 0) == 0:
            # Reset any previously failed URLs so resumed runs retry them if the queue is empty.
            try:
                self.checkpoint.conn.execute(
                    "UPDATE urls SET status = 'pending' WHERE status = 'failed'"
                )
                self.checkpoint.conn.commit()
            except Exception:
                pass
            self._queue_url(url, depth=0, is_seed=True)

        results = {
            "target": url,
            "normalized_final_url": None,
            "mode": mode,
            "depth": self.config.max_depth,
            "started_at": run_info["started_at"],
            "run_id": run_info["run_id"],
            "run_dir": run_info["run_dir"],
            "weapons_fired": [],
            "pages_scraped": 0,
            "errors": 0,
            "error_details": [],
            "outputs": {
                "events": str(self.output_dir / "events.jsonl"),
                "tool_versions": str(self.output_dir / "tool_versions.json"),
                "backend_report": str(self.output_dir / "backend_report.json"),
            }
        }

        self._prepare_crawl_backend(results)

        # Mode-specific scraping
        if mode == "quick":
            # Just wget
            wget_path = self.wget_fetcher.fetch_site(url)
            if wget_path:
                self._append_weapon(results, "wget")
                results["outputs"]["wget"] = str(wget_path)
            else:
                self._write_event("skipped_optional_backend", backend="wget", reason="missing_or_failed")

        elif mode == "archive":
            await self._run_archive_backend(url, results)

        elif mode in ("smart", "stealth", "full"):
            # Crawl and scrape
            use_browser = mode == "stealth"

            self._append_weapon(results, "http" if not use_browser else "playwright")

            # Process queue
            output_path = self.output_dir / "pages" / safe_domain
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
                                        self._queue_url(link, depth=page_depth + 1)

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
                    self._append_weapon(results, "wget")
                    results["outputs"]["wget"] = str(wget_path)

            if mode == "full" and self.config.archive_backend != "native":
                await self._run_archive_backend(url, results)

        elif mode == "forensic":
            # Complete forensic capture
            self._append_weapon(results, "forensic_capture")

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
                    generate_wacz=self.config.generate_wacz,
                )

                result_dir = save_forensic_result(forensic_result, self.output_dir / "forensic")
                self._normalized_final_url = forensic_result.final_url
                results["outputs"]["forensic"] = str(result_dir)
                results["outputs"]["warc"] = forensic_result.warc_path
                if getattr(forensic_result, "cdxj_path", None):
                    results["outputs"]["cdxj"] = forensic_result.cdxj_path
                if getattr(forensic_result, "wacz_path", None):
                    results["outputs"]["wacz"] = forensic_result.wacz_path
                elif self.config.generate_wacz:
                    self._record_warning("native WACZ generation failed; see forensic/wacz/*.wacz_error.json")
                results["outputs"]["screenshot"] = forensic_result.screenshot_path
                if forensic_result.pdf_path:
                    results["outputs"]["pdf"] = forensic_result.pdf_path
                results["forensic_stats"] = {
                    "requests_captured": len(forensic_result.requests),
                    "assets_captured": len(forensic_result.assets),
                    "cookies": len(forensic_result.cookies),
                    "local_storage_keys": len(forensic_result.local_storage),
                }
                self._run_asset_extractors_for_dir(self.output_dir / "forensic" / "assets")
                self._pages_scraped = 1

            except ImportError as e:
                logger.error(f"Forensic capture requires additional modules: {e}")
                results["errors"] = 1

        elif mode == "planetary":
            # MAXIMUM DESTRUCTION - everything!
            logger.info("PLANETARY DESTRUCTION MODE - ALL WEAPONS FIRING")

            # 1. Site discovery first
            try:
                from .site_discovery import SiteDiscovery

                discovery = SiteDiscovery(output_dir=self.output_dir / "discovery")
                discovery_result = await discovery.discover_site(
                    url,
                    max_depth=min(self.config.max_depth, 2),
                    max_pages=self.config.discovery_max_pages,
                    max_urls=self.config.discovery_max_urls,
                )
                self._append_weapon(results, "site_discovery")
                results["outputs"]["discovery"] = str(self.output_dir / "discovery" / safe_domain)
                results["discovery_stats"] = discovery_result.stats

                # Add discovered URLs to queue
                for discovered_url in list(discovery_result.html_pages)[:self.config.max_pages]:
                    self._queue_url(discovered_url, depth=1)

            except Exception as e:
                logger.warning(f"Site discovery failed: {e}")

            # 2. Forensic capture of main page
            forensic_result = None
            try:
                from .forensic_capture import ForensicCapture, save_forensic_result

                forensic = ForensicCapture(output_dir=self.output_dir / "forensic")
                forensic_result = await forensic.capture_page(url, generate_wacz=self.config.generate_wacz)
                save_forensic_result(forensic_result, self.output_dir / "forensic")
                self._run_asset_extractors_for_dir(self.output_dir / "forensic" / "assets")
                self._normalized_final_url = forensic_result.final_url
                self._append_weapon(results, "forensic_capture")
                results["outputs"]["forensic"] = str(self.output_dir / "forensic")
                if getattr(forensic_result, "warc_path", None):
                    results["outputs"]["warc"] = forensic_result.warc_path
                if getattr(forensic_result, "cdxj_path", None):
                    results["outputs"]["cdxj"] = forensic_result.cdxj_path
                if getattr(forensic_result, "wacz_path", None):
                    results["outputs"]["wacz"] = forensic_result.wacz_path
                elif self.config.generate_wacz:
                    self._record_warning("native WACZ generation failed; see forensic/wacz/*.wacz_error.json")

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
                    self._append_weapon(results, "media_extractor")
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
            output_path = self.output_dir / "pages" / safe_domain
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
                                        self._queue_url(link, depth=page_depth + 1)
                        else:
                            self.checkpoint.mark_failed(page_url, "fetch_failed")
                            self._errors += 1

                    except Exception as e:
                        self.checkpoint.mark_failed(page_url, str(e))
                        self._errors += 1

            self._append_weapon(results, "stealth_crawl")
            results["outputs"]["pages"] = str(output_path)

            # 5. wget mirror
            if self._tools.get('wget'):
                wget_path = self.wget_fetcher.fetch_site(url)
                if wget_path:
                    self._append_weapon(results, "wget")
                    results["outputs"]["wget"] = str(wget_path)

            # 6. Optional external archive backend
            if self.config.archive_backend != "native":
                await self._run_archive_backend(url, results)

        elif mode == "ultimate":
            # ULTIMATE MODE - Absolutely everything
            logger.info("ULTIMATE DESTRUCTION MODE - LEAVING NOTHING BEHIND")

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
                    self._append_weapon(results, "advanced_capture")
                    results["outputs"]["advanced"] = str(self.output_dir / "advanced" / safe_domain)
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
                        generate_har=True,
                        generate_wacz=self.config.generate_wacz,
                    )
                    save_forensic_result(forensic_result, self.output_dir / "forensic")
                    self._run_asset_extractors_for_dir(self.output_dir / "forensic" / "assets")
                    self._normalized_final_url = forensic_result.final_url
                    self._append_weapon(results, "forensic_capture")
                    results["outputs"]["forensic"] = str(self.output_dir / "forensic")
                    results["outputs"]["warc"] = forensic_result.warc_path
                    if getattr(forensic_result, "cdxj_path", None):
                        results["outputs"]["cdxj"] = forensic_result.cdxj_path
                    if getattr(forensic_result, "wacz_path", None):
                        results["outputs"]["wacz"] = forensic_result.wacz_path
                    elif self.config.generate_wacz:
                        self._record_warning("native WACZ generation failed; see forensic/wacz/*.wacz_error.json")
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
                    self._append_weapon(results, "wayback_integration")
                    results["outputs"]["wayback"] = str(self.output_dir / "wayback" / safe_domain)
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
                    discovery_result = await discovery.discover_site(
                        url,
                        max_depth=min(self.config.max_depth, 2),
                        max_pages=self.config.discovery_max_pages,
                        max_urls=self.config.discovery_max_urls,
                    )
                    self._append_weapon(results, "site_discovery")
                    results["outputs"]["discovery"] = str(self.output_dir / "discovery" / safe_domain)
                    results["discovery_stats"] = discovery_result.stats

                    # Add discovered URLs to queue (skip non-HTML assets)
                    for discovered_url in list(discovery_result.html_pages)[:self.config.max_pages]:
                        if self._should_crawl_url(discovered_url):
                            self._queue_url(discovered_url, depth=1)

                except Exception as e:
                    logger.warning(f"Site discovery failed: {e}")

                # 5. Media extraction
                try:
                    from .media_extractor import MediaExtractor

                    extractor = MediaExtractor(output_dir=self.output_dir / "media")
                    html = await browser_page.content()
                    media_result = await extractor.extract_all(url, html)
                    self._append_weapon(results, "media_extractor")
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
            output_path = self.output_dir / "pages" / safe_domain
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
                                        self._queue_url(link, depth=page_depth + 1)
                        else:
                            self.checkpoint.mark_failed(page_url, "fetch_failed")
                            self._errors += 1

                    except Exception as e:
                        self.checkpoint.mark_failed(page_url, str(e))
                        self._errors += 1

            self._append_weapon(results, "stealth_crawl")
            results["outputs"]["pages"] = str(output_path)

            # 7. wget mirror
            if self._tools.get('wget'):
                wget_path = self.wget_fetcher.fetch_site(url)
                if wget_path:
                    self._append_weapon(results, "wget")
                    results["outputs"]["wget"] = str(wget_path)

            # 8. Optional external archive backend
            if self.config.archive_backend != "native":
                await self._run_archive_backend(url, results)

            logger.info("ULTIMATE DESTRUCTION COMPLETE - NOTHING REMAINS")

        # Finalize results
        results["pages_scraped"] = self._pages_scraped
        results["errors"] = self._errors
        results["normalized_final_url"] = self._normalized_final_url or results.get("normalized_final_url")
        results["completed_at"] = datetime.now().isoformat()
        results["checkpoint_stats"] = self.checkpoint.stats()
        results["crawl_stats"] = self._crawl_stats()
        results["warnings"] = list(self._run_warnings)

        self._write_event(
            "run_finished",
            pages_scraped=self._pages_scraped,
            errors=self._errors,
            warnings=len(self._run_warnings),
        )

        # Save manifest
        manifest_path = self._write_manifest(results, safe_domain)
        results["manifest"] = str(manifest_path)

        logger.info(f"DESTRUCTION COMPLETE: {self._pages_scraped} pages, {self._errors} errors")

        return results

    def _save_page(self, page: ScrapedPage, output_dir: Path):
        """Save scraped page to disk."""
        # Create filename from URL
        parsed = urlparse(page.url)
        path_parts = parsed.path.strip('/').replace('/', '_') or 'index'
        path_parts = safe_path_component(path_parts)
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
            "metadata": page.metadata,
        }

        # Save metadata
        meta_path = output_dir / f"{filename}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(_to_serializable(page_data), f, indent=2, default=str)

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

        if self.config.extract_content:
            try:
                from .extractors import run_page_extractors

                self._write_event("extraction_backend_started", url=page.url, extractors=self.config.extractors)
                extraction = run_page_extractors(
                    page.raw_html,
                    page.final_url or page.url,
                    self.output_dir / "extract" / "pages",
                    filename,
                    requested=self.config.extractors,
                )
                self._write_event(
                    "extraction_backend_finished",
                    url=page.url,
                    ok=True,
                    primary=extraction.get("chosen_primary_extractor"),
                )
                page_data["extractors"] = extraction
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(_to_serializable(page_data), f, indent=2, default=str)
            except Exception as e:
                self._write_event(
                    "extraction_backend_finished",
                    url=page.url,
                    ok=False,
                    error=str(e),
                )

    async def close(self):
        """Clean up resources."""
        if self._playwright_fetcher:
            await self._playwright_fetcher.close()
        if self.checkpoint:
            self.checkpoint.close()


# =============================================================================
# CLI INTERFACE
# =============================================================================

def _find_replay_archives(run_dir: Path) -> List[Path]:
    patterns = ("*.warc", "*.warc.gz", "*.arc", "*.arc.gz", "*.wacz")
    archives: List[Path] = []
    for pattern in patterns:
        archives.extend(path for path in run_dir.rglob(pattern) if path.is_file())
    return sorted(set(archives))


def replay_run(
    run_dir: str,
    host: str = "127.0.0.1",
    port: int = 8080,
    prepare_only: bool = False,
) -> int:
    """Prepare a pywb replay collection for a Death Star run and start wayback."""
    run_path = Path(run_dir).resolve()
    replay_dir = run_path / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    report_path = replay_dir / "pywb_replay.json"

    if not run_path.exists():
        print(f"Run directory does not exist: {run_path}")
        return 1

    archives = _find_replay_archives(run_path)
    report = {
        "run_dir": str(run_path),
        "archives": [str(path) for path in archives],
        "host": host,
        "port": port,
        "source_url": "https://github.com/webrecorder/pywb",
        "license": "GPL-3.0-or-later",
        "boundary": "External pywb CLI only; no pywb source is vendored.",
    }

    if not archives:
        report["error"] = "No WARC/ARC/WACZ archives found under run directory"
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(report["error"])
        return 1

    wb_manager = resolve_cli("wb-manager")
    wayback = resolve_cli("wayback")
    if not wb_manager or not wayback:
        report["error"] = "pywb CLI missing; install with `pip install pywb`"
        report["wb_manager"] = wb_manager
        report["wayback"] = wayback
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(report["error"])
        print(f"Archives are still available under: {run_path}")
        print("WACZ files can also be opened with ReplayWeb.page.")
        return 1

    pywb_root = replay_dir / "pywb"
    pywb_root.mkdir(parents=True, exist_ok=True)
    collection = re.sub(r"[^A-Za-z0-9_-]+", "_", f"death-star-{run_path.name}")[:80]
    collection = collection.strip("_-") or "death-star-run"
    warc_archives = [path for path in archives if path.suffix.lower() != ".wacz"]
    wacz_archives = [path for path in archives if path.suffix.lower() == ".wacz"]

    commands = [
        [wb_manager, "init", collection],
    ]
    for archive in warc_archives:
        commands.append([wb_manager, "add", collection, str(archive)])
    for archive in wacz_archives:
        commands.append(
            [wb_manager, "add", "--unpack-wacz", collection, str(archive)]
        )
    report["collection"] = collection
    report["pywb_root"] = str(pywb_root)
    report["commands"] = commands

    for command in commands:
        result = subprocess.run(command, cwd=pywb_root, capture_output=True, text=True)
        report.setdefault("command_results", []).append(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout_tail": (result.stdout or "")[-2000:],
                "stderr_tail": (result.stderr or "")[-2000:],
            }
        )
        if result.returncode != 0 and "already exists" not in (result.stderr or "").lower():
            report["error"] = f"pywb command failed: {' '.join(command)}"
            report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(report["error"])
            return result.returncode

    serve_command = [wayback, "-p", str(port)]
    report["serve_command"] = serve_command
    report["url"] = f"http://{host}:{port}/{collection}/"
    report["prepare_only"] = prepare_only
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if prepare_only:
        print(f"Prepared pywb replay collection at {pywb_root}")
        print(f"Replay URL after starting wayback: {report['url']}")
        return 0
    print(f"Starting pywb replay at {report['url']}")
    print("Press Ctrl+C to stop the replay server.")
    return subprocess.run(serve_command, cwd=pywb_root).returncode


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "replay":
        replay_parser = argparse.ArgumentParser(
            description="Replay a Death Star run directory with optional pywb"
        )
        replay_parser.add_argument("run_dir", help="Death Star run directory")
        replay_parser.add_argument("--host", default="127.0.0.1", help="Replay host")
        replay_parser.add_argument("--port", type=int, default=8080, help="Replay port")
        replay_parser.add_argument("--prepare-only", action="store_true", help="Build pywb collection without starting server")
        replay_args = replay_parser.parse_args(sys.argv[2:])
        raise SystemExit(
            replay_run(
                replay_args.run_dir,
                replay_args.host,
                replay_args.port,
                prepare_only=replay_args.prepare_only,
            )
        )

    parser = argparse.ArgumentParser(
        description="Death Star V2 - Nuke From Orbit Web Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  quick      Fast wget-only download
  smart      Adaptive routing (HTTP + browser fallback) [DEFAULT]
  stealth    Browser-only with anti-bot evasion
  full       All weapons (smart crawl + wget + archivebox)
  archive    Full archival via ArchiveBox only
  forensic   Complete forensic capture (WARC, HAR, assets, storage)
  planetary  MAXIMUM DESTRUCTION - all modes combined
  watch      Passive CDP capture while you browse manually
  x_community  X/Twitter community scraper (requires --cookies)

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
                       choices=["quick", "smart", "stealth", "full", "archive", "forensic", "planetary", "ultimate", "watch", "x_community"],
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
    parser.add_argument("--wacz", action="store_true",
                       help="Generate WACZ package when WARC and wacz CLI are available")
    parser.add_argument("--block-ads", action="store_true",
                       help="Block known ad/tracker resources in browser modes")
    parser.add_argument("--block-rules-file",
                       help="Additional regex block rules file (one pattern per line)")
    parser.add_argument("--behavior-profile", default="archive",
                       choices=["minimal", "archive", "aggressive"],
                       help="Browser behavior profile (default: archive)")
    parser.add_argument("--wait-until", default="load",
                       choices=["domcontentloaded", "load", "networkidle", "commit"],
                       help="Browser navigation wait state (default: load)")
    parser.add_argument("--net-idle-wait", type=float, default=2.0,
                       help="Seconds to wait for networkidle after behaviors (default: 2.0)")
    parser.add_argument("--auto-click-selector",
                       help="Optional CSS selector to click after page load in browser modes")
    parser.add_argument("--save-wayback", action="store_true",
                       help="Submit captured target URL to Internet Archive SavePageNow")
    parser.add_argument("--include",
                       help="Regex of URLs to include in crawl scope")
    parser.add_argument("--exclude",
                       help="Regex of URLs to exclude from crawl scope")
    parser.add_argument("--ignore-patterns",
                       help="Regex file for crawl ignores (one regex per line)")
    parser.add_argument("--no-global-ignores", action="store_true",
                       help="Disable built-in global ignore set")
    parser.add_argument("--discovery-max-pages", type=int, default=200,
                       help="Max pages for site discovery phases (default: 200)")
    parser.add_argument("--discovery-max-urls", type=int, default=5000,
                       help="Max URLs tracked in site discovery (default: 5000)")
    parser.add_argument("--crawl-backend", default="native",
                       choices=["native", "crawlee"],
                       help="Crawler backend (default: native)")
    parser.add_argument("--archive-backend", default="native",
                       choices=["native", "archivebox", "browsertrix"],
                       help="Archive backend preference (default: native)")
    parser.add_argument("--extractors", default="auto",
                       help="Comma-separated extractors, or auto (default: auto)")
    parser.add_argument("--asset-extractors", default="auto",
                       help="Comma-separated asset extractors, or auto (default: auto)")

    # Browser engine and CDP
    parser.add_argument("--cdp", help="CDP endpoint to attach to running Chrome (e.g. http://localhost:9222)")
    parser.add_argument("--engine", default="auto",
                       choices=["auto", "playwright", "patchright", "camoufox", "nodriver"],
                       help="Browser engine (default: auto)")
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
    parser.add_argument("--doctor", action="store_true",
                       help="Report optional backend availability and exit")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.install:
        print_installation_guide()
        return

    if args.doctor:
        from .backends import format_doctor

        print(format_doctor())
        return

    if args.mode == "watch" and not args.cdp:
        parser.error("--mode watch requires --cdp")

    if not args.target and not args.targets and args.mode != "watch":
        parser.print_help()
        print("\nExample: python death_star_v2.py --target https://example.com --mode smart")
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
        generate_wacz=args.wacz,
        block_ads=args.block_ads,
        block_rules_file=args.block_rules_file,
        behavior_profile=args.behavior_profile,
        wait_until=args.wait_until,
        net_idle_wait=args.net_idle_wait,
        auto_click_selector=args.auto_click_selector,
        save_to_wayback=args.save_wayback,
        use_global_ignores=not args.no_global_ignores,
        ignore_patterns_file=args.ignore_patterns,
        scope_include_regex=args.include,
        scope_exclude_regex=args.exclude,
        discovery_max_pages=args.discovery_max_pages,
        discovery_max_urls=args.discovery_max_urls,
        crawl_backend=args.crawl_backend,
        archive_backend=args.archive_backend,
        extractors=args.extractors,
        asset_extractors=args.asset_extractors,
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
        if args.mode == "watch":
            from .watch_mode import WatchMode

            watcher = WatchMode(
                cdp_endpoint=args.cdp,
                output_dir=str(output_dir / "watch"),
                snapshot_interval=30,
            )
            await watcher.run()
            return

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
                print(f"\nX COMMUNITY SCRAPED: {result.name}")
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
                print(json.dumps(_to_serializable(result), indent=2, default=str))

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

                print(json.dumps(_to_serializable(results), indent=2, default=str))
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
