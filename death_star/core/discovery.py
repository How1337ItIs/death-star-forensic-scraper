"""
Site Discovery Module
=====================

Discover site structure:
- robots.txt parsing
- sitemap.xml discovery
- Link graph generation
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("death_star.discovery")


@dataclass
class SiteDiscoveryResult:
    """Result of site discovery."""
    url: str
    domain: str
    
    robots_txt: Optional[str]
    sitemaps: List[str]
    
    html_pages: Set[str] = field(default_factory=set)
    resources: Set[str] = field(default_factory=set)
    external_links: Set[str] = field(default_factory=set)
    
    stats: Dict = field(default_factory=dict)


class SiteDiscovery:
    """
    Discover site structure and content.
    
    Usage:
        discovery = SiteDiscovery()
        result = await discovery.discover_site("https://example.com")
    """
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/discovery")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def discover_site(
        self,
        url: str,
        max_depth: int = 2,
        max_pages: int = 1000,
    ) -> SiteDiscoveryResult:
        """
        Discover a site's structure.
        
        Args:
            url: Starting URL
            max_depth: Maximum crawl depth
            max_pages: Maximum pages to discover
        
        Returns:
            SiteDiscoveryResult
        """
        parsed = urlparse(url)
        domain = parsed.netloc
        base_url = f"{parsed.scheme}://{domain}"
        
        result = SiteDiscoveryResult(
            url=url,
            domain=domain,
            robots_txt=None,
            sitemaps=[],
        )
        
        # Get robots.txt
        robots_txt = await self._fetch_robots(base_url)
        result.robots_txt = robots_txt
        
        # Parse sitemaps from robots.txt
        if robots_txt:
            result.sitemaps = self._parse_sitemaps_from_robots(robots_txt)
        
        # Try common sitemap locations
        common_sitemaps = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap.xml.gz",
        ]
        
        for sitemap_url in common_sitemaps:
            if sitemap_url not in result.sitemaps:
                result.sitemaps.append(sitemap_url)
        
        # Parse sitemaps
        for sitemap_url in result.sitemaps[:5]:  # Limit
            urls = await self._parse_sitemap(sitemap_url)
            for u in urls:
                if len(result.html_pages) >= max_pages:
                    break
                if urlparse(u).netloc == domain:
                    result.html_pages.add(u)
        
        # Crawl from starting URL
        await self._crawl(url, domain, result, max_depth, max_pages)
        
        # Calculate stats
        result.stats = {
            "total_pages": len(result.html_pages),
            "total_resources": len(result.resources),
            "external_links": len(result.external_links),
            "sitemaps_found": len(result.sitemaps),
            "has_robots": result.robots_txt is not None,
        }
        
        return result
    
    async def _fetch_robots(self, base_url: str) -> Optional[str]:
        """Fetch robots.txt."""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/robots.txt",
                    timeout=10,
                )
                
                if response.status_code == 200:
                    return response.text
                
        except Exception:
            pass
        
        return None
    
    def _parse_sitemaps_from_robots(self, robots_txt: str) -> List[str]:
        """Parse sitemap URLs from robots.txt."""
        sitemaps = []
        
        for line in robots_txt.splitlines():
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                sitemaps.append(sitemap_url)
        
        return sitemaps
    
    async def _parse_sitemap(self, url: str) -> List[str]:
        """Parse a sitemap XML file."""
        urls = []
        
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30)
                
                if response.status_code != 200:
                    return urls
                
                content = response.text
                
                # Parse URLs from sitemap
                # Simple regex parsing (could use proper XML parser)
                for match in re.finditer(r"<loc>([^<]+)</loc>", content):
                    urls.append(match.group(1))
                
        except Exception as e:
            logger.debug(f"Failed to parse sitemap {url}: {e}")
        
        return urls
    
    async def _crawl(
        self,
        start_url: str,
        domain: str,
        result: SiteDiscoveryResult,
        max_depth: int,
        max_pages: int,
    ):
        """Crawl site to discover pages."""
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            return
        
        visited = set()
        queue = [(start_url, 0)]
        
        async with httpx.AsyncClient() as client:
            while queue and len(result.html_pages) < max_pages:
                url, depth = queue.pop(0)
                
                if url in visited or depth > max_depth:
                    continue
                
                visited.add(url)
                
                try:
                    response = await client.get(url, timeout=10, follow_redirects=True)
                    
                    if response.status_code != 200:
                        continue
                    
                    content_type = response.headers.get("content-type", "")
                    
                    if "text/html" in content_type:
                        result.html_pages.add(url)
                        
                        # Parse links
                        soup = BeautifulSoup(response.text, "lxml")
                        
                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            full_url = urljoin(url, href)
                            parsed = urlparse(full_url)
                            
                            if parsed.netloc == domain:
                                if full_url not in visited:
                                    queue.append((full_url, depth + 1))
                            elif parsed.scheme in ("http", "https"):
                                result.external_links.add(full_url)
                        
                        # Find resources
                        for tag, attr in [("img", "src"), ("script", "src"), ("link", "href")]:
                            for el in soup.find_all(tag, **{attr: True}):
                                resource_url = urljoin(url, el[attr])
                                result.resources.add(resource_url)
                    
                except Exception:
                    pass
                
                # Small delay
                await asyncio.sleep(0.1)
    
    def save_result(self, result: SiteDiscoveryResult):
        """Save discovery result to disk."""
        output_dir = self.output_dir / result.domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save robots.txt
        if result.robots_txt:
            with open(output_dir / "robots.txt", "w") as f:
                f.write(result.robots_txt)
        
        # Save discovered URLs
        data = {
            "url": result.url,
            "domain": result.domain,
            "discovered_at": datetime.now().isoformat(),
            "stats": result.stats,
            "sitemaps": result.sitemaps,
            "pages": list(result.html_pages)[:1000],
            "resources": list(result.resources)[:500],
            "external_links": list(result.external_links)[:200],
        }
        
        with open(output_dir / "discovery.json", "w") as f:
            json.dump(data, f, indent=2)
