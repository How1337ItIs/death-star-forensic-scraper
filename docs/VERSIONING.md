# Death Star Versioning

## Current: Canonical Death Star V2

**Location:** `src/scraping/core/death_star_v2.py`

**Entry points:**
- Module: `python -m scraping.core.death_star_v2 --target URL --mode MODE`
- Repo compatibility wrapper: `python death_star_v2.py --target URL --mode MODE`
- Installed console scripts: `death-star` and `ds-scrape`
- Package compatibility wrapper: `python -m death_star.cli --target URL --mode MODE`
- Dashboard launcher: `dashboard.py`, which invokes `python -m scraping.core.death_star_v2`

Use this implementation for all new work. The installed CLI, root wrapper, package wrapper, and dashboard now route to the same canonical V2 engine.

## Compatibility Surface

The root `death_star_v2.py` file and the `death_star/` package are compatibility shims only. They preserve older commands while delegating behavior to the canonical V2 module.

Do not add new scraper behavior under `death_star/` unless it is strictly wrapper compatibility. New fetch, crawl, archive, extractor, replay, manifest, and dashboard behavior belongs under `src/scraping/core/`.

## Optional Backends

Optional tools are detected at runtime through `death-star --doctor` and recorded in every run as `backend_report.json` and `tool_versions.json`.

GPL/AGPL applications such as Browsertrix, SingleFile, pywb, wget, and nodriver stay outside the runtime package path. Death Star invokes them only through CLI/container boundaries and records provenance in run manifests and command reports.

## Run Contract

Every canonical V2 run writes a timestamped run directory under the selected output root with:

- `manifest.json`
- `events.jsonl`
- `backend_report.json`
- `tool_versions.json`
- `pages/`, `assets/`, `warc/`, `har/`, `wacz/`, `extract/`, `screenshots/`, `replay/`

Manifests record cookie/proxy/auth presence as booleans only. Secrets must not be written to manifests or logs.
