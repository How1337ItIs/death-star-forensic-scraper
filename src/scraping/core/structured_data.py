"""
Structured Data Extractor — Extract JSON-LD, microdata, RDFa, OpenGraph, and more.

Extracts machine-readable structured data from HTML pages, including:
- JSON-LD (Schema.org)
- Microdata (Schema.org)
- RDFa
- OpenGraph meta tags
- Twitter Card meta tags
- Dublin Core metadata
- Microformats

Requires:
    pip install extruct  (for JSON-LD, microdata, RDFa, microformats)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger("death_star_v2.structured_data")


class StructuredDataExtractor:
    """Extract all forms of structured data from HTML.

    Usage:
        extractor = StructuredDataExtractor()
        data = extractor.extract(html, url="https://example.com")
        print(data["json_ld"])       # JSON-LD objects
        print(data["opengraph"])     # OpenGraph tags
        print(data["meta"])          # All meta tags
    """

    def extract(self, html: str, url: str = "") -> Dict[str, Any]:
        """Extract all structured data from HTML.

        Returns dict with keys:
            json_ld, microdata, rdfa, opengraph, twitter_card,
            dublin_core, microformat, meta_tags
        """
        result = {
            "json_ld": [],
            "microdata": [],
            "rdfa": [],
            "opengraph": {},
            "twitter_card": {},
            "dublin_core": {},
            "microformat": [],
            "meta_tags": {},
        }

        # Try extruct first (handles JSON-LD, microdata, RDFa, OpenGraph, microformats)
        try:
            import extruct
            extracted = extruct.extract(
                html,
                base_url=url,
                syntaxes=[
                    "json-ld",
                    "microdata",
                    "rdfa",
                    "opengraph",
                    "microformat",
                    "dublincore",
                ],
                uniform=True,
            )
            result["json_ld"] = extracted.get("json-ld", [])
            result["microdata"] = extracted.get("microdata", [])
            result["rdfa"] = extracted.get("rdfa", [])
            result["opengraph"] = extracted.get("opengraph", [])
            result["microformat"] = extracted.get("microformat", [])
            result["dublin_core"] = extracted.get("dublincore", [])
            logger.debug(
                f"extruct extracted: {sum(len(v) if isinstance(v, list) else 1 for v in result.values())} items"
            )
        except ImportError:
            logger.debug("extruct not installed, falling back to manual extraction")
            # Manual fallback for JSON-LD
            result["json_ld"] = self._extract_json_ld(html)
            result["opengraph"] = self._extract_opengraph(html)

        # Always extract Twitter Card and meta tags (extruct doesn't cover Twitter Cards)
        result["twitter_card"] = self._extract_twitter_card(html)
        result["meta_tags"] = self._extract_meta_tags(html)

        return result

    def _extract_json_ld(self, html: str) -> List[Dict]:
        """Manually extract JSON-LD from script tags."""
        results = []
        pattern = re.compile(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            try:
                data = json.loads(match.group(1).strip())
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except json.JSONDecodeError:
                continue
        return results

    def _extract_opengraph(self, html: str) -> Dict[str, str]:
        """Extract OpenGraph meta tags."""
        og = {}
        pattern = re.compile(
            r'<meta\s+(?:property|name)=["\']og:([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            og[match.group(1)] = match.group(2)

        # Also check reversed attribute order
        pattern2 = re.compile(
            r'<meta\s+content=["\']([^"\']*)["\'].*?(?:property|name)=["\']og:([^"\']+)["\']',
            re.IGNORECASE,
        )
        for match in pattern2.finditer(html):
            if match.group(2) not in og:
                og[match.group(2)] = match.group(1)

        return og

    def _extract_twitter_card(self, html: str) -> Dict[str, str]:
        """Extract Twitter Card meta tags."""
        tc = {}
        pattern = re.compile(
            r'<meta\s+(?:name|property)=["\']twitter:([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            tc[match.group(1)] = match.group(2)

        pattern2 = re.compile(
            r'<meta\s+content=["\']([^"\']*)["\'].*?(?:name|property)=["\']twitter:([^"\']+)["\']',
            re.IGNORECASE,
        )
        for match in pattern2.finditer(html):
            if match.group(2) not in tc:
                tc[match.group(2)] = match.group(1)

        return tc

    def _extract_meta_tags(self, html: str) -> Dict[str, str]:
        """Extract all meta tags (name/property -> content)."""
        meta = {}

        # name="..." content="..."
        for pattern in [
            re.compile(
                r'<meta\s+name=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
                re.IGNORECASE,
            ),
            re.compile(
                r'<meta\s+content=["\']([^"\']*)["\'].*?name=["\']([^"\']+)["\']',
                re.IGNORECASE,
            ),
            re.compile(
                r'<meta\s+property=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
                re.IGNORECASE,
            ),
        ]:
            for match in pattern.finditer(html):
                key = match.group(1) if pattern == list([])[0:0] else match.group(1)
                val = match.group(2)
                # Skip og: and twitter: as they're extracted separately
                if not key.startswith(("og:", "twitter:")):
                    meta[key] = val

        return meta

    def extract_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a human-readable summary of extracted structured data."""
        summary = {
            "has_json_ld": len(data.get("json_ld", [])) > 0,
            "has_microdata": len(data.get("microdata", [])) > 0,
            "has_rdfa": len(data.get("rdfa", [])) > 0,
            "has_opengraph": len(data.get("opengraph", {})) > 0,
            "has_twitter_card": len(data.get("twitter_card", {})) > 0,
        }

        # Extract schema types from JSON-LD
        schema_types = set()
        for item in data.get("json_ld", []):
            if isinstance(item, dict) and "@type" in item:
                t = item["@type"]
                if isinstance(t, list):
                    schema_types.update(t)
                else:
                    schema_types.add(t)
        summary["schema_types"] = list(schema_types)

        # OG title/description
        og = data.get("opengraph", {})
        if isinstance(og, list) and og:
            og = og[0] if og else {}
        if isinstance(og, dict):
            if "title" in og:
                summary["og_title"] = og["title"]
            if "description" in og:
                summary["og_description"] = og["description"]

        return summary
