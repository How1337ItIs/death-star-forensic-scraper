# Wayback Machine Scraping Research

**Author:** HUNTER (V17 Research)
**Date:** 2026-01-08
**Status:** COMPLETE
**Supports:** BILLY's Terrapin Nation acquisition task

## Executive Summary

This document provides patterns and tools for scraping archived websites from the Wayback Machine when the live site is unreachable. Specifically supports BILLY's V17-P0-BILLY task: "Terrapin Nation scrape via Wayback Machine (live site unreachable)."

**RECOMMENDATION:** Use `pywaybackup` for bulk downloading, combined with CDX API queries for inventory and verification.

---

## Tools Comparison

| Tool | Best For | Installation | Notes |
|------|----------|--------------|-------|
| **pywaybackup** | Bulk download entire sites | `pip install pywaybackup` | Resume support, parallel downloads |
| **waybackpy** | API queries, single pages | `pip install waybackpy` | Good for checking availability |
| **CDX API direct** | Inventory, filtering | HTTP requests | Best for planning before download |
| **wget** | Simple mirroring | Built-in | No resume, rate limiting needed |

---

## Recommended Workflow for Terrapin Nation

### Step 1: Inventory Available Snapshots

Use CDX API to discover what's archived:

```bash
# Get all Terrapin Nation snapshots
curl "http://web.archive.org/cdx/search/cdx?url=terrapinnation.com/*&output=json&fl=timestamp,original,statuscode&collapse=urlkey" > terrapin_inventory.json
```

**Python version:**
```python
import httpx
import json

def get_wayback_inventory(domain: str) -> list:
    """Get all archived URLs for a domain."""
    url = "http://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "collapse": "urlkey",  # Dedupe by URL
        "filter": "statuscode:200"  # Only successful captures
    }

    response = httpx.get(url, params=params, timeout=60)
    data = response.json()

    # First row is headers
    headers = data[0]
    records = [dict(zip(headers, row)) for row in data[1:]]

    return records

# Usage
inventory = get_wayback_inventory("terrapinnation.com")
print(f"Found {len(inventory)} archived pages")
```

### Step 2: Bulk Download with pywaybackup

**Installation:**
```bash
pip install pywaybackup
```

**Download entire site (latest versions):**
```bash
waybackup -u https://terrapinnation.com -a \
    --workers 5 \
    --delay 1 \
    --retry 3 \
    --output data/raw/terrapin_nation/ \
    --keep
```

**Download specific date range:**
```bash
# Get snapshots from 2005-2015 (prime Terrapin era)
waybackup -u https://terrapinnation.com -a \
    --start 20050101000000 \
    --end 20151231235959 \
    --workers 5 \
    --output data/raw/terrapin_nation/
```

**Download only HTML (skip images/CSS):**
```bash
waybackup -u https://terrapinnation.com -a \
    --filetype html,htm \
    --statuscode 200 \
    --workers 5 \
    --output data/raw/terrapin_nation/
```

### Step 3: Verify Download Completeness

```python
import os
from pathlib import Path

def verify_wayback_download(download_dir: Path, inventory: list) -> dict:
    """Compare downloaded files against inventory."""
    downloaded = set()
    for root, dirs, files in os.walk(download_dir):
        for f in files:
            downloaded.add(f)

    expected = len(inventory)
    actual = len(downloaded)
    missing = expected - actual

    return {
        "expected": expected,
        "downloaded": actual,
        "missing": missing,
        "completeness": (actual / expected * 100) if expected > 0 else 0
    }
```

---

## CDX API Reference

### Base URL
```
http://web.archive.org/cdx/search/cdx
```

### Key Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `url` | Target URL/domain | `terrapinnation.com/*` |
| `output` | Response format | `json` (or `text`) |
| `fl` | Fields to return | `timestamp,original,statuscode` |
| `from`/`to` | Date range | `20050101`-`20151231` |
| `collapse` | Dedupe results | `urlkey` (by URL) |
| `filter` | Filter results | `statuscode:200` |
| `limit` | Max results | `1000` |

### Field Names

Available CDX fields:
- `urlkey` - Canonicalized URL key
- `timestamp` - Capture timestamp (YYYYMMDDhhmmss)
- `original` - Original URL
- `mimetype` - Content type
- `statuscode` - HTTP status
- `digest` - Content hash
- `length` - File size

### Pagination for Large Sites

For sites with >10,000 pages, use pagination:

```python
def paginated_cdx_query(domain: str, page_size: int = 5000):
    """Paginated CDX query for large sites."""
    page = 0
    all_records = []

    while True:
        params = {
            "url": f"{domain}/*",
            "output": "json",
            "limit": page_size,
            "page": page,
            "filter": "statuscode:200"
        }

        response = httpx.get(CDX_URL, params=params, timeout=60)
        data = response.json()

        if len(data) <= 1:  # Only headers or empty
            break

        records = data[1:] if page == 0 else data  # Skip headers on first page
        all_records.extend(records)
        page += 1

        print(f"Page {page}: {len(records)} records")

    return all_records
```

---

## Rate Limiting & Best Practices

### Archive.org Guidelines

1. **Concurrency:** Keep parallel requests low (~5-10)
2. **Delay:** 1-2 seconds between requests
3. **Retry:** Handle 429 (rate limit) and 5xx errors with backoff
4. **Cache:** Don't re-request the same URLs

### Python Rate Limiter

```python
import time
import random
from functools import wraps

def rate_limited(max_per_second: float = 2.0):
    """Decorator for rate limiting."""
    min_interval = 1.0 / max_per_second

    def decorator(func):
        last_called = [0.0]

        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            wait_time = min_interval - elapsed + random.uniform(0, 0.5)
            if wait_time > 0:
                time.sleep(wait_time)
            last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapper
    return decorator

@rate_limited(max_per_second=2.0)
def fetch_archived_page(url: str, timestamp: str) -> bytes:
    """Fetch a single archived page with rate limiting."""
    wayback_url = f"http://web.archive.org/web/{timestamp}/{url}"
    response = httpx.get(wayback_url, timeout=30)
    return response.content
```

---

## Terrapin Nation Specific Recommendations

### Expected Content

Based on domain name, Terrapin Nation likely contains:
- Forum threads (discussion boards)
- Show reviews
- Song annotations
- Community content
- Possibly image galleries

### Download Strategy

1. **First pass:** Download HTML only (faster, smaller)
2. **Inventory:** Count unique threads/pages
3. **Second pass:** Download images if needed
4. **Extraction:** Use same patterns as RuKind (HEALY's task)

### Estimated Size

For a medium-sized Dead forum:
- 5,000-20,000 pages estimated
- ~500MB-2GB raw HTML
- 1-4 hours download time with rate limiting

---

## Integration with Content Tracking

After download, register with content tracking:

```python
from scripts.utilities.content_tracker import ContentTracker

tracker = ContentTracker()

# Register acquisition
tracker.register_source(
    source_id="terrapin_nation_wayback",
    source_type="forum",
    file_count=len(downloaded_files),
    metadata={
        "method": "wayback_machine",
        "date_range": "2005-2015",
        "tool": "pywaybackup"
    }
)
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| 429 Rate Limit | Reduce workers, increase delay |
| Incomplete download | Use `--keep` flag, resume same command |
| Missing pages | Some pages not archived; check CDX inventory first |
| Windows path length | Use WSL (Linux recommended) |
| Encoding errors | Use `--encoding utf-8` flag |

### Resume Interrupted Downloads

`pywaybackup` automatically resumes when run with same parameters:

```bash
# Same command resumes from where it left off
waybackup -u https://terrapinnation.com -a --workers 5 --output data/raw/terrapin_nation/
```

---

## References

- [Wayback Machine CDX API](https://archive.org/developers/wayback-cdx-server.html)
- [pywaybackup GitHub](https://github.com/bitdruid/python-wayback-machine-downloader)
- [waybackpy PyPI](https://pypi.org/project/waybackpy/)
- [Internet Archive API Help](https://archive.org/help/wayback_api.php)

---

*Research by HUNTER - V17 Phase 0*
