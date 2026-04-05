# SOL-CANNABIS Web Scraping Tools

This module provides comprehensive web scraping capabilities for cannabis research and data acquisition.

## Current version: Death Star V2

**Death Star V2** is the **current, supported** scraper in this repo. The pip-installable package in `death_star/` is deprecated; use V2 for full forensic and ultimate modes.

## 🌟 Death Star V2 - "Nuke From Orbit" Scraper

The **Death Star V2** is an all-consuming web scraper designed for complete forensic capture of cannabis research sites. It integrates multiple tools for maximum coverage:

### Features

| Feature | Description |
|---------|-------------|
| **Multi-tool Arsenal** | wget, ArchiveBox, Playwright, Crawl4AI, trafilatura |
| **Forensic Capture** | WARC/HAR archives, SSL certificates, DNS records |
| **Media Extraction** | yt-dlp integration for 1000+ video platforms |
| **Site Discovery** | robots.txt, sitemaps, link graphs, API detection |
| **Wayback Machine** | Historical snapshots, version comparison |
| **Advanced Capture** | WebSocket messages, forms, tech stack fingerprinting |
| **Anti-bot Evasion** | Stealth browser, proxy rotation, human-like behavior |
| **Crash Recovery** | SQLite WAL checkpointing, graceful shutdown |

### Capture Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `quick` | Fast wget mirror | Basic site backup |
| `smart` | Adaptive HTTP/browser routing | **Recommended default** |
| `stealth` | Playwright with anti-bot evasion | JS-heavy/protected sites |
| `full` | All crawl tools combined | Complete research capture |
| `archive` | ArchiveBox only | Long-term preservation |
| `forensic` | Complete forensic capture | Reverse engineering |
| `planetary` | Maximum destruction | When you need EVERYTHING |
| `ultimate` | Total annihilation | WebSocket + forms + tech + Wayback |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run Death Star V2 (recommended for cannabis research)
python src/scraping/core/death_star_v2.py --target https://rollitup.org --mode smart

# Full forensic capture of a grow forum
python src/scraping/core/death_star_v2.py --target https://icmag.com --mode forensic

# Original Death Star (simpler, faster)
python src/scraping/core/death_star.py --target https://example-cannabis-site.com --full

# Get help
python src/scraping/core/death_star_v2.py --help
```

## Components

### Core Tools (`src/scraping/core/`)

| File | Lines | Description |
|------|-------|-------------|
| `death_star_v2.py` | 2100+ | Main orchestrator with all modes |
| `advanced_capture.py` | 800+ | WebSocket, forms, tech detection |
| `forensic_capture.py` | 700+ | WARC/HAR/asset capture |
| `media_extractor.py` | 500+ | Video/audio/image download via yt-dlp |
| `site_discovery.py` | 600+ | Sitemap/robots/link graph mapping |
| `wayback_integration.py` | 500+ | Internet Archive integration |
| `death_star.py` | 350+ | Original V1 scraper (simpler) |
| `base_scraper.py` | 300+ | Abstract base with checkpoint/resume |
| `checkpoint.py` | 250+ | SQLite WAL persistence |

### Site Adapters (`src/scraping/plugins/`)

| Adapter | Sites | Extraction |
|---------|-------|------------|
| `RollitupAdapter` | rollitup.org | Forum threads, grow journals |
| `GrasscityAdapter` | grasscity.com | Forum posts |
| `IcmagAdapter` | icmag.com | Forum threads |
| `GrowWeedEasyAdapter` | growweedeasy.com | Grow guides, problem solving |
| `LeaflyAdapter` | leafly.com | Strains, dispensaries (needs browser) |
| `Magazine420Adapter` | 420magazine.com | Forums, news |
| `CannabisNetAdapter` | cannabis.net | News articles |

### Specialized Scrapers

- **`forums/`**: Forum-specific scrapers (vBulletin, phpBB, XenForo)
- **`reddit/`**: Reddit scraping and indexing tools
- **`acquisition/`**: Broad content acquisition scripts

## Usage Examples

### Cannabis Research Scraping

```bash
# Scrape a grow journal thread
python src/scraping/core/death_star_v2.py \
    --target https://rollitup.org/t/my-grow-journal.12345 \
    --mode smart

# Deep scrape a cultivation wiki
python src/scraping/core/death_star_v2.py \
    --target https://growweedeasy.com \
    --mode full \
    --depth 5 \
    --max-pages 1000

# Forensic capture for legal research
python src/scraping/core/death_star_v2.py \
    --target https://cannabis-research-site.com \
    --mode forensic \
    --polite

# Resume an interrupted scrape
python src/scraping/core/death_star_v2.py \
    --target https://example.com \
    --resume
```

### Python API Usage

```python
from src.scraping.core import get_death_star_v2

# Initialize V2 scraper
DeathStarV2 = get_death_star_v2()
scraper = DeathStarV2()

# Scrape with smart routing
import asyncio
results = asyncio.run(scraper.destroy(
    url="https://rollitup.org",
    mode="smart",
    depth=3
))

print(f"Pages scraped: {results['pages_scraped']}")
print(f"Output: {results['outputs']}")
```

### Individual Module Usage

```python
# Forensic capture only
from src.scraping.core import get_forensic_capture
ForensicCapture = get_forensic_capture()

capture = ForensicCapture(output_dir="data/forensic")
result = await capture.capture_page("https://example.com")

# Media extraction (videos, audio, images)
from src.scraping.core import get_media_extractor
MediaExtractor = get_media_extractor()

extractor = MediaExtractor(output_dir="data/media")
result = await extractor.extract_all(url, html)

# Site discovery (sitemaps, robots, links)
from src.scraping.core import get_site_discovery
SiteDiscovery = get_site_discovery()

discovery = SiteDiscovery(output_dir="data/discovery")
result = await discovery.discover_site("https://example.com")

# Wayback Machine integration
from src.scraping.core import get_wayback_machine
WaybackMachine = get_wayback_machine()

wayback = WaybackMachine()
snapshots = await wayback.get_snapshots("https://example.com")
content = await wayback.fetch_snapshot("https://example.com", "20200101")
```

## Output Structure

```
data/scraped_sites/
├── example.com_manifest.json     # Scrape summary
├── pages/
│   └── example.com/
│       ├── index_abc123.html     # Raw HTML
│       ├── index_abc123.md       # LLM-ready markdown
│       └── index_abc123.json     # Metadata
├── forensic/
│   ├── results/                  # Full forensic bundles
│   ├── warc/                     # WARC archives
│   ├── har/                      # HAR files
│   ├── screenshots/              # Full-page captures
│   ├── pdfs/                     # PDF renders
│   ├── assets/                   # CSS, JS, fonts
│   └── certificates/             # SSL certs
├── media/
│   ├── videos/                   # yt-dlp downloads
│   ├── audio/                    # Audio files
│   ├── images/                   # All images
│   └── documents/                # PDFs, docs
├── discovery/
│   └── example.com/
│       ├── discovery.json        # Site structure
│       ├── all_urls.txt          # URL inventory
│       ├── robots.txt            # Captured robots
│       └── link_graph.json       # Internal/external links
├── wget/                         # wget mirror
└── archivebox/                   # ArchiveBox output
```

## Installation

### Core Requirements

```bash
# Base requirements
pip install requests trafilatura playwright httpx

# Browser automation
playwright install chromium

# WARC generation (optional)
pip install warcio

# DNS records (optional)
pip install dnspython
```

### Full Installation

```bash
# All dependencies
pip install \
    requests \
    trafilatura \
    playwright \
    httpx \
    warcio \
    dnspython \
    yt-dlp \
    archivebox

# Browser setup
playwright install chromium

# ArchiveBox init (optional)
archivebox init --setup

# Verify installation
python src/scraping/core/death_star_v2.py --install
```

## Anti-Bot Evasion

The Death Star V2 includes comprehensive anti-bot countermeasures:

- **User-Agent Rotation**: 7 realistic browser fingerprints
- **Header Randomization**: Accept, Accept-Language, DNT
- **Stealth Browser**: Playwright with webdriver detection bypass
- **Human-like Behavior**: Random scrolling, delays, mouse simulation
- **Fingerprint Masking**: Chrome/plugins/languages spoofing
- **Domain Rate Limiting**: Adaptive delays based on errors
- **Proxy Pool Support**: Load from file, rotation, health tracking

## Best Practices

### Respectful Scraping
- Use `--polite` flag to respect robots.txt
- Set appropriate delays (`--delay 2.0`)
- Limit concurrent requests to avoid overloading servers
- Include research contact info in User-Agent

### Legal Considerations
- Only scrape publicly available information
- Check site Terms of Service before scraping
- Store data securely, especially personal information
- Comply with GDPR, CCPA, and applicable regulations

### Cannabis Research Ethics
- Respect user privacy on forums
- Don't scrape personal cultivation addresses
- Verify legal status of content in your jurisdiction

## Documentation

See [docs/DEATH_STAR_V2_COMPLETE.md](../docs/DEATH_STAR_V2_COMPLETE.md) for the full technical documentation.

---

*"The music never stopped. Neither does our scraper."* 🌿💀