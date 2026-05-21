# Death Star Forensic Capture

Use this workflow when the goal is durable evidence, replayable archives, and debuggable artifacts.

## Command

```powershell
python -m scraping.core.death_star_v2 --target <url> --mode forensic --wacz --output output
```

## Checklist

- Run `python -m scraping.core.death_star_v2 --doctor` first and note missing optional tools.
- Prefer `--mode forensic` for single-page evidence capture.
- Add `--wacz` when the `wacz` CLI/module is installed.
- Keep cookies/proxies outside manifests; Death Star records only boolean presence.
- Inspect `manifest.json`, `events.jsonl`, `backend_report.json`, and `tool_versions.json`.
- Use `death-star replay <run_dir>` when pywb is installed, or open WACZ files in ReplayWeb.page.

## Outputs

Expected run artifacts include WARC, HAR, screenshot, optional PDF, optional WACZ, CDXJ, extractor output, and a manifest with backend provenance.
