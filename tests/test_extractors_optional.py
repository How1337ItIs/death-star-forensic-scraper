from __future__ import annotations

from pathlib import Path

import pytest

from scraping.core.extractors import run_asset_extractors, run_page_extractors


def test_scrapling_extractor_when_installed(tmp_path: Path):
    pytest.importorskip("scrapling")
    html = "<html><head><title>Fixture</title></head><body><h1>Hello</h1><a href='/a'>A</a></body></html>"
    result = run_page_extractors(
        html,
        "http://example.test/",
        tmp_path,
        "fixture",
        requested="scrapling",
    )
    extractor = result["extractors"][0]
    assert extractor["available"] is True
    assert extractor["error"] is None
    assert Path(extractor["output_path"]).exists()


def test_crawl4ai_extractor_when_installed(tmp_path: Path):
    pytest.importorskip("crawl4ai")
    html = "<html><head><title>Fixture</title></head><body><h1>Hello</h1><p>World</p></body></html>"
    result = run_page_extractors(
        html,
        "http://example.test/",
        tmp_path,
        "fixture",
        requested="crawl4ai",
    )
    extractor = result["extractors"][0]
    assert extractor["available"] is True
    assert extractor["error"] is None
    assert Path(extractor["output_path"]).exists()


def test_asset_extractors_when_installed(tmp_path: Path):
    pytest.importorskip("markitdown")
    pytest.importorskip("docling")
    asset = tmp_path / "asset.txt"
    asset.write_text("hello optional asset extraction", encoding="utf-8")
    result = run_asset_extractors(asset, tmp_path / "extract", requested="markitdown,docling")
    assert len(result["outputs"]) == 2
    assert all(Path(path).exists() for path in result["outputs"])
