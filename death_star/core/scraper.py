"""
Death Star Scraper - Main Orchestrator
======================================

The all-consuming "nuke from orbit" web scraper.
Orchestrates multiple scraping tools with intelligent routing,
anti-bot evasion, and crash-proof checkpointing.
"""

import asyncio
import hashlib
import json
import logging
import random
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from death_star.core.checkpoint import Checkpoint
from death_star.utils.proxy import ProxyPool
from death_star.utils.session import SessionManager

logger = logging.getLogger("death_star")

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_OUTPUT_DIR = Path("data/scraped_sites")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

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
    browser_timeout: int = 30000
    
    # Proxy settings
    proxy_list: List[str] = field(default_factory=list)
    rotate_proxies: bool = False
    proxy_pool_file: Optional[str] = None
    
    # Session/Cookie settings
    cookie_file: Optional[str] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    
    # Authentication
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    auth_type: str = "basic"


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
    method: str
    content_hash: str


# =============================================================================
# RATE LIMITER
# =============================================================================

class DomainRateLimiter:
    """Rate limiter that tracks per-domain request timing."""
    
    def __init__(self, config: ScrapeConfig):
        self.config = config
        self._last_request: Dict[str, float] = {}
        self._request_counts: Dict[str, List[float]] = {}
    
    async def wait_for_slot(self, domain: str):
        """Wait until a request slot is available for this domain."""
        now = time.time()
        
        # Check last request time
        if domain in self._last_request:
            elapsed = now - self._last_request[domain]
            min_wait = random.uniform(self.config.min_delay, self.config.max_delay)
            if elapsed < min_wait:
                await asyncio.sleep(min_wait - elapsed)
        
        # Clean old request counts
        minute_ago = now - 60
        if domain in self._request_counts:
            self._request_counts[domain] = [
                t for t in self._request_counts[domain] if t > minute_ago
            ]
        
        # Check rate limit
        if domain in self._request_counts:
            if len(self._request_counts[domain]) >= self.config.requests_per_minute:
                oldest = self._request_counts[domain][0]
                wait_time = 60 - (now - oldest) + random.uniform(0.1, 0.5)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
        
        # Record this request
        self._last_request[domain] = time.time()
        if domain not in self._request_counts:
            self._request_counts[domain] = []
        self._request_counts[domain].append(time.time())


# =============================================================================
# ROBOTS HANDLER
# =============================================================================

class RobotsHandler:
    """Handle robots.txt parsing and compliance."""
    
    def __init__(self):
        self._parsers: Dict[str, RobotFileParser] = {}
        self._user_agent = "DeathStarScraper/2.0"
    
    async def can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        if domain not in self._parsers:
            await self._load_robots(domain, parsed.scheme)
        
        parser = self._parsers.get(domain)
        if parser:
            return parser.can_fetch(self._user_agent, url)
        return True
    
    async def _load_robots(self, domain: str, scheme: str):
        """Load and parse robots.txt for a domain."""
        robots_url = f"{scheme}://{domain}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(robots_url, timeout=10)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
        except Exception:
            pass
        
        self._parsers[domain] = parser


# =============================================================================
# HTTP FETCHER
# =============================================================================

class HTTPFetcher:
    """Fast HTTP fetcher for static content."""
    
    def __init__(self, config: ScrapeConfig, proxy_pool: ProxyPool = None, session_manager: SessionManager = None):
        self.config = config
        self.proxy_pool = proxy_pool
        self.session_manager = session_manager
    
    def _get_headers(self, url: str) -> Dict[str, str]:
        """Generate randomized headers."""
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": random.choice(ACCEPT_HEADERS),
            "Accept-Language": random.choice(ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        if self.session_manager:
            domain = urlparse(url).netloc
            cookie = self.session_manager.get_cookie_header(domain)
            if cookie:
                headers["Cookie"] = cookie
            headers.update(self.session_manager.headers)
        
        return headers
    
    async def fetch(self, url: str) -> Optional[ScrapedPage]:
        """Fetch a page using HTTP."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed. Run: pip install httpx")
            return None
        
        headers = self._get_headers(url)
        proxy = self.proxy_pool.get_httpx_proxy() if self.proxy_pool else None
        
        try:
            async with httpx.AsyncClient(proxy=proxy, follow_redirects=True, timeout=30) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code != 200:
                    return None
                
                html = response.text
                
                # Extract content
                clean_text, markdown, title, links, media, metadata = self._extract_content(html, str(response.url))
                
                return ScrapedPage(
                    url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                    raw_html=html,
                    clean_text=clean_text,
                    markdown=markdown,
                    title=title,
                    links=links,
                    media=media,
                    metadata=metadata,
                    scraped_at=datetime.now().isoformat(),
                    method="http",
                    content_hash=hashlib.md5(html.encode()).hexdigest()
                )
                
        except Exception as e:
            logger.debug(f"HTTP fetch failed for {url}: {e}")
            if proxy and self.proxy_pool:
                self.proxy_pool.report_failure(proxy)
            return None
    
    def _extract_content(self, html: str, url: str) -> Tuple[str, str, str, List[str], List[str], Dict]:
        """Extract clean content from HTML."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "lxml")
        
        # Title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        
        # Clean text
        clean_text = ""
        try:
            import trafilatura
            clean_text = trafilatura.extract(html) or ""
        except ImportError:
            for script in soup(["script", "style"]):
                script.decompose()
            clean_text = soup.get_text(separator=" ", strip=True)
        
        # Markdown
        markdown = ""
        try:
            import html2text
            h2t = html2text.HTML2Text()
            h2t.ignore_links = False
            markdown = h2t.handle(html)
        except ImportError:
            markdown = clean_text
        
        # Links
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("http://", "https://")):
                links.append(href)
            elif href.startswith("/"):
                links.append(urljoin(url, href))
        
        # Media
        media = []
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if src.startswith(("http://", "https://")):
                media.append(src)
            elif src.startswith("/"):
                media.append(urljoin(url, src))
        
        # Metadata
        metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property", "")
            content = meta.get("content", "")
            if name and content:
                metadata[name] = content
        
        return clean_text, markdown, title, links, media, metadata


# =============================================================================
# PLAYWRIGHT FETCHER
# =============================================================================

class PlaywrightFetcher:
    """Stealth browser fetcher for JS-heavy sites."""
    
    def __init__(self, config: ScrapeConfig, proxy_pool: ProxyPool = None, session_manager: SessionManager = None):
        self.config = config
        self.proxy_pool = proxy_pool
        self.session_manager = session_manager
        self._browser = None
        self._context = None
    
    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
                
                self._playwright = await async_playwright().start()
                
                launch_options = {
                    "headless": self.config.headless,
                }
                
                # Add proxy if available
                if self.proxy_pool:
                    proxy = self.proxy_pool.get_playwright_proxy()
                    if proxy:
                        launch_options["proxy"] = proxy
                
                self._browser = await self._playwright.chromium.launch(**launch_options)
                
                # Create context with stealth settings
                context_options = {
                    "user_agent": random.choice(USER_AGENTS),
                    "viewport": {"width": 1920, "height": 1080},
                    "java_script_enabled": True,
                }
                
                self._context = await self._browser.new_context(**context_options)
                
                # Add cookies if available
                if self.session_manager:
                    cookies = self.session_manager.get_playwright_cookies()
                    if cookies:
                        await self._context.add_cookies(cookies)
                
            except ImportError:
                logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
                raise
    
    async def fetch(self, url: str) -> Optional[ScrapedPage]:
        """Fetch a page using Playwright."""
        await self._ensure_browser()
        
        page = await self._context.new_page()
        
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=self.config.browser_timeout)
            
            if not response or response.status >= 400:
                return None
            
            # Human-like scrolling
            await self._human_scroll(page)
            
            html = await page.content()
            
            # Extract content using same logic as HTTP fetcher
            http_fetcher = HTTPFetcher(self.config)
            clean_text, markdown, title, links, media, metadata = http_fetcher._extract_content(html, str(page.url))
            
            return ScrapedPage(
                url=url,
                final_url=str(page.url),
                status_code=response.status,
                content_type=response.headers.get("content-type", ""),
                raw_html=html,
                clean_text=clean_text,
                markdown=markdown,
                title=title,
                links=links,
                media=media,
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
                method="playwright",
                content_hash=hashlib.md5(html.encode()).hexdigest()
            )
            
        except Exception as e:
            logger.debug(f"Playwright fetch failed for {url}: {e}")
            return None
        finally:
            await page.close()
    
    async def _human_scroll(self, page):
        """Simulate human-like scrolling."""
        try:
            total_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")
            
            current = 0
            while current < total_height:
                scroll_amount = random.randint(200, 400)
                current += scroll_amount
                await page.evaluate(f"window.scrollTo(0, {current})")
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
        except Exception:
            pass
    
    async def close(self):
        """Close browser."""
        if self._browser:
            await self._browser.close()
            await self._playwright.stop()


# =============================================================================
# DEATH STAR MAIN CLASS
# =============================================================================

class DeathStar:
    """
    The all-consuming "nuke from orbit" web scraper.
    
    Usage:
        scraper = DeathStar()
        result = await scraper.scrape("https://example.com")
        
        # Or full destruction
        result = await scraper.destroy("https://example.com", mode="forensic")
    """
    
    def __init__(
        self,
        config: Optional[ScrapeConfig] = None,
        output_dir: Optional[Path] = None
    ):
        self.config = config or ScrapeConfig()
        self.output_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.checkpoint = None
        self.robots = RobotsHandler()
        self.rate_limiter = DomainRateLimiter(self.config)
        
        # Proxy pool
        self.proxy_pool = None
        if self.config.proxy_pool_file:
            self.proxy_pool = ProxyPool(proxy_file=self.config.proxy_pool_file)
        elif self.config.proxy_list:
            self.proxy_pool = ProxyPool(proxies=self.config.proxy_list)
        
        # Session manager
        self.session_manager = None
        if self.config.cookie_file:
            self.session_manager = SessionManager(cookie_file=self.config.cookie_file)
        
        if self.config.auth_username and self.config.auth_password:
            if not self.session_manager:
                self.session_manager = SessionManager()
            self.session_manager.add_auth_headers(
                self.config.auth_username,
                self.config.auth_password,
                self.config.auth_type
            )
        
        # Fetchers (lazy initialized)
        self._http_fetcher = None
        self._playwright_fetcher = None
        
        # State
        self._shutdown_requested = False
        self._pages_scraped = 0
        self._errors = 0
        
        # Signal handlers
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)
    
    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown requested, finishing current page...")
        self._shutdown_requested = True
    
    @property
    def http_fetcher(self) -> HTTPFetcher:
        """Get or create HTTP fetcher."""
        if self._http_fetcher is None:
            self._http_fetcher = HTTPFetcher(self.config, self.proxy_pool, self.session_manager)
        return self._http_fetcher
    
    @property
    def playwright_fetcher(self) -> PlaywrightFetcher:
        """Get or create Playwright fetcher."""
        if self._playwright_fetcher is None:
            self._playwright_fetcher = PlaywrightFetcher(self.config, self.proxy_pool, self.session_manager)
        return self._playwright_fetcher
    
    async def scrape(
        self,
        url: str,
        use_browser: bool = False
    ) -> Optional[ScrapedPage]:
        """
        Scrape a single page.
        
        Args:
            url: URL to scrape
            use_browser: Force browser-based scraping
        
        Returns:
            ScrapedPage or None if failed
        """
        domain = urlparse(url).netloc
        
        # Rate limiting
        await self.rate_limiter.wait_for_slot(domain)
        
        # Robots check
        if self.config.respect_robots:
            if not await self.robots.can_fetch(url):
                logger.debug(f"Blocked by robots.txt: {url}")
                return None
        
        # Fetch
        if use_browser:
            return await self.playwright_fetcher.fetch(url)
        else:
            # Try HTTP first, fall back to browser
            result = await self.http_fetcher.fetch(url)
            if result is None or self._needs_browser(result):
                result = await self.playwright_fetcher.fetch(url)
            return result
    
    def _needs_browser(self, page: ScrapedPage) -> bool:
        """Check if page needs browser rendering."""
        if not page:
            return True
        
        # Check for JS framework indicators
        js_indicators = [
            "__NEXT_DATA__",
            "__NUXT__",
            "react-root",
            "ng-app",
            "data-reactroot",
        ]
        
        for indicator in js_indicators:
            if indicator in page.raw_html:
                if len(page.clean_text) < 200:
                    return True
        
        return False
    
    async def destroy(
        self,
        url: str,
        mode: str = "smart",
        resume: bool = False
    ) -> Dict[str, Any]:
        """
        Full site destruction (scraping).
        
        Args:
            url: Target URL
            mode: Scraping mode (quick, smart, stealth, full, forensic, planetary, ultimate)
            resume: Resume from checkpoint
        
        Returns:
            Dictionary with scrape results
        """
        domain = urlparse(url).netloc
        
        # Initialize checkpoint
        self.checkpoint = Checkpoint(f"death_star_{domain}")
        
        if not resume:
            self.checkpoint.clear()
        
        self.checkpoint.add_url(url, depth=0)
        
        logger.info(f"DEATH STAR TARGETING: {domain}")
        logger.info(f"   Mode: {mode}")
        
        results = {
            "target": url,
            "domain": domain,
            "mode": mode,
            "started_at": datetime.now().isoformat(),
            "pages_scraped": 0,
            "errors": 0,
            "outputs": {},
        }
        
        # Execute based on mode
        if mode == "quick":
            # Fast HTTP-only crawl
            await self._crawl_site(url, use_browser=False)
        
        elif mode in ("smart", "stealth", "full", "forensic", "planetary", "ultimate"):
            # Full crawl with browser
            await self._crawl_site(url, use_browser=True)
        
        results["pages_scraped"] = self._pages_scraped
        results["errors"] = self._errors
        results["completed_at"] = datetime.now().isoformat()
        
        # Save manifest
        manifest_path = self.output_dir / f"{domain}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(results, f, indent=2)
        
        results["manifest"] = str(manifest_path)
        
        logger.info(f"DESTRUCTION COMPLETE: {self._pages_scraped} pages")
        
        return results
    
    async def _crawl_site(self, url: str, use_browser: bool = False):
        """Crawl a site."""
        domain = urlparse(url).netloc
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
                
                page_url = item["url"]
                page_depth = item["depth"]
                
                try:
                    page = await self.scrape(page_url, use_browser=use_browser)
                    
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
                                if link_domain == domain:
                                    self.checkpoint.add_url(link, depth=page_depth + 1)
                    else:
                        self.checkpoint.mark_failed(page_url, "fetch_failed")
                        self._errors += 1
                        
                except Exception as e:
                    self.checkpoint.mark_failed(page_url, str(e))
                    self._errors += 1
    
    def _save_page(self, page: ScrapedPage, output_dir: Path):
        """Save scraped page to disk."""
        parsed = urlparse(page.url)
        path_parts = parsed.path.strip("/").replace("/", "_") or "index"
        filename = f"{path_parts}_{page.content_hash[:8]}"
        
        page_dir = output_dir / filename
        page_dir.mkdir(parents=True, exist_ok=True)
        
        # Save raw HTML
        if self.config.save_raw_html:
            with open(page_dir / "raw.html", "w", encoding="utf-8") as f:
                f.write(page.raw_html)
        
        # Save clean text
        with open(page_dir / "clean.txt", "w", encoding="utf-8") as f:
            f.write(page.clean_text)
        
        # Save markdown
        with open(page_dir / "content.md", "w", encoding="utf-8") as f:
            f.write(page.markdown)
        
        # Save metadata
        meta = {
            "url": page.url,
            "final_url": page.final_url,
            "title": page.title,
            "status_code": page.status_code,
            "content_type": page.content_type,
            "scraped_at": page.scraped_at,
            "method": page.method,
            "content_hash": page.content_hash,
            "link_count": len(page.links),
            "media_count": len(page.media),
            "metadata": page.metadata,
        }
        
        with open(page_dir / "metadata.json", "w") as f:
            json.dump(meta, f, indent=2)
    
    async def close(self):
        """Clean up resources."""
        if self._playwright_fetcher:
            await self._playwright_fetcher.close()
