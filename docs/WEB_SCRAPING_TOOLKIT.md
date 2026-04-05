# Web Scraping Toolkit for SOL-CANNABIS
=======================================

**Created:** 2026-01-12
**Status:** OPERATIONAL
**Purpose:** Comprehensive guide to web scraping tools adapted for cannabis research

---

## Quick Reference - Tool Selection

| Need | Tool | Command |
|------|------|---------|
| **Archive entire site** | ArchiveBox | `archivebox add URL --depth=5` |
| **Fast recursive download** | wget | `wget -r -l5 -p -k URL` |
| **LLM-ready extraction** | Crawl4AI | `crawler.run(url=URL)` |
| **JavaScript-heavy sites** | Playwright/Crawlee | See examples below |
| **Forums (vBulletin/phpBB)** | forumscraper | `forumscraper URL` |
| **Reddit historical** | Arctic Shift | API access |
| **Wayback archives** | wayback-machine-downloader | `wayback_machine_downloader URL` |

---

## Tier 1: Death Star Tools (Comprehensive)

### 1. ArchiveBox ⭐ RECOMMENDED
**Stars:** 22K+ | **Type:** Self-hosted archiving platform

The closest thing to "point and shoot, get everything."

**What it saves:**
- Full HTML with all assets
- PDF rendering of each page
- Screenshot (full page)
- WARC archive (web archive format)
- Media files (images, video, audio)
- Single-page app content (via headless Chrome)

**Installation:**
```bash
pip install archivebox
mkdir ~/archivebox && cd ~/archivebox
archivebox init --setup
```

**Usage:**
```bash
# Single URL with depth
archivebox add "https://example.com" --depth=5

# Multiple URLs from file
archivebox add --input-file urls.txt

# With custom output directory
archivebox add "https://example.com" --output-dir ./data/scraped_sites
```

### 2. Death Star Scraper ⭐⭐⭐ OUR TOOL
**Type:** Multi-tool comprehensive scraper

Combines ArchiveBox, Crawl4AI, wget, and Playwright for maximum coverage.

**Features:**
- **ArchiveBox**: Full site archival (HTML, PDF, screenshots, WARC)
- **Crawl4AI**: LLM-ready structured extraction
- **wget**: Fast recursive download with asset preservation
- **Playwright**: JavaScript rendering for dynamic content

**Installation:**
```bash
pip install archivebox crawl4ai scrapy playwright
playwright install chromium
```

**Usage:**
```bash
# Full site destruction (all tools)
python src/scraping/core/death_star.py --target https://example.com --full

# Quick mode (wget only, fast)
python src/scraping/core/death_star.py --target https://example.com --quick

# Multiple sites from file
python src/scraping/core/death_star.py --targets urls.txt --full --depth 5
```

---

## Tier 2: Specialized Tools

### Crawl4AI
**Stars:** 15K+ | **Type:** LLM-first web scraper

Returns clean markdown and structured data perfect for AI processing.

**Installation:**
```bash
pip install crawl4ai
crawl4ai-setup
```

**Usage:**
```python
from crawl4ai import WebCrawler

crawler = WebCrawler()
crawler.warmup()

result = crawler.run(url="https://example.com")
print(result.markdown)  # Clean markdown
print(result.links)     # Extracted links
```

### wget
**Type:** Classic recursive downloader

Battle-tested, reliable, fast. Gets everything including all assets.

**Usage:**
```bash
# Basic recursive download
wget --recursive --level=5 --page-requisites --convert-links URL

# Polite scraping with delays
wget -r -l5 -p -k --wait=1 --random-wait --limit-rate=1M URL

# Cannabis research example
wget -r -l3 -p -k --user-agent="SOL-CANNABIS-Research/1.0" \
     --directory-prefix=data/scraped_sites/ https://example-cannabis-site.com
```

---

## Directory Structure

```
src/scraping/
├── __init__.py              # Main scraping module
└── core/
    ├── __init__.py          # Core components
    ├── death_star.py        # Main Death Star scraper ⭐
    ├── base_scraper.py      # Abstract base class
    └── checkpoint.py        # State management

data/scraped_sites/          # Output directory
├── archivebox/             # ArchiveBox archives
├── crawl4ai/              # Structured extractions
└── wget/                  # Raw downloads
```

---

## Death Star Usage Examples

### Basic Usage
```bash
# Single site, full destruction
python src/scraping/core/death_star.py --target https://cannabis-research-site.com --full

# Quick mode for fast results
python src/scraping/core/death_star.py --target https://news-site.com --quick

# Multiple targets
echo -e "https://site1.com\nhttps://site2.com" > targets.txt
python src/scraping/core/death_star.py --targets targets.txt --depth 3
```

### Advanced Usage
```bash
# Custom output directory
python src/scraping/core/death_star.py --target https://example.com --full --output data/cannabis_research

# Show installation instructions
python src/scraping/core/death_star.py --install
```

---

## Installation Checklist

```bash
# Core tools
pip install archivebox crawl4ai scrapy playwright
playwright install chromium

# Forum tools
git clone https://github.com/TUVIMEN/forumscraper

# Reddit
pip install arctic-shift

# Wayback
pip install wayback-machine-downloader

# Media
pip install yt-dlp gallery-dl

# Process management
pip install supervisor

# Verify installations
archivebox --version
crawl4ai --version
scrapy version
```

---

## Cannabis Research Use Cases

### Academic Papers & Research
```bash
# Scrape academic cannabis research
python src/scraping/core/death_star.py --target https://pubmed.ncbi.nlm.nih.gov --full --depth 2

# Medical cannabis studies
python src/scraping/core/death_star.py --target https://clinicaltrials.gov --targets cannabis_studies.txt
```

### News & Industry Updates
```bash
# Industry news sites
python src/scraping/core/death_star.py --targets cannabis_news_sites.txt --full

# Regulatory updates
python src/scraping/core/death_star.py --target https://www.dea.gov --depth 3
```

### Community Forums
```bash
# Cannabis forums (use specialized scrapers)
python src/scraping/forums/forum_scraper.py --target https://forum.example.com --depth 5
```

---

## Best Practices

### Respectful Scraping
- Always include `--wait=1` and `--random-wait` with wget
- Use `--limit-rate=1M` to avoid overwhelming servers
- Respect robots.txt
- Include contact information in User-Agent

### Data Organization
- Use descriptive directory names: `data/scraped_sites/cannabis_research_2026`
- ArchiveBox creates timestamped directories automatically
- Keep manifests and logs for reproducibility

### Legal Considerations
- Only scrape publicly available information
- Comply with terms of service
- Consider fair use for research purposes
- Document your scraping activities

---

## Troubleshooting

### Common Issues
1. **ArchiveBox fails**: Run `archivebox init --setup` first
2. **Crawl4AI errors**: Ensure `crawl4ai-setup` was run
3. **Playwright issues**: Run `playwright install chromium`
4. **Permission errors**: Check output directory permissions

### Recovery
- Death Star creates JSON manifests for each run
- Check `data/scraped_sites/*/manifest.json` for run details
- Resume failed scrapes with checkpoint system

---

**Need Help?** Check the logs in `data/scraped_sites/` or run with `--help` for usage details.