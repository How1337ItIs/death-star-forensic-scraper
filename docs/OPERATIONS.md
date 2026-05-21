# Death Star Operations

## Install

Core editable install:

```powershell
python -m pip install -e .
```

Full local feature set, still optional at runtime:

```powershell
python -m pip install -e .[full]
python -m pip install -e .[crawl4ai]
python -m pip install -e .[scrapling]
python -m pip install pytest ruff
npm install -g single-file-cli
uv tool install pywb --python 3.12 --with "setuptools<81"
```

`crawl4ai` and `scrapling` are separate extras because their current releases declare incompatible
`lxml` requirements. They can both be installed on this host and the Death Star adapters pass, but
`pip check` reports the metadata conflict.

Browser support:

```powershell
python -m playwright install chromium
python -m patchright install chromium
python -m camoufox fetch
docker pull webrecorder/browsertrix-crawler
```

External archive/replay tools are optional. Use `death-star --doctor` to see what is installed.

## Canonical Commands

```powershell
python -m scraping.core.death_star_v2 --doctor
python -m scraping.core.death_star_v2 --target https://example.com --mode smart --max-pages 5
python death_star_v2.py --target https://example.com --mode forensic --wacz
death-star --target https://example.com --mode full --archive-backend archivebox
death-star --target https://example.com --mode archive --archive-backend browsertrix
death-star replay output\example.com_YYYYMMDD_HHMMSS
```

`death-star replay` uses external pywb only. If pywb is not installed or no archive files exist, it writes `replay/pywb_replay.json` and exits with a clean diagnostic.

## Modes

- `quick`: wget mirror when wget exists; missing wget is recorded as an optional skip.
- `smart`: HTTP first, then browser escalation for JS-heavy or blocked pages.
- `stealth`: browser-first path with optional Patchright, Camoufox, or nodriver escalation.
- `full`: smart crawl plus wget and a selected non-native archive backend when requested.
- `archive`: selected archive backend; `native` uses forensic WARC/HAR capture.
- `forensic`: native browser forensic capture with WARC, HAR, screenshots, assets, storage, PDF, CDXJ, and optional WACZ.
- `planetary` and `ultimate`: combined discovery, forensic, media, crawl, and optional external archive paths.
- `watch`: passive CDP watch mode; requires `--cdp`.

## Output Contract

Every run creates a timestamped directory under the selected output root. Required top-level files are:

- `manifest.json`
- `events.jsonl`
- `backend_report.json`
- `tool_versions.json`

Required artifact directories are:

- `pages/`
- `assets/`
- `warc/`
- `har/`
- `wacz/`
- `extract/`
- `screenshots/`
- `replay/`

Manifest paths are relative where possible. Cookie, proxy, and auth values are never written; only boolean presence is recorded.

## Optional Backend Policy

Use local dependencies where they are permissively licensed and lightweight. Keep full applications and copyleft projects behind subprocess or container boundaries:

- Browsertrix: Docker command report under `browsertrix/browsertrix_command.json`.
- ArchiveBox: CLI command report under `archivebox/<domain>/archivebox_command.json`.
- pywb: replay command report under `replay/pywb_replay.json`.
- wacz: post-processing only when the `wacz` CLI/module is available.

Known Windows notes:

- ArchiveBox 0.7.1 installs but its native Windows CLI currently fails on `os.getuid`; Death Star records the failed command under `archivebox/<domain>/archivebox_command.json`.
- pywb should be installed through `uv tool install pywb --python 3.12 --with "setuptools<81"` on Python 3.13 hosts because the PyPI dependency set is not compatible with Python 3.13 in-process.
- py-wacz 0.4.9 installs and is detected, but native WACZ generation can fail on Windows path handling. Browsertrix Docker WACZ generation is the tested WACZ path on this host.
- Crawl4AI 0.7.8 and Scrapling 0.4.8 currently declare incompatible `lxml` requirements. Both import and the Death Star extractor tests pass here, but `pip check` reports that package metadata conflict.

Missing optional tools are warnings, manifest notes, and `skipped_optional_backend` events unless the selected mode cannot produce any useful output.

## Local Verification

Run the focused smoke checks:

```powershell
python -m pytest tests -q
python scripts\death_star_smoke.py
```

Run the broader static checks:

```powershell
python -m ruff check src\scraping\core dashboard.py death_star_v2.py death_star tests scripts\death_star_smoke.py
python -m compileall src\scraping\core death_star dashboard.py death_star_v2.py tests scripts\death_star_smoke.py
```

The current shell may not have the Python user `Scripts` directory on `PATH`. If `death-star` is not found after editable install, call the installed executable from the Python user scripts directory or use `python -m scraping.core.death_star_v2`.
