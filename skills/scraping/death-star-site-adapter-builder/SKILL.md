# Death Star Site Adapter Builder

Use this workflow when a target needs repeatable site-specific selectors, API replay, or extraction post-processing.

## Baseline

```powershell
python -m scraping.core.death_star_v2 --target <url> --mode smart --max-pages 3 --depth 1 --save-wayback
```

## Build Steps

- Start with a narrow `--include` regex and low `--max-pages`.
- Inspect saved HTML, extractor summaries, structured JSON, and `events.jsonl`.
- Prefer stable API endpoints or structured data before fragile DOM selectors.
- Keep selectors and replay assumptions in a site adapter file, not in the core crawler.
- Add a fixture route or saved HTML fixture when the adapter behavior matters for regression tests.

## Verification

Run the adapter against a fixture or a low-page live crawl, then compare extractor outputs under `extract/pages/` and manifest crawl stats.
