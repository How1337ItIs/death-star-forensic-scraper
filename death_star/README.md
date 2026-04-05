# Death Star Scraper (pip package) — **Deprecated**

This directory is the **pip-installable** Death Star package (`death-star-scraper`). It is **deprecated** and no longer the recommended way to use Death Star.

## Why deprecated?

- **Forensic and ultimate modes** in this package only run a basic browser crawl. They do **not** perform full forensic capture (WARC, HAR, request/response bodies, API capture) or the full “ultimate” pipeline (advanced capture + forensic + Wayback).
- All of that behavior lives in **Death Star V2** in `src/scraping/core/`, which is the current, supported implementation.

## What to use instead

Use **Death Star V2** from the repo:

```bash
# From repo root
set PYTHONPATH=src
python -m scraping.core.death_star_v2 --target https://example.com --mode ultimate

# Or from src/scraping/core
python death_star_v2.py --target https://example.com --mode forensic --output ../../../../data/scraped_sites
```

See the [main README](../README.md) and [docs/DEATH_STAR_V2_COMPLETE.md](../docs/DEATH_STAR_V2_COMPLETE.md) for full documentation.

## If you still use this package

- No new features will be added here.
- For full forensic/ultimate behavior, migrate to V2.
- This package may be removed in a future release.

---

*Deprecated in favor of Death Star V2 (`src/scraping/core/`).*
