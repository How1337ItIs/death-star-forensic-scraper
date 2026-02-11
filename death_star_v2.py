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
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

# When run as script (e.g. python death_star_v2.py), ensure core dir is on path
# so sibling modules (forensic_capture, media_extractor, etc.) can be imported.
if __name__ == "__main__" or not __package__:
    _core_dir = Path(__file__).resolve().parent
    _core_str = str(_core_dir)
    if _core_str not in sys.path:
        sys.path.insert(0, _core_str)


def _import_core(module_name: str, *names: str):
    """Import from a sibling core module, handling both package and script invocation.
    
    Usage:
        ForensicCapture, save_forensic_result = _import_core(
            'forensic_capture', 'ForensicCapture', 'save_forensic_result'
        )
    Returns the requested attributes, or raises ImportError.
    """
    mod = None
    for attempt in [f'.{module_name}', module_name]:
        try:
            mod = __import__(attempt, fromlist=list(names)) if '.' not in attempt else None
            if mod is None:
                import importlib
                mod = importlib.import_module(attempt, package=__package__)
            break
        except (ImportError, TypeError):
            continue
    if mod is None:
        # Final fallback: direct import from already-patched sys.path
        mod = __import__(module_name, fromlist=list(names))
    if len(names) == 1:
        return getattr(mod, names[0])
    return tuple(getattr(mod, n) for n in names)


# JSON-safe serialization for manifests and results
_JSON_SAFE = (str, int, float, bool, type(None))

def _to_serializable(obj):
    """Recursively convert non-JSON-safe types (Path, URL, set, etc.) to primitives."""
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
    # Catch-all: datetime, httpx.URL, etc.
    return str(obj)


def normalize_target_url(url: str) -> str:
    """Normalize target input to a valid HTTP(S) URL."""
    def _is_valid_netloc(netloc: str) -> bool:
        if not netloc or any(ch.isspace() for ch in netloc):
            return False

        host_port = netloc.rsplit("@", 1)[-1]

        # IPv6 literal: [::1] or [::1]:8443
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

        # Split optional port
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            if not port.isdigit():
                return False
        else:
            host = host_port

        if not host:
            return False

        # IPv4 literal
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

        labels = host.split(".")
        for label in labels:
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

    # Already a valid HTTP(S) URL
    if parsed.scheme in {"http", "https"}:
        if not _is_valid_netloc(parsed.netloc):
            raise ValueError("Target URL is missing a host")
        return raw

    # Handle host:port shorthand (e.g., localhost:8000)
    if parsed.scheme and not parsed.netloc and "://" not in raw:
        normalized = f"https://{raw}"
        parsed = urlparse(normalized)
        if not _is_valid_netloc(parsed.netloc):
            raise ValueError("Target URL is invalid")
        return normalized

    # Unsupported explicit scheme (ftp:, file:, etc.)
    if parsed.scheme:
        raise ValueError(f"Unsupported URL scheme '{parsed.scheme}'. Use http:// or https://")

    # Bare host/domain -> default to HTTPS
    normalized = f"https://{raw}"
    parsed = urlparse(normalized)
    if not _is_valid_netloc(parsed.netloc):
        raise ValueError("Target URL is invalid")

    return normalized


def safe_path_component(value: str) -> str:
    """Make a string safe for cross-platform file and directory names."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"

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

# Output directory (use --output to override)
DEFAULT_OUTPUT_DIR = Path("output")

# User agents pool (realistic browser fingerprints)
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
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
    
    # Browser settings
    headless: bool = True
    browser_timeout: int = 30000  # ms
    
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
        domain = urlparse(url).netloc
        try:
            self.conn.execute('''
                INSERT OR IGNORE INTO urls (url, domain, depth, added_at)
                VALUES (?, ?, ?, ?)
            ''', (url, domain, depth, datetime.now().isoformat()))
            self.conn.commit()
            return True
        except Exception:
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
        """Clear all checkpoint state for a fresh non-resume run."""
        self.conn.executescript('''
            DELETE FROM urls;
            DELETE FROM content_hashes;
            DELETE FROM domain_state;
            DELETE FROM session;
        ''')
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
    
    def fetch(self, url: str) -> Optional[ScrapedPage]:
        """Fetch a page via HTTP."""
        session = self._get_session()
        headers = self._get_headers()
        
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=self.config.browser_timeout / 1000,
                allow_redirects=True
            )
            
            content_type = response.headers.get('Content-Type', '')
            
            # Only process HTML
            if 'text/html' not in content_type.lower():
                return None
            
            raw_html = response.text
            
            # Extract content
            title, clean_text, markdown, links, media = self._extract_content(
                raw_html, response.url
            )
            
            content_hash = hashlib.sha256(clean_text.encode()).hexdigest()[:16]
            
            return ScrapedPage(
                url=url,
                final_url=response.url,
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
                    "elapsed_ms": response.elapsed.total_seconds() * 1000
                },
                scraped_at=datetime.now().isoformat(),
                method="http",
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
    
    Uses playwright-stealth for anti-bot evasion.
    """

    DEFAULT_BLOCK_RULES = [
        "doubleclick.net",
        "googletagmanager.com",
        "google-analytics.com",
        "adservice.google.com",
        "adsystem.com",
        "ads-twitter.com",
        "facebook.net/tr",
        "hotjar.com",
        "segment.com",
        "optimizely.com",
    ]
    
    def __init__(self, config: ScrapeConfig):
        self.config = config
        self._browser = None
        self._context = None
        self._playwright = None
        self._block_rules_installed = False
        self._blocked_request_count = 0
    
    async def _ensure_browser(self):
        """Ensure browser is running."""
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
                return False
            
            self._playwright = await async_playwright().start()
            
            # Launch with stealth settings
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--window-size=1920,1080',
                    '--disable-gpu',
                ]
            )
            
            # Create context with realistic viewport
            self._context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=random.choice(USER_AGENTS),
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],
                java_script_enabled=True,
            )
            
            # Apply stealth scripts
            await self._apply_stealth()
            await self._setup_block_rules()
            
        return True
    
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

    async def _setup_block_rules(self):
        """Optionally block known tracker/ad resources."""
        if self._block_rules_installed or not self.config.block_ads:
            return

        block_terms = [term.lower() for term in self.DEFAULT_BLOCK_RULES]

        async def route_handler(route):
            request = route.request
            req_url = request.url.lower()
            if any(term in req_url for term in block_terms):
                self._blocked_request_count += 1
                await route.abort()
            else:
                await route.continue_()

        await self._context.route("**/*", route_handler)
        self._block_rules_installed = True
    
    async def fetch(self, url: str) -> Optional[ScrapedPage]:
        """Fetch page with stealth browser."""
        if not await self._ensure_browser():
            return None
        
        page = None
        try:
            blocked_start = self._blocked_request_count
            page = await self._context.new_page()
            
            # Navigate: use 'load' to get DOM + resources without waiting for network idle (mirror.xyz etc.)
            response = await page.goto(
                url,
                wait_until='load',
                timeout=self.config.browser_timeout
            )
            
            if not response:
                return None
            
            # Random scroll to trigger lazy loading
            await self._human_scroll(page)
            
            # Wait a bit for any dynamic content
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Get content
            raw_html = await page.content()
            title = await page.title()
            final_url = page.url
            
            # Extract text content
            clean_text = await page.evaluate('''
                () => {
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(s => s.remove());
                    return document.body.innerText;
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
            
            return ScrapedPage(
                url=url,
                final_url=final_url,
                status_code=response.status,
                content_type=response.headers.get('content-type', ''),
                raw_html=raw_html,
                clean_text=clean_text,
                markdown=clean_text,  # Could use html2text here
                title=title,
                links=links,
                media=media,
                metadata={
                    "screenshot": screenshot_data is not None,
                    "js_rendered": True,
                    "blocked_requests": self._blocked_request_count - blocked_start,
                    "block_rules_enabled": self.config.block_ads,
                },
                scraped_at=datetime.now().isoformat(),
                method="playwright",
                content_hash=content_hash
            )
            
        except Exception as e:
            logger.warning(f"Playwright fetch failed for {url}: {e}")
            return None
        finally:
            if page:
                await page.close()
    
    async def _human_scroll(self, page):
        """Simulate human-like scrolling."""
        try:
            # Get page height
            height = await page.evaluate('document.body.scrollHeight')
            
            # Scroll in chunks with random pauses
            viewport_height = 1080
            current = 0
            
            while current < height:
                scroll_amount = random.randint(300, 700)
                current += scroll_amount
                
                await page.evaluate(f'window.scrollTo(0, {current})')
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Scroll back to top
            await page.evaluate('window.scrollTo(0, 0)')
            
        except Exception:
            pass
    
    async def close(self):
        """Close browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


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
        output_path = self.output_dir / "wget" / safe_path_component(domain)
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🌐 WGET: Downloading {url} (depth={self.config.max_depth})")
        
        cmd = [
            "wget",
            "--recursive",
            "--level", str(self.config.max_depth),
            "--page-requisites",
            "--convert-links",
            "--adjust-extension",
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
        import shutil
        return shutil.which("archivebox") is not None
    
    def archive_url(self, url: str) -> Optional[Path]:
        """Archive a URL with all formats."""
        if not self._available:
            logger.warning("archivebox not available. Install: pip install archivebox")
            return None
        
        domain = urlparse(url).netloc.replace("www.", "")
        output_path = self.output_dir / "archivebox" / safe_path_component(domain)
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
                logger.info(f"ARCHIVEBOX complete: {output_path}")
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
        
        logger.info("=== DEATH STAR V2 WEAPONS SYSTEMS ===")
        for tool, available in tools.items():
            status = "[OK] ARMED" if available else "[--] OFFLINE"
            logger.info(f"  {tool}: {status}")
        
        self._tools = tools
    
    def _check_module(self, module: str) -> bool:
        """Check if Python module is available."""
        try:
            __import__(module)
            return True
        except ImportError:
            return False
    
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
        """Lazy-initialize playwright fetcher."""
        if self._playwright_fetcher is None:
            self._playwright_fetcher = PlaywrightFetcher(self.config)
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
        domain = urlparse(url).netloc
        
        # Check robots.txt
        if self.config.respect_robots and not self.robots.can_fetch(url):
            logger.debug(f"Blocked by robots.txt: {url}")
            return None
        
        # Rate limiting
        await self.rate_limiter.wait_for_domain(domain)
        
        result = None
        
        # Try HTTP first unless browser requested
        if not use_browser:
            result = self.http_fetcher.fetch(url)
            
            # If content seems JS-heavy, fall back to browser
            if result and self._should_use_browser(url, result.raw_html):
                logger.debug(f"Detected JS content, switching to browser: {url}")
                use_browser = True
                result = None
        
        # Use Playwright for JS content
        if use_browser and self._tools.get('playwright'):
            fetcher = await self._get_playwright_fetcher()
            result = await fetcher.fetch(url)
        
        # Update rate limiter based on result
        if result:
            self.rate_limiter.record_success(domain)
        else:
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
        url = normalize_target_url(url)

        if depth:
            self.config.max_depth = depth

        # Reset per-target counters/state when reusing the scraper instance.
        self._pages_scraped = 0
        self._errors = 0
        self._shutdown_requested = False
        
        domain = urlparse(url).netloc.replace("www.", "")
        safe_domain = safe_path_component(domain)
        logger.info(f"DEATH STAR V2 FIRING ON: {url} (mode={mode})")
        
        # Initialize checkpoint
        self.checkpoint = EnhancedCheckpoint(safe_domain)
        
        # Add seed URL
        if resume:
            stats = self.checkpoint.stats()
            if stats.get('total', 0) == 0:
                self.checkpoint.add_url(url, depth=0)
        else:
            self.checkpoint.reset()
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
                                    # Stay within domain unless configured otherwise
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
                ForensicCapture, save_forensic_result = _import_core(
                    'forensic_capture', 'ForensicCapture', 'save_forensic_result'
                )
                
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
                self._errors += 1
            except Exception as e:
                logger.error(f"Forensic capture failed: {e}")
                self._errors += 1
        
        elif mode == "planetary":
            # MAXIMUM DESTRUCTION - everything!
            logger.info("PLANETARY DESTRUCTION MODE - ALL WEAPONS FIRING!")
            
            # 1. Site discovery first
            try:
                SiteDiscovery = _import_core('site_discovery', 'SiteDiscovery')
                
                discovery = SiteDiscovery(output_dir=self.output_dir / "discovery")
                discovery_result = await discovery.discover_site(url, max_depth=2)
                results["weapons_fired"].append("site_discovery")
                results["outputs"]["discovery"] = str(self.output_dir / "discovery" / safe_domain)
                results["discovery_stats"] = discovery_result.stats
                
                # Add discovered URLs to queue
                for discovered_url in list(discovery_result.html_pages)[:self.config.max_pages]:
                    self.checkpoint.add_url(discovered_url, depth=1)
                    
            except Exception as e:
                logger.warning(f"Site discovery failed: {e}")
            
            # 2. Forensic capture of main page
            planetary_forensic_result = None
            try:
                ForensicCapture, save_forensic_result = _import_core(
                    'forensic_capture', 'ForensicCapture', 'save_forensic_result'
                )
                
                forensic = ForensicCapture(output_dir=self.output_dir / "forensic")
                planetary_forensic_result = await forensic.capture_page(url)
                save_forensic_result(planetary_forensic_result, self.output_dir / "forensic")
                results["weapons_fired"].append("forensic_capture")
                results["outputs"]["forensic"] = str(self.output_dir / "forensic")
                self._pages_scraped += 1
                
            except Exception as e:
                logger.warning(f"Forensic capture failed: {e}")
            
            # 3. Media extraction
            try:
                MediaExtractor = _import_core('media_extractor', 'MediaExtractor')
                
                extractor = MediaExtractor(output_dir=self.output_dir / "media")
                # Get HTML from forensic result or fetch
                html = planetary_forensic_result.raw_html if planetary_forensic_result and hasattr(planetary_forensic_result, 'raw_html') else ""
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
            logger.info("ULTIMATE DESTRUCTION MODE - LEAVING NOTHING BEHIND!")
            
            # Initialize browser for advanced capture
            playwright_fetcher = await self._get_playwright_fetcher()
            await playwright_fetcher._ensure_browser()
            browser_page = await playwright_fetcher._context.new_page()
            
            # Track main page HTML for link extraction
            main_page_html = ""
            main_page_content_hash = None
            
            try:
                # Navigate to page
                response = await browser_page.goto(url, wait_until='networkidle', timeout=60000)
                await asyncio.sleep(2)
                
                # Grab page HTML early (used by link extraction & media)
                main_page_html = await browser_page.content()
                main_page_content_hash = hashlib.sha256(
                    (await browser_page.evaluate('() => document.body.innerText') or "").encode()
                ).hexdigest()[:16]
                
                # 1. Advanced capture (WebSocket, forms, tech stack, source maps)
                try:
                    AdvancedCapture = _import_core('advanced_capture', 'AdvancedCapture')
                    
                    advanced = AdvancedCapture(output_dir=self.output_dir / "advanced")
                    headers = dict(response.headers) if response else {}
                    advanced_result = await advanced.capture_advanced(
                        browser_page,
                        url,
                        headers=headers,
                        capture_iframes=True,
                        capture_source_maps=True
                    )
                    advanced.save_result(advanced_result, safe_domain)
                    results["weapons_fired"].append("advanced_capture")
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
                forensic_result = None
                try:
                    ForensicCapture, save_forensic_result = _import_core(
                        'forensic_capture', 'ForensicCapture', 'save_forensic_result'
                    )
                    
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
                    WaybackMachine = _import_core('wayback_integration', 'WaybackMachine')
                    
                    wayback = WaybackMachine(output_dir=self.output_dir / "wayback")
                    
                    # Get historical snapshots
                    snapshots = await wayback.get_snapshots(url, limit=100)
                    wayback.save_snapshots_index(url, snapshots, safe_domain)
                    results["weapons_fired"].append("wayback_integration")
                    results["outputs"]["wayback"] = str(self.output_dir / "wayback" / safe_domain)
                    results["wayback_stats"] = {
                        "snapshots_found": len(snapshots),
                        "oldest": snapshots[-1].datetime.isoformat() if snapshots else None,
                        "newest": snapshots[0].datetime.isoformat() if snapshots else None,
                    }
                    
                    # Submit current page for archival
                    archived_url = await wayback.save_url(url)
                    if archived_url:
                        results["wayback_stats"]["archived_to"] = str(archived_url)
                        
                except Exception as e:
                    logger.warning(f"Wayback integration failed: {e}")
                
                # 4. Site discovery
                try:
                    SiteDiscovery = _import_core('site_discovery', 'SiteDiscovery')
                    
                    discovery = SiteDiscovery(output_dir=self.output_dir / "discovery")
                    discovery_result = await discovery.discover_site(url, max_depth=2)
                    results["weapons_fired"].append("site_discovery")
                    results["outputs"]["discovery"] = str(self.output_dir / "discovery" / safe_domain)
                    results["discovery_stats"] = discovery_result.stats
                    
                    # Add discovered URLs to queue
                    for discovered_url in list(discovery_result.html_pages)[:self.config.max_pages]:
                        self.checkpoint.add_url(discovered_url, depth=1)
                        
                except Exception as e:
                    logger.warning(f"Site discovery failed: {e}")
                
                # 5. Media extraction
                try:
                    MediaExtractor = _import_core('media_extractor', 'MediaExtractor')
                    
                    extractor = MediaExtractor(output_dir=self.output_dir / "media")
                    html = main_page_html or await browser_page.content()
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
                
                # ---- SEED PAGE BOOKKEEPING ----
                # Mark the main page as scraped / complete so the stealth crawl
                # doesn't re-fetch it, and pages_scraped starts at >= 1.
                self._pages_scraped += 1
                if main_page_content_hash:
                    self.checkpoint.add_content_hash(main_page_content_hash, url)
                self.checkpoint.mark_complete(url, "playwright/ultimate", main_page_content_hash)
                
                # Extract links from the main page and seed the crawl queue
                try:
                    page_links = await browser_page.evaluate('''
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => a.href)
                            .filter(href => href.startsWith('http'))
                    ''')
                    target_domain = urlparse(url).netloc
                    for link in page_links:
                        if urlparse(link).netloc == target_domain:
                            self.checkpoint.add_url(link, depth=1)
                    logger.info(f"Seeded {len(page_links)} links from main page into crawl queue")
                except Exception as e:
                    logger.debug(f"Link extraction from main page failed: {e}")
                
                # Also seed from forensic result internal links if available
                if forensic_result and hasattr(forensic_result, 'internal_links'):
                    for link in forensic_result.internal_links:
                        self.checkpoint.add_url(link, depth=1)
                
            finally:
                await browser_page.close()
            
            # 6. Full stealth crawl of discovered/linked pages
            output_path = self.output_dir / "pages" / safe_domain
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Save the main page too
            if main_page_html:
                try:
                    main_page_title_match = re.search(r'<title[^>]*>(.*?)</title>', main_page_html, re.IGNORECASE | re.DOTALL)
                    main_title = main_page_title_match.group(1).strip() if main_page_title_match else domain
                    
                    main_page_obj = ScrapedPage(
                        url=url, final_url=url,
                        status_code=200, content_type="text/html",
                        raw_html=main_page_html, clean_text="",
                        markdown="", title=main_title,
                        links=[], media=[],
                        metadata={"ultimate_mode": True, "js_rendered": True},
                        scraped_at=datetime.now().isoformat(),
                        method="playwright/ultimate",
                        content_hash=main_page_content_hash or ""
                    )
                    self._save_page(main_page_obj, output_path)
                except Exception as e:
                    logger.debug(f"Failed to save main page to pages dir: {e}")
            
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
            
            logger.info("ULTIMATE DESTRUCTION COMPLETE - NOTHING REMAINS")
        
        # Finalize results
        results["pages_scraped"] = self._pages_scraped
        results["errors"] = self._errors
        results["completed_at"] = datetime.now().isoformat()
        results["checkpoint_stats"] = self.checkpoint.stats()
        
        # Save manifest (sanitize for JSON: Path, URL, set, etc.)
        manifest_path = self.output_dir / f"{safe_domain}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(_to_serializable(results), f, indent=2, default=str)
        
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
  planetary  MAXIMUM - all modes combined
  ultimate   Everything + WebSockets, forms, tech stack, Wayback

Examples:
  python death_star_v2.py --target https://example.com
  python death_star_v2.py --target https://example.com --mode stealth --depth 10
  python death_star_v2.py --target https://example.com --mode forensic
  python death_star_v2.py --target https://example.com --mode planetary
  python death_star_v2.py --target https://example.com --resume
  python death_star_v2.py --target https://example.com --mode full
  python death_star_v2.py --targets urls.txt --mode smart
        """
    )
    
    parser.add_argument("--target", "-t", help="Target URL to scrape")
    parser.add_argument("--targets", "-T", help="File with URLs (one per line)")
    parser.add_argument("--mode", "-m", default="smart",
                       choices=["quick", "smart", "stealth", "full", "archive", "forensic", "planetary", "ultimate"],
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
                       help="Generate WACZ package when WARC is available (forensic/planetary/ultimate)")
    parser.add_argument("--block-ads", action="store_true",
                       help="Block known ad/tracker resources in Playwright modes")
    parser.add_argument("--save-wayback", action="store_true",
                       help="Submit captured target URL to Internet Archive SavePageNow")
    
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
        print("\nExample: python death_star_v2.py --target https://example.com --mode forensic")
        return
    
    # Build config
    proxy_list = [args.proxy] if args.proxy else []

    if args.target:
        try:
            args.target = normalize_target_url(args.target)
        except ValueError as e:
            parser.error(str(e))
    
    config = ScrapeConfig(
        max_depth=args.depth,
        max_pages=args.max_pages,
        min_delay=args.delay,
        max_delay=args.delay * 2,
        respect_robots=args.polite,
        deduplicate=not args.no_dedup,
        generate_wacz=args.wacz,
        block_ads=args.block_ads,
        save_to_wayback=args.save_wayback,
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
        death_star = DeathStarV2(config=config, output_dir=output_dir)
        
        try:
            if args.target:
                try:
                    result = await death_star.destroy(
                        args.target,
                        mode=args.mode,
                        depth=args.depth,
                        resume=args.resume
                    )
                except ValueError as e:
                    result = {
                        "target": args.target,
                        "mode": args.mode,
                        "depth": args.depth,
                        "started_at": datetime.now().isoformat(),
                        "weapons_fired": [],
                        "pages_scraped": 0,
                        "errors": 1,
                        "outputs": {},
                        "completed_at": datetime.now().isoformat(),
                        "error_message": str(e),
                    }
                print(json.dumps(result, indent=2))
                
            elif args.targets:
                with open(args.targets) as f:
                    urls = [line.strip() for line in f if line.strip()]
                
                results = []
                for url in urls:
                    try:
                        normalized_url = normalize_target_url(url)
                        result = await death_star.destroy(
                            normalized_url,
                            mode=args.mode,
                            depth=args.depth,
                            resume=args.resume
                        )
                    except ValueError as e:
                        result = {
                            "target": url,
                            "mode": args.mode,
                            "depth": args.depth,
                            "started_at": datetime.now().isoformat(),
                            "weapons_fired": [],
                            "pages_scraped": 0,
                            "errors": 1,
                            "outputs": {},
                            "completed_at": datetime.now().isoformat(),
                            "error_message": str(e),
                        }
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
pip install requests trafilatura playwright archivebox && playwright install chromium

Verify Installation:
--------------------
python death_star_v2.py --install

=== READY TO NUKE FROM ORBIT ===
""")


if __name__ == "__main__":
    main()
