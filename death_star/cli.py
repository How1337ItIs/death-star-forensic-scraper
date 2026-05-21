"""Compatibility CLI that delegates to the canonical V2 implementation."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path():
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main():
    _ensure_src_on_path()
    from scraping.core.death_star_v2 import main as canonical_main

    return canonical_main()


if __name__ == "__main__":
    main()
