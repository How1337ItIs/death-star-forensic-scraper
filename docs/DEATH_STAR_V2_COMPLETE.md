# Death Star V2 - Complete "Planetary Destroyer" Scraping System

**This is the current, supported Death Star implementation.** Use the `death_star/` pip package only for legacy compatibility; it is deprecated and does not provide full forensic/ultimate behavior.

**Created:** January 2026  
**Status:** OPERATIONAL  
**Purpose:** Maximum forensic capture of web content

---

## 🌍💥 Overview

The Death Star V2 is a comprehensive, all-purpose web scraping system designed for **complete forensic capture**. It combines multiple tools and techniques to grab every trace of everything for analysis and reverse engineering.

---

## 📂 System Architecture

```
scripts/scraping/
├── core/
│   ├── death_star_v2.py      # Main orchestrator (2100+ lines)
│   ├── advanced_capture.py   # WebSocket, forms, tech detection (800+ lines)
│   ├── forensic_capture.py   # WARC/HAR/asset capture (700+ lines)
│   ├── media_extractor.py    # Video/audio/image download (500+ lines)
│   ├── site_discovery.py     # sitemap/robots/link graph (600+ lines)
│   ├── wayback_integration.py # Wayback Machine integration (500+ lines)
│   ├── base_scraper.py       # Base class with checkpoint
│   └── checkpoint.py         # SQLite WAL persistence
├── plugins/
│   ├── base_adapter.py       # Site adapter framework
│   └── grateful_dead_adapter.py  # GD-specific adapters
└── utilities/
    └── health_check.py       # Monitoring
```

---

## 🎯 Capture Modes

| Mode | Description | What It Captures |
|------|-------------|------------------|
| `quick` | Fast wget mirror | HTML, CSS, JS, images |
| `smart` | Adaptive routing | Content + metadata |
| `stealth` | Anti-bot browser | JS-rendered content |
| `full` | All crawl tools | Smart + wget + ArchiveBox |
| `archive` | ArchiveBox only | WARC, PDF, screenshots |
| `forensic` | Complete forensic | EVERYTHING (see below) |
| `planetary` | **MAXIMUM** | All modes combined |
| `ultimate` | **🌌 TOTAL ANNIHILATION** | Everything + WebSockets + Forms + Tech Stack + Wayback + Source Maps |

---

## 🔬 Forensic Mode Captures

### Network Layer
- ✅ Full HTTP request headers
- ✅ Full HTTP response headers
- ✅ Request/response body content
- ✅ HAR (HTTP Archive) file
- ✅ WARC (Web ARChive) file
- ✅ Redirect chain tracking
- ✅ Cookie jar preservation
- ✅ Session management

### Content Layer
- ✅ Raw HTML (original)
- ✅ DOM snapshot (post-JavaScript execution)
- ✅ Clean text extraction
- ✅ Markdown conversion (LLM-ready)
- ✅ Shadow DOM content (via Playwright)

### Asset Layer
- ✅ Images (all formats: JPG, PNG, GIF, WebP, SVG, AVIF)
- ✅ CSS files
- ✅ JavaScript files
- ✅ Fonts (WOFF, WOFF2, TTF)
- ✅ Videos (via yt-dlp - 1000+ sites)
- ✅ Audio files
- ✅ PDFs and documents

### Metadata Layer
- ✅ Open Graph tags (og:title, og:image, etc.)
- ✅ Twitter Card metadata
- ✅ Schema.org / JSON-LD structured data
- ✅ Canonical URLs
- ✅ Alternate languages (hreflang)
- ✅ RSS/Atom feed discovery
- ✅ Favicon extraction

### Browser Storage
- ✅ Cookies (all attributes)
- ✅ localStorage
- ✅ sessionStorage
- ✅ IndexedDB database listing

### Security Data
- ✅ SSL/TLS certificate capture
- ✅ Certificate fingerprint (SHA256)
- ✅ DNS records (A, AAAA, MX, TXT, NS)
- ✅ Security headers (CSP, HSTS, X-Frame-Options)
- ✅ CORS configuration

### Visual Capture
- ✅ Full-page screenshot (PNG)
- ✅ PDF rendering of page
- ✅ Thumbnail generation

### Site Structure
- ✅ robots.txt parsing and storage
- ✅ sitemap.xml discovery and parsing
- ✅ Link graph generation
- ✅ Internal/external link mapping
- ✅ Orphan page detection
- ✅ Hub page identification
- ✅ API endpoint detection

### Media Extraction (yt-dlp)
- ✅ YouTube videos
- ✅ Vimeo videos
- ✅ SoundCloud audio
- ✅ Bandcamp music
- ✅ Archive.org recordings
- ✅ Reddit videos
- ✅ Twitter/X media
- ✅ 1000+ other platforms

---

## 🌌 Ultimate Mode (NEW!)

The **Ultimate Mode** adds the following capabilities beyond forensic mode:

### Advanced Capture (advanced_capture.py)
- ✅ **WebSocket capture** - Real-time WS connections and messages
- ✅ **Form extraction** - All forms with fields, actions, hidden values
- ✅ **Iframe recursive capture** - Content from nested iframes
- ✅ **Source map downloading** - Original source from minified JS
- ✅ **Technology stack detection** - Wappalyzer-style fingerprinting:
  - CMS (WordPress, Drupal, Shopify, etc.)
  - Frameworks (React, Vue, Angular, Next.js, etc.)
  - JS libraries (jQuery, Lodash, etc.)
  - CSS frameworks (Bootstrap, Tailwind, etc.)
  - Analytics (Google Analytics, Mixpanel, etc.)
  - Advertising (Google Ads, Facebook Pixel, etc.)
  - CDN (Cloudflare, Fastly, etc.)
  - Server (nginx, Apache, etc.)
- ✅ **Third-party script inventory** - All external scripts categorized
- ✅ **Contact info extraction** - Emails, phones, social links
- ✅ **API endpoint extraction** - Discover API calls in JavaScript
- ✅ **CSS analysis** - Fonts, colors, custom properties, media queries

### Wayback Machine Integration (wayback_integration.py)
- ✅ **Historical snapshots** - List all archived versions
- ✅ **Fetch archived pages** - Download specific historical versions
- ✅ **Submit for archival** - Save current page to Wayback Machine
- ✅ **Version comparison** - Diff between snapshots
- ✅ **Timeline reconstruction** - Yearly/monthly snapshot history
- ✅ **Deleted content recovery** - Find content that's been removed

### Proxy & Authentication Support
- ✅ **Proxy pool management** - Load from file, rotation, health tracking
- ✅ **Cookie import** - JSON or Netscape format from browser export
- ✅ **HTTP authentication** - Basic and Digest auth support
- ✅ **Session management** - Persist auth across requests

---

## 💻 Usage

### Basic Usage

```bash
# Smart crawl (default - recommended for most sites)
python scripts/scraping/core/death_star_v2.py --target https://example.com

# Complete forensic capture
python scripts/scraping/core/death_star_v2.py --target https://example.com --mode forensic

# PLANETARY DESTRUCTION (everything!)
python scripts/scraping/core/death_star_v2.py --target https://example.com --mode planetary

# 🌌 ULTIMATE MODE - Total annihilation (WebSocket, Forms, Tech Stack, Wayback, etc.)
python scripts/scraping/core/death_star_v2.py --target https://example.com --mode ultimate
```

### Advanced Options

```bash
# Deep stealth scrape with anti-bot evasion
python scripts/scraping/core/death_star_v2.py \
    --target https://protected-site.com \
    --mode stealth \
    --depth 10 \
    --max-pages 5000

# Resume interrupted scrape
python scripts/scraping/core/death_star_v2.py \
    --target https://example.com \
    --resume

# Polite mode (respect robots.txt)
python scripts/scraping/core/death_star_v2.py \
    --target https://example.com \
    --polite \
    --delay 2.0

# Multiple targets from file
python scripts/scraping/core/death_star_v2.py \
    --targets urls.txt \
    --mode forensic
```

### Proxy & Authentication Options

```bash
# Use a single proxy
python scripts/scraping/core/death_star_v2.py \
    --target https://example.com \
    --proxy http://proxy.example.com:8080

# Use proxy pool from file
python scripts/scraping/core/death_star_v2.py \
    --target https://example.com \
    --proxy-file proxies.txt \
    --mode stealth

# Use cookies from browser export
python scripts/scraping/core/death_star_v2.py \
    --target https://protected-site.com \
    --cookies cookies.json

# HTTP Basic Authentication
python scripts/scraping/core/death_star_v2.py \
    --target https://example.com \
    --auth-user username \
    --auth-pass password
```

### Individual Module Usage

```python
# Forensic capture only
from scripts.scraping.core.forensic_capture import ForensicCapture

capture = ForensicCapture(output_dir="data/forensic")
result = await capture.capture_page("https://example.com")

# Media extraction only
from scripts.scraping.core.media_extractor import MediaExtractor

extractor = MediaExtractor(output_dir="data/media")
result = await extractor.extract_all(url, html)

# Site discovery only
from scripts.scraping.core.site_discovery import SiteDiscovery

discovery = SiteDiscovery(output_dir="data/discovery")
result = await discovery.discover_site("https://example.com")

# Advanced capture (WebSocket, forms, tech stack)
from scripts.scraping.core.advanced_capture import AdvancedCapture

advanced = AdvancedCapture(output_dir="data/advanced")
result = await advanced.capture_advanced(playwright_page, url)
# result.websocket_messages, result.forms, result.tech_stack, etc.

# Wayback Machine integration
from scripts.scraping.core.wayback_integration import WaybackMachine

wayback = WaybackMachine()
snapshots = await wayback.get_snapshots("https://example.com")
content = await wayback.fetch_snapshot("https://example.com", "20200101")
await wayback.save_url("https://example.com")  # Submit for archival
```

---

## 📦 Output Structure

```
data/scraped_sites/
├── example.com_manifest.json     # Summary of scrape
├── pages/
│   └── example.com/
│       ├── index_abc123.html     # Raw HTML
│       ├── index_abc123.md       # Markdown
│       └── index_abc123.json     # Metadata
├── forensic/
│   ├── results/
│   │   └── example.com_2026-01-15T12-00-00/
│   │       ├── metadata.json
│   │       ├── raw.html
│   │       ├── dom_snapshot.html
│   │       ├── clean_text.txt
│   │       ├── internal_links.txt
│   │       ├── external_links.txt
│   │       └── network.har
│   ├── warc/
│   │   └── example.com_2026-01-15.warc.gz
│   ├── har/
│   │   └── example.com_2026-01-15.har
│   ├── screenshots/
│   │   └── example.com_2026-01-15.png
│   ├── pdfs/
│   │   └── example.com_2026-01-15.pdf
│   ├── assets/
│   │   └── example.com/
│   │       ├── style_abc123.css
│   │       ├── script_def456.js
│   │       └── image_ghi789.png
│   └── certificates/
│       └── example.com.json
├── media/
│   ├── videos/
│   │   └── example.com/
│   ├── audio/
│   │   └── example.com/
│   ├── images/
│   │   └── example.com/
│   └── documents/
│       └── example.com/
├── discovery/
│   └── example.com/
│       ├── discovery.json
│       ├── all_urls.txt
│       ├── robots.txt
│       └── link_graph.json
├── wget/
│   └── example.com/
│       └── (mirrored site)
└── archivebox/
    └── example.com/
        └── (full archive)
```

---

## 🔧 Installation

### Core Requirements

```bash
# Base requirements
pip install requests trafilatura playwright httpx

# Browser automation
playwright install chromium

# WARC generation (optional but recommended)
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

# ArchiveBox init
archivebox init --setup

# Verify
python scripts/scraping/core/death_star_v2.py --install
```

---

## 🛡️ Anti-Bot Evasion

The Death Star V2 includes comprehensive anti-bot evasion:

| Technique | Implementation |
|-----------|----------------|
| User-Agent Rotation | 7 realistic browser fingerprints |
| Header Randomization | Accept, Accept-Language, DNT |
| Stealth Browser | Playwright with webdriver detection bypass |
| Human-like Behavior | Random scrolling, delays, mouse simulation |
| Fingerprint Masking | Chrome/plugins/languages spoofing |
| Domain Rate Limiting | Adaptive delays based on errors |
| Exponential Backoff | Increasing delays on repeated failures |

### Stealth Scripts Applied

```javascript
// Bypass webdriver detection
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fake Chrome runtime
window.chrome = { runtime: {} };

// Spoof plugins and languages
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
```

---

## 🔄 Checkpoint/Resume

All scraping operations are crash-proof:

- **SQLite WAL mode** - Writes survive power failures
- **Per-URL tracking** - Know exactly what's been scraped
- **Content deduplication** - Hash-based duplicate detection
- **Domain state tracking** - Rate limiting persists across sessions
- **Graceful shutdown** - SIGTERM/SIGINT saves state

Resume any interrupted scrape:

```bash
python scripts/scraping/core/death_star_v2.py --target https://example.com --resume
```

---

## 📊 Statistics & Monitoring

Each scrape generates comprehensive statistics:

```json
{
  "target": "https://example.com",
  "mode": "planetary",
  "started_at": "2026-01-15T12:00:00",
  "completed_at": "2026-01-15T14:30:00",
  "weapons_fired": [
    "site_discovery",
    "forensic_capture",
    "media_extractor",
    "stealth_crawl",
    "wget",
    "archivebox"
  ],
  "pages_scraped": 1523,
  "errors": 12,
  "discovery_stats": {
    "total_urls": 2341,
    "sitemaps_found": 3,
    "feeds_found": 2
  },
  "forensic_stats": {
    "requests_captured": 847,
    "assets_captured": 234,
    "cookies": 15,
    "local_storage_keys": 8
  },
  "media_stats": {
    "videos": 12,
    "audio": 45,
    "images": 892,
    "documents": 23
  }
}
```

---

## 🎯 Use Cases

### Forensic Analysis
- Capture complete state of a website for legal evidence
- Preserve exact browser storage state
- Verify certificate and security configuration

### Reverse Engineering
- Capture all API calls via HAR
- Extract JavaScript and understand client-side logic
- Map complete site structure

### Archival
- Create WARC files for long-term preservation
- Generate PDF snapshots
- Mirror sites for offline access

### Research
- Extract all content for text analysis
- Build link graphs for network analysis
- Capture multimedia for analysis

---

## ⚠️ Legal & Ethical Notes

- Always respect `robots.txt` when using `--polite`
- Check site Terms of Service before scraping
- Use appropriate rate limiting to avoid overloading servers
- Store data securely, especially if it contains personal information
- Comply with GDPR, CCPA, and other applicable privacy regulations

---

*"The music never stopped. Neither does our scraper."*
