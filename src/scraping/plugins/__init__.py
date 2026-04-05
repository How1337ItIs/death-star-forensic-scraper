"""
Scraping Plugins Module
=======================

Site-specific adapters for specialized scraping behavior.
"""

from .base_adapter import SiteAdapter, AdapterConfig, AdapterRegistry
from .cannabis_adapter import (
    RollitupAdapter,
    GrasscityAdapter,
    IcmagAdapter,
    GrowWeedEasyAdapter,
    LeaflyAdapter,
    Magazine420Adapter,
    CannabisNetAdapter,
    register_cannabis_adapters,
)

__all__ = [
    # Base classes
    "SiteAdapter",
    "AdapterConfig",
    "AdapterRegistry",
    # Cannabis adapters
    "RollitupAdapter",
    "GrasscityAdapter",
    "IcmagAdapter",
    "GrowWeedEasyAdapter",
    "LeaflyAdapter",
    "Magazine420Adapter",
    "CannabisNetAdapter",
    "register_cannabis_adapters",
]
