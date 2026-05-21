#!/usr/bin/env python3
"""
Site Discovery Module
=====================

Discovers and maps entire website structure.

Features:
---------
1. robots.txt parsing and storage
2. sitemap.xml discovery and parsing
3. RSS/Atom feed discovery
4. API endpoint detection
5. Link graph generation
6. Site structure mapping

Usage:
------
    from site_discovery import SiteDiscovery

    discovery = SiteDiscovery()
    result = await discovery.discover_site("https://example.com")
"""

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("site_discovery")


@dataclass
class RobotsData:
    """Parsed robots.txt data."""
    url: str
    raw_content: str
    user_agents: Dict[str, Dict]  # agent -> {allow: [], disallow: [], crawl_delay: float}
    sitemaps: List[str]
    parsed_at: str
    can_crawl: bool


@dataclass
class SitemapData:
    """Parsed sitemap data."""
    url: str
    sitemap_type: str  # 'sitemap', 'sitemapindex', 'rss', 'atom'
    urls: List[Dict]  # {loc, lastmod, changefreq, priority}
    nested_sitemaps: List[str]
    parsed_at: str


@dataclass
class FeedData:
    """Discovered feed data."""
    url: str
    feed_type: str  # 'rss', 'atom', 'json'
    title: str
    entries: List[Dict]
    parsed_at: str


@dataclass
class LinkGraph:
    """Site link structure."""
    nodes: Set[str]  # All URLs
    edges: List[Tuple[str, str]]  # (from_url, to_url)
    internal_links: Dict[str, List[str]]  # url -> [linked_urls]
    external_links: Dict[str, List[str]]  # url -> [external_urls]
    orphan_pages: Set[str]  # Pages with no incoming links
    hub_pages: List[Tuple[str, int]]  # (url, outgoing_count) sorted by count


@dataclass
class DiscoveryResult:
    """Complete site discovery result."""
    domain: str
    base_url: str
    discovered_at: str

    # Standard files
    robots: Optional[RobotsData]
    sitemaps: List[SitemapData]
    feeds: List[FeedData]

    # Discovered URLs
    all_urls: Set[str]
    html_pages: Set[str]
    resources: Set[str]  # CSS, JS, images
    documents: Set[str]  # PDFs, etc.
    api_endpoints: Set[str]

    # Structure
    link_graph: LinkGraph
    depth_map: Dict[str, int]  # url -> depth from root

    # API/endpoint discovery
    detected_apis: List[Dict]
    forms: List[Dict]

    # Statistics
    stats: Dict[str, Any]


class SiteDiscovery:
    """
    Comprehensive site structure discovery.
    """

    # Common API patterns
    API_PATTERNS = [
        r'/api/',
        r'/v\d+/',
        r'/graphql',
        r'/rest/',
        r'\.json$',
        r'/ajax/',
        r'/wp-json/',
        r'/feed/',
    ]

    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/discovery")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def discover_site(
        self,
        url: str,
        max_depth: int = 3,
        max_pages: int = 200,
        max_urls: int = 5000,
        crawl_for_links: bool = True,
        respect_robots: bool = True,
    ) -> DiscoveryResult:
        """
        Discover complete site structure.

        Args:
            url: Base URL to discover
            max_depth: Max depth for link crawling
            max_pages: Max HTML pages to fetch while discovering links
            max_urls: Max URLs to track in the discovery graph
            crawl_for_links: Actually crawl pages for link discovery
            respect_robots: Honor robots.txt

        Returns:
            DiscoveryResult with complete site map
        """
        parsed = urlparse(url)
        domain = parsed.netloc
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        logger.info(f"🔍 Discovering site structure: {base_url}")

        # Discover robots.txt
        robots = await self._parse_robots(base_url)

        # Discover sitemaps
        sitemaps = []
        sitemap_urls = set()

        # From robots.txt
        if robots and robots.sitemaps:
            for sitemap_url in robots.sitemaps:
                sitemap = await self._parse_sitemap(sitemap_url)
                if sitemap:
                    sitemaps.append(sitemap)
                    sitemap_urls.update(s['loc'] for s in sitemap.urls if 'loc' in s)

        # Try common sitemap locations
        common_sitemaps = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap-index.xml",
            f"{base_url}/sitemaps/sitemap.xml",
        ]

        for sitemap_url in common_sitemaps:
            if not any(s.url == sitemap_url for s in sitemaps):
                sitemap = await self._parse_sitemap(sitemap_url)
                if sitemap:
                    sitemaps.append(sitemap)
                    sitemap_urls.update(s['loc'] for s in sitemap.urls if 'loc' in s)

        # Discover feeds
        feeds = await self._discover_feeds(base_url)

        # Initialize URL sets
        all_urls = set(sitemap_urls)
        all_urls.add(url)
        html_pages = set()
        resources = set()
        documents = set()
        api_endpoints = set()

        # Link graph
        edges = []
        internal_links = defaultdict(list)
        external_links = defaultdict(list)
        depth_map = {url: 0}

        # Crawl for links if enabled
        if crawl_for_links:
            crawled = set()
            to_crawl = [(url, 0)]

            while to_crawl:
                if len(crawled) >= max_pages or len(all_urls) >= max_urls:
                    break
                current_url, depth = to_crawl.pop(0)

                if current_url in crawled:
                    continue
                if depth > max_depth:
                    continue
                if respect_robots and robots and not robots.can_crawl:
                    if not self._check_robots_allow(robots, current_url):
                        continue

                crawled.add(current_url)

                try:
                    links, page_resources = await self._fetch_and_extract_links(current_url)
                    html_pages.add(current_url)

                    for link in links:
                        link_domain = urlparse(link).netloc

                        if link_domain == domain:
                            # Internal link
                            internal_links[current_url].append(link)
                            edges.append((current_url, link))
                            all_urls.add(link)
                            if len(all_urls) >= max_urls:
                                continue

                            if link not in crawled and link not in [u for u, _ in to_crawl]:
                                to_crawl.append((link, depth + 1))
                                depth_map[link] = depth + 1
                        else:
                            # External link
                            external_links[current_url].append(link)

                    # Categorize resources
                    for res in page_resources:
                        res_lower = res.lower()
                        if any(res_lower.endswith(ext) for ext in ['.css', '.js', '.jpg', '.png', '.gif', '.svg', '.webp', '.woff', '.woff2']):
                            resources.add(res)
                        elif any(res_lower.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
                            documents.add(res)
                        elif any(re.search(p, res) for p in self.API_PATTERNS):
                            api_endpoints.add(res)

                except Exception as e:
                    logger.debug(f"Failed to crawl {current_url}: {e}")

        # Detect API endpoints from patterns
        detected_apis = self._detect_api_patterns(all_urls)

        # Detect forms (would need HTML content)
        forms = []

        # Build link graph
        nodes = all_urls

        # Find orphan pages (no incoming links)
        linked_to = set()
        for from_url, to_url in edges:
            linked_to.add(to_url)
        orphan_pages = nodes - linked_to - {url}  # Exclude root

        # Find hub pages (most outgoing links)
        hub_pages = sorted(
            [(u, len(links)) for u, links in internal_links.items()],
            key=lambda x: x[1],
            reverse=True
        )[:20]

        link_graph = LinkGraph(
            nodes=nodes,
            edges=edges,
            internal_links=dict(internal_links),
            external_links=dict(external_links),
            orphan_pages=orphan_pages,
            hub_pages=hub_pages
        )

        # Statistics
        stats = {
            'total_urls': len(all_urls),
            'html_pages': len(html_pages),
            'resources': len(resources),
            'documents': len(documents),
            'api_endpoints': len(api_endpoints),
            'internal_links': sum(len(v) for v in internal_links.values()),
            'external_links': sum(len(v) for v in external_links.values()),
            'orphan_pages': len(orphan_pages),
            'max_depth_found': max(depth_map.values()) if depth_map else 0,
            'sitemaps_found': len(sitemaps),
            'sitemap_urls': len(sitemap_urls),
            'feeds_found': len(feeds),
        }

        result = DiscoveryResult(
            domain=domain,
            base_url=base_url,
            discovered_at=datetime.now().isoformat(),
            robots=robots,
            sitemaps=sitemaps,
            feeds=feeds,
            all_urls=all_urls,
            html_pages=html_pages,
            resources=resources,
            documents=documents,
            api_endpoints=api_endpoints,
            link_graph=link_graph,
            depth_map=depth_map,
            detected_apis=detected_apis,
            forms=forms,
            stats=stats
        )

        # Save discovery result
        self._save_discovery(result, domain)

        return result

    async def _parse_robots(self, base_url: str) -> Optional[RobotsData]:
        """Parse robots.txt."""
        robots_url = f"{base_url}/robots.txt"

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(robots_url, timeout=10, follow_redirects=True)

                if response.status_code != 200:
                    return None

                content = response.text
        except Exception as e:
            logger.debug(f"Failed to fetch robots.txt: {e}")
            return None

        # Parse content
        user_agents = {}
        sitemaps = []
        current_agent = '*'
        user_agents[current_agent] = {'allow': [], 'disallow': [], 'crawl_delay': None}

        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if ':' not in line:
                continue

            key, _, value = line.partition(':')
            key = key.strip().lower()
            value = value.strip()

            if key == 'user-agent':
                current_agent = value
                if current_agent not in user_agents:
                    user_agents[current_agent] = {'allow': [], 'disallow': [], 'crawl_delay': None}
            elif key == 'disallow':
                user_agents[current_agent]['disallow'].append(value)
            elif key == 'allow':
                user_agents[current_agent]['allow'].append(value)
            elif key == 'crawl-delay':
                try:
                    user_agents[current_agent]['crawl_delay'] = float(value)
                except ValueError:
                    pass
            elif key == 'sitemap':
                sitemaps.append(value)

        # Check if we can crawl
        can_crawl = True
        default_rules = user_agents.get('*', {})
        if '/' in default_rules.get('disallow', []):
            can_crawl = False

        return RobotsData(
            url=robots_url,
            raw_content=content,
            user_agents=user_agents,
            sitemaps=sitemaps,
            parsed_at=datetime.now().isoformat(),
            can_crawl=can_crawl
        )

    def _check_robots_allow(self, robots: RobotsData, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        path = urlparse(url).path
        rules = robots.user_agents.get('*', {})

        # Check disallow rules
        for pattern in rules.get('disallow', []):
            if pattern and path.startswith(pattern):
                # Check if there's a more specific allow
                for allow in rules.get('allow', []):
                    if allow and path.startswith(allow) and len(allow) > len(pattern):
                        return True
                return False

        return True

    async def _parse_sitemap(self, url: str) -> Optional[SitemapData]:
        """Parse a sitemap (XML or index)."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30, follow_redirects=True)

                if response.status_code != 200:
                    return None

                content = response.text
        except Exception as e:
            logger.debug(f"Failed to fetch sitemap {url}: {e}")
            return None

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            logger.debug(f"Failed to parse sitemap XML: {url}")
            return None

        # Detect sitemap type
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        urls = []
        nested_sitemaps = []
        sitemap_type = 'sitemap'

        # Check for sitemap index
        for sitemap in root.findall('.//sm:sitemap', ns) or root.findall('.//sitemap'):
            sitemap_type = 'sitemapindex'
            loc = sitemap.find('sm:loc', ns) or sitemap.find('loc')
            if loc is not None and loc.text:
                nested_sitemaps.append(loc.text.strip())

        # Parse URLs
        for url_elem in root.findall('.//sm:url', ns) or root.findall('.//url'):
            url_data = {}

            loc = url_elem.find('sm:loc', ns) or url_elem.find('loc')
            if loc is not None and loc.text:
                url_data['loc'] = loc.text.strip()

            lastmod = url_elem.find('sm:lastmod', ns) or url_elem.find('lastmod')
            if lastmod is not None and lastmod.text:
                url_data['lastmod'] = lastmod.text.strip()

            changefreq = url_elem.find('sm:changefreq', ns) or url_elem.find('changefreq')
            if changefreq is not None and changefreq.text:
                url_data['changefreq'] = changefreq.text.strip()

            priority = url_elem.find('sm:priority', ns) or url_elem.find('priority')
            if priority is not None and priority.text:
                url_data['priority'] = priority.text.strip()

            if url_data.get('loc'):
                urls.append(url_data)

        # Recursively parse nested sitemaps
        for nested_url in nested_sitemaps:
            nested = await self._parse_sitemap(nested_url)
            if nested:
                urls.extend(nested.urls)

        return SitemapData(
            url=url,
            sitemap_type=sitemap_type,
            urls=urls,
            nested_sitemaps=nested_sitemaps,
            parsed_at=datetime.now().isoformat()
        )

    async def _discover_feeds(self, base_url: str) -> List[FeedData]:
        """Discover RSS/Atom feeds."""
        feeds = []

        # Try common feed URLs
        common_feeds = [
            f"{base_url}/feed",
            f"{base_url}/feed/",
            f"{base_url}/rss",
            f"{base_url}/rss.xml",
            f"{base_url}/atom.xml",
            f"{base_url}/feed.xml",
            f"{base_url}/index.xml",
        ]

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                for feed_url in common_feeds:
                    try:
                        response = await client.get(
                            feed_url, timeout=10, follow_redirects=True
                        )

                        if response.status_code != 200:
                            continue

                        content_type = response.headers.get('content-type', '')
                        if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                            feed = self._parse_feed(feed_url, response.text)
                            if feed:
                                feeds.append(feed)
                    except Exception:
                        continue
        except ImportError:
            pass

        return feeds

    def _parse_feed(self, url: str, content: str) -> Optional[FeedData]:
        """Parse an RSS or Atom feed."""
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return None

        entries = []
        title = ""
        feed_type = "unknown"

        # Detect feed type and parse
        if root.tag == 'rss' or root.find('channel') is not None:
            feed_type = 'rss'
            channel = root.find('channel')
            if channel is not None:
                title_elem = channel.find('title')
                title = title_elem.text if title_elem is not None else ""

                for item in channel.findall('item'):
                    entry = {}
                    for child in item:
                        entry[child.tag] = child.text
                    entries.append(entry)

        elif root.tag.endswith('feed'):
            feed_type = 'atom'
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            title_elem = root.find('atom:title', ns) or root.find('title')
            title = title_elem.text if title_elem is not None else ""

            for entry in root.findall('atom:entry', ns) or root.findall('entry'):
                entry_data = {}
                for child in entry:
                    tag = child.tag.split('}')[-1]  # Remove namespace
                    entry_data[tag] = child.text or child.get('href', '')
                entries.append(entry_data)

        if not entries:
            return None

        return FeedData(
            url=url,
            feed_type=feed_type,
            title=title,
            entries=entries[:50],  # Limit entries
            parsed_at=datetime.now().isoformat()
        )

    async def _fetch_and_extract_links(self, url: str) -> Tuple[List[str], List[str]]:
        """Fetch page and extract links and resources."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=15, follow_redirects=True)

                if response.status_code != 200:
                    return [], []

                content_type = response.headers.get('content-type', '')
                if 'text/html' not in content_type:
                    return [], []

                html = response.text
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return [], []

        links = []
        resources = []

        # Extract links
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            href = match.group(1)
            if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            full_url = urljoin(url, href)
            links.append(full_url)

        # Extract resources
        for match in re.finditer(r'src=["\']([^"\']+)["\']', html, re.I):
            src = match.group(1)
            full_url = urljoin(url, src)
            resources.append(full_url)

        # CSS links
        for match in re.finditer(r'<link[^>]+href=["\']([^"\']+)["\']', html, re.I):
            href = match.group(1)
            full_url = urljoin(url, href)
            resources.append(full_url)

        return links, resources

    def _detect_api_patterns(self, urls: Set[str]) -> List[Dict]:
        """Detect potential API endpoints."""
        apis = []

        for url in urls:
            for pattern in self.API_PATTERNS:
                if re.search(pattern, url):
                    apis.append({
                        'url': url,
                        'pattern': pattern,
                        'detected_at': datetime.now().isoformat()
                    })
                    break

        return apis

    def _save_discovery(self, result: DiscoveryResult, domain: str):
        """Save discovery result to disk."""
        output_dir = self.output_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save main discovery data
        discovery_data = {
            'domain': result.domain,
            'base_url': result.base_url,
            'discovered_at': result.discovered_at,
            'stats': result.stats,
            'robots': {
                'url': result.robots.url if result.robots else None,
                'sitemaps': result.robots.sitemaps if result.robots else [],
                'can_crawl': result.robots.can_crawl if result.robots else True,
            } if result.robots else None,
            'sitemaps': [
                {
                    'url': s.url,
                    'type': s.sitemap_type,
                    'url_count': len(s.urls)
                }
                for s in result.sitemaps
            ],
            'feeds': [
                {
                    'url': f.url,
                    'type': f.feed_type,
                    'title': f.title,
                    'entry_count': len(f.entries)
                }
                for f in result.feeds
            ],
            'detected_apis': result.detected_apis,
        }

        with open(output_dir / 'discovery.json', 'w') as f:
            json.dump(discovery_data, f, indent=2)

        # Save all URLs
        with open(output_dir / 'all_urls.txt', 'w') as f:
            f.write('\n'.join(sorted(result.all_urls)))

        # Save robots.txt
        if result.robots:
            with open(output_dir / 'robots.txt', 'w') as f:
                f.write(result.robots.raw_content)

        # Save link graph
        graph_data = {
            'nodes': list(result.link_graph.nodes),
            'edges': result.link_graph.edges,
            'hub_pages': result.link_graph.hub_pages,
            'orphan_pages': list(result.link_graph.orphan_pages)
        }
        with open(output_dir / 'link_graph.json', 'w') as f:
            json.dump(graph_data, f, indent=2)

        logger.info(f"Discovery saved to: {output_dir}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python site_discovery.py <url>")
        sys.exit(1)

    url = sys.argv[1]

    async def main():
        discovery = SiteDiscovery()
        result = await discovery.discover_site(url)

        print("\n🔍 Site Discovery Complete!")
        print(f"   Domain: {result.domain}")
        print(f"   Total URLs: {result.stats['total_urls']}")
        print(f"   HTML Pages: {result.stats['html_pages']}")
        print(f"   Sitemaps: {result.stats['sitemaps_found']}")
        print(f"   Feeds: {result.stats['feeds_found']}")
        print(f"   API Endpoints: {result.stats['api_endpoints']}")

    asyncio.run(main())
