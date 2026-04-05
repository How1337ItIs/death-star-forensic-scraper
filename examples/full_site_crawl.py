#!/usr/bin/env python3
"""
Full Site Crawl Example
=======================

Shows how to crawl an entire site with Death Star.
"""

import asyncio
from pathlib import Path

from death_star import DeathStar, ScrapeConfig


async def main():
    # Configure the scrape
    config = ScrapeConfig(
        max_depth=3,           # How deep to crawl
        max_pages=100,         # Maximum pages to scrape
        min_delay=1.0,         # Minimum delay between requests
        max_delay=3.0,         # Maximum delay (randomized)
        respect_robots=True,   # Be polite, respect robots.txt
        deduplicate=True,      # Skip duplicate content
    )
    
    # Create scraper
    scraper = DeathStar(
        config=config,
        output_dir=Path("./scraped_data"),
    )
    
    try:
        # Destroy (scrape) the target
        result = await scraper.destroy(
            "https://example.com",
            mode="smart",  # Adaptive HTTP/browser
            resume=False,  # Start fresh (set True to resume)
        )
        
        print("\n" + "=" * 50)
        print("SCRAPE COMPLETE")
        print("=" * 50)
        print(f"Target: {result['target']}")
        print(f"Pages scraped: {result['pages_scraped']}")
        print(f"Errors: {result['errors']}")
        print(f"Manifest: {result['manifest']}")
        
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
