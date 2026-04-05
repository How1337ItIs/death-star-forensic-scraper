# Death Star Scraping Toolkit - Setup & Usage Guide

## 🔫 Weapons Systems Status

| Tool | Status | Purpose |
|------|--------|---------|
| **wget** | ✅ ARMED (via WSL) | Recursive site download with all assets |
| **crawl4ai** | ✅ ARMED | LLM-ready structured extraction |
| **playwright** | ✅ ARMED | JavaScript rendering, screenshots |
| **archivebox** | ⚠️ PARTIAL | Full archival (HTML, PDF, WARC) |
| **beautifulsoup4** | ✅ ARMED | HTML parsing |
| **httpx** | ✅ ARMED | HTTP requests |

## 📦 Installation

### Quick Install (All Weapons)
```bash
# Python packages
pip install crawl4ai playwright beautifulsoup4 httpx archivebox scrapy

# Playwright browsers
python -m playwright install chromium

# wget is pre-installed in WSL
wsl which wget  # Should show /usr/bin/wget
```

### Full Install for Windows
```powershell
# Install WSL if not already
wsl --install

# Install Python packages
pip install crawl4ai playwright beautifulsoup4 httpx archivebox[all] scrapy

# Install Playwright browsers
python -m playwright install chromium

# Verify
python -c "from src.scraping.core.death_star import DeathStar; ds = DeathStar()"
```

## 🎯 Usage

### Method 1: Death Star CLI (Recommended)
```bash
# Full destruction (all tools)
python src/scraping/core/death_star.py --target https://target.com --full

# Quick mode (wget only)
python src/scraping/core/death_star.py --target https://target.com --quick

# Custom depth
python src/scraping/core/death_star.py --target https://target.com --depth 3

# Multiple targets
python src/scraping/core/death_star.py --targets urls.txt --full

# Help
python src/scraping/core/death_star.py --help
```

### Method 2: WSL wget Direct
```bash
# Recursive download with all assets
wsl wget --recursive --level=3 --page-requisites --convert-links \
    --adjust-extension --no-parent --wait=1 --random-wait \
    --limit-rate=1M --user-agent="Research/1.0" \
    --directory-prefix=/mnt/c/path/to/output \
    --no-clobber --timeout=30 --tries=3 \
    https://target.com/
```

### Method 3: Crawl4AI Python
```python
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

async def scrape():
    config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(screenshot=True, wait_until='domcontentloaded')
    
    async with AsyncWebCrawler(config=config) as crawler:
        result = await crawler.arun(url='https://target.com/', config=run_config)
        
        print(f'HTML: {len(result.html)} bytes')
        print(f'Markdown: {len(result.markdown)} bytes')
        print(f'Links: {result.links}')
        print(f'Media: {result.media}')

asyncio.run(scrape())
```

### Method 4: Browser Subagent (Antigravity)
Use the browser_subagent tool for interactive forensics:
- Screenshots
- JavaScript execution
- Console logs
- Network monitoring
- DevTools access

## 📂 Output Structure

```
data/forensics/<target>/
├── index.html          # Full HTML source
├── content.md          # Markdown extraction
├── screenshot.png      # Full page screenshot
├── links.json          # All extracted links
├── media.json          # All media assets
├── metadata.json       # Scrape metadata
├── evidence.json       # Red flag analysis
├── text_content.txt    # Plain text
└── wget/               # Recursive download (if used)
    └── target.com/
        ├── index.html
        ├── styles/
        └── scripts/
```

## 🔍 Forensic Analysis Features

### Content Extraction
- HTML source code
- Markdown conversion
- Plain text content
- All hyperlinks (internal/external)
- All media assets (images, video, audio)

### Technical Analysis
- HLS/streaming sources
- API endpoints
- WebSocket connections
- LocalStorage contents
- SessionStorage contents
- Cookies
- Console errors
- Network requests

### Red Flag Detection
- Solana addresses (pump.fun patterns)
- Cloudflare tunnels (temporary infrastructure)
- Fake claims (Amsterdam licensing, etc.)
- Static/looping video feeds
- Pre-recorded terminal logs

## 🛡️ Best Practices

### Respectful Scraping
- Use `--wait=1` for delays between requests
- Limit rate with `--limit-rate=1M`
- Include research contact in User-Agent
- Respect robots.txt (when appropriate)

### Evidence Preservation
- Save timestamps on all files
- Keep original HTML unmodified
- Screenshot key pages
- Archive network requests
- Document console errors

### Legal Considerations
- Only scrape publicly accessible content
- Document all scraping activities
- Comply with applicable laws
- Consider fair use for research

## 📋 Forensic Checklist

```
[ ] Main page HTML saved
[ ] Main page screenshot captured
[ ] All subpages scraped (if applicable)
[ ] All images/media downloaded
[ ] API endpoints tested
[ ] Console errors logged
[ ] Network requests documented
[ ] LocalStorage extracted
[ ] Social profiles archived
[ ] Token/blockchain data captured
[ ] Red flags documented
[ ] Final report written
```

## 🎯 Example: Forensic Site Analysis

```bash
# 1. Create evidence directory
mkdir -p data/forensics/target_site

# 2. Wget recursive download
wsl wget --recursive --level=2 --page-requisites \
    --directory-prefix=/mnt/c/Users/USER/project/data/forensics/target_site/wget \
    https://suspicious-site.com/

# 3. Crawl4AI extraction
python -c "
from crawl4ai import AsyncWebCrawler
# ... extraction code
"

# 4. Browser forensics (via Antigravity)
# Use browser_subagent for screenshots, DevTools, etc.

# 5. Generate report
# Compile findings into docs/forensics/target_analysis.md
```

---

*Death Star Toolkit - Sol Cannabis Research Division*
*"Leave no stone unturned"*
