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
