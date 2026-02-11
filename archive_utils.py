#!/usr/bin/env python3
"""
Shared archival helpers for crawl policy and WARC indexing.

Patterns are inspired by grab-site (ignore sets), Scrapy (priority queueing),
and Browsertrix/py-wacz (CDXJ indexing for replay workflows).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Pattern, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger("archive_utils")

TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref_src",
    "ref_url",
    "_ga",
    "_gl",
}

# Curated subset of grab-site's global ignore set: tracking, share loops, auth walls.
DEFAULT_IGNORE_PATTERNS = [
    r"^https?://(www|ssl)\.google-analytics\.com/(r/)?(__utm\.gif|collect\?)",
    r"^https?://stats\.g\.doubleclick\.net/dc\.js$",
    r"^https?://pixel\.redditmedia\.com/pixel/",
    r"^https?://(www\.)?facebook\.com/(plugins/(share_button|like(box)?)\.php|sharer/sharer\.php|dialog/(feed|share))\?",
    r"^https?://(www\.)?twitter\.com/(share\?|intent/((re)?tweet|favorite))",
    r"^https?://platform\d?\.twitter\.com/widgets/tweet_button\.html\?",
    r"^https?://(www\.)?linkedin\.com/(cws/share|shareArticle)\?",
    r"^https?://([^\.]+\.)?pinterest\.com/pin/create/",
    r"^https?://(www\.)?reddit\.com/(login\?dest=|submit\?|static/button/button)",
    r"^https?://(www\.)?blogger\.com/(navbar\.g|post-edit\.g|delete-comment\.g|share-post\.g|email-post\.g)\?",
    r"^https?://{any_start_netloc}/.+[\?&]share=[a-z]{4,}",
    r"^https?://{any_start_netloc}/.+[\?&](replyto(com)?|like_comment)=\d+",
    r"^https?://{any_start_netloc}/.+\?showComment(=|%5C)\d+",
    r"^https?://mail\.google\.com/mail/",
    r"^https?://accounts\.google\.com/(SignUp|ServiceLogin|AccountChooser|a/UniversalLogin)",
    r"^https?://(www\.)?google\.com/recaptcha/(api|mailhide/d\?)",
    r"^https?://{any_start_netloc}/(wp-admin/|wp-login\.php\?)",
    r"^https?://[^/]+\.facebook\.com/login\.php",
    r"^https?://{any_start_netloc}/.+/jetpack-comment/\?blogid=\d+&postid=\d+",
    r"^https?://{any_start_netloc}/.+/quote-comment-\d+/$",
    r"%25252525",
]


def _read_pattern_file(path: str) -> List[str]:
    pattern_file = Path(path)
    if not pattern_file.exists():
        logger.warning(f"Ignore pattern file not found: {path}")
        return []

    patterns: List[str] = []
    try:
        for line in pattern_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            patterns.append(raw)
    except Exception as exc:
        logger.warning(f"Failed reading ignore patterns from {path}: {exc}")
    return patterns


def canonicalize_url(url: str) -> Optional[str]:
    """
    Normalize URL for queue dedupe and stable crawl behavior.

    - keep only http/https
    - remove fragments
    - lowercase scheme/netloc
    - remove default ports
    - trim common tracking query params
    - sort query params
    """
    raw = (url or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    kept_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QUERY_KEYS
    ]
    kept_query.sort(key=lambda item: (item[0], item[1]))
    query = urlencode(kept_query, doseq=True)

    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized


def to_surt(url: str) -> str:
    """Create a simple SURT key for CDXJ output."""
    parsed = urlparse(url)
    host = parsed.hostname or parsed.netloc.split(":")[0]
    host = host.lower().strip(".")
    host_parts = [part for part in host.split(".") if part]
    host_surt = ",".join(reversed(host_parts))

    port = parsed.port
    include_port = port and not (
        (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
    )
    port_suffix = f":{port}" if include_port else ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""

    return f"{host_surt}{port_suffix}){path}{query}"


def _warc_date_to_timestamp(warc_date: str) -> str:
    if not warc_date:
        return "19700101000000"

    try:
        # warc uses ISO 8601, often with trailing Z.
        dt = datetime.fromisoformat(warc_date.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.strptime(warc_date[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return "19700101000000"

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S")


@dataclass
class CrawlPolicy:
    """
    Crawl filtering policy inspired by Browsertrix scope options + grab-site ignores.
    """

    include_regex: Optional[str] = None
    exclude_regex: Optional[str] = None
    ignore_patterns: List[str] = field(default_factory=list)
    ignore_patterns_file: Optional[str] = None
    use_default_ignore_set: bool = True
    max_url_length: int = 4096
    _include_re: Optional[Pattern] = field(default=None, init=False, repr=False)
    _exclude_re: Optional[Pattern] = field(default=None, init=False, repr=False)
    _ignore_res: List[Pattern] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        if self.include_regex:
            try:
                self._include_re = re.compile(self.include_regex)
            except re.error as exc:
                logger.warning(f"Invalid include regex {self.include_regex!r}: {exc}")
                self._include_re = None

        if self.exclude_regex:
            try:
                self._exclude_re = re.compile(self.exclude_regex)
            except re.error as exc:
                logger.warning(f"Invalid exclude regex {self.exclude_regex!r}: {exc}")
                self._exclude_re = None

        all_patterns: List[str] = []
        if self.use_default_ignore_set:
            all_patterns.extend(DEFAULT_IGNORE_PATTERNS)
        all_patterns.extend(self.ignore_patterns)
        if self.ignore_patterns_file:
            all_patterns.extend(_read_pattern_file(self.ignore_patterns_file))

        for pattern in all_patterns:
            try:
                self._ignore_res.append(re.compile(pattern))
            except re.error as exc:
                logger.debug(f"Skipping invalid ignore regex {pattern!r}: {exc}")

    def evaluate_url(
        self,
        raw_url: str,
        target_netloc: str,
        follow_external: bool,
        is_seed: bool = False,
    ) -> Tuple[bool, Optional[str], str]:
        """
        Return (allow, canonical_url, reason).
        """
        canonical = canonicalize_url(raw_url)
        if not canonical:
            return False, None, "invalid-url"

        if len(canonical) > self.max_url_length:
            return False, None, "too-long"

        parsed = urlparse(canonical)
        netloc = parsed.netloc.lower()

        if not is_seed:
            if not follow_external and target_netloc and netloc != target_netloc.lower():
                return False, None, "external-domain"

            if self._include_re and not self._include_re.search(canonical):
                return False, None, "scope-include-miss"

            if self._exclude_re and self._exclude_re.search(canonical):
                return False, None, "scope-excluded"

            for pattern in self._ignore_res:
                pattern_text = pattern.pattern
                if "{any_start_netloc}" in pattern_text:
                    pattern_text = pattern_text.replace("{any_start_netloc}", re.escape(target_netloc))
                    try:
                        if re.search(pattern_text, canonical):
                            return False, None, "ignore-pattern"
                    except re.error:
                        continue
                elif pattern.search(canonical):
                    return False, None, "ignore-pattern"

        return True, canonical, "ok"


def score_crawl_priority(url: str, target_netloc: str, depth: int) -> int:
    """
    Score URL priority similar to Scrapy-style frontier weighting.
    Higher score means fetched sooner.
    """
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = (parsed.query or "").lower()

    score = 1000 - (depth * 120)

    if parsed.netloc.lower() == (target_netloc or "").lower():
        score += 80
    else:
        score -= 160

    if path in {"", "/"}:
        score += 40

    for token in ("/blog", "/article", "/news", "/docs", "/research", "/press"):
        if token in path:
            score += 30
            break

    for token in ("/login", "/signup", "/checkout", "/cart", "/share", "/wp-admin", "/account"):
        if token in path:
            score -= 140
            break

    if parsed.query:
        score -= 20

    if any(token in query for token in ("replyto", "replytocom", "share=", "utm_", "gclid", "fbclid")):
        score -= 80

    if re.search(r"\.(zip|exe|dmg|mp4|mp3|avi|mkv|mov|png|jpg|jpeg|gif|webp|svg|pdf)$", path):
        score -= 180

    return int(score)


def generate_cdxj_index(warc_path: Path, output_dir: Optional[Path] = None) -> Optional[str]:
    """
    Generate a CDXJ sidecar index for a WARC file.
    """
    try:
        from warcio.archiveiterator import ArchiveIterator
    except Exception:
        logger.warning("warcio unavailable, skipping CDXJ generation")
        return None

    warc_path = Path(warc_path)
    if not warc_path.exists():
        return None

    out_dir = Path(output_dir or warc_path.parent)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = warc_path.name
    if stem.endswith(".warc.gz"):
        stem = stem[:-8]
    elif stem.endswith(".warc"):
        stem = stem[:-5]
    output_path = out_dir / f"{stem}.cdxj"

    entries = []
    try:
        with open(warc_path, "rb") as fh:
            for record in ArchiveIterator(fh):
                if record.rec_type not in {"response", "revisit"}:
                    continue

                target_url = record.rec_headers.get_header("WARC-Target-URI")
                if not target_url:
                    continue

                canonical = canonicalize_url(target_url) or target_url
                ts = _warc_date_to_timestamp(record.rec_headers.get_header("WARC-Date"))
                index_doc = {
                    "url": canonical,
                    "recordType": record.rec_type,
                    "filename": warc_path.name,
                }

                if record.http_headers:
                    statuscode = getattr(record.http_headers, "statuscode", "")
                    if statuscode:
                        index_doc["status"] = str(statuscode)
                    content_type = record.http_headers.get_header("Content-Type")
                    if content_type:
                        index_doc["mime"] = content_type.split(";")[0].strip()

                digest = (
                    record.rec_headers.get_header("WARC-Payload-Digest")
                    or record.rec_headers.get_header("WARC-Block-Digest")
                )
                if digest:
                    index_doc["digest"] = digest

                content_length = record.rec_headers.get_header("Content-Length")
                if content_length:
                    index_doc["length"] = content_length

                entries.append((to_surt(canonical), ts, index_doc))
    except Exception as exc:
        logger.warning(f"CDXJ generation failed for {warc_path}: {exc}")
        return None

    entries.sort(key=lambda item: (item[0], item[1]))
    with open(output_path, "w", encoding="utf-8") as f:
        for surt_key, ts, index_doc in entries:
            f.write(f"{surt_key} {ts} {json.dumps(index_doc, separators=(',', ':'), sort_keys=True)}\n")

    return str(output_path)
