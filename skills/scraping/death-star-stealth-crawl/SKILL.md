# Death Star Stealth Crawl

Use this workflow for JS-heavy pages, anti-bot friction, or crawl sessions that need browser escalation.

## Command

```powershell
python -m scraping.core.death_star_v2 --target <url> --mode stealth --engine auto --max-pages 25 --depth 2
```

## Options

- `--engine auto`: HTTP/curl path first where possible, then Playwright escalation.
- `--engine patchright`: use Patchright when installed and the target justifies stealth escalation.
- `--engine camoufox`: use Camoufox when installed for a Firefox-based profile.
- `--headed`: make the browser visible for debugging.
- `--include` and `--exclude`: keep crawl scope narrow and repeatable.
- `--block-ads` and `--block-rules-file`: reduce noisy third-party requests in browser modes.

## Review

Read `events.jsonl` for browser escalation, retries, skipped optional backends, and extractor failures. Check `manifest.json` for fingerprint metadata, backend availability, warnings, and crawl stats.
