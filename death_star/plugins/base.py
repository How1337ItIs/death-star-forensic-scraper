"""
Plugin Base Classes
===================

Base classes for site-specific adapters.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from urllib.parse import urlparse

logger = logging.getLogger("death_star.plugins")


class SiteAdapter(ABC):
    """
    Base class for site-specific scrapers.
    
    Subclass this to create custom scrapers for specific sites
    with their own extraction logic.
    
    Usage:
        class MySiteAdapter(SiteAdapter):
            domains = ["example.com", "www.example.com"]
            
            async def extract(self, html: str, url: str) -> Dict[str, Any]:
                # Custom extraction logic
                return {"custom_field": "value"}
    """
    
    # List of domains this adapter handles
    domains: List[str] = []
    
    # Priority (higher = preferred)
    priority: int = 0
    
    @abstractmethod
    async def extract(self, html: str, url: str) -> Dict[str, Any]:
        """
        Extract structured data from HTML.
        
        Args:
            html: Page HTML content
            url: Page URL
        
        Returns:
            Dictionary of extracted data
        """
        pass
    
    def can_handle(self, url: str) -> bool:
        """Check if this adapter can handle a URL."""
        domain = urlparse(url).netloc
        return domain in self.domains
    
    async def pre_scrape(self, url: str) -> Optional[Dict]:
        """
        Hook called before scraping.
        
        Can return custom headers, cookies, etc.
        """
        return None
    
    async def post_scrape(self, data: Dict, url: str) -> Dict:
        """
        Hook called after scraping.
        
        Can modify or enrich extracted data.
        """
        return data


class AdapterRegistry:
    """
    Registry for site adapters.
    
    Usage:
        registry = AdapterRegistry()
        registry.register(MySiteAdapter)
        
        adapter = registry.get_adapter("https://example.com/page")
        if adapter:
            data = await adapter.extract(html, url)
    """
    
    def __init__(self):
        self._adapters: List[Type[SiteAdapter]] = []
    
    def register(self, adapter_class: Type[SiteAdapter]):
        """Register an adapter class."""
        self._adapters.append(adapter_class)
        # Sort by priority (descending)
        self._adapters.sort(key=lambda a: a.priority, reverse=True)
        logger.debug(f"Registered adapter: {adapter_class.__name__}")
    
    def get_adapter(self, url: str) -> Optional[SiteAdapter]:
        """Get an adapter that can handle a URL."""
        for adapter_class in self._adapters:
            adapter = adapter_class()
            if adapter.can_handle(url):
                return adapter
        return None
    
    def list_adapters(self) -> List[Dict]:
        """List all registered adapters."""
        return [
            {
                "name": a.__name__,
                "domains": a.domains,
                "priority": a.priority,
            }
            for a in self._adapters
        ]


# Global registry
_registry = AdapterRegistry()


def register_adapter(adapter_class: Type[SiteAdapter]):
    """Decorator to register an adapter."""
    _registry.register(adapter_class)
    return adapter_class


def get_adapter(url: str) -> Optional[SiteAdapter]:
    """Get an adapter for a URL from the global registry."""
    return _registry.get_adapter(url)
