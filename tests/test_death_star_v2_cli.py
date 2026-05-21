from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fixture_server import FixtureServer

ROOT = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else src + os.pathsep + env["PYTHONPATH"]
    return env


def _run_cli(*args: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scraping.core.death_star_v2", *args],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_help_and_doctor():
    help_result = _run_cli("--help")
    assert help_result.returncode == 0
    assert "Death Star V2" in help_result.stdout

    doctor = _run_cli("--doctor")
    assert doctor.returncode == 0
    assert "Death Star V2 Doctor" in doctor.stdout
    assert "Playwright" in doctor.stdout
    assert "Browsertrix Docker" in doctor.stdout


def test_smart_fixture_scrape_writes_manifest(tmp_path: Path):
    with FixtureServer() as server:
        output_dir = tmp_path / "output"
        result = _run_cli(
            "--target",
            f"{server.base_url}/static",
            "--mode",
            "smart",
            "--max-pages",
            "1",
            "--depth",
            "0",
            "--delay",
            "0",
            "--output",
            str(output_dir),
        )

    assert result.returncode == 0, result.stderr
    manifests = list(output_dir.glob("*/manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["target"].endswith("/static")
    assert manifest["normalized_final_url"].endswith("/static")
    assert manifest["pages_scraped"] == 1
    assert manifest["secrets_present"] == {"cookies": False, "proxy": False, "auth": False}
    assert manifest["output_paths"]["events"] == "events.jsonl"
    assert "backend_list" in manifest
    assert manifest["crawl_stats"]["effective_backend"] == "native"
    assert (manifests[0].parent / "events.jsonl").exists()
    assert (manifests[0].parent / "tool_versions.json").exists()
    assert (manifests[0].parent / "backend_report.json").exists()
    assert list((manifests[0].parent / "extract" / "pages").glob("*.extractors.json"))


def test_optional_crawlee_degrades_to_native(tmp_path: Path):
    with FixtureServer() as server:
        result = _run_cli(
            "--target",
            f"{server.base_url}/static",
            "--mode",
            "smart",
            "--crawl-backend",
            "crawlee",
            "--max-pages",
            "1",
            "--depth",
            "0",
            "--delay",
            "0",
            "--output",
            str(tmp_path / "output"),
        )

    assert result.returncode == 0, result.stderr
    manifest_path = next((tmp_path / "output").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["crawl_backend"]["requested"] == "crawlee"
    assert manifest["crawl_backend"]["effective"] == "native"
    assert any("crawlee" in warning.lower() for warning in manifest["warnings"])


def test_replay_reports_missing_archives(tmp_path: Path):
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    result = _run_cli("replay", str(run_dir))
    assert result.returncode == 1
    assert "No WARC/ARC/WACZ archives found" in result.stdout
    assert (run_dir / "replay" / "pywb_replay.json").exists()
