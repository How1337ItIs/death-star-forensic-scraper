"""
Base Scraper Class with Self-Healing Patterns
==============================================

Provides robust foundation for all scrapers with:
- Checkpoint/resume capability (survives crashes)
- Graceful shutdown handling
- Rate limiting with exponential backoff
- Comprehensive logging

Usage:
    class MyScraper(BaseScraper):
        def scrape_page(self, url: str) -> dict:
            # Your scraping logic here
            return data

    scraper = MyScraper(name="my_scraper", db_path="state.db")
    scraper.run(urls)
"""

import signal
import time
import random
import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterator
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@dataclass
class ScraperConfig:
    """Configuration for scraper behavior."""
    min_delay: float = 1.0  # Minimum delay between requests
    max_delay: float = 3.0  # Maximum delay between requests
    max_retries: int = 3    # Max retries on failure
    backoff_factor: float = 2.0  # Exponential backoff multiplier
    checkpoint_interval: int = 10  # Save checkpoint every N items
    user_agent: str = "SOL-CANNABIS-Research/1.0 (Cannabis Research)"


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.

    Implements:
    - SQLite-based checkpoint/resume
    - Signal handling for graceful shutdown
    - Rate limiting with jitter
    - Exponential backoff on errors
    """

    def __init__(
        self,
        name: str,
        db_path: Optional[str] = None,
        config: Optional[ScraperConfig] = None
    ):
        self.name = name
        self.config = config or ScraperConfig()
        self.logger = logging.getLogger(f"scraper.{name}")

        # State management
        self._shutdown_requested = False
        self._items_scraped = 0
        self._errors = 0

        # Initialize checkpoint database
        self.db_path = db_path or f"data/scraping_state/{name}_state.db"
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # Register signal handlers
        self._register_signal_handlers()

    def _init_db(self):
        """Initialize SQLite database with WAL mode for crash safety."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute('PRAGMA journal_mode=WAL')  # Crash-safe writes
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS checkpoints (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS scraped_items (
                url TEXT PRIMARY KEY,
                status TEXT,
                scraped_at TEXT,
                error TEXT
            )
        ''')
        self.conn.commit()

    def _register_signal_handlers(self):
        """Register handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

    def _shutdown_handler(self, sig, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Shutdown signal received ({sig}). Finishing current item...")
        self._shutdown_requested = True

    def save_checkpoint(self, key: str, value: str):
        """Save a checkpoint value (crash-safe)."""
        self.conn.execute('''
            INSERT OR REPLACE INTO checkpoints (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now().isoformat()))
        self.conn.commit()

    def get_checkpoint(self, key: str) -> Optional[str]:
        """Retrieve a checkpoint value."""
        row = self.conn.execute(
            'SELECT value FROM checkpoints WHERE key = ?', (key,)
        ).fetchone()
        return row[0] if row else None

    def mark_scraped(self, url: str, status: str = "success", error: str = None):
        """Mark a URL as scraped."""
        self.conn.execute('''
            INSERT OR REPLACE INTO scraped_items (url, status, scraped_at, error)
            VALUES (?, ?, ?, ?)
        ''', (url, status, datetime.now().isoformat(), error))
        self.conn.commit()

    def is_scraped(self, url: str) -> bool:
        """Check if URL has already been scraped successfully."""
        row = self.conn.execute(
            'SELECT status FROM scraped_items WHERE url = ? AND status = ?',
            (url, "success")
        ).fetchone()
        return row is not None

    def _random_delay(self):
        """Apply random delay between requests."""
        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        time.sleep(delay)

    def _exponential_backoff(self, attempt: int):
        """Apply exponential backoff after errors."""
        delay = self.config.backoff_factor ** attempt
        jitter = random.uniform(0, delay * 0.1)
        self.logger.info(f"Backing off for {delay + jitter:.2f}s (attempt {attempt})")
        time.sleep(delay + jitter)

    @abstractmethod
    def scrape_page(self, url: str) -> dict:
        """
        Scrape a single page. Must be implemented by subclasses.

        Args:
            url: The URL to scrape

        Returns:
            dict: The scraped data

        Raises:
            Exception: On scraping failure (will be retried)
        """
        pass

    def run(self, urls: Iterator[str]) -> dict:
        """
        Run the scraper on a list of URLs.

        Args:
            urls: Iterator of URLs to scrape

        Returns:
            dict: Summary of scraping results
        """
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} scraper")

        for url in urls:
            if self._shutdown_requested:
                self.logger.info("Shutdown requested, saving state and exiting...")
                break

            # Skip already scraped
            if self.is_scraped(url):
                self.logger.debug(f"Skipping already scraped: {url}")
                continue

            # Attempt to scrape with retries
            for attempt in range(self.config.max_retries):
                try:
                    self._random_delay()
                    self.scrape_page(url)
                    self.mark_scraped(url, "success")
                    self._items_scraped += 1

                    # Periodic checkpoint
                    if self._items_scraped % self.config.checkpoint_interval == 0:
                        self.save_checkpoint("last_url", url)
                        self.save_checkpoint("items_scraped", str(self._items_scraped))
                        self.logger.info(f"Checkpoint: {self._items_scraped} items scraped")

                    break

                except Exception as e:
                    self._errors += 1
                    self.logger.warning(f"Error scraping {url} (attempt {attempt + 1}): {e}")

                    if attempt < self.config.max_retries - 1:
                        self._exponential_backoff(attempt + 1)
                    else:
                        self.mark_scraped(url, "failed", str(e))
                        self.logger.error(f"Failed after {self.config.max_retries} attempts: {url}")

        # Final summary
        elapsed = (datetime.now() - start_time).total_seconds()
        summary = {
            "scraper": self.name,
            "items_scraped": self._items_scraped,
            "errors": self._errors,
            "elapsed_seconds": elapsed,
            "shutdown_clean": not self._shutdown_requested or self._items_scraped > 0
        }

        self.logger.info(f"Scraping complete: {summary}")
        self.save_checkpoint("last_run_summary", str(summary))

        return summary

    def get_stats(self) -> dict:
        """Get current scraping statistics."""
        total = self.conn.execute('SELECT COUNT(*) FROM scraped_items').fetchone()[0]
        success = self.conn.execute(
            'SELECT COUNT(*) FROM scraped_items WHERE status = ?', ("success",)
        ).fetchone()[0]
        failed = self.conn.execute(
            'SELECT COUNT(*) FROM scraped_items WHERE status = ?', ("failed",)
        ).fetchone()[0]

        return {
            "total_urls": total,
            "successful": success,
            "failed": failed,
            "success_rate": success / total if total > 0 else 0
        }

    def close(self):
        """Close database connection."""
        self.conn.close()


class RateLimiter:
    """
    Token bucket rate limiter for respectful scraping.

    Usage:
        limiter = RateLimiter(requests_per_minute=30)
        with limiter:
            # Make request
            pass
    """

    def __init__(self, requests_per_minute: int = 30):
        self.min_interval = 60.0 / requests_per_minute
        self.last_request = 0

    def __enter__(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        return self

    def __exit__(self, *args):
        self.last_request = time.time()


if __name__ == "__main__":
    # Example usage / self-test
    class TestScraper(BaseScraper):
        def scrape_page(self, url: str) -> dict:
            print(f"Would scrape: {url}")
            return {"url": url, "data": "test"}

    scraper = TestScraper(name="test", db_path="/tmp/test_scraper.db")
    result = scraper.run(iter(["http://example.com/1", "http://example.com/2"]))
    print(f"Result: {result}")
    scraper.close()
