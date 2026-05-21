"""Optional backend registry and doctor reporting for Death Star V2."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import shutil
import site
import subprocess
import sysconfig
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class BackendSpec:
    name: str
    kind: str
    license: str
    source_url: str
    import_name: Optional[str] = None
    distribution_names: tuple[str, ...] = ()
    cli_names: tuple[str, ...] = ()
    risk_note: str = ""


BACKENDS: tuple[BackendSpec, ...] = (
    BackendSpec(
        name="Playwright",
        kind="browser",
        license="Apache-2.0",
        source_url="https://github.com/microsoft/playwright-python",
        import_name="playwright",
        distribution_names=("playwright",),
        cli_names=("playwright",),
    ),
    BackendSpec(
        name="Patchright",
        kind="browser",
        license="Apache-2.0",
        source_url="https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python",
        import_name="patchright",
        distribution_names=("patchright",),
        cli_names=("patchright",),
        risk_note="Stealth browser engine; use only for lawful testing/research.",
    ),
    BackendSpec(
        name="Camoufox",
        kind="browser",
        license="MPL-2.0",
        source_url="https://github.com/daijro/camoufox",
        import_name="camoufox",
        distribution_names=("camoufox",),
        cli_names=("camoufox",),
        risk_note="Firefox-based stealth profile; optional local dependency.",
    ),
    BackendSpec(
        name="nodriver",
        kind="browser",
        license="AGPL-3.0",
        source_url="https://github.com/ultrafunkamsterdam/nodriver",
        import_name="nodriver",
        distribution_names=("nodriver",),
        risk_note="AGPL package; keep optional and do not vendor into core.",
    ),
    BackendSpec(
        name="curl_cffi",
        kind="fetch",
        license="MIT",
        source_url="https://github.com/lexiforest/curl_cffi",
        import_name="curl_cffi",
        distribution_names=("curl_cffi", "curl-cffi"),
    ),
    BackendSpec(
        name="browserforge",
        kind="fetch",
        license="MIT",
        source_url="https://github.com/daijro/browserforge",
        import_name="browserforge",
        distribution_names=("browserforge",),
    ),
    BackendSpec(
        name="Crawl4AI",
        kind="extract",
        license="Apache-2.0",
        source_url="https://github.com/unclecode/crawl4ai",
        import_name="crawl4ai",
        distribution_names=("crawl4ai",),
        cli_names=("crawl4ai",),
    ),
    BackendSpec(
        name="Scrapling",
        kind="crawl",
        license="BSD-3-Clause",
        source_url="https://github.com/D4Vinci/Scrapling",
        import_name="scrapling",
        distribution_names=("scrapling",),
    ),
    BackendSpec(
        name="Crawlee Python",
        kind="crawl",
        license="Apache-2.0",
        source_url="https://github.com/apify/crawlee-python",
        import_name="crawlee",
        distribution_names=("crawlee",),
    ),
    BackendSpec(
        name="MarkItDown",
        kind="extract",
        license="MIT",
        source_url="https://github.com/microsoft/markitdown",
        import_name="markitdown",
        distribution_names=("markitdown",),
        cli_names=("markitdown",),
    ),
    BackendSpec(
        name="Docling",
        kind="extract",
        license="MIT",
        source_url="https://github.com/docling-project/docling",
        import_name="docling",
        distribution_names=("docling",),
        cli_names=("docling",),
    ),
    BackendSpec(
        name="ArchiveBox",
        kind="archive",
        license="MIT",
        source_url="https://github.com/ArchiveBox/ArchiveBox",
        import_name="archivebox",
        distribution_names=("archivebox",),
        cli_names=("archivebox",),
        risk_note="Native CLI may not run on Windows; Death Star falls back to archivebox/archivebox Docker when Docker is available.",
    ),
    BackendSpec(
        name="Browsertrix Docker",
        kind="archive",
        license="AGPL-3.0",
        source_url="https://github.com/webrecorder/browsertrix-crawler",
        cli_names=("docker",),
        risk_note="AGPL application; use only through Docker/CLI boundaries.",
    ),
    BackendSpec(
        name="SingleFile",
        kind="package",
        license="AGPL-3.0",
        source_url="https://github.com/gildas-lormeau/SingleFile",
        cli_names=("single-file", "single-file-cli"),
        risk_note="AGPL CLI; invoke externally and do not vendor.",
    ),
    BackendSpec(
        name="wacz",
        kind="package",
        license="Apache-2.0",
        source_url="https://github.com/webrecorder/py-wacz",
        import_name="wacz",
        distribution_names=("wacz",),
        cli_names=("wacz",),
    ),
    BackendSpec(
        name="pywb",
        kind="replay",
        license="GPL-3.0-or-later",
        source_url="https://github.com/webrecorder/pywb",
        import_name="pywb",
        distribution_names=("pywb",),
        cli_names=("wayback", "wb-manager"),
        risk_note="GPL replay server; optional external tool only.",
    ),
    BackendSpec(
        name="wget",
        kind="fetch",
        license="GPL-3.0-or-later",
        source_url="https://www.gnu.org/software/wget/",
        cli_names=("wget",),
        risk_note="GPL CLI; invoked externally.",
    ),
    BackendSpec(
        name="yt-dlp",
        kind="extract",
        license="Unlicense",
        source_url="https://github.com/yt-dlp/yt-dlp",
        import_name="yt_dlp",
        distribution_names=("yt-dlp",),
        cli_names=("yt-dlp",),
    ),
)


def _module_available(import_name: Optional[str]) -> bool:
    if not import_name:
        return False
    return importlib.util.find_spec(import_name) is not None


def _cli_path(cli_names: Iterable[str]) -> Optional[str]:
    script_dirs = [sysconfig.get_path("scripts")]
    try:
        script_dirs.append(str(Path(site.getusersitepackages()).parent / "Scripts"))
    except Exception:
        pass
    script_dirs = [path for path in script_dirs if path]
    for cli_name in cli_names:
        path = shutil.which(cli_name)
        if path:
            return path
        for scripts_dir in script_dirs:
            candidates = [Path(scripts_dir) / cli_name]
            if not cli_name.lower().endswith(".exe"):
                candidates.append(Path(scripts_dir) / f"{cli_name}.exe")
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate)
    return None


def _package_version(distribution_names: Iterable[str]) -> Optional[str]:
    for distribution_name in distribution_names:
        try:
            return importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _cli_version(cli_path: Optional[str]) -> Optional[str]:
    if not cli_path:
        return None
    candidates = ([cli_path, "--version"], [cli_path, "version"])
    for cmd in candidates:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception:
            continue
        output = (result.stdout or result.stderr or "").strip().splitlines()
        if result.returncode == 0 and output:
            return output[0][:200]
    return None


def inspect_backend(spec: BackendSpec) -> Dict[str, Any]:
    module_ok = _module_available(spec.import_name)
    cli_path = _cli_path(spec.cli_names)
    package_version = _package_version(spec.distribution_names)
    version = package_version or _cli_version(cli_path)
    return {
        **asdict(spec),
        "available": bool(module_ok or cli_path),
        "module_available": module_ok,
        "cli_path": cli_path,
        "version": version,
    }


def get_backend_report() -> Dict[str, Any]:
    backends = [inspect_backend(spec) for spec in BACKENDS]
    return {
        "schema_version": 1,
        "backends": backends,
        "available": [item["name"] for item in backends if item["available"]],
        "missing": [item["name"] for item in backends if not item["available"]],
    }


def tool_versions_from_report(report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    report = report or get_backend_report()
    tools: Dict[str, Any] = {}
    for item in report["backends"]:
        tools[item["name"]] = {
            "available": item["available"],
            "version": item.get("version"),
            "cli_path": item.get("cli_path"),
            "kind": item["kind"],
            "source_url": item["source_url"],
            "license": item["license"],
        }
    return {"schema_version": 1, "tools": tools}


def write_backend_reports(output_dir: Path, report: Optional[Dict[str, Any]] = None) -> Dict[str, Path]:
    report = report or get_backend_report()
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_report_path = output_dir / "backend_report.json"
    tool_versions_path = output_dir / "tool_versions.json"
    backend_report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    tool_versions_path.write_text(
        json.dumps(tool_versions_from_report(report), indent=2, default=str),
        encoding="utf-8",
    )
    return {"backend_report": backend_report_path, "tool_versions": tool_versions_path}


def format_doctor(report: Optional[Dict[str, Any]] = None) -> str:
    report = report or get_backend_report()
    lines = ["Death Star V2 Doctor", ""]
    for item in report["backends"]:
        status = "installed" if item["available"] else "missing"
        version = item.get("version") or "-"
        cli = item.get("cli_path") or "-"
        note = f" ({item['risk_note']})" if item.get("risk_note") else ""
        lines.append(f"{status:9} {item['kind']:8} {item['name']:20} {version} [{cli}]{note}")
    lines.extend(
        [
            "",
            f"Available: {len(report['available'])}",
            f"Missing:   {len(report['missing'])}",
        ]
    )
    return "\n".join(lines)
