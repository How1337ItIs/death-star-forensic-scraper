#!/usr/bin/env python3
"""
Death Star Scraper - CLI
========================

Command-line interface for the Death Star Scraper.

Usage:
    death-star --target https://example.com --mode forensic
    death-star --target https://example.com --mode quick --output ./data
    death-star --targets urls.txt --mode full
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from death_star import __version__
from death_star.core.scraper import DeathStar, ScrapeConfig


def setup_logging(verbose: bool = False):
    """Set up logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def print_banner():
    """Print the Death Star banner."""
    banner = """
    +-----------------------------------------------------------+
    |   DEATH STAR - Ultimate All-Purpose Web Scraper v{version}   |
    +-----------------------------------------------------------+
    """.format(version=__version__)
    try:
        print(banner)
    except UnicodeEncodeError:
        print("Death Star Scraper v{}".format(__version__))


def print_installation_guide():
    """Print installation guide."""
    guide = """
    DEATH STAR SCRAPER - Installation Guide
    ========================================

    1. BASIC INSTALLATION:
       pip install death-star-scraper

    2. WITH BROWSER SUPPORT (for JS-heavy sites):
       pip install death-star-scraper[browser]
       playwright install chromium

    3. FULL INSTALLATION (all features):
       pip install death-star-scraper[full]
       playwright install chromium

    4. OPTIONAL TOOLS (for additional features):
       - wget: For fast site mirroring
       - yt-dlp: For video/audio downloading (included)
       - archivebox: For full archival (optional)

    QUICK START:
       death-star --target https://example.com
       death-star --target https://example.com --mode forensic
       death-star --target https://example.com --mode ultimate
    """
    print(guide)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Death Star Scraper - Ultimate All-Purpose Web Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  death-star --target https://example.com
  death-star --target https://example.com --mode forensic
  death-star --target https://example.com --mode stealth --depth 10
  death-star --targets urls.txt --mode full
  death-star --target https://protected.com --cookies cookies.json
        """,
    )
    
    # Target options
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument(
        "--target", "-t",
        help="URL to scrape",
    )
    target_group.add_argument(
        "--targets",
        help="File with URLs to scrape (one per line)",
    )
    
    # Mode options
    parser.add_argument(
        "--mode", "-m",
        default="smart",
        choices=["quick", "smart", "stealth", "full", "forensic", "planetary", "ultimate"],
        help="Scraping mode (default: smart)",
    )
    
    # Crawl options
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=5,
        help="Maximum crawl depth (default: 5)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10000,
        help="Maximum pages to scrape (default: 10000)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint",
    )
    parser.add_argument(
        "--polite", "-p",
        action="store_true",
        help="Respect robots.txt",
    )
    
    # Output options
    parser.add_argument(
        "--output", "-o",
        help="Output directory",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Min delay between requests (default: 1.0)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable content deduplication",
    )
    
    # Proxy and authentication
    parser.add_argument(
        "--proxy",
        help="Proxy URL (http://host:port)",
    )
    parser.add_argument(
        "--proxy-file",
        help="File with proxy list (one per line)",
    )
    parser.add_argument(
        "--cookies",
        help="Cookie file (JSON or Netscape format)",
    )
    parser.add_argument(
        "--auth-user",
        help="Username for HTTP authentication",
    )
    parser.add_argument(
        "--auth-pass",
        help="Password for HTTP authentication",
    )
    
    # Utility options
    parser.add_argument(
        "--install",
        action="store_true",
        help="Show installation instructions",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"Death Star Scraper v{__version__}",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output",
    )
    
    args = parser.parse_args()
    
    # Handle utility commands
    if args.install:
        print_installation_guide()
        return 0
    
    # Setup logging
    if not args.quiet:
        setup_logging(args.verbose)
        print_banner()
    
    # Validate target
    if not args.target and not args.targets:
        parser.error("Either --target or --targets is required")
    
    # Build config
    proxy_list = [args.proxy] if args.proxy else []
    
    config = ScrapeConfig(
        max_depth=args.depth,
        max_pages=args.max_pages,
        min_delay=args.delay,
        max_delay=args.delay * 2,
        respect_robots=args.polite,
        deduplicate=not args.no_dedup,
        proxy_list=proxy_list,
        proxy_pool_file=args.proxy_file,
        cookie_file=args.cookies,
        auth_username=args.auth_user,
        auth_password=args.auth_pass,
    )
    
    output_dir = Path(args.output) if args.output else Path("data/scraped_sites")
    
    # Get targets
    targets = []
    if args.target:
        targets = [args.target]
    elif args.targets:
        targets_file = Path(args.targets)
        if targets_file.exists():
            targets = [
                line.strip()
                for line in targets_file.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            ]
        else:
            print(f"Error: Targets file not found: {args.targets}")
            return 1
    
    # Run scraper
    async def run():
        death_star = DeathStar(config=config, output_dir=output_dir)
        
        try:
            for target in targets:
                print(f"\nTarget: {target}")
                print(f"   Mode: {args.mode}")
                print(f"   Output: {output_dir}")
                print()
                
                result = await death_star.destroy(
                    target,
                    mode=args.mode,
                    resume=args.resume,
                )
                
                print(f"\nComplete!")
                print(f"   Pages scraped: {result['pages_scraped']}")
                print(f"   Errors: {result['errors']}")
                print(f"   Manifest: {result['manifest']}")
        
        finally:
            await death_star.close()
    
    try:
        asyncio.run(run())
        return 0
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
