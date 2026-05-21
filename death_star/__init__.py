"""Death Star package compatibility exports for the canonical V2 engine."""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "3.0.0"
__author__ = "Deadhead-LLM Project"

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scraping.core.death_star_v2 import DeathStarV2, ScrapeConfig, ScrapedPage  # noqa: E402

DeathStar = DeathStarV2

__all__ = [
    "__version__",
    "DeathStar",
    "DeathStarV2",
    "ScrapeConfig",
    "ScrapedPage",
]
