#!/usr/bin/env python3
"""
Proxy and Cookie Example
========================

Shows how to use Death Star with proxies and cookies
for scraping protected sites.
"""

import asyncio
from pathlib import Path

from death_star import DeathStar, ScrapeConfig
from death_star.utils import ProxyPool, SessionManager


async def main():
    # Create proxy pool (from file or list)
    proxy_pool = ProxyPool(proxies=[
        "http://proxy1.example.com:8080",
        "http://user:pass@proxy2.example.com:8080",
    ])
    
    # Or load from file:
    # proxy_pool = ProxyPool(proxy_file="proxies.txt")
    
    # Create session manager with cookies
    session = SessionManager()
    
    # Load cookies from file
    # session = SessionManager(cookie_file="cookies.json")
    
    # Or add cookies manually
    session.add_cookie(
        name="session_id",
        value="abc123",
        domain=".example.com",
    )
    
    # Add authentication if needed
    session.add_auth_headers(
        username="myuser",
        password="mypass",
        auth_type="basic",
    )
    
    # Configure with proxy and cookies
    config = ScrapeConfig(
        max_depth=3,
        max_pages=50,
        min_delay=2.0,  # Be extra polite with proxies
        max_delay=5.0,
        proxy_list=[
            "http://proxy1.example.com:8080",
            "http://proxy2.example.com:8080",
        ],
        # Or use proxy file:
        # proxy_pool_file="proxies.txt",
        cookie_file="cookies.json",  # If you have a cookie file
    )
    
    scraper = DeathStar(config=config)
    
    try:
        # Use stealth mode for protected sites
        result = await scraper.destroy(
            "https://example.com",
            mode="stealth",
        )
        
        print(f"Scraped {result['pages_scraped']} pages")
        
    finally:
        await scraper.close()


if __name__ == "__main__":
    print("Note: Update proxy and cookie values for your target site")
    asyncio.run(main())
