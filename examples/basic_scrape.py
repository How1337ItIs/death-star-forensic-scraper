#!/usr/bin/env python3
"""
Basic Scraping Example
======================

Shows how to use Death Star for simple web scraping.
"""

import asyncio
from death_star import DeathStar


async def main():
    # Create scraper with default settings
    scraper = DeathStar()
    
    # Scrape a single page
    page = await scraper.scrape("https://example.com")
    
    if page:
        print(f"Title: {page.title}")
        print(f"URL: {page.final_url}")
        print(f"Status: {page.status_code}")
        print(f"Method: {page.method}")
        print(f"Links found: {len(page.links)}")
        print(f"Media found: {len(page.media)}")
        print()
        print("Clean text (first 500 chars):")
        print(page.clean_text[:500])
    else:
        print("Failed to scrape page")
    
    await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
