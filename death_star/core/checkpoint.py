"""
Checkpoint Manager
==================

SQLite-based checkpoint system for crash-proof scraping.
Supports resume from any point after interruption.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class Checkpoint:
    """
    SQLite-based checkpoint for crash-proof scraping.
    
    Tracks:
    - URLs queued, completed, failed
    - Content hashes for deduplication
    - Session metadata
    
    Usage:
        checkpoint = Checkpoint("my_scrape")
        checkpoint.add_url("https://example.com", depth=0)
        
        for item in checkpoint.get_pending():
            # scrape...
            checkpoint.mark_complete(item["url"], "http", content_hash)
    """
    
    def __init__(self, name: str, db_dir: str = "data/scraping_state"):
        self.name = name
        self.db_path = Path(db_dir) / f"{name}.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                depth INTEGER DEFAULT 0,
                method TEXT,
                content_hash TEXT,
                error TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS content_hashes (
                hash TEXT PRIMARY KEY,
                url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status);
            CREATE INDEX IF NOT EXISTS idx_urls_depth ON urls(depth);
        """)
        self.conn.commit()
    
    def add_url(self, url: str, depth: int = 0) -> bool:
        """Add URL to queue if not already present."""
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO urls (url, depth) VALUES (?, ?)",
                (url, depth)
            )
            self.conn.commit()
            return True
        except Exception:
            return False
    
    def get_pending(self, limit: int = 10) -> List[Dict]:
        """Get pending URLs to scrape."""
        cursor = self.conn.execute(
            "SELECT url, depth FROM urls WHERE status = 'pending' ORDER BY depth, added_at LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def mark_complete(self, url: str, method: str, content_hash: str):
        """Mark URL as completed."""
        self.conn.execute(
            """UPDATE urls SET status = 'complete', method = ?, content_hash = ?, 
               completed_at = ? WHERE url = ?""",
            (method, content_hash, datetime.now().isoformat(), url)
        )
        self.conn.commit()
    
    def mark_failed(self, url: str, error: str):
        """Mark URL as failed."""
        self.conn.execute(
            "UPDATE urls SET status = 'failed', error = ?, completed_at = ? WHERE url = ?",
            (error, datetime.now().isoformat(), url)
        )
        self.conn.commit()
    
    def add_content_hash(self, content_hash: str, url: str):
        """Add content hash for deduplication."""
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO content_hashes (hash, url) VALUES (?, ?)",
                (content_hash, url)
            )
            self.conn.commit()
        except Exception:
            pass
    
    def is_duplicate_content(self, content_hash: str) -> bool:
        """Check if content has been seen before."""
        cursor = self.conn.execute(
            "SELECT 1 FROM content_hashes WHERE hash = ?",
            (content_hash,)
        )
        return cursor.fetchone() is not None
    
    def stats(self) -> Dict[str, int]:
        """Get checkpoint statistics."""
        stats = {}
        
        cursor = self.conn.execute(
            "SELECT status, COUNT(*) as count FROM urls GROUP BY status"
        )
        for row in cursor.fetchall():
            stats[row["status"]] = row["count"]
        
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM content_hashes")
        stats["unique_content"] = cursor.fetchone()["count"]
        
        return stats
    
    def clear(self):
        """Clear all checkpoint data."""
        self.conn.execute("DELETE FROM urls")
        self.conn.execute("DELETE FROM content_hashes")
        self.conn.commit()
    
    def set_metadata(self, key: str, value: str):
        """Set metadata value."""
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value."""
        cursor = self.conn.execute(
            "SELECT value FROM metadata WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        return row["value"] if row else None
    
    def close(self):
        """Close database connection."""
        self.conn.close()
