#!/usr/bin/env python3
"""Local smoke runner for the canonical Death Star V2 CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


def _has_cli(name: str) -> bool:
    if shutil.which(name):
        return True
    script_dirs = [sysconfig.get_path("scripts")]
    try:
        script_dirs.append(str(Path(site.getusersitepackages()).parent / "Scripts"))
    except Exception:
        pass
    for scripts_dir in [path for path in script_dirs if path]:
        candidates = [Path(scripts_dir) / name]
        if not name.lower().endswith(".exe"):
            candidates.append(Path(scripts_dir) / f"{name}.exe")
        if any(path.exists() for path in candidates):
            return True
    return False


def _env() -> dict[str, str]:
    env = os.environ.copy()
    paths = [str(ROOT / "src"), str(TESTS)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def run_step(label: str, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    print(f"[smoke] {label}")
    result = subprocess.run(
        [sys.executable, "-m", "scraping.core.death_star_v2", *args],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    print(result.stdout[-1200:])
    if result.stderr:
        print(result.stderr[-1200:], file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Death Star smoke checks")
    parser.add_argument("--output", default=str(Path(tempfile.gettempdir()) / "death-star-smoke"))
    parser.add_argument("--forensic", action="store_true", help="Also run the browser forensic smoke")
    args = parser.parse_args()

    from fixture_server import FixtureServer

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_step("help", ["--help"])
    run_step("doctor", ["--doctor"])

    with FixtureServer() as server:
        run_step(
            "smart fixture scrape",
            [
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
            ],
        )
        run_step(
            "extractor comparison",
            [
                "--target",
                f"{server.base_url}/static",
                "--mode",
                "smart",
                "--extractors",
                "trafilatura,readability,extruct,markdownify",
                "--max-pages",
                "1",
                "--depth",
                "0",
                "--delay",
                "0",
                "--output",
                str(output_dir),
            ],
        )
        if args.forensic:
            forensic_args = [
                "--target",
                f"{server.base_url}/static",
                "--mode",
                "forensic",
                "--output",
                str(output_dir),
            ]
            if _has_cli("wacz"):
                forensic_args.append("--wacz")
            run_step("forensic fixture scrape", forensic_args, timeout=240)

    print(f"[smoke] output: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
