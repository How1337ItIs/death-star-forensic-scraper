#!/usr/bin/env python3
"""
Wayback Machine Integration
===========================

Integration with the Internet Archive's Wayback Machine for
historical web capture and preservation.

Features:
---------
1. Fetch historical snapshots
2. Submit URLs for archival
3. Compare versions over time
4. Timeline reconstruction
5. Bulk historical retrieval

Usage:
------
    from wayback_integration import WaybackMachine
    
    wayback = WaybackMachine()
    
    # Get available snapshots
    snapshots = await wayback.get_snapshots("https://example.com")
    
    # Fetch specific snapshot
    content = await wayback.fetch_snapshot("https://example.com", "20200101")
    
    # Submit for archival
    await wayback.save_url("https://example.com")
"""

import argparse
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse
import sys

logger = logging.getLogger("wayback_integration")


def safe_path_component(value: str) -> str:
    """Make a string safe for cross-platform file and directory names."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


@dataclass
class Snapshot:
    """A Wayback Machine snapshot."""
    url: str
    timestamp: str  # YYYYMMDDhhmmss format
    datetime: datetime
    status_code: int
    mime_type: str
    wayback_url: str
    digest: str  # Content hash


@dataclass
class SnapshotContent:
    """Content from a snapshot."""
    url: str
    timestamp: str
    html: str
    headers: Dict[str, str]
    status_code: int


@dataclass
class VersionDiff:
    """Difference between two snapshots."""
    url: str
    timestamp_old: str
    timestamp_new: str
    changes_detected: bool
    added_lines: int
    removed_lines: int
    diff_summary: str


class WaybackMachine:
    """
    Wayback Machine client for historical web capture.
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
        from_date: str = None,  # YYYYMMDD
        to_date: str = None,
        limit: int = 1000,
        collapse: str = "timestamp:8",  # One per day
        retries: int = 3
    ) -> List[Snapshot]:
        """
        Get list of available snapshots for a URL.
        
        Args:
            url: URL to check
            from_date: Start date (YYYYMMDD)
            to_date: End date (YYYYMMDD)
            limit: Maximum snapshots to return
            collapse: Collapse similar timestamps (e.g., "timestamp:8" = daily)
            retries: Number of retry attempts for transient failures
        
        Returns:
            List of Snapshot objects
        """
        try:
            import httpx
        except ImportError:
            import requests as httpx
        
        params = {
            "url": url,
            "output": "json",
            "limit": limit,
            "collapse": collapse,
        }
        
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        
        last_error = None
        for attempt in range(retries):
            try:
                if hasattr(httpx, 'AsyncClient'):
                    async with httpx.AsyncClient() as client:
                        response = await client.get(self.CDX_API, params=params, timeout=30)
                        data = response.json()
                else:
                    response = httpx.get(self.CDX_API, params=params, timeout=30)
                    data = response.json()
                
                if not data:
                    return []
                
                # First row is headers
                headers = data[0] if data else []
                snapshots = []
                
                for row in data[1:]:
                    if len(row) < 7:
                        continue
                    
                    timestamp = row[1]
                    
                    snapshots.append(Snapshot(
                        url=row[2],
                        timestamp=timestamp,
                        datetime=datetime.strptime(timestamp, "%Y%m%d%H%M%S"),
                        status_code=int(row[4]) if row[4].isdigit() else 0,
                        mime_type=row[3],
                        wayback_url=f"{self.WAYBACK_BASE}/{timestamp}/{row[2]}",
                        digest=row[5]
                    ))
                
                return snapshots
                
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    backoff = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"CDX API attempt {attempt+1}/{retries} failed: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Failed to get snapshots for {url} after {retries} attempts: {last_error}")
        
        return []
    
    async def fetch_snapshot(
        self,
        url: str,
        timestamp: str = None  # YYYYMMDD or YYYYMMDDhhmmss
    ) -> Optional[SnapshotContent]:
        """
        Fetch content from a specific snapshot.
        
        Args:
            url: Original URL
            timestamp: Snapshot timestamp (default: most recent)
        
        Returns:
            SnapshotContent or None
        """
        try:
            import httpx
        except ImportError:
            import requests as httpx
        
        # If no timestamp, get most recent
        if not timestamp:
            timestamp = datetime.now().strftime("%Y%m%d")
        
        wayback_url = f"{self.WAYBACK_BASE}/{timestamp}id_/{url}"
        
        try:
            if hasattr(httpx, 'AsyncClient'):
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        wayback_url,
                        timeout=30,
                        follow_redirects=True
                    )
            else:
                response = httpx.get(wayback_url, timeout=30, allow_redirects=True)
            
            if response.status_code != 200:
                logger.debug(f"Snapshot not found: {wayback_url}")
                return None
            
            return SnapshotContent(
                url=url,
                timestamp=timestamp,
                html=response.text,
                headers=dict(response.headers),
                status_code=response.status_code
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch snapshot: {e}")
            return None
    
    async def save_url(self, url: str, capture_all: bool = False) -> Optional[str]:
        """
        Submit URL to Wayback Machine for archival.
        
        Args:
            url: URL to archive
            capture_all: Capture outlinks and embedded resources
        
        Returns:
            Wayback URL of saved page or None
        """
        try:
            import httpx
        except ImportError:
            import requests as httpx
        
        save_url = f"{self.SAVE_API}/{url}"
        
        headers = {
            "User-Agent": "DeadheadLLM-Archiver/2.0"
        }
        
        if capture_all:
            headers["Capture-All"] = "on"
        
        try:
            if hasattr(httpx, 'AsyncClient'):
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        save_url,
                        headers=headers,
                        timeout=60,
                        follow_redirects=True
                    )
            else:
                response = httpx.get(
                    save_url,
                    headers=headers,
                    timeout=60,
                    allow_redirects=True
                )
            
            if response.status_code == 200:
                # Extract the archived URL from response or headers
                content_location = response.headers.get('Content-Location', '')
                if content_location:
                    return f"https://web.archive.org{content_location}"
                if hasattr(response, 'url'):
                    resp_url = response.url
                    return str(resp_url) if resp_url is not None else save_url
                return save_url
            
            logger.warning(f"Failed to save URL: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to save URL to Wayback: {e}")
            return None
    
    async def compare_snapshots(
        self,
        url: str,
        timestamp1: str,
        timestamp2: str
    ) -> Optional[VersionDiff]:
        """
        Compare two snapshots of the same URL.
        
        Args:
            url: URL to compare
            timestamp1: Earlier snapshot
            timestamp2: Later snapshot
        
        Returns:
            VersionDiff with comparison results
        """
        # Fetch both snapshots
        content1 = await self.fetch_snapshot(url, timestamp1)
        content2 = await self.fetch_snapshot(url, timestamp2)
        
        if not content1 or not content2:
            return None
        
        # Simple line-based diff
        lines1 = set(content1.html.splitlines())
        lines2 = set(content2.html.splitlines())
        
        added = lines2 - lines1
        removed = lines1 - lines2
        
        return VersionDiff(
            url=url,
            timestamp_old=timestamp1,
            timestamp_new=timestamp2,
            changes_detected=len(added) > 0 or len(removed) > 0,
            added_lines=len(added),
            removed_lines=len(removed),
            diff_summary=f"+{len(added)} / -{len(removed)} lines"
        )
    
    async def get_timeline(
        self,
        url: str,
        years: int = 10
    ) -> List[Dict]:
        """
        Get a timeline of snapshots for a URL.
        
        Args:
            url: URL to get timeline for
            years: How many years back to look
        
        Returns:
            List of yearly snapshot summaries
        """
        from_date = str(datetime.now().year - years) + "0101"
        
        snapshots = await self.get_snapshots(
            url,
            from_date=from_date,
            collapse="timestamp:6"  # Monthly
        )
        
        if not snapshots:
            return []
        
        # Group by year
        timeline = {}
        for snap in snapshots:
            year = snap.datetime.year
            if year not in timeline:
                timeline[year] = {
                    'year': year,
                    'snapshots': 0,
                    'first': snap.datetime.isoformat(),
                    'last': snap.datetime.isoformat(),
                    'sample_url': snap.wayback_url
                }
            timeline[year]['snapshots'] += 1
            timeline[year]['last'] = snap.datetime.isoformat()
        
        return sorted(timeline.values(), key=lambda x: x['year'])
    
    async def bulk_fetch_history(
        self,
        url: str,
        interval: str = "yearly",  # yearly, monthly, weekly
        output_dir: Path = None
    ) -> List[Path]:
        """
        Fetch multiple historical versions of a URL.
        
        Args:
            url: URL to fetch history for
            interval: How often to sample (yearly, monthly, weekly)
            output_dir: Directory to save snapshots
        
        Returns:
            List of paths to saved snapshots
        """
        output_dir = output_dir or self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Map interval to collapse parameter
        collapse_map = {
            'yearly': 'timestamp:4',
            'monthly': 'timestamp:6',
            'weekly': 'timestamp:8',
            'daily': 'timestamp:8',
        }
        
        snapshots = await self.get_snapshots(
            url,
            collapse=collapse_map.get(interval, 'timestamp:6')
        )
        
        saved_files = []
        
        for snap in snapshots[:50]:  # Limit to 50 snapshots
            content = await self.fetch_snapshot(url, snap.timestamp)
            
            if content:
                filename = f"{snap.timestamp}.html"
                filepath = output_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content.html)
                
                saved_files.append(filepath)
                logger.debug(f"Saved snapshot: {filepath}")
            
            # Rate limit
            await asyncio.sleep(1)
        
        return saved_files
    
    async def find_deleted_content(
        self,
        url: str
    ) -> Optional[SnapshotContent]:
        """
        Find the most recent snapshot of a URL that may now be deleted.
        
        Args:
            url: URL to find archived version of
        
        Returns:
            SnapshotContent if found
        """
        snapshots = await self.get_snapshots(url, limit=1)
        
        if snapshots:
            return await self.fetch_snapshot(url, snapshots[0].timestamp)
        
        return None
    
    def save_snapshots_index(
        self,
        url: str,
        snapshots: List[Snapshot],
        domain: str
    ):
        """Save snapshot index to disk."""
        output_dir = self.output_dir / safe_path_component(domain)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            'url': url,
            'retrieved_at': datetime.now().isoformat(),
            'snapshot_count': len(snapshots),
            'snapshots': [
                {
                    'timestamp': s.timestamp,
                    'datetime': s.datetime.isoformat(),
                    'status_code': s.status_code,
                    'mime_type': s.mime_type,
                    'wayback_url': s.wayback_url,
                    'digest': s.digest
                }
                for s in snapshots
            ]
        }
        
        with open(output_dir / 'wayback_index.json', 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Wayback index saved to: {output_dir}")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def get_archived_version(url: str) -> Optional[str]:
    """
    Get the most recent archived version of a URL.
    
    Returns HTML content or None.
    """
    wayback = WaybackMachine()
    content = await wayback.find_deleted_content(url)
    return content.html if content else None


async def archive_url_now(url: str) -> Optional[str]:
    """
    Archive a URL to the Wayback Machine right now.
    
    Returns the Wayback URL.
    """
    wayback = WaybackMachine()
    return await wayback.save_url(url, capture_all=True)


async def get_url_history(url: str, years: int = 10) -> List[Dict]:
    """
    Get timeline of a URL's history.
    """
    wayback = WaybackMachine()
    return await wayback.get_timeline(url, years)


if __name__ == "__main__":
    def _is_http_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    parser = argparse.ArgumentParser(
        description="Query or submit URLs to the Wayback Machine."
    )
    parser.add_argument("url", help="Target URL (must include http:// or https://)")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["snapshots", "timeline", "save", "fetch"],
        default="snapshots",
        help="Operation to run (default: snapshots)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data/wayback",
        help="Output directory (default: data/wayback)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=10,
        help="Years of history for timeline mode (default: 10)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Rows to print for snapshots mode (default: 10)",
    )
    parser.add_argument(
        "--timestamp",
        help="Timestamp for fetch mode (YYYYMMDD or YYYYMMDDhhmmss)",
    )
    args = parser.parse_args()

    if not _is_http_url(args.url):
        parser.error("url must include a valid http:// or https:// scheme")

    async def main():
        wayback = WaybackMachine(output_dir=Path(args.output))

        if args.command == "snapshots":
            snapshots = await wayback.get_snapshots(args.url)
            print(f"\nFound {len(snapshots)} snapshots for {args.url}")
            for snapshot in snapshots[: max(args.limit, 1)]:
                print(f"   {snapshot.datetime.strftime('%Y-%m-%d')}: {snapshot.wayback_url}")

        elif args.command == "timeline":
            timeline = await wayback.get_timeline(args.url, years=args.years)
            print(f"\nTimeline for {args.url}")
            for year_data in timeline:
                print(f"   {year_data['year']}: {year_data['snapshots']} snapshots")

        elif args.command == "save":
            result = await wayback.save_url(args.url)
            if result:
                print(f"Saved to: {result}")
            else:
                print("Failed to save")

        elif args.command == "fetch":
            if args.timestamp:
                content = await wayback.fetch_snapshot(args.url, timestamp=args.timestamp)
            else:
                content = await wayback.find_deleted_content(args.url)

            if content:
                print(f"Found content from {content.timestamp}")
                print(content.html[:500])
            else:
                print("No archived content found")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
