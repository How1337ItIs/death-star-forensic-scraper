# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Death Star Scraper** is an all-purpose forensic web scraper designed for comprehensive data acquisition and research. It's a multi-tool orchestrator that combines multiple scraping approaches for maximum coverage and reliability.

### Philosophy

*"The Death Star pattern: use multiple tools in combination, not relying on a single approach."*

The scraper captures EVERYTHING automatically during network interception - no manual phases, no post-processing. Everything flows through response handlers using authenticated sessions.

## Architecture

### Current vs deprecated

1. **Death Star V2 (`src/scraping/core/`)** — **CURRENT, use this**
   - Full implementation: forensic, ultimate, planetary, and all other modes.
   - Entry point: `python -m scraping.core.death_star_v2` (with `PYTHONPATH=src`) or `python src/scraping/core/death_star_v2.py --target URL --mode ultimate`
   - Includes advanced capture, forensic capture (WARC/HAR/API), Wayback, etc.

2. **Package (`death_star/`)** — **DEPRECATED**
   - Pip-installable library with CLI (`death-star --target URL`).
   - Only does a basic browser crawl; "forensic" and "ultimate" do not run the full pipelines. Do not use for new work. Prefer V2.

### Core Components

| Module | Purpose |
|--------|---------|
| `death_star_v2.py` | Main orchestrator (2500+ lines) - all modes |
| `advanced_capture.py` | WebSocket, forms, tech stack, __NEXT_DATA__, GraphQL |
| `forensic_capture.py` | WARC/HAR/asset capture, SSL certificates |
| `media_extractor.py` | Video/audio/image download via yt-dlp |
| `site_discovery.py` | Sitemap/robots.txt/link graph mapping |
| `wayback_integration.py` | Internet Archive integration |
| `checkpoint.py` | SQLite WAL persistence, crash recovery |
| `base_scraper.py` | Abstract base with rate limiting |
| `circuit_breaker.py` | Per-domain circuit breaker (CLOSED/OPEN/HALF_OPEN) |
| `captcha_handler.py` | CAPTCHA detection + solving (CapSolver, FlareSolverr) |
| `structured_data.py` | JSON-LD, microdata, RDFa, OpenGraph extraction |
| `session_pool.py` | Coherent identity pool (proxy+UA+fingerprint+cookies) |
| `cookie_extractor.py` | Extract cookies from Chrome/Firefox profile DBs |
| `singlefile_capture.py` | Full-fidelity single-HTML capture via SingleFile CLI |
| `watch_mode.py` | Passive capture while user browses manually via CDP |

### Multi-Tool Arsenal

| Tool | Purpose |
|------|---------|
| **wget** | Deep recursive download with all assets |
| **ArchiveBox** | Full archival (HTML, PDF, screenshot, WARC) |
| **Crawl4AI** | LLM-ready structured extraction |
| **Playwright** | JavaScript rendering, anti-bot evasion, CDP mode |
| **rebrowser-playwright** | Patched Playwright (no CDP Runtime.Enable leak) |
| **patchright** | Stealth-patched Playwright (anti-bot escalation) |
| **camoufox** | Firefox-based stealth browser (C++ fingerprint spoofing) |
| **nodriver** | Undetectable Chrome via raw DevTools Protocol |
| **curl_cffi** | HTTP with TLS fingerprint impersonation (JA3/JA4/HTTP2) |
| **trafilatura** | Clean text/markdown extraction |
| **extruct** | Structured data extraction (JSON-LD, microdata, RDFa) |
| **yt-dlp** | Video/audio download (1000+ platforms) |
| **SingleFile** | Full-fidelity single-HTML page capture |
| **FlareSolverr** | Cloudflare challenge solver (cf_clearance cookies) |
| **CapSolver** | CAPTCHA solving API (reCAPTCHA, hCaptcha, Turnstile) |
| **BrowserForge** | Realistic browser fingerprint generation |
| **browser-cookie3** | Extract cookies from browser profile databases |

## Commands

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows

# Install from package
pip install -e .
playwright install chromium

# Or install dependencies directly
pip install -r requirements.txt
playwright install chromium

# Optional stealth engines (for anti-bot escalation)
pip install patchright camoufox nodriver

# Optional: Full stealth suite (TLS fingerprinting, CAPTCHA solving, browser cookies)
pip install curl_cffi browserforge browser-cookie3 capsolver

# Optional: SingleFile CLI (full-fidelity page capture)
npm install -g single-file-cli

# Optional: FlareSolverr (Cloudflare challenge solver)
docker run -d -p 8191:8191 flaresolverr/flaresolverr
```

### Running the Scraper

**Use Death Star V2 (current):**

```bash
# From repo root
set PYTHONPATH=src
python -m scraping.core.death_star_v2 --target https://example.com --mode smart
python -m scraping.core.death_star_v2 --target https://example.com --mode ultimate

# Attach to a running Chrome (CDP mode — reuse authenticated sessions)
python death_star_v2.py --target https://example.com --cdp http://localhost:9222

# Use patchright stealth engine for anti-bot sites
python death_star_v2.py --target https://example.com --engine patchright --mode stealth

# Or from src/scraping/core
cd src/scraping/core
python death_star_v2.py --target https://example.com --mode forensic
python death_star_v2.py --help
```

**Deprecated (pip package):** `death-star --target URL` — use V2 instead for full forensic/ultimate behavior.

### Scraping Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `quick` | Fast wget mirror | Static sites, speed priority |
| `smart` | Adaptive HTTP/browser | **Default - general purpose** |
| `stealth` | Anti-bot browser | Protected sites |
| `full` | All crawl tools | Comprehensive capture |
| `forensic` | Complete forensic | Legal/research analysis |
| `planetary` | Maximum capture | Archive everything |
| `ultimate` | **Total annihilation** | Leave nothing behind |
| `watch` | **Passive capture** | Manual browse + background capture via CDP |

## Key Files

| File | Purpose |
|------|---------|
| `src/scraping/core/death_star_v2.py` | **Current** – main orchestrator (use this) |
| `src/scraping/core/forensic_capture.py` | Forensic capture (WARC, HAR, etc.) |
| `src/scraping/core/advanced_capture.py` | WebSocket, forms, tech stack, __NEXT_DATA__, GraphQL |
| `death_star/cli.py` | **Deprecated** – old CLI |
| `death_star/core/scraper.py` | **Deprecated** – old package scraper |
| `docs/` | Full documentation |

## Python API

```python
import asyncio
from death_star import DeathStar, ScrapeConfig

async def main():
    # Simple scrape
    scraper = DeathStar()
    page = await scraper.scrape("https://example.com")
    print(page.title)
    print(page.clean_text)
    
    # Full site destruction
    result = await scraper.destroy("https://example.com", mode="forensic")
    print(f"Scraped {result['pages_scraped']} pages")
    
    await scraper.close()

asyncio.run(main())
```

## Anti-Bot Evasion

- **User-Agent Rotation**: 8+ realistic 2025-2026 browser fingerprints (Chrome 134, Firefox 135, Safari 18.3, Edge 134)
- **Header Randomization**: Accept, Accept-Language, DNT
- **Browser Engine Escalation**: playwright -> patchright -> camoufox -> nodriver (auto-escalate on block)
- **CDP Connection Mode**: Attach to running Chrome to reuse authenticated sessions (bypasses anti-bot entirely)
- **In-Browser Fetch**: Execute fetch() from page context (carries all cookies/tokens, evades PerimeterX)
- **Stealth Browser**: Playwright with webdriver detection bypass
- **Human-like Behavior**: Random scrolling, delays, mouse simulation
- **Fingerprint Masking**: Chrome/plugins/languages spoofing
- **Domain Rate Limiting**: Adaptive delays based on errors
- **Proxy Pool Support**: Load from file, rotation, health tracking, auto-injection into browser

## CAPTCHA Handling

Automatic CAPTCHA detection and solving. Solving chain (cheapest first):
1. **Browser-native** — camoufox/nodriver often pass Turnstile without solving
2. **CapSolver API** — reCAPTCHA v2/v3, hCaptcha, Turnstile, FunCaptcha ($0.0005/token)
3. **FlareSolverr** — Cloudflare-specific, returns cf_clearance cookies

Config: Set `CAPSOLVER_API_KEY` in `.env` (already configured), or `--captcha-solver none` to disable.

## Circuit Breaker

Per-domain circuit breaker prevents hammering blocked domains:
- **CLOSED** → normal operation
- **OPEN** → skip domain after 5 consecutive failures (403/429/503/CAPTCHA)
- **HALF_OPEN** → probe with 2 test requests after 5 min recovery timeout

## Structured Data Extraction

- **JSON-LD / Schema.org**: Auto-extracts via `extruct` library
- **Microdata / RDFa**: Schema.org markup extraction
- **OpenGraph / Twitter Cards**: Social media metadata
- **Dublin Core**: Academic/library metadata
- **__NEXT_DATA__**: Auto-extracts JSON from Next.js SSR pages (e.g. Walmart, Airbnb, TikTok)
- **__NUXT__**: Auto-extracts data from Nuxt.js SSR pages
- **__APOLLO_STATE__**: Apollo GraphQL client cache
- **Redux / __PRELOADED_STATE__**: Redux store state
- **__remixContext**: Remix framework data
- **__GATSBY_DATA__**: Gatsby page data
- **GraphQL Interception**: Captures Apollo/Relay GraphQL responses during page load
- **In-Browser HTML Fetch**: Fetch pages as HTML from within browser context for data extraction

## Watch Mode (Passive Capture)

For sites where automated scraping fails (anti-bot too strong), use watch mode:
```bash
# 1. Launch Chrome with debugging
chrome --remote-debugging-port=9222 --user-data-dir="C:\path\to\profile"

# 2. Browse manually while Death Star captures everything
python src/scraping/core/watch_mode.py --cdp http://localhost:9222 -o data/watch_capture
```
Captures all network traffic, GraphQL, API responses, cookies, page snapshots in background.

## Output Structure

```
data/scraped_sites/
├── example.com_manifest.json     # Scrape summary
├── pages/                        # Raw HTML + markdown
├── forensic/                     # WARC, HAR, screenshots
├── media/                        # Videos, images, audio
├── discovery/                    # Sitemaps, link graphs
├── wget/                         # wget mirror
└── archivebox/                   # ArchiveBox output
```

## Site Adapters

Custom extraction logic for specific sites:

| Adapter | Sites | Extraction |
|---------|-------|------------|
| `RollitupAdapter` | rollitup.org | Forum threads, grow journals |
| `GrasscityAdapter` | grasscity.com | Forum posts |
| `IcmagAdapter` | icmag.com | Forum threads |
| `GrowWeedEasyAdapter` | growweedeasy.com | Grow guides |
| `LeaflyAdapter` | leafly.com | Strains, dispensaries |

## Best Practices

### Respectful Scraping
- Use `--polite` flag to respect robots.txt
- Set appropriate delays (`--delay 2.0`)
- Include research contact info in User-Agent

### Legal Considerations
- Only scrape publicly available information
- Check site Terms of Service
- Comply with GDPR, CCPA, and applicable regulations

## CDP Mode (Chrome DevTools Protocol)

Attach to a running Chrome instance to reuse authenticated sessions. This is the most reliable approach for anti-bot protected sites (Walmart, Amazon, etc.):

```bash
# 1. Launch Chrome with debugging
chrome --remote-debugging-port=9222 --user-data-dir="C:\path\to\profile"

# 2. Log in manually, then run scraper
python death_star_v2.py --target https://www.walmart.com/orders --cdp http://localhost:9222
```

Key patterns for CDP scraping:
- **DO NOT** use `page.goto()` for pagination — triggers anti-bot CAPTCHA
- **DO** use `PlaywrightFetcher.in_browser_fetch()` — executes `fetch()` inside the page context
- **DO** use click-and-intercept for pagination — click Next button + capture GraphQL response
- GraphQL replay via direct `fetch()` returns 418 even from browser context (PerimeterX blocks it)

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/walmart_ultimate_scraper.py` | CDP-based Walmart order scraper (3-phase: fetch + click-paginate + details) |
| `scripts/analyze_walmart_purchases.py` | Categorizes items into tax-deductible categories |
| `scripts/walmart_console_scraper.js` | Browser console fallback for manual extraction |

## Documentation

See `docs/` folder for comprehensive documentation:
- `DEATH_STAR_V2_COMPLETE.md` - Full technical docs
- `DEATH_STAR_SETUP.md` - Installation guide
- `DEATH_STAR_SCRAPER_ARCHITECTURE.md` - Architecture overview
- `WEB_SCRAPING_TOOLKIT.md` - Tool reference

---

*"That's no moon..."*
