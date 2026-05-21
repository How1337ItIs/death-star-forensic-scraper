# Death Star Watch Mode

Use this workflow when you need to browse manually in an authenticated Chrome session while Death Star passively records activity through CDP.

## Start Chrome

```powershell
chrome.exe --remote-debugging-port=9222 --user-data-dir=%TEMP%\death-star-cdp
```

## Start Watch Mode

```powershell
python -m scraping.core.death_star_v2 --mode watch --cdp http://localhost:9222 --output output
```

## Review

- Watch mode requires `--cdp`; the CLI fails fast without it.
- Keep secrets in the browser profile, not in command arguments.
- Review the watch output directory and `events.jsonl` for capture timing and warnings.
