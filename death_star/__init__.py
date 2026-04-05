"""
Death Star Scraper (pip package) -- DEPRECATED
===============================================

This package is deprecated. Use Death Star V2 in this repo instead:

    From repo root: set PYTHONPATH=src && python -m scraping.core.death_star_v2 --target URL --mode ultimate
    See: README.md in repo root and death_star/README.md

The pip package only performs a basic browser crawl. Modes "forensic" and
"ultimate" here do NOT run the full forensic/ultimate pipelines (WARC, HAR,
API capture, advanced capture, Wayback). That behavior is in V2 only.

Legacy features (for existing users only):
---------
- Multi-tool orchestration (HTTP, Playwright)
- Basic crawl with browser fallback
- death_star.core.forensic.ForensicCapture (single-page capture)

Author: Deadhead-LLM Project
License: MIT
"""

__version__ = "2.0.0"
__author__ = "Deadhead-LLM Project"

# Core exports
from death_star.core.scraper import DeathStar, ScrapeConfig, ScrapedPage
from death_star.core.checkpoint import Checkpoint

# Advanced modules
from death_star.core.forensic import ForensicCapture
from death_star.core.advanced import AdvancedCapture
from death_star.core.wayback import WaybackMachine
from death_star.core.media import MediaExtractor
from death_star.core.discovery import SiteDiscovery

# Utilities
from death_star.utils.proxy import ProxyPool
from death_star.utils.session import SessionManager

__all__ = [
    # Version
    "__version__",
    
    # Core
    "DeathStar",
    "ScrapeConfig", 
    "ScrapedPage",
    "Checkpoint",
    
    # Advanced
    "ForensicCapture",
    "AdvancedCapture",
    "WaybackMachine",
    "MediaExtractor",
    "SiteDiscovery",
    
    # Utilities
    "ProxyPool",
    "SessionManager",
]
