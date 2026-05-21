#!/usr/bin/env python3
"""Compatibility wrapper for the canonical Death Star V2 CLI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scraping.core.death_star_v2 import DeathStarV2, ScrapeConfig, ScrapedPage, main  # noqa: E402

__all__ = ["DeathStarV2", "ScrapeConfig", "ScrapedPage", "main"]


if __name__ == "__main__":
    main()
