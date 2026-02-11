# Scraper & Archival Reference Research

Research on other scraper/archival tools and cloned repos used to make Death Star Forensic Scraper more complete.

---

## Cloned Repos (reference/)

Clone these locally for study (they are in `.gitignore`):

```bash
cd death-star-forensic-scraper
mkdir -p reference
git clone --depth 1 https://github.com/webrecorder/warcio.git reference/warcio
git clone --depth 1 https://github.com/webrecorder/py-wacz.git reference/py-wacz
git clone --depth 1 https://github.com/webrecorder/browsertrix-crawler.git reference/browsertrix-crawler
git clone --depth 1 https://github.com/ArchiveBox/ArchiveBox.git reference/ArchiveBox
git clone --depth 1 https://github.com/gildas-lormeau/SingleFile.git reference/SingleFile
```

| Repo | Purpose | What to steal |
|------|---------|----------------|
| **webrecorder/warcio** | WARC/ARC read/write (Python) | We already use it optionally; now in `requirements.txt`. Use `warcio` CLI for recompress/index. |
| **webrecorder/py-wacz** | WACZ create/validate (Python) | Add WACZ export: `wacz create -o out.wacz capture.warc.gz`. Enables ReplayWeb.page and signed archives. |
| **webrecorder/browsertrix-crawler** | Browser-based high-fidelity crawler (Node/TypeScript, Docker) | WACZ generation, CDP capture, block rules, behaviors (scroll, wait), replay server. |
| **ArchiveBox/ArchiveBox** | Self-hosted web archiver (Python/Django) | Plugin architecture (wget, SingleFile, readability, mercury, favicon, PDF, yt-dlp, archive.org, headers, DOM). |
| **gildas-lormeau/SingleFile** | Save full page as single HTML (extension + CLI) | Concept: one self-contained HTML with inlined assets. SingleFile CLI can be invoked for “single-file” snapshot. |

---

## Comparison: Death Star vs Others

| Feature | Death Star | Browsertrix | ArchiveBox |
|--------|------------|-------------|------------|
| WARC | ✅ (forensic) | ✅ | ✅ (plugin) |
| HAR | ✅ | via CDP | ❌ |
| WACZ | ❌ | ✅ | ❌ |
| Screenshot / PDF | ✅ | ✅ | ✅ |
| DOM / HTML | ✅ | ✅ | ✅ + SingleFile |
| robots.txt / sitemap | ✅ (site_discovery) | ✅ | ✅ |
| Wayback | ✅ (wayback_integration) | ❌ | ✅ (SavePageNow) |
| Readability / Mercury | ❌ (we have Trafilatura) | ❌ | ✅ |
| Favicon | ❌ | ✅ | ✅ |
| Single-file HTML | ❌ | ❌ | ✅ (SingleFile plugin) |
| yt-dlp / media | ✅ (media_extractor) | ❌ | ✅ |
| Signed / verified archive | ❌ | ✅ (WACZ signing) | ❌ |
| Replay (ReplayWeb.page) | ❌ | ✅ (WACZ) | ❌ |

---

## How to Make Death Star More Complete

### 1. **WACZ output (ReplayWeb.page compatible)**

- **Idea:** After writing WARC in forensic/planetary, optionally produce a WACZ for replay and sharing.
- **How:** Add optional dependency `wacz`. After `forensic_capture` writes a WARC, run:
  - `wacz create -o <out>.wacz <capture>.warc.gz --detect-pages`
- **Ref:** `reference/py-wacz/` (CLI and API). Browsertrix does WACZ natively in `src/util/wacz.ts`.

### 2. **Single-file HTML snapshot**

- **Idea:** For “one file per page” archival, add a SingleFile-style capture (inline HTML+CSS+images).
- **How:** Either call [single-file-cli](https://github.com/gildas-lormeau/single-file-cli) from Python when available, or implement a minimal inliner in Playwright (serialize DOM + inline key resources). ArchiveBox does this via `plugins/singlefile/`.
- **Ref:** `reference/SingleFile/`, `reference/ArchiveBox/archivebox/plugins/singlefile/`.

### 3. **Favicon + title extraction**

- **Idea:** Always extract and save favicon and `<title>` for each URL (for dashboards and thumbnails).
- **How:** In forensic capture: parse `<link rel="icon">` and `<title>`, download favicon, save as `favicon.ico` and in metadata. ArchiveBox: `plugins/favicon/`, `plugins/title/`.
- **Ref:** `reference/ArchiveBox/archivebox/plugins/favicon/`, `plugins/title/`.

### 4. **Readability / Mercury (article extraction)**

- **Idea:** In addition to Trafilatura, offer Readability or Mercury for “article only” text/HTML.
- **How:** Add optional extractors (e.g. `readability-lxml` or ArchiveBox’s Mercury plugin) and store as `article.html` / `article.txt` alongside `clean_text.txt`.
- **Ref:** `reference/ArchiveBox/archivebox/plugins/readability/`, `plugins/mercury/`.

### 5. **Archive.org SavePageNow integration**

- **Idea:** Optionally submit each captured URL to Internet Archive (SavePageNow) for public archival.
- **How:** POST to `https://web.archive.org/save/<url>` (or use CDX API for “save if not recent”). ArchiveBox: `plugins/archivedotorg/`.
- **Ref:** `reference/ArchiveBox/archivebox/plugins/archivedotorg/`. Death Star already has `wayback_integration` for reading; this is the “write” path.

### 6. **warcio in requirements**

- **Done:** `warcio` is now in `requirements.txt` so WARC generation works without fallback. Use `warcio` for proper WARC 1.0/1.1 and optional CLI (index, recompress).

### 7. **Block rules / ad-blocking (Browsertrix-style)**

- **Idea:** Optional blocklist (e.g. ads, trackers) during browser capture to reduce noise and size.
- **How:** Load Brave/Chromium with a block list (e.g. uBlock-style) or implement request interception in Playwright to block by URL pattern. Browsertrix: `config/policies/`, `src/util/blockrules.ts`.
- **Ref:** `reference/browsertrix-crawler/config/policies/`, `src/util/blockrules.ts`.

### 8. **Behaviors: scroll / wait for SPAs**

- **Idea:** Before saving, optionally scroll the page or wait for network idle so SPAs render fully.
- **How:** In Playwright: `page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))`, then `page.wait_for_load_state('networkidle')`. Browsertrix: custom behaviors and flows in `src/` and tests.
- **Ref:** `reference/browsertrix-crawler/src/` (flowbehavior, timing).

### 9. **Signed WACZ (provenance)**

- **Idea:** When producing WACZ, optionally sign it for verification (ReplayWeb.page supports this).
- **How:** Use `py-wacz` or Browsertrix signing (signing URL + token). Ref: `reference/py-wacz` (validate, signing), `reference/browsertrix-crawler/src/util/wacz.ts`.

### 10. **Plugin / extractor registry (ArchiveBox-style)**

- **Idea:** Make “extractors” pluggable (favicon, readability, SingleFile, archive.org, etc.) so new capture types can be added without touching core.
- **How:** Define a small registry: name, config (enable/disable), and a single “run(url, output_dir, context)” function per extractor. Load from a `plugins/` or `extractors/` dir. Ref: ArchiveBox `plugins/*/config.json` + `on_Snapshot__*.py` / `.js`.

---

## Quick wins already in place

- **warcio:** Now in `requirements.txt` — no fallback JSON-WARC needed when installed.
- **WARC + HAR + DOM + assets + certs + screenshot + PDF** in forensic mode.
- **Site discovery:** robots.txt, sitemap, RSS, link graph in `site_discovery.py`.
- **Wayback:** fetch/save/timeline in `wayback_integration.py`.
- **Media:** `media_extractor.py` (yt-dlp optional).
- **Dashboard:** `dashboard.py` for running and inspecting captures.

---

## Summary

- **Cloned:** `warcio`, `py-wacz`, `browsertrix-crawler`, `ArchiveBox`, `SingleFile` under `reference/`.
- **Added:** `warcio` to `requirements.txt`; `reference/` in `.gitignore`.
- **Next steps (by impact):** WACZ export → Single-file HTML or SingleFile CLI → Favicon/title → Readability/Mercury → SavePageNow → Block rules / behaviors → Optional plugin registry and signed WACZ.

Use `reference/` as the local reference when implementing any of the above.

---

## Additional Scrapers (not yet studied)

Effective, mature, open-source scrapers worth cloning for more patterns. Run from repo root:

```bash
mkdir -p reference
# Already have: warcio, py-wacz, browsertrix-crawler, ArchiveBox, SingleFile

# New: archival & scale
git clone --depth 1 https://github.com/internetarchive/heritrix3.git reference/heritrix3
git clone --depth 1 https://github.com/scrapy/scrapy.git reference/scrapy
git clone --depth 1 https://github.com/q-m/scrapy-webarchive.git reference/scrapy-webarchive

# New: browser-based / high-fidelity
git clone --depth 1 https://github.com/N0taN3rd/Squidwarc.git reference/Squidwarc
git clone --depth 1 https://github.com/webrecorder/archiveweb.page.git reference/archiveweb.page
git clone --depth 1 https://github.com/ganapativs/puppeteer-warc.git reference/puppeteer-warc

# New: simple archivers & utilities
git clone --depth 1 https://github.com/turicas/crau.git reference/crau
git clone --depth 1 https://github.com/webrecorder/warcit.git reference/warcit
```

Or run the script: `./scripts/clone_reference.sh` (or `scripts\clone_reference.bat` on Windows).

| Repo | Stack | Purpose | What to steal |
|------|--------|---------|----------------|
| **internetarchive/heritrix3** | Java | IA’s web-scale archival crawler | Crawl order, frontier, robots handling, WARC writing at scale, job config (crawl scope, politeness). |
| **scrapy/scrapy** | Python | Most-used scraping framework | Middleware pipeline, request/response lifecycle, item pipelines, Scrapyd deployment, rate limiting. |
| **q-m/scrapy-webarchive** | Python | Scrapy → WARC/WACZ | How to plug WARC/WACZ into a crawler pipeline; datapackage.json, ZIP layout for WACZ. |
| **N0taN3rd/Squidwarc** | Node/Chrome | High-fidelity scriptable crawler | User scripts, CDP capture patterns, crawl modes (page / same-domain / links), config schema. |
| **webrecorder/archiveweb.page** | Extension | In-browser high-fidelity archiving | Extension UX, recording flow, WACZ from browser (same ecosystem as Browsertrix). |
| **ganapativs/puppeteer-warc** | Node/Puppeteer | Browser → WARC + screenshots | Puppeteer→WARC pattern (close to our Playwright path); request/response capture, screenshot hook. |
| **turicas/crau** | Python | Simple CLI archiver | `crau archive/list/extract/play`; minimal API for “URL list → WARC” and local replay. |
| **webrecorder/warcit** | Node | Files/dirs → WARC | Turning a mirrored tree or ZIP into valid WARC (post-process mirror → archive). |

### Other notable (no clone yet)

- **HTTrack** (httrack.com) — Classic recursive site copier (GPL); mirroring heuristics, not WARC.
- **Common Crawl** — Dataset only; use for testing against real crawl data.
- **crawl** (git.jordan.im/crawl) — Go recursive crawler → WARC; resume, binding; smaller community.
- **JustAnotherArchivist/qwarc** — High-throughput URL archiver; use responsibly.

---

## More “everything” archivers

Full-site / full-fidelity / save-everything archivers. Clone for patterns (replay, dashboard, permanent links, bookmark→archive).

```bash
# Everything archivers (run from repo root; reference/ in .gitignore)
git clone --depth 1 https://github.com/ArchiveTeam/grab-site.git reference/grab-site
git clone --depth 1 https://github.com/webrecorder/pywb.git reference/pywb
git clone --depth 1 https://github.com/reprozip-news-apps/reprozip-web.git reference/reprozip-web
git clone --depth 1 https://github.com/rhizome-conifer/conifer.git reference/conifer
git clone --depth 1 https://github.com/harvard-lil/perma.git reference/perma
git clone --depth 1 https://github.com/go-shiori/shiori.git reference/shiori
```

| Repo | Stack | Purpose | What to steal |
|------|--------|---------|----------------|
| **ArchiveTeam/grab-site** | Python/shell | Archivist’s crawler: WARC, dashboard, ignore patterns | Crawl dashboard UX, pause/resume, dynamic ignore rules, WARC-focused crawl workflow. |
| **webrecorder/pywb** | Python | Replay + live capture (Wayback-style), proxy recording | Proxy recording flow, CDX index/API, collection config, replay server; core of Webrecorder stack. |
| **reprozip-news-apps/reprozip-web** | Python | Full web app preservation: trace app → .rpz (can include .wacz) | Packaging server+frontend for reproducible replay; when you need “app + archive” in one bundle. |
| **rhizome-conifer/conifer** | Full stack | User-facing high-fidelity archiving service (Conifer) | How to wrap Webrecorder (frontend, nginx, redis, webrecorder); service UX, auth, quotas. (Service sunsets June 2026; code still useful.) |
| **harvard-lil/perma** | JS/Django | Permanent citation links: capture URL → stable perma.cc link | “Save URL → stable link” flow, capture pipeline, replay UX, institutional archiving product. |
| **go-shiori/shiori** | Go | Self-hosted bookmark manager with optional offline archive | Bookmark import (Pocket, Netscape), “archive this page” for offline readable copy, simple API and extension. |

---

## Implemented Steals (Current Codebase)

Borrowed and implemented in `death_star_v2.py`, `forensic_capture.py`, and `archive_utils.py`:

1. **Grab-site style ignore sets + dynamic regex policy**
   - Built-in global ignore regex subset to avoid analytics/share/login/comment traps.
   - CLI: `--ignore-patterns`, `--no-global-ignores`, `--include`, `--exclude`.

2. **Scrapy-style frontier priority**
   - URL queue now supports priority scoring (depth + content heuristics) instead of plain FIFO-by-depth.
   - Checkpoint schema updated with `priority`.

3. **Browsertrix-style behavior profile + block rules**
   - Playwright behavior profiles: `minimal`, `archive`, `aggressive`.
   - CLI controls: `--behavior-profile`, `--wait-until`, `--net-idle-wait`, `--auto-click-selector`.
   - Regex block rules file support: `--block-rules-file`.

4. **Browsertrix/py-wacz style indexing hardening**
   - Generate CDXJ sidecar index for each WARC capture.
   - Optional WACZ validation metadata after generation (when `wacz` CLI is available).
