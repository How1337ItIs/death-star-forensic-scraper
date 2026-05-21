"""Optional extraction registry for Death Star V2 page and asset outputs."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ExtractorOutput:
    name: str
    available: bool
    output_path: Optional[str] = None
    content_length: int = 0
    title: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _selected(requested: str, defaults: Iterable[str]) -> List[str]:
    requested = (requested or "auto").strip().lower()
    if requested in {"", "auto"}:
        return list(defaults)
    return [item.strip().lower() for item in requested.split(",") if item.strip()]


def _safe_text_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip()).strip("._-")
    return cleaned or "page"


def run_page_extractors(
    html: str,
    url: str,
    output_dir: Path,
    base_name: str,
    requested: str = "auto",
) -> Dict[str, Any]:
    """Run available page extractors and write compare-friendly outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = _selected(requested, ["trafilatura", "readability", "extruct", "markdownify"])
    outputs: List[ExtractorOutput] = []

    for name in selected:
        if name == "trafilatura":
            outputs.append(_extract_trafilatura(html, url, output_dir, base_name))
        elif name == "readability":
            outputs.append(_extract_readability(html, output_dir, base_name))
        elif name == "extruct":
            outputs.append(_extract_extruct(html, url, output_dir, base_name))
        elif name in {"markdownify", "html2text"}:
            outputs.append(_extract_markdown(html, output_dir, base_name, name))
        elif name == "crawl4ai":
            outputs.append(_extract_crawl4ai(html, url, output_dir, base_name))
        elif name == "scrapling":
            outputs.append(_extract_scrapling(html, url, output_dir, base_name))
        else:
            outputs.append(ExtractorOutput(name=name, available=False, error="unknown extractor"))

    primary = _choose_primary(outputs)
    summary = {
        "url": url,
        "extractors": [output.__dict__ for output in outputs],
        "chosen_primary_text": primary.output_path if primary else None,
        "chosen_primary_extractor": primary.name if primary else None,
    }
    summary_path = output_dir / f"{_safe_text_name(base_name)}.extractors.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def run_asset_extractors(
    asset_path: Path,
    output_dir: Path,
    requested: str = "auto",
) -> Dict[str, Any]:
    """Run optional document/media extractors for downloaded assets."""
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = _selected(requested, ["markitdown", "docling"])
    base_name = _safe_text_name(asset_path.stem)
    outputs: List[ExtractorOutput] = []

    for name in selected:
        if name == "markitdown":
            outputs.append(_extract_markitdown(asset_path, output_dir, base_name))
        elif name == "docling":
            outputs.append(_extract_docling(asset_path, output_dir, base_name))
        else:
            outputs.append(ExtractorOutput(name=name, available=False, error="unknown asset extractor"))

    summary = {
        "asset_path": str(asset_path),
        "extractors": [output.__dict__ for output in outputs],
        "outputs": [output.output_path for output in outputs if output.output_path],
    }
    summary_path = output_dir / f"{base_name}.asset_extractors.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _choose_primary(outputs: List[ExtractorOutput]) -> Optional[ExtractorOutput]:
    candidates = [
        output
        for output in outputs
        if output.available and output.output_path and output.content_length > 0 and not output.error
    ]
    if not candidates:
        return None
    preferred = {"trafilatura": 4, "readability": 3, "markdownify": 2, "html2text": 1}
    return max(candidates, key=lambda output: (preferred.get(output.name, 0), output.content_length))


def _extract_trafilatura(html: str, url: str, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("trafilatura"):
        return ExtractorOutput(name="trafilatura", available=False)
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
        ) or ""
        path = output_dir / f"{_safe_text_name(base_name)}.content.trafilatura.md"
        path.write_text(text, encoding="utf-8")
        return ExtractorOutput(
            name="trafilatura",
            available=True,
            output_path=str(path),
            content_length=len(text),
        )
    except Exception as exc:
        return ExtractorOutput(name="trafilatura", available=True, error=str(exc))


def _extract_readability(html: str, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("readability"):
        return ExtractorOutput(name="readability", available=False)
    try:
        from markdownify import markdownify as md
        from readability import Document

        doc = Document(html)
        content = md(doc.summary(html_partial=True))
        path = output_dir / f"{_safe_text_name(base_name)}.content.readability.md"
        path.write_text(content, encoding="utf-8")
        return ExtractorOutput(
            name="readability",
            available=True,
            output_path=str(path),
            content_length=len(content),
            title=doc.short_title(),
        )
    except Exception as exc:
        return ExtractorOutput(name="readability", available=True, error=str(exc))


def _extract_extruct(html: str, url: str, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("extruct"):
        return ExtractorOutput(name="extruct", available=False)
    try:
        import extruct

        data = extruct.extract(html, base_url=url, syntaxes=["json-ld", "microdata", "opengraph", "rdfa"])
        path = output_dir / f"{_safe_text_name(base_name)}.structured.extruct.json"
        payload = json.dumps(data, indent=2, default=str)
        path.write_text(payload, encoding="utf-8")
        return ExtractorOutput(
            name="extruct",
            available=True,
            output_path=str(path),
            content_length=len(payload),
            metadata={"syntax_counts": {key: len(value or []) for key, value in data.items()}},
        )
    except Exception as exc:
        return ExtractorOutput(name="extruct", available=True, error=str(exc))


def _extract_markdown(html: str, output_dir: Path, base_name: str, name: str) -> ExtractorOutput:
    module_name = "markdownify" if name == "markdownify" else "html2text"
    if not _has_module(module_name):
        return ExtractorOutput(name=name, available=False)
    try:
        if name == "markdownify":
            from markdownify import markdownify as md

            text = md(html)
        else:
            import html2text

            converter = html2text.HTML2Text()
            converter.ignore_links = False
            text = converter.handle(html)
        path = output_dir / f"{_safe_text_name(base_name)}.content.{name}.md"
        path.write_text(text, encoding="utf-8")
        return ExtractorOutput(
            name=name,
            available=True,
            output_path=str(path),
            content_length=len(text),
        )
    except Exception as exc:
        return ExtractorOutput(name=name, available=True, error=str(exc))


def _run_async_in_thread(coro):
    result: Dict[str, Any] = {}

    def runner():
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result["value"] = asyncio.run(coro)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _extract_crawl4ai(html: str, url: str, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("crawl4ai"):
        return ExtractorOutput(name="crawl4ai", available=False)
    try:
        from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

        async def run():
            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                only_text=False,
                verbose=False,
                word_count_threshold=1,
            )
            async with AsyncWebCrawler() as crawler:
                return await crawler.arun(url="raw://" + html, config=config)

        result = _run_async_in_thread(run())
        markdown = getattr(result, "markdown", "") or ""
        if not isinstance(markdown, str):
            markdown = getattr(markdown, "raw_markdown", "") or str(markdown)
        data = {
            "url": url,
            "success": getattr(result, "success", None),
            "title": getattr(result, "metadata", {}).get("title") if getattr(result, "metadata", None) else None,
            "links": getattr(result, "links", None),
            "metadata": getattr(result, "metadata", None),
            "error": getattr(result, "error_message", None),
        }
        md_path = output_dir / f"{_safe_text_name(base_name)}.content.crawl4ai.md"
        md_path.write_text(markdown, encoding="utf-8")
        json_path = output_dir / f"{_safe_text_name(base_name)}.crawl4ai.json"
        json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return ExtractorOutput(
            name="crawl4ai",
            available=True,
            output_path=str(md_path),
            content_length=len(markdown),
            title=data.get("title"),
            error=data.get("error") if not markdown else None,
            metadata={"summary_path": str(json_path), "success": data.get("success")},
        )
    except Exception as exc:
        return ExtractorOutput(name="crawl4ai", available=True, error=str(exc))


def _extract_scrapling(html: str, url: str, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("scrapling"):
        return ExtractorOutput(name="scrapling", available=False)
    try:
        from scrapling import Selector

        selector = Selector(content=html, url=url)
        title = selector.css("title::text").get()
        text = selector.get_all_text()
        links = []
        for link in selector.css("a"):
            href = link.attrib.get("href")
            if href:
                links.append(selector.urljoin(href))
        data = {
            "url": url,
            "title": title,
            "text": text,
            "links": links,
        }
        path = output_dir / f"{_safe_text_name(base_name)}.content.scrapling.json"
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return ExtractorOutput(
            name="scrapling",
            available=True,
            output_path=str(path),
            content_length=len(text or ""),
            title=title,
            metadata={"links_count": len(links)},
        )
    except Exception as exc:
        return ExtractorOutput(name="scrapling", available=True, error=str(exc))


def _extract_markitdown(asset_path: Path, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("markitdown"):
        return ExtractorOutput(name="markitdown", available=False)
    try:
        from markitdown import MarkItDown

        result = MarkItDown().convert(str(asset_path))
        text = getattr(result, "text_content", "") or str(result)
        path = output_dir / f"{base_name}.content.markitdown.md"
        path.write_text(text, encoding="utf-8")
        return ExtractorOutput(
            name="markitdown",
            available=True,
            output_path=str(path),
            content_length=len(text),
        )
    except Exception as exc:
        return ExtractorOutput(name="markitdown", available=True, error=str(exc))


def _extract_docling(asset_path: Path, output_dir: Path, base_name: str) -> ExtractorOutput:
    if not _has_module("docling"):
        return ExtractorOutput(name="docling", available=False)
    try:
        from docling.document_converter import DocumentConverter

        result = DocumentConverter().convert(str(asset_path))
        document = getattr(result, "document", None)
        text = document.export_to_markdown() if document else str(result)
        path = output_dir / f"{base_name}.content.docling.md"
        path.write_text(text, encoding="utf-8")
        return ExtractorOutput(
            name="docling",
            available=True,
            output_path=str(path),
            content_length=len(text),
        )
    except Exception as exc:
        return ExtractorOutput(name="docling", available=True, error=str(exc))
