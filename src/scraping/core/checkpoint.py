"""
Checkpoint/Resume Module for Scrapers
=====================================

Standalone SQLite-based persistence for scraper state.
Uses WAL mode for crash-safe writes.

Features:
- Progress tracking (items processed, last URL)
- Deduplication (track what's already scraped)
- Resume from any point after crash
- Queue management for pending URLs

Usage:
    from checkpoint import CheckpointManager

    with CheckpointManager("my_scraper") as cp:
        cp.add_to_queue(["url1", "url2", "url3"])

        for url in cp.pending_urls():
            # scrape url
            cp.mark_complete(url, data={"content": "..."})

        print(cp.stats())
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Any, Dict, List
from contextlib import contextmanager


class CheckpointManager:
    """
    Manages scraper state persistence with crash recovery.

    All writes use WAL mode for durability - state survives crashes.
    """

    def __init__(self, name: str, db_dir: str = "data/scraping_state"):
        self.name = name
        self.db_path = Path(db_dir) / f"{name}_checkpoint.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Initialize database with WAL mode."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA journal_mode=WAL')

        # Create tables
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS queue (
                url TEXT PRIMARY KEY,
                added_at TEXT,
                priority INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS completed (
                url TEXT PRIMARY KEY,
                status TEXT,
                completed_at TEXT,
                data TEXT,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_queue_priority
                ON queue(priority DESC);

            CREATE INDEX IF NOT EXISTS idx_completed_status
                ON completed(status);
        ''')
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    # === Queue Management ===

    def add_to_queue(self, urls: List[str], priority: int = 0):
        """Add URLs to the scraping queue."""
        now = datetime.now().isoformat()
        for url in urls:
            try:
                self.conn.execute(
                    'INSERT OR IGNORE INTO queue (url, added_at, priority) VALUES (?, ?, ?)',
                    (url, now, priority)
                )
            except sqlite3.IntegrityError:
                pass  # Already in queue
        self.conn.commit()

    def pending_urls(self, limit: int = None) -> Iterator[str]:
        """
        Iterate over pending URLs (not yet completed).

        Yields URLs in priority order (highest first).
        """
        query = '''
            SELECT q.url FROM queue q
            LEFT JOIN completed c ON q.url = c.url
            WHERE c.url IS NULL
            ORDER BY q.priority DESC
        '''
        if limit:
            query += f' LIMIT {limit}'

        cursor = self.conn.execute(query)
        for row in cursor:
            yield row['url']

    def pending_count(self) -> int:
        """Count pending URLs."""
        row = self.conn.execute('''
            SELECT COUNT(*) FROM queue q
            LEFT JOIN completed c ON q.url = c.url
            WHERE c.url IS NULL
        ''').fetchone()
        return row[0]

    # === Completion Tracking ===

    def mark_complete(
        self,
        url: str,
        status: str = "success",
        data: Dict = None,
        error: str = None
    ):
        """Mark a URL as completed."""
        self.conn.execute('''
            INSERT OR REPLACE INTO completed (url, status, completed_at, data, error)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            url,
            status,
            datetime.now().isoformat(),
            json.dumps(data) if data else None,
            error
        ))
        self.conn.commit()

    def is_complete(self, url: str) -> bool:
        """Check if URL has been completed."""
        row = self.conn.execute(
            'SELECT 1 FROM completed WHERE url = ?', (url,)
        ).fetchone()
        return row is not None

    def get_completed_data(self, url: str) -> Optional[Dict]:
        """Get data for a completed URL."""
        row = self.conn.execute(
            'SELECT data FROM completed WHERE url = ? AND status = ?',
            (url, "success")
        ).fetchone()
        if row and row['data']:
            return json.loads(row['data'])
        return None

    # === Metadata ===

    def set_meta(self, key: str, value: Any):
        """Set a metadata value."""
        self.conn.execute('''
            INSERT OR REPLACE INTO metadata (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, json.dumps(value), datetime.now().isoformat()))
        self.conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        """Get a metadata value."""
        row = self.conn.execute(
            'SELECT value FROM metadata WHERE key = ?', (key,)
        ).fetchone()
        if row:
            return json.loads(row['value'])
        return default

    # === Statistics ===

    def stats(self) -> Dict:
        """Get scraping statistics."""
        total_queued = self.conn.execute('SELECT COUNT(*) FROM queue').fetchone()[0]
        total_complete = self.conn.execute('SELECT COUNT(*) FROM completed').fetchone()[0]
        successful = self.conn.execute(
            'SELECT COUNT(*) FROM completed WHERE status = ?', ("success",)
        ).fetchone()[0]
        failed = self.conn.execute(
            'SELECT COUNT(*) FROM completed WHERE status = ?', ("failed",)
        ).fetchone()[0]
        pending = self.pending_count()

        return {
            "name": self.name,
            "total_queued": total_queued,
            "completed": total_complete,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "progress_pct": (total_complete / total_queued * 100) if total_queued > 0 else 0,
            "success_rate": (successful / total_complete * 100) if total_complete > 0 else 0
        }

    def export_completed(self, output_path: str):
        """Export all completed data to JSON."""
        cursor = self.conn.execute('''
            SELECT url, status, completed_at, data
            FROM completed
            WHERE status = 'success' AND data IS NOT NULL
        ''')

        with open(output_path, 'w') as f:
            for row in cursor:
                record = {
                    "url": row['url'],
                    "completed_at": row['completed_at'],
                    "data": json.loads(row['data']) if row['data'] else None
                }
                f.write(json.dumps(record) + '\n')


@contextmanager
def checkpoint(name: str, db_dir: str = "data/scraping_state"):
    """Context manager for checkpoint operations."""
    cp = CheckpointManager(name, db_dir)
    try:
        yield cp
    finally:
        cp.close()


if __name__ == "__main__":
    # Self-test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        with CheckpointManager("test", db_dir=tmpdir) as cp:
            # Add URLs
            cp.add_to_queue(["http://a.com", "http://b.com", "http://c.com"])
            print(f"Initial stats: {cp.stats()}")

            # Process some
            for i, url in enumerate(cp.pending_urls()):
                if i >= 2:
                    break
                cp.mark_complete(url, data={"content": f"data_{i}"})

            print(f"After processing: {cp.stats()}")

            # Check pending
            pending = list(cp.pending_urls())
            print(f"Pending URLs: {pending}")
