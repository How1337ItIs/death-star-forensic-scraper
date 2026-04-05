"""
Cannabis Cultivation Site Adapters
==================================

Site-specific scrapers for cannabis cultivation forums, 
dispensary sites, grow guides, and research resources.

Registers adapters for:
- Rollitup.org (forum)
- Grasscity.com (forum + shop)
- Icmag.com (forum)
- Growweedeasy.com (guides)
- Leafly.com (strains + dispensaries)
- Cannabis.net (news)
- 420magazine.com (forum + news)
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_adapter import SiteAdapter, AdapterConfig, AdapterRegistry


class RollitupAdapter(SiteAdapter):
    """Adapter for Rollitup.org cannabis growing forum."""
    
    name = "rollitup"
    patterns = [r"rollitup\.org"]
    config = AdapterConfig(
        min_delay=2.0,
        max_delay=5.0,
        concurrent_requests=1,
        needs_browser=False,
        respect_robots=True,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract thread/post content from Rollitup."""
        # Extract thread title
        title_match = re.search(
            r'<h1[^>]*class="[^"]*p-title-value[^"]*"[^>]*>([^<]+)</h1>',
            html, re.I
        )
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract posts (XenForo format)
        posts = []
        post_pattern = r'<article[^>]*class="[^"]*message[^"]*"[^>]*>.*?<div[^>]*class="bbWrapper"[^>]*>(.*?)</div>'
        for match in re.finditer(post_pattern, html, re.I | re.DOTALL):
            text = re.sub(r'<[^>]+>', ' ', match.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 20:
                posts.append(text[:3000])
        
        # Extract grow journal metadata if present
        journal_info = {}
        if 'grow-journal' in url.lower() or 'journal' in html.lower():
            # Try to extract strain info
            strain_match = re.search(r'strain[:\s]*([^<]+)', html, re.I)
            if strain_match:
                journal_info['strain'] = strain_match.group(1).strip()[:100]
            
            # Medium (soil, hydro, coco)
            medium_match = re.search(r'medium[:\s]*([^<]+)', html, re.I)
            if medium_match:
                journal_info['medium'] = medium_match.group(1).strip()[:50]
        
        return {
            "type": "forum_thread",
            "source": "rollitup",
            "title": title,
            "posts": posts,
            "post_count": len(posts),
            "journal_info": journal_info,
            "url": url
        }


class GrasscityAdapter(SiteAdapter):
    """Adapter for Grasscity.com forums."""
    
    name = "grasscity"
    patterns = [r"forum\.grasscity\.com", r"grasscity\.com/forum"]
    config = AdapterConfig(
        min_delay=2.0,
        max_delay=4.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract content from Grasscity forums."""
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        posts = []
        # vBulletin/XenForo hybrid patterns
        post_patterns = [
            r'<div[^>]*class="[^"]*message-body[^"]*"[^>]*>(.*?)</div>',
            r'<blockquote[^>]*class="[^"]*messageText[^"]*"[^>]*>(.*?)</blockquote>',
        ]
        
        for pattern in post_patterns:
            for match in re.finditer(pattern, html, re.I | re.DOTALL):
                text = re.sub(r'<[^>]+>', ' ', match.group(1))
                text = re.sub(r'\s+', ' ', text).strip()
                if text and len(text) > 30:
                    posts.append(text[:2500])
            if posts:
                break
        
        return {
            "type": "forum_thread",
            "source": "grasscity",
            "title": title,
            "posts": posts,
            "post_count": len(posts),
            "url": url
        }


class IcmagAdapter(SiteAdapter):
    """Adapter for ICMag cannabis forums."""
    
    name = "icmag"
    patterns = [r"icmag\.com"]
    config = AdapterConfig(
        min_delay=3.0,
        max_delay=6.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract content from ICMag forums."""
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        posts = []
        # ICMag uses vBulletin
        for match in re.finditer(
            r'<div[^>]*id="post_message_\d+"[^>]*>(.*?)</div>',
            html, re.I | re.DOTALL
        ):
            text = re.sub(r'<[^>]+>', ' ', match.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 30:
                posts.append(text[:2500])
        
        return {
            "type": "forum_thread",
            "source": "icmag",
            "title": title,
            "posts": posts,
            "post_count": len(posts),
            "url": url
        }


class GrowWeedEasyAdapter(SiteAdapter):
    """Adapter for GrowWeedEasy.com cultivation guides."""
    
    name = "growweedeasy"
    patterns = [r"growweedeasy\.com"]
    config = AdapterConfig(
        min_delay=1.5,
        max_delay=3.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract grow guide content."""
        # Try trafilatura for article extraction
        try:
            import trafilatura
            
            result = trafilatura.bare_extraction(
                html,
                include_comments=False,
                include_tables=True,
                favor_precision=True
            )
            
            if result:
                # Parse out grow-specific metadata
                content = result.get('text', '')
                
                # Detect article type
                article_type = 'general'
                type_patterns = {
                    'problem': r'(deficiency|problem|issue|pest|disease|bug)',
                    'how-to': r'(how to|guide|tutorial|step)',
                    'strain': r'(strain review|strain guide)',
                    'equipment': r'(light|tent|fan|nutrient|soil|hydro)',
                }
                for t, pattern in type_patterns.items():
                    if re.search(pattern, content[:1000].lower()):
                        article_type = t
                        break
                
                return {
                    "type": "grow_guide",
                    "source": "growweedeasy",
                    "article_type": article_type,
                    "title": result.get('title', ''),
                    "content": content,
                    "author": result.get('author', ''),
                    "url": url
                }
        except ImportError:
            pass
        
        # Fallback to regex
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        # Try to get main content
        content_match = re.search(
            r'<article[^>]*>(.*?)</article>',
            html, re.I | re.DOTALL
        )
        content = ""
        if content_match:
            content = re.sub(r'<[^>]+>', ' ', content_match.group(1))
            content = re.sub(r'\s+', ' ', content).strip()
        
        return {
            "type": "grow_guide",
            "source": "growweedeasy",
            "title": title,
            "content": content[:15000],
            "url": url
        }


class LeaflyAdapter(SiteAdapter):
    """Adapter for Leafly.com strain/dispensary data."""
    
    name = "leafly"
    patterns = [r"leafly\.com"]
    config = AdapterConfig(
        min_delay=2.0,
        max_delay=4.0,
        needs_browser=True,  # JS-heavy site
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract strain or dispensary data from Leafly."""
        # Detect page type
        if '/strains/' in url:
            return self._extract_strain(html, url)
        elif '/dispensaries/' in url:
            return self._extract_dispensary(html, url)
        else:
            return self._extract_article(html, url)
    
    def _extract_strain(self, html: str, url: str) -> Dict[str, Any]:
        """Extract strain information."""
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        strain_name = title_match.group(1).strip() if title_match else ""
        
        # Try to get strain type (indica/sativa/hybrid)
        strain_type = "unknown"
        for t in ['indica', 'sativa', 'hybrid']:
            if t in html.lower():
                strain_type = t
                break
        
        # THC/CBD levels
        thc_match = re.search(r'THC[:\s]*(\d+(?:\.\d+)?)\s*%', html, re.I)
        cbd_match = re.search(r'CBD[:\s]*(\d+(?:\.\d+)?)\s*%', html, re.I)
        
        # Effects and flavors (look for common patterns)
        effects = []
        effect_patterns = ['relaxed', 'euphoric', 'happy', 'uplifted', 'creative', 
                          'sleepy', 'hungry', 'tingly', 'focused', 'energetic']
        for effect in effect_patterns:
            if effect in html.lower():
                effects.append(effect)
        
        return {
            "type": "strain",
            "source": "leafly",
            "name": strain_name,
            "strain_type": strain_type,
            "thc": float(thc_match.group(1)) if thc_match else None,
            "cbd": float(cbd_match.group(1)) if cbd_match else None,
            "effects": effects[:5],
            "url": url
        }
    
    def _extract_dispensary(self, html: str, url: str) -> Dict[str, Any]:
        """Extract dispensary information."""
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        name = title_match.group(1).strip() if title_match else ""
        
        return {
            "type": "dispensary",
            "source": "leafly",
            "name": name,
            "url": url
        }
    
    def _extract_article(self, html: str, url: str) -> Dict[str, Any]:
        """Extract article content."""
        try:
            import trafilatura
            result = trafilatura.bare_extraction(html)
            if result:
                return {
                    "type": "article",
                    "source": "leafly",
                    "title": result.get('title', ''),
                    "content": result.get('text', ''),
                    "url": url
                }
        except ImportError:
            pass
        
        return {"type": "article", "source": "leafly", "url": url}


class Magazine420Adapter(SiteAdapter):
    """Adapter for 420Magazine.com forums and news."""
    
    name = "420magazine"
    patterns = [r"420magazine\.com"]
    config = AdapterConfig(
        min_delay=2.0,
        max_delay=4.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract content from 420 Magazine."""
        if '/forums/' in url or '/threads/' in url:
            return self._extract_forum(html, url)
        else:
            return self._extract_article(html, url)
    
    def _extract_forum(self, html: str, url: str) -> Dict[str, Any]:
        """Extract forum thread."""
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        
        posts = []
        for match in re.finditer(
            r'<article[^>]*class="[^"]*message[^"]*"[^>]*>.*?<div[^>]*class="bbWrapper"[^>]*>(.*?)</div>',
            html, re.I | re.DOTALL
        ):
            text = re.sub(r'<[^>]+>', ' ', match.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 20:
                posts.append(text[:2500])
        
        # Detect if this is a grow journal
        is_journal = any(kw in url.lower() or kw in title.lower() 
                        for kw in ['journal', 'grow', 'diary'])
        
        return {
            "type": "grow_journal" if is_journal else "forum_thread",
            "source": "420magazine",
            "title": title,
            "posts": posts,
            "post_count": len(posts),
            "url": url
        }
    
    def _extract_article(self, html: str, url: str) -> Dict[str, Any]:
        """Extract news article."""
        try:
            import trafilatura
            result = trafilatura.bare_extraction(html)
            if result:
                return {
                    "type": "news_article",
                    "source": "420magazine",
                    "title": result.get('title', ''),
                    "content": result.get('text', ''),
                    "author": result.get('author', ''),
                    "date": result.get('date', ''),
                    "url": url
                }
        except ImportError:
            pass
        
        return {"type": "news_article", "source": "420magazine", "url": url}


class CannabisNetAdapter(SiteAdapter):
    """Adapter for Cannabis.net news and articles."""
    
    name = "cannabisnet"
    patterns = [r"cannabis\.net"]
    config = AdapterConfig(
        min_delay=1.5,
        max_delay=3.0,
        needs_browser=False,
    )
    
    def extract(self, html: str, url: str) -> Dict[str, Any]:
        """Extract news article."""
        try:
            import trafilatura
            result = trafilatura.bare_extraction(
                html,
                include_comments=False,
                favor_precision=True
            )
            if result:
                return {
                    "type": "news_article",
                    "source": "cannabis.net",
                    "title": result.get('title', ''),
                    "content": result.get('text', ''),
                    "author": result.get('author', ''),
                    "date": result.get('date', ''),
                    "url": url
                }
        except ImportError:
            pass
        
        # Fallback
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        return {
            "type": "news_article",
            "source": "cannabis.net",
            "title": title_match.group(1).strip() if title_match else "",
            "url": url
        }


# =============================================================================
# REGISTER ALL CANNABIS ADAPTERS
# =============================================================================

def register_cannabis_adapters():
    """Register all cannabis-specific adapters."""
    adapters = [
        RollitupAdapter,
        GrasscityAdapter,
        IcmagAdapter,
        GrowWeedEasyAdapter,
        LeaflyAdapter,
        Magazine420Adapter,
        CannabisNetAdapter,
    ]
    
    for adapter in adapters:
        AdapterRegistry.register(adapter)
    
    return adapters


# Auto-register on import
register_cannabis_adapters()
