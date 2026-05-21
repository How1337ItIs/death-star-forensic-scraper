# Death Star Replay Audit

Use this workflow to verify that a completed run has replayable archive artifacts and traceable tool provenance.

## Command

```powershell
death-star replay <run_dir>
```

Equivalent module command:

```powershell
python -m scraping.core.death_star_v2 replay <run_dir>
```

## Checklist

- Confirm the run has `manifest.json`, `backend_report.json`, `tool_versions.json`, and `events.jsonl`.
- Confirm at least one WARC, ARC, or WACZ exists under the run directory.
- If pywb is missing, inspect `replay/pywb_replay.json` and use WACZ artifacts with ReplayWeb.page.
- Keep pywb as an external GPL CLI boundary; do not vendor replay-server source into Death Star.
