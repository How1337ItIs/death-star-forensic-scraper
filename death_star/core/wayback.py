"""
Wayback Machine Integration
===========================

Integration with the Internet Archive's Wayback Machine.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("death_star.wayback")


@dataclass
class Snapshot:
    """A Wayback Machine snapshot."""
    url: str
    timestamp: str
    datetime: datetime
    status_code: int
    wayback_url: str


@dataclass
class SnapshotContent:
    """Content from a snapshot."""
    url: str
    timestamp: str
    html: str
    status_code: int


class WaybackMachine:
    """
    Wayback Machine client for historical web capture.
    
    Usage:
        wayback = WaybackMachine()
        
        # Get snapshots
        snapshots = await wayback.get_snapshots("https://example.com")
        
        # Fetch historical version
        content = await wayback.fetch_snapshot("https://example.com", "20200101")
        
        # Submit for archival
        await wayback.save_url("https://example.com")
    """
    
    CDX_API = "https://web.archive.org/cdx/search/cdx"
    SAVE_API = "https://web.archive.org/save"
    WAYBACK_BASE = "https://web.archive.org/web"
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/wayback")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_snapshots(
        self,
        url: str,
        from_date: str = None,
        to_date: str = None,
        limit: int = 100,
    ) -> List[Snapshot]:
        """
        Get list of available snapshots for a URL.
        
        Args:
            url: URL to check
            from_date: Start date (YYYYMMDD)
            to_date: End date (YYYYMMDD)
            limit: Maximum snapshots
        
        Returns:
            List of Snapshot objects
        """
        try:
            import httpx
        except ImportError:
            logger.error("httpx required for Wayback integration")
            return []
        
        params = {
            "url": url,
            "output": "json",
            "limit": limit,
            "collapse": "timestamp:8",
        }
        
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.CDX_API, params=params, timeout=30)
                data = response.json()
            
            if not data or len(data) < 2:
                return []
            
            snapshots = []
            for row in data[1:]:
                if len(row) < 5:
                    continue
                
                timestamp = row[1]
                snapshots.append(Snapshot(
                    url=row[2],
                    timestamp=timestamp,
                    datetime=datetime.strptime(timestamp, "%Y%m%d%H%M%S"),
                    status_code=int(row[4]) if row[4].isdigit() else 0,
                    wayback_url=f"{self.WAYBACK_BASE}/{timestamp}/{row[2]}",
                ))
            
            return snapshots
            
        except Exception as e:
            logger.error(f"Failed to get snapshots: {e}")
            return []
    
    async def fetch_snapshot(
        self,
        url: str,
        timestamp: str = None,
    ) -> Optional[SnapshotContent]:
        """
        Fetch content from a specific snapshot.
        
        Args:
            url: Original URL
            timestamp: Snapshot timestamp (YYYYMMDD)
        
        Returns:
            SnapshotContent or None
        """
        try:
            import httpx
        except ImportError:
            return None
        
        if not timestamp:
            timestamp = datetime.now().strftime("%Y%m%d")
        
        wayback_url = f"{self.WAYBACK_BASE}/{timestamp}id_/{url}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    wayback_url,
                    timeout=30,
                    follow_redirects=True,
                )
            
            if response.status_code != 200:
                return None
            
            return SnapshotContent(
                url=url,
                timestamp=timestamp,
                html=response.text,
                status_code=response.status_code,
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch snapshot: {e}")
            return None
    
    async def save_url(self, url: str) -> Optional[str]:
        """
        Submit URL to Wayback Machine for archival.
        
        Args:
            url: URL to archive
        
        Returns:
            Wayback URL of saved page
        """
        try:
            import httpx
        except ImportError:
            return None
        
        save_url = f"{self.SAVE_API}/{url}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    save_url,
                    headers={"User-Agent": "DeathStarScraper/2.0"},
                    timeout=60,
                    follow_redirects=True,
                )
            
            if response.status_code == 200:
                return str(response.url)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to save URL: {e}")
            return None
    
    async def get_timeline(self, url: str, years: int = 10) -> List[Dict]:
        """
        Get timeline of snapshots for a URL.
        
        Args:
            url: URL to get timeline for
            years: How many years back
        
        Returns:
            List of yearly snapshot summaries
        """
        from_date = str(datetime.now().year - years) + "0101"
        
        snapshots = await self.get_snapshots(url, from_date=from_date)
        
        if not snapshots:
            return []
        
        # Group by year
        timeline = {}
        for snap in snapshots:
            year = snap.datetime.year
            if year not in timeline:
                timeline[year] = {
                    "year": year,
                    "snapshots": 0,
                    "sample_url": snap.wayback_url,
                }
            timeline[year]["snapshots"] += 1
        
        return sorted(timeline.values(), key=lambda x: x["year"])
    
    async def find_deleted_content(self, url: str) -> Optional[SnapshotContent]:
        """
        Find archived version of potentially deleted content.
        
        Args:
            url: URL to find
        
        Returns:
            SnapshotContent if found
        """
        snapshots = await self.get_snapshots(url, limit=1)
        
        if snapshots:
            return await self.fetch_snapshot(url, snapshots[0].timestamp)
        
        return None
    
    def save_snapshots_index(self, url: str, snapshots: List[Snapshot], domain: str):
        """Save snapshot index to disk."""
        output_dir = self.output_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "url": url,
            "retrieved_at": datetime.now().isoformat(),
            "snapshot_count": len(snapshots),
            "snapshots": [
                {
                    "timestamp": s.timestamp,
                    "datetime": s.datetime.isoformat(),
                    "wayback_url": s.wayback_url,
                }
                for s in snapshots
            ],
        }
        
        with open(output_dir / "wayback_index.json", "w") as f:
            json.dump(data, f, indent=2)
