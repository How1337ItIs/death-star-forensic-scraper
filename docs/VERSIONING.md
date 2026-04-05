# Death Star Versioning: Current vs Deprecated

## Current: Death Star V2

**Location:** `src/scraping/core/`

**Entry points:**
- From repo root: `PYTHONPATH=src python -m scraping.core.death_star_v2 --target URL --mode MODE`
- From core dir: `python death_star_v2.py --target URL --mode MODE`

**Use this for:** All new work. Full forensic capture, ultimate mode (advanced + forensic + Wayback), and all other modes work as documented.

**Docs:** [DEATH_STAR_V2_COMPLETE.md](DEATH_STAR_V2_COMPLETE.md), [../src/scraping/README.md](../src/scraping/README.md)

---

## Deprecated: death_star package (pip)

**Location:** `death_star/` (pip install: `death-star-scraper`)

**Entry point:** `death-star --target URL` or `python -m death_star.cli --target URL`

**Status:** Deprecated. Do not use for new work.

**Why deprecated:** The package only performs a basic browser crawl. The `forensic` and `ultimate` modes do **not** run the full forensic/ultimate pipelines (no full WARC/HAR/API capture, no advanced capture, no Wayback). That behavior exists only in V2.

**Migration:** Use Death Star V2 (above) for full behavior. See [../death_star/README.md](../death_star/README.md).
