# Death Star Build Log

## 2026-05-21

### Phase 0 Baseline
- Started from a dirty worktree. Existing modified/untracked files included `README.md`, `.env`, handoff notes, Walmart scripts, cookies, and prior scrape outputs.
- Boundary for this build: do not edit `.env`, cookies, Walmart scripts, handoff docs, prior scrape outputs, or unrelated dirty files.
- Canonical candidate confirmed: `src/scraping/core/death_star_v2.py`.
- Compatibility entry points confirmed: `death_star_v2.py`, `death_star/cli.py`, and `dashboard.py`.

### Commands Run
- `git status --short`
- `rg --files`
- `Get-Content` inspections for canonical V2, root V2, package CLI, dashboard, and local Death Star scraper skill.

### Next Checkpoint
- Unify entry points on the canonical V2 module.
- Add backend registry, doctor output, and per-run artifact/report contract.

### Phase 1 Canonical V2 Unification
- `src/scraping/core/death_star_v2.py` is now the canonical CLI/API implementation.
- Root `death_star_v2.py` is a thin compatibility wrapper around `scraping.core.death_star_v2`.
- `death_star/cli.py` and `death_star/__init__.py` delegate/export the canonical V2 engine.
- `pyproject.toml` console scripts now point directly at `scraping.core.death_star_v2:main`.
- Package discovery now includes `src/scraping`.
- `dashboard.py` launches `python -m scraping.core.death_star_v2` with `PYTHONPATH=src`.

### Phase 2 Backend Registry and Doctor
- Added `src/scraping/core/backends.py`.
- Added `--doctor` output for browser, stealth, crawl, archive, package, replay, and extraction backends.
- Every run writes `backend_report.json` and `tool_versions.json`.

### Phase 3 Manifest and Output Contract
- Runs now create timestamped run directories with `manifest.json`, `events.jsonl`, backend/tool reports, and standard artifact subdirectories.
- Manifests record secret presence as booleans only.
- Added JSONL events for run start/finish, queued targets, fetch start/finish, browser escalation, optional backend skips, and extractor status.
- Fresh non-resume runs now reset checkpoint URL/content state.

### Phase 4/5/7/9 Partial Wiring
- Added `--engine auto|playwright|patchright|camoufox|nodriver`, `--headed`, `--mode watch --cdp`, behavior profiles, block rules, include/exclude scope, WACZ/CDXJ sidecars, and extractor output registry.
- Dashboard now exposes mode, engine, crawl backend, archive backend, WACZ, block ads, include/exclude, headed, CDP endpoint, and backend availability.

### Verification
- `python -m compileall src\scraping\core death_star dashboard.py death_star_v2.py`
- `python death_star_v2.py --help`
- `python death_star_v2.py --doctor`
- `python -m scraping.core.death_star_v2 --help`
- `python -m scraping.core.death_star_v2 --doctor`
- `python -m pip install -e .`
- Verified console entry through installed `death-star.exe --help` and `death-star.exe --doctor`.
- Smoke scrape: `python death_star_v2.py --target https://example.com --mode smart --max-pages 1 --depth 0 --delay 0 --output %TEMP%\death-star-smoke`

### Blockers / Notes
- `ruff` was not installed in the active Python environment, so lint did not run.
- The editable install succeeded, but this shell does not have the Python user `Scripts` directory on `PATH`; direct `death-star` failed while the installed `death-star.exe` path worked.
- Existing dirty/untracked user files remain untouched.

### Phase 5 Archive and Replay Completion
- Added Docker-only Browsertrix backend wrapper with command/provenance reporting and clean Docker-missing diagnostics.
- Switched archive mode to honor `--archive-backend native|archivebox|browsertrix`; native archive uses forensic WARC/HAR capture.
- Added ArchiveBox command reports under the run directory.
- Added `death-star replay RUN_DIR` / `python -m scraping.core.death_star_v2 replay RUN_DIR` pywb helper with clean missing-archive and missing-pywb reports.
- Added WACZ requested-but-missing warning path while preserving WARC/CDXJ outputs.

### Phase 6/7 Crawler and Extraction Completion
- Added manifest `crawl_stats` with requested/effective backend, checkpoint counts, domain status counts, rate limiter errors, and resume checkpoint path.
- Added feature-detected Crawlee degradation path; missing or not-selected Crawlee is reported without failing native crawls.
- Added asset extractor registry hooks for MarkItDown and Docling under `extract/assets/`.
- Page extractor outputs remain compare-friendly under `extract/pages/`.

### Phase 10 Testing and Smoke
- Added a local fixture server under `tests/fixture_server.py` with static, JS, sitemap, robots, JSON, GraphQL-like, asset, duplicate, broken, and slow routes.
- Added CLI tests for help, doctor, manifest output, Crawlee degradation, and replay no-archive behavior.
- Added `scripts/death_star_smoke.py` for help/doctor/local fixture/extractor smoke checks.

### Documentation Updates
- Updated `docs/VERSIONING.md` to mark canonical V2 as the only current implementation and old surfaces as wrappers.
- Added `docs/OPERATIONS.md` with install, canonical commands, modes, output contract, optional backend policy, and verification commands.

### Commands Run After Backend/Test Work
- `python -m pip install ruff`
- `python -m ruff check --fix --unsafe-fixes src\scraping\core\death_star_v2.py src\scraping\core\forensic_capture.py src\scraping\core\site_discovery.py dashboard.py`
- `python -m ruff check src\scraping\core\death_star_v2.py src\scraping\core\extractors.py tests\fixture_server.py tests\test_death_star_v2_cli.py scripts\death_star_smoke.py`
- `python -m compileall src\scraping\core\death_star_v2.py src\scraping\core\extractors.py`
- `python -m compileall src\scraping\core tests scripts\death_star_smoke.py`
- `python -m pytest tests -q`

### Current Notes
- Core tests pass without optional tools.
- Optional Browsertrix, ArchiveBox, wacz, pywb, MarkItDown, Docling, and Crawlee features are feature-detected and degrade through warnings/events/manifests.
- `README.md`, `.env`, cookies, Walmart scripts, handoff notes, and prior scrape outputs were pre-existing dirty files and were not edited for this pass.

### Optional Backend Install/Test Pass
- Installed Python optional packages: `browserforge`, `scrapling`, `crawlee`, `markitdown`, `docling`, `archivebox`, `wacz`, and `camoufox`.
- Installed SingleFile CLI with `npm install -g single-file-cli`.
- Installed Playwright/Patchright Chromium and fetched Camoufox browser binaries.
- Pulled `webrecorder/browsertrix-crawler:latest`.
- Installed pywb through uv using Python 3.12 and `setuptools<81`: `uv tool install pywb --python 3.12 --with "setuptools<81"`.
- `death-star --doctor` now reports all 18 configured optional backend entries installed.
- Verified page extractors: `trafilatura`, `readability`, `extruct`, `markdownify`, `crawl4ai`, and `scrapling`.
- Verified asset extractors: `markitdown` and `docling`.
- Verified browser engines: Playwright, Patchright escalation, and Camoufox.
- Verified Crawlee selection degrades to the canonical native queue with manifest warnings.
- Verified Browsertrix Docker backend creates WARC/WACZ/pages JSONL under the run directory.
- Verified SingleFile CLI capture.
- Verified `death-star replay RUN_DIR --prepare-only` creates a pywb collection from Browsertrix artifacts.

### Optional Backend Caveats Found
- ArchiveBox 0.7.1 installs, but the native Windows CLI fails on `os.getuid`; this is now reported as `archive_backend.ok=false` with command details in `archivebox_command.json`.
- py-wacz 0.4.9 is installed and detected, but native WACZ generation can fail on Windows ZIP path handling. Invalid partial WACZ files are removed and a `.wacz_error.json` report is written. Browsertrix Docker WACZ was verified as the working WACZ path.
- `python -m pip check` reports pre-existing/global environment conflicts plus the current Crawl4AI/Scrapling `lxml` metadata conflict. Death Star tests and extractor probes pass in this environment.

### Final Verification Before Commit
- Updated `pyproject.toml` optional extras so `.[full]` installs the resolvable optional Python backend set, with `.[crawl4ai]` and `.[scrapling]` split because their releases declare incompatible `lxml` ranges.
- Reinstalled editable package with `python -m pip install -e .[full]`.
- `python -m ruff check src\scraping\core\death_star_v2.py src\scraping\core\forensic_capture.py src\scraping\core\site_discovery.py src\scraping\core\archive_utils.py src\scraping\core\backends.py src\scraping\core\extractors.py dashboard.py death_star\cli.py death_star\__init__.py death_star_v2.py tests\fixture_server.py tests\test_death_star_v2_cli.py tests\test_extractors_optional.py scripts\death_star_smoke.py`
- `python -m compileall src\scraping\core death_star dashboard.py death_star_v2.py tests scripts\death_star_smoke.py`
- `python -m scraping.core.death_star_v2 --doctor` reports 18 available, 0 missing.
- `python death_star_v2.py --help`
- `python -m pytest tests -q` -> 7 passed, 1 warning.
- `python scripts\death_star_smoke.py --forensic --output %TEMP%\death-star-final-smoke`
- Optional probe verified Playwright, Patchright escalation, Camoufox, nodriver fallback, all page extractors, Crawlee selection, ArchiveBox manifest failure reporting, Browsertrix Docker WARC/WACZ output, pywb replay preparation, and SingleFile CLI capture.
- `python -m pip check` still reports global dependency metadata conflicts for beets/numpy, Crawl4AI/Scrapling lxml, fastapi/anyio, njsparser/typer, and spotdl/rich.

### Fix-Everything Pass
- Updated the local Codex `death-star-scraper` skill to point future agents at canonical V2 commands, `--doctor`, dashboard launch, optional extras, Docker ArchiveBox, WACZ/replay, and dirty-file safety.
- Implemented a real nodriver runtime adapter for `--engine nodriver`; it now launches nodriver, captures rendered HTML/text/links/media, and writes `method=nodriver`.
- Added ArchiveBox Docker fallback using `archivebox/archivebox:latest` when the native Windows CLI is installed but unusable. Localhost targets are translated to `host.docker.internal` for Docker.
- Added a Windows py-wacz wrapper that normalizes ZIP entry paths during native WACZ generation.
- Added WACZ local structural validation fallback for py-wacz Windows validation false negatives.
- Pulled `archivebox/archivebox:latest`.
- Tried safe dependency resolver repairs. `pip check` cannot be fully clean while the current installed package set contains incompatible release metadata: Crawl4AI vs Scrapling/njsparser on `lxml`, njsparser vs HuggingFace/Docling on `typer`, spotdl vs dashboard/Crawl4AI on FastAPI/AnyIO/Rich, and beets vs OpenCV on NumPy. The Death Star runtime checks pass with the current selected versions.
- Targeted probes passed for real nodriver scraping, native WACZ creation/structural validation, and ArchiveBox Docker archival.
