"""
Base Site Adapter
=================

Abstract base class for site-specific scraping adapters.

Usage:
------
    from scripts.scraping.plugins.base_adapter import SiteAdapter, AdapterRegistry

    class RedditAdapter(SiteAdapter):
        name = "reddit"
        patterns = [r"reddit\.com", r"old\.reddit\.com"]
        
        def extract(self, html: str, url: str) -> dict:
            # Custom extraction logic
            return {"posts": [...], "comments": [...]}
    
    # Register adapter
    AdapterRegistry.register(RedditAdapter)
    
    # Get adapter for URL
    adapter = AdapterRegistry.get_adapter("https://reddit.com/r/gratefuldead")
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Pattern, Type


@dataclass
class AdapterConfig:
    """Configuration overrides for a site adapter."""
    # Rate limiting
    min_delay: float = 1.0
    max_delay: float = 3.0
    concurrent_requests: int = 2
    
    # Behavior
    needs_browser: bool = False
    needs_auth: bool = False
    respect_robots: bool = True
    
    # Extraction
    selectors: Dict[str, str] = field(default_factory=dict)
    pagination_selector: str = None
    content_selector: str = None
    
    # Headers
    custom_headers: Dict[str, str] = field(default_factory=dict)


class SiteAdapter(ABC):
    """
    Abstract base class for site-specific scraping logic.
    
    Subclasses must implement:
    - name: Unique identifier
    - patterns: List of regex patterns to match URLs
    - extract(): Custom extraction logic
    
    Optional overrides:
    - config: AdapterConfig with site-specific settings
    - pre_process(): Run before fetching
    - post_process(): Run after fetching
    - get_next_pages(): Pagination logic
    """
    
    name: str = "base"
    patterns: List[str] = []
    config: AdapterConfig = AdapterConfig()
    
    @classmethod
    def matches(cls, url: str) -> bool:
        """Check if URL matches this adapter's patterns."""
        for pattern in cls.patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    @abstractmethod
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """
        Extract structured data from page HTML.
        
        Args:
            html: Raw HTML content
            url: Source URL
        
        Returns:
            Dict with extracted data (schema varies by adapter)
        """
        pass
    
    def pre_process(self, url: str) -> Optional[str]:
        """
        Pre-process URL before fetching.
        
        Can modify URL, add tracking, etc.
        Return None to skip this URL.
        """
        return url
    
    def post_process(self, data: Dict, html: str, url: str) -> Dict:
        """
        Post-process extracted data.
        
        Clean, normalize, validate, etc.
        """
        return data
    
    def get_next_pages(self, html: str, url: str) -> List[str]:
        """
        Get pagination URLs from current page.
        
        Override for custom pagination logic.
        """
        if self.config.pagination_selector:
            # Use configured selector
            import re
            matches = re.findall(
                rf'{self.config.pagination_selector}=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE
            )
            return matches
        return []
    
    def should_use_browser(self, url: str) -> bool:
        """Check if this URL needs browser rendering."""
        return self.config.needs_browser
    
    def get_headers(self) -> Dict[str, str]:
        """Get custom headers for requests."""
        return self.config.custom_headers


class AdapterRegistry:
    """
    Registry for site adapters.
    
    Manages adapter registration and lookup.
    """
    
    _adapters: Dict[str, Type[SiteAdapter]] = {}
    
    @classmethod
    def register(cls, adapter_class: Type[SiteAdapter]):
        """Register a site adapter."""
        cls._adapters[adapter_class.name] = adapter_class
    
    @classmethod
    def unregister(cls, name: str):
        """Unregister an adapter by name."""
        if name in cls._adapters:
            del cls._adapters[name]
    
    @classmethod
    def get_adapter(cls, url: str) -> Optional[SiteAdapter]:
        """Get adapter instance for URL."""
        for adapter_class in cls._adapters.values():
            if adapter_class.matches(url):
                return adapter_class()
        return None
    
    @classmethod
    def list_adapters(cls) -> List[str]:
        """List all registered adapter names."""
        return list(cls._adapters.keys())
    
    @classmethod
    def get_by_name(cls, name: str) -> Optional[Type[SiteAdapter]]:
        """Get adapter class by name."""
        return cls._adapters.get(name)


# =============================================================================
# BUILT-IN ADAPTERS
# =============================================================================

class GenericAdapter(SiteAdapter):
    """Generic adapter that works with any site."""
    
    name = "generic"
    patterns = [r".*"]  # Matches everything (lowest priority)
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Basic extraction using common patterns."""
        import re
        
        # Extract title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract meta description
        meta_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
            html, re.I
        )
        description = meta_match.group(1) if meta_match else ""
        
        # Extract main content (try common patterns)
        content = ""
        for selector in ['article', 'main', '.content', '#content', '.post', '.entry']:
            pattern = rf'<{selector}[^>]*>(.*?)</{selector}>'
            match = re.search(pattern, html, re.I | re.DOTALL)
            if match:
                content = match.group(1)
                break
        
        # Strip HTML tags from content
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()
        
        return {
            "title": title,
            "description": description,
            "content": content[:5000] if content else "",
            "url": url
        }


class ForumAdapter(SiteAdapter):
    """Adapter for forum-style sites (vBulletin, phpBB, etc.)."""
    
    name = "forum"
    patterns = [
        r"forum\.",
        r"/forums?/",
        r"/threads?/",
        r"/topic/",
        r"phpbb",
        r"vbulletin",
    ]
    config = AdapterConfig(
        min_delay=2.0,
        max_delay=5.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract forum posts and threads."""
        import re
        
        posts = []
        
        # Try common forum post patterns
        post_patterns = [
            # vBulletin style
            r'<div[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)</div>',
            # phpBB style  
            r'<div[^>]*class="[^"]*postbody[^"]*"[^>]*>(.*?)</div>',
            # Generic
            r'<article[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)</article>',
        ]
        
        for pattern in post_patterns:
            matches = re.findall(pattern, html, re.I | re.DOTALL)
            if matches:
                for match in matches:
                    # Strip HTML
                    text = re.sub(r'<[^>]+>', ' ', match)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if text and len(text) > 50:
                        posts.append(text[:2000])
                break
        
        # Extract thread title
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        return {
            "type": "forum_thread",
            "title": title,
            "posts": posts,
            "post_count": len(posts),
            "url": url
        }


class NewsAdapter(SiteAdapter):
    """Adapter for news/article sites."""
    
    name = "news"
    patterns = [
        r"news\.",
        r"/news/",
        r"/article/",
        r"/story/",
        r"blog\.",
    ]
    config = AdapterConfig(
        min_delay=1.0,
        max_delay=3.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract article content."""
        # Try trafilatura for best extraction
        try:
            import trafilatura
            
            result = trafilatura.bare_extraction(
                html,
                include_comments=False,
                include_tables=True,
                favor_precision=True
            )
            
            if result:
                return {
                    "type": "article",
                    "title": result.get("title", ""),
                    "author": result.get("author", ""),
                    "date": result.get("date", ""),
                    "content": result.get("text", ""),
                    "url": url
                }
        except ImportError:
            pass
        
        # Fallback to regex
        import re
        
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        # Try to find article body
        article_match = re.search(
            r'<article[^>]*>(.*?)</article>',
            html, re.I | re.DOTALL
        )
        content = ""
        if article_match:
            content = re.sub(r'<[^>]+>', ' ', article_match.group(1))
            content = re.sub(r'\s+', ' ', content).strip()
        
        return {
            "type": "article",
            "title": title,
            "content": content[:10000],
            "url": url
        }


# Register built-in adapters
AdapterRegistry.register(GenericAdapter)
AdapterRegistry.register(ForumAdapter)
AdapterRegistry.register(NewsAdapter)
