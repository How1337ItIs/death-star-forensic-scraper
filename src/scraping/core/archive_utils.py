"""Shared archival helpers for scope filtering, priority, and WARC indexing."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Pattern, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger("death_star_v2.archive_utils")

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

DEFAULT_IGNORE_PATTERNS = [
    r"^https?://(www|ssl)\.google-analytics\.com/(r/)?(__utm\.gif|collect\?)",
    r"^https?://stats\.g\.doubleclick\.net/dc\.js$",
    r"^https?://pixel\.redditmedia\.com/pixel/",
    r"^https?://(www\.)?facebook\.com/(plugins/(share_button|like(box)?)\.php|sharer/sharer\.php|dialog/(feed|share))\?",
    r"^https?://(www\.)?twitter\.com/(share\?|intent/((re)?tweet|favorite))",
    r"^https?://(www\.)?reddit\.com/(login\?dest=|submit\?|static/button/button)",
    r"^https?://mail\.google\.com/mail/",
    r"^https?://accounts\.google\.com/(SignUp|ServiceLogin|AccountChooser|a/UniversalLogin)",
    r"^https?://(www\.)?google\.com/recaptcha/(api|mailhide/d\?)",
    r"^https?://{any_start_netloc}/(wp-admin/|wp-login\.php\?)",
    r"%25252525",
]


def _read_pattern_file(path: str) -> List[str]:
    pattern_file = Path(path)
    if not pattern_file.exists():
        logger.warning(f"Ignore pattern file not found: {path}")
        return []
    patterns: List[str] = []
    for line in pattern_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if raw and not raw.startswith("#"):
            patterns.append(raw)
    return patterns


def canonicalize_url(url: str) -> Optional[str]:
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

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    query_items = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QUERY_KEYS
    ]
    query_items.sort(key=lambda item: (item[0], item[1]))
    return urlunparse((scheme, netloc, path, "", urlencode(query_items, doseq=True), ""))


@dataclass
class CrawlPolicy:
    """Browsertrix-style scope rules plus a small grab-site-inspired ignore set."""

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
        if self.exclude_regex:
            try:
                self._exclude_re = re.compile(self.exclude_regex)
            except re.error as exc:
                logger.warning(f"Invalid exclude regex {self.exclude_regex!r}: {exc}")

        patterns: List[str] = []
        if self.use_default_ignore_set:
            patterns.extend(DEFAULT_IGNORE_PATTERNS)
        patterns.extend(self.ignore_patterns)
        if self.ignore_patterns_file:
            patterns.extend(_read_pattern_file(self.ignore_patterns_file))

        for pattern in patterns:
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
    parsed = urlparse(url)
    path = parsed.path.lower()
    score = 1000 - (depth * 120)
    score += 80 if parsed.netloc.lower() == (target_netloc or "").lower() else -160
    if path in {"", "/"}:
        score += 40
    if any(token in path for token in ("/blog", "/article", "/news", "/docs", "/research")):
        score += 30
    if any(token in path for token in ("/login", "/signup", "/checkout", "/cart", "/share", "/wp-admin")):
        score -= 140
    if parsed.query:
        score -= 20
    if re.search(r"\.(zip|exe|dmg|mp4|mp3|avi|mkv|mov|png|jpg|jpeg|gif|webp|svg|pdf)$", path):
        score -= 180
    return int(score)


def _warc_date_to_timestamp(warc_date: str) -> str:
    if not warc_date:
        return "19700101000000"
    try:
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


def _to_surt(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or parsed.netloc.split(":")[0]).lower().strip(".")
    host_surt = ",".join(reversed([part for part in host.split(".") if part]))
    port = parsed.port
    include_port = port and not (
        (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
    )
    port_suffix = f":{port}" if include_port else ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host_surt}{port_suffix}){parsed.path or '/'}{query}"


def generate_cdxj_index(warc_path: Path, output_dir: Optional[Path] = None) -> Optional[str]:
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
                index_doc = {
                    "url": canonical,
                    "recordType": record.rec_type,
                    "filename": warc_path.name,
                }
                if record.http_headers:
                    status_code = getattr(record.http_headers, "statuscode", "")
                    if status_code:
                        index_doc["status"] = str(status_code)
                    content_type = record.http_headers.get_header("Content-Type")
                    if content_type:
                        index_doc["mime"] = content_type.split(";")[0].strip()
                entries.append(
                    (
                        _to_surt(canonical),
                        _warc_date_to_timestamp(record.rec_headers.get_header("WARC-Date")),
                        index_doc,
                    )
                )
    except Exception as exc:
        logger.warning(f"CDXJ generation failed for {warc_path}: {exc}")
        return None

    entries.sort(key=lambda item: (item[0], item[1]))
    with open(output_path, "w", encoding="utf-8") as f:
        for surt_key, ts, index_doc in entries:
            f.write(f"{surt_key} {ts} {json.dumps(index_doc, separators=(',', ':'), sort_keys=True)}\n")
    return str(output_path)
