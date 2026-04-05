"""
Core Scraping Infrastructure
============================

Core components for robust web scraping:

- death_star: Multi-tool comprehensive site scraper (original)
- death_star_v2: Enhanced "Nuke From Orbit" scraper with:
  - Forensic capture (WARC, HAR, certificates, DNS)
  - Media extraction (yt-dlp integration)
  - Site discovery (sitemaps, robots, link graphs)
  - Wayback Machine integration
  - Advanced capture (WebSocket, forms, tech stack detection)
  - Proxy pool and session management
  - Anti-bot evasion with Playwright stealth
- base_scraper: Abstract base class with checkpoint/resume
- checkpoint: SQLite-based state management
"""

# Original V1 scraper
from .death_star import DeathStar

# Base infrastructure
from .base_scraper import BaseScraper, ScraperConfig, RateLimiter
from .checkpoint import CheckpointManager, checkpoint

# V2 Enhanced modules (lazy import to avoid heavy dependencies at load time)
def get_death_star_v2():
    """Get the enhanced DeathStarV2 class."""
    from .death_star_v2 import DeathStarV2
    return DeathStarV2

def get_forensic_capture():
    """Get ForensicCapture for WARC/HAR generation."""
    from .forensic_capture import ForensicCapture
    return ForensicCapture

def get_media_extractor():
    """Get MediaExtractor for video/audio/image download."""
    from .media_extractor import MediaExtractor
    return MediaExtractor

def get_site_discovery():
    """Get SiteDiscovery for sitemap/robots parsing."""
    from .site_discovery import SiteDiscovery
    return SiteDiscovery

def get_wayback_machine():
    """Get WaybackMachine for historical snapshots."""
    from .wayback_integration import WaybackMachine
    return WaybackMachine

def get_advanced_capture():
    """Get AdvancedCapture for WebSocket/forms/tech detection."""
    from .advanced_capture import AdvancedCapture
    return AdvancedCapture


__all__ = [
    # Original V1
    'DeathStar',
    # Base infrastructure  
    'BaseScraper',
    'ScraperConfig',
    'RateLimiter',
    'CheckpointManager',
    'checkpoint',
    # V2 lazy getters
    'get_death_star_v2',
    'get_forensic_capture',
    'get_media_extractor',
    'get_site_discovery',
    'get_wayback_machine',
    'get_advanced_capture',
]