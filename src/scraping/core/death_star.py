"""
DEATH STAR Web Scraper
======================

All-consuming, leave-no-stone-unturned web scraper.

Combines multiple tools for maximum coverage:
1. ArchiveBox - Full archival (HTML, PDF, screenshot, WARC)
2. Crawl4AI - LLM-ready structured output
3. wget recursive - Classic deep crawl
4. Playwright - JavaScript rendering

Usage:
    # Destroy a single site (archive everything)
    python death_star.py --target https://example.com --depth 5

    # Destroy multiple sites from file
    python death_star.py --targets urls.txt --depth 3

    # Quick mode (wget only, fast)
    python death_star.py --target https://example.com --quick

    # Full death star (all tools)
    python death_star.py --target https://example.com --full
"""

import argparse
import subprocess
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("death_star")

# Output directory
OUTPUT_DIR = Path("data/scraped_sites")


class DeathStar:
    """
    The all-consuming web scraper.

    Combines multiple tools for comprehensive site archival:
    - wget: Deep recursive download
    - ArchiveBox: Full archival with multiple formats
    - Crawl4AI: LLM-ready structured extraction
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tools_available = self._check_tools()
        self._log_tools()

    def _check_tools(self) -> dict:
        """Check which tools are available."""
        tools = {
            "wget": shutil.which("wget") is not None,
            "archivebox": shutil.which("archivebox") is not None,
            "crawl4ai": self._check_python_module("crawl4ai"),
            "playwright": self._check_python_module("playwright"),
        }
        return tools

    def _check_python_module(self, module: str) -> bool:
        """Check if a Python module is installed."""
        try:
            __import__(module)
            return True
        except ImportError:
            return False

    def _log_tools(self):
        """Log available tools."""
        logger.info("=== DEATH STAR WEAPONS SYSTEMS ===")
        for tool, available in self.tools_available.items():
            status = "✅ ARMED" if available else "❌ OFFLINE"
            logger.info(f"  {tool}: {status}")

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.replace("www.", "")

    def wget_recursive(self, url: str, depth: int = 5) -> Path:
        """
        Classic wget recursive download.

        Downloads entire site structure with all assets.
        """
        if not self.tools_available["wget"]:
            logger.warning("wget not available, skipping")
            return None

        domain = self._get_domain(url)
        output_path = self.output_dir / "wget" / domain
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"🌐 WGET: Initiating recursive download of {url}")

        cmd = [
            "wget",
            "--recursive",                    # Follow links recursively
            "--level", str(depth),            # Depth limit
            "--page-requisites",              # Get all assets (CSS, JS, images)
            "--convert-links",                # Convert links for offline viewing
            "--adjust-extension",             # Add .html to pages
            "--no-parent",                    # Don't go up to parent directories
            "--wait", "1",                    # Polite delay
            "--random-wait",                  # Random delay variation
            "--limit-rate", "1M",             # Rate limit
            "--user-agent", "SOL-CANNABIS-Research/1.0",
            "--directory-prefix", str(output_path),
            "--no-clobber",                   # Don't re-download existing
            "--timeout", "30",                # Timeout per request
            "--tries", "3",                   # Retry count
            url
        ]

        try:
            subprocess.run(cmd, check=False, timeout=3600)  # 1 hour max
            logger.info(f"✅ WGET complete: {output_path}")
            return output_path
        except subprocess.TimeoutExpired:
            logger.warning("WGET timed out after 1 hour")
            return output_path
        except Exception as e:
            logger.error(f"WGET failed: {e}")
            return None

    def archivebox_archive(self, url: str, depth: int = 3) -> Path:
        """
        ArchiveBox full archival.

        Saves: HTML, PDF, screenshot, WARC, media, git repos.
        """
        if not self.tools_available["archivebox"]:
            logger.warning("archivebox not available. Install: pip install archivebox")
            return None

        domain = self._get_domain(url)
        output_path = self.output_dir / "archivebox" / domain
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"📦 ARCHIVEBOX: Full archival of {url}")

        # Initialize if needed
        init_cmd = ["archivebox", "init", "--setup"]
        subprocess.run(init_cmd, cwd=output_path, capture_output=True)

        # Add URL with depth
        add_cmd = [
            "archivebox", "add",
            url,
            f"--depth={depth}",
            "--parser=auto"
        ]

        try:
            subprocess.run(
                add_cmd,
                cwd=output_path,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours max
            )
            logger.info(f"✅ ARCHIVEBOX complete: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"ARCHIVEBOX failed: {e}")
            return None

    def crawl4ai_extract(self, url: str) -> dict:
        """
        Crawl4AI LLM-ready extraction.

        Returns structured data ready for embedding.
        """
        if not self.tools_available["crawl4ai"]:
            logger.warning("crawl4ai not available. Install: pip install crawl4ai")
            return None

        logger.info(f"🤖 CRAWL4AI: Extracting structured content from {url}")

        try:
            from crawl4ai import WebCrawler

            crawler = WebCrawler()
            crawler.warmup()

            result = crawler.run(url=url)

            if result.success:
                return {
                    "url": url,
                    "title": result.metadata.get("title", ""),
                    "markdown": result.markdown,
                    "links": result.links,
                    "media": result.media,
                    "extracted_at": datetime.now().isoformat()
                }
            else:
                logger.warning(f"CRAWL4AI extraction failed for {url}")
                return None
        except Exception as e:
            logger.error(f"CRAWL4AI failed: {e}")
            return None

    def destroy(
        self,
        url: str,
        depth: int = 5,
        quick: bool = False,
        full: bool = False
    ) -> dict:
        """
        FIRE THE DEATH STAR.

        Args:
            url: Target URL to destroy
            depth: How deep to crawl
            quick: Fast mode (wget only)
            full: Full destruction (all tools)

        Returns:
            Dict with results from each weapon system
        """
        logger.info(f"💥💥💥 DEATH STAR FIRING ON: {url} 💥💥💥")

        results = {
            "target": url,
            "depth": depth,
            "timestamp": datetime.now().isoformat(),
            "weapons_fired": [],
            "outputs": {}
        }

        # Always fire wget (fast, reliable)
        wget_result = self.wget_recursive(url, depth)
        if wget_result:
            results["weapons_fired"].append("wget")
            results["outputs"]["wget"] = str(wget_result)

        if quick:
            logger.info("⚡ Quick mode - wget only")
            return results

        # Fire ArchiveBox (comprehensive)
        if full or not quick:
            ab_result = self.archivebox_archive(url, min(depth, 3))
            if ab_result:
                results["weapons_fired"].append("archivebox")
                results["outputs"]["archivebox"] = str(ab_result)

        # Fire Crawl4AI (structured extraction)
        if full:
            c4ai_result = self.crawl4ai_extract(url)
            if c4ai_result:
                results["weapons_fired"].append("crawl4ai")
                # Save structured output
                domain = self._get_domain(url)
                c4ai_path = self.output_dir / "crawl4ai" / f"{domain}.json"
                c4ai_path.parent.mkdir(parents=True, exist_ok=True)
                with open(c4ai_path, "w") as f:
                    json.dump(c4ai_result, f, indent=2)
                results["outputs"]["crawl4ai"] = str(c4ai_path)

        logger.info(f"💥 DESTRUCTION COMPLETE. Weapons fired: {results['weapons_fired']}")

        # Save results manifest
        manifest_path = self.output_dir / f"{self._get_domain(url)}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(results, f, indent=2)

        return results

    def destroy_list(self, urls: List[str], **kwargs) -> List[dict]:
        """Destroy multiple targets."""
        results = []
        for url in urls:
            result = self.destroy(url, **kwargs)
            results.append(result)
        return results


def install_weapons():
    """Install all weapon systems."""
    print("=== INSTALLING DEATH STAR WEAPONS ===")

    # wget (usually pre-installed on Linux)
    print("\n1. wget: Usually pre-installed on Linux")
    print("   Ubuntu/Debian: sudo apt install wget")

    # ArchiveBox
    print("\n2. ArchiveBox:")
    print("   pip install archivebox")
    print("   archivebox init --setup")

    # Crawl4AI
    print("\n3. Crawl4AI:")
    print("   pip install crawl4ai")
    print("   crawl4ai-setup")

    # Playwright (for JS rendering)
    print("\n4. Playwright:")
    print("   pip install playwright")
    print("   playwright install chromium")

    print("\n=== RUN THESE COMMANDS TO ARM THE DEATH STAR ===")


def main():
    parser = argparse.ArgumentParser(
        description="SOL-CANNABIS DEATH STAR - Comprehensive web scraper for cannabis research"
    )
    parser.add_argument("--target", "-t", help="Target URL to destroy")
    parser.add_argument("--targets", "-T", help="File with URLs (one per line)")
    parser.add_argument("--depth", "-d", type=int, default=5, help="Crawl depth (default: 5)")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode (wget only)")
    parser.add_argument("--full", "-f", action="store_true", help="Full destruction (all tools)")
    parser.add_argument("--install", action="store_true", help="Show installation instructions")
    parser.add_argument("--output", "-o", help="Output directory")

    args = parser.parse_args()

    if args.install:
        install_weapons()
        return

    if not args.target and not args.targets:
        parser.print_help()
        print("\nExample: python src/scraping/core/death_star.py --target https://cannabis-research-site.com --full")
        return

    output_dir = Path(args.output) if args.output else OUTPUT_DIR
    death_star = DeathStar(output_dir)

    if args.target:
        result = death_star.destroy(
            args.target,
            depth=args.depth,
            quick=args.quick,
            full=args.full
        )
        print(json.dumps(result, indent=2))

    elif args.targets:
        with open(args.targets) as f:
            urls = [line.strip() for line in f if line.strip()]
        results = death_star.destroy_list(
            urls,
            depth=args.depth,
            quick=args.quick,
            full=args.full
        )
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
