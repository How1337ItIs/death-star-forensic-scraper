# Death Star Scraper Research Findings

**Date:** 2026-01-05  
**Source:** deadhead-llm repository analysis  
**Status:** ✅ COMPLETE

## Key Discovery: `death_star.py`

**Location:** `deadhead-llm/scripts/scraping/core/death_star.py`

### Architecture

The Death Star scraper is a **multi-tool orchestrator** that combines:

1. **wget** - Deep recursive download with all assets
2. **ArchiveBox** - Full archival (HTML, PDF, screenshot, WARC, media)
3. **Crawl4AI** - LLM-ready structured extraction
4. **Playwright** - JavaScript rendering (mentioned but not fully implemented)

### Key Patterns from `death_star.py`

#### 1. Multi-Tool Approach
```python
def destroy(self, url, depth=5, quick=False, full=False):
    # Always fire wget (fast, reliable)
    wget_result = self.wget_recursive(url, depth)
    
    if not quick:
        # Fire ArchiveBox (comprehensive)
        ab_result = self.archivebox_archive(url, min(depth, 3))
    
    if full:
        # Fire Crawl4AI (structured extraction)
        c4ai_result = self.crawl4ai_extract(url)
```

**Key Insight:** The "Death Star" philosophy is about using **multiple tools in combination**, not relying on a single approach.

#### 2. wget Configuration (Comprehensive)
```python
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
    "--user-agent", "DeadheadLLM-Research/1.0",
    "--directory-prefix", str(output_path),
    "--no-clobber",                   # Don't re-download existing
    "--timeout", "30",                # Timeout per request
    "--tries", "3",                   # Retry count
    url
]
```

**Key Flags:**
- `--page-requisites` - **CRITICAL**: Downloads ALL assets (CSS, JS, images)
- `--convert-links` - Makes offline viewing possible
- `--random-wait` - Avoids detection patterns
- `--no-clobber` - Resume capability

#### 3. ArchiveBox Integration
```python
def archivebox_archive(self, url, depth=3):
    # Initialize if needed
    init_cmd = ["archivebox", "init", "--setup"]
    
    # Add URL with depth
    add_cmd = [
        "archivebox", "add",
        url,
        f"--depth={depth}",
        "--parser=auto"
    ]
```

**What ArchiveBox Captures:**
- Full HTML with all assets
- PDF rendering of each page
- Screenshot (full page)
- WARC archive (web archive format)
- Media files (images, video, audio)
- Git repositories (if applicable)
- Single-page app content (via headless Chrome)

### Patterns NOT Found in death_star.py

The `death_star.py` file does **NOT** contain:
- ❌ Puppeteer-specific patterns
- ❌ `response.buffer()` usage
- ❌ Automatic asset downloading during network interception
- ❌ API response parsing for embedded URLs

**Why:** It's a Python tool orchestrator, not a Puppeteer scraper.

### Additional Research: Scraping Patterns Summary

**Location:** `deadhead-llm/docs/acquisition/SCRAPING_PATTERNS_SUMMARY.md`

#### Key Patterns Found:

1. **Session Management with Retry**
```python
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1.0,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)
```

2. **Resume Capability**
```python
def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'processed_ids': set(), 'last_index': 0}
```

3. **File Download with Validation**
```python
def download_file(url, output_path, min_size_kb=1.0):
    # Skip if exists
    if output_path.exists():
        return True
    
    # Check content type
    content_type = response.headers.get('content-type', '').lower()
    if 'text/html' in content_type:
        logger.warning(f"Got HTML instead of file: {url}")
        return False
    
    # Validate size
    size_kb = output_path.stat().st_size / 1024
    if size_kb < min_size_kb:
        logger.warning(f"File too small: {size_kb:.1f}KB")
        output_path.unlink()
        return False
```

### December 2025 Updates

**Location:** `deadhead-llm/docs/acquisition/WEB_SCRAPING_UPDATE_DECEMBER_2025.md`

#### Key Insights:

1. **Network Request Interception**
```python
# Monitor network for API calls
network = browser_network_requests()
for request in network:
    if request['method'] == 'GET' and 'api' in request['url']:
        # Intercept API calls - often faster than HTML parsing
        api_url = request['url']
        response = session.get(api_url)
        data = response.json()
```

2. **Hybrid Approach**
```python
# Step 1: Use browser to discover URLs
browser_navigate(url="https://example.com/search")
snapshot = browser_snapshot()
# Extract URLs from snapshot

# Step 2: Use requests for bulk extraction
for url in discovered_urls:
    response = session.get(url)  # Fast, no browser overhead
    soup = BeautifulSoup(response.content, 'html.parser')
```

## What We're Missing

### 1. Multi-Tool Orchestration
The death_star.py shows that a true "Death Star" scraper should:
- Use multiple tools in combination
- Not rely on a single approach
- Have fallback mechanisms

**For Our Puppeteer Scraper:**
- ✅ We're using Puppeteer (good for JS-heavy sites)
- ❌ We're NOT using wget as a fallback for static assets
- ❌ We're NOT using ArchiveBox for comprehensive archival
- ❌ We're NOT using Crawl4AI for structured extraction

### 2. wget Integration
The death_star.py shows wget with `--page-requisites` flag which automatically downloads ALL assets.

**For Our Puppeteer Scraper:**
- ✅ We're downloading assets via `response.buffer()` (good)
- ❌ We're NOT using wget as a parallel/fallback mechanism
- ❌ We could use wget for authenticated static assets after login

### 3. ArchiveBox Integration
ArchiveBox provides comprehensive archival that we're not using.

**Potential Enhancement:**
- After Puppeteer scrape, run ArchiveBox on discovered URLs
- ArchiveBox handles WARC, PDF, screenshots automatically
- Could be a post-processing step

## Recommendations

### Immediate Enhancements

1. **Add wget Fallback for Static Assets**
   - After Puppeteer discovers URLs, use wget with `--page-requisites` for authenticated static assets
   - wget can use cookies from Puppeteer session

2. **Add ArchiveBox Post-Processing**
   - After Puppeteer scrape, run ArchiveBox on key URLs
   - Provides WARC, PDF, screenshots automatically

3. **Add Crawl4AI for Structured Extraction**
   - Use Crawl4AI to extract structured data from scraped HTML
   - Provides LLM-ready markdown output

### Architecture Enhancement

**Current:** Single Puppeteer scraper with response interception

**Enhanced Death Star:**
```
1. Puppeteer (Primary)
   ├─ Network interception (current)
   ├─ Asset downloading (current)
   └─ API response parsing (current)

2. wget (Fallback/Parallel)
   ├─ Static asset downloading
   └─ Deep recursive crawl

3. ArchiveBox (Post-Processing)
   ├─ WARC archival
   ├─ PDF rendering
   └─ Screenshot capture

4. Crawl4AI (Structured Extraction)
   ├─ Markdown extraction
   └─ LLM-ready output
```

## Conclusion

The `death_star.py` file shows that a true "Death Star" scraper is about **orchestrating multiple tools**, not just using one tool comprehensively.

**Our Current Approach:**
- ✅ Comprehensive Puppeteer scraper with automatic asset downloading
- ✅ Network interception and API response parsing
- ✅ Authenticated session handling

**What We Could Add:**
- ⚠️ wget integration for static assets (parallel/fallback)
- ⚠️ ArchiveBox integration for comprehensive archival
- ⚠️ Crawl4AI integration for structured extraction

**Key Insight:** The "Death Star" philosophy is about **multiple tools working together**, not a single perfect tool.

---

*Research complete: 2026-01-05*
