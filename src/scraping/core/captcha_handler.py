"""
CAPTCHA Handler — Detect and solve CAPTCHAs automatically.

Solving chain (tried in order, cheapest/fastest first):
1. Browser-native pass — camoufox/nodriver often pass Turnstile without solving
2. CapSolver API — reCAPTCHA v2/v3, hCaptcha, Turnstile, FunCaptcha ($0.0005/token)
3. FlareSolverr — Cloudflare-specific, returns cf_clearance cookies
4. Skip + circuit break — if no solver available

Requires:
    pip install capsolver  (optional, for CapSolver API)

Environment:
    CAPSOLVER_API_KEY=CAP-xxx  (in .env)
    FLARESOLVERR_URL=http://localhost:8191  (optional)
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("death_star_v2.captcha")


class CAPTCHAType(Enum):
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    TURNSTILE = "turnstile"
    FUNCAPTCHA = "funcaptcha"
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"
    UNKNOWN = "unknown"


@dataclass
class CAPTCHADetection:
    """Result of CAPTCHA detection."""
    detected: bool
    captcha_type: CAPTCHAType
    sitekey: Optional[str] = None
    action: Optional[str] = None  # reCAPTCHA v3 action
    page_url: Optional[str] = None
    confidence: float = 0.0


@dataclass
class CAPTCHASolution:
    """Result of CAPTCHA solving."""
    solved: bool
    token: Optional[str] = None
    cookies: Optional[Dict[str, str]] = None  # e.g. cf_clearance
    user_agent: Optional[str] = None  # UA that was used (must match for cookie reuse)
    error: Optional[str] = None
    solve_time: float = 0.0
    method: str = ""  # which solver was used


class CAPTCHADetector:
    """Detect CAPTCHAs in HTML content and HTTP responses."""

    # Signatures for each CAPTCHA type
    SIGNATURES = {
        CAPTCHAType.RECAPTCHA_V2: [
            'class="g-recaptcha"',
            'data-sitekey=',
            'google.com/recaptcha/api.js',
            'google.com/recaptcha/enterprise.js',
            'grecaptcha.execute',
        ],
        CAPTCHAType.RECAPTCHA_V3: [
            'grecaptcha.execute',
            'recaptcha/api.js?render=',
            'recaptcha/enterprise.js?render=',
        ],
        CAPTCHAType.HCAPTCHA: [
            'class="h-captcha"',
            'data-sitekey=',
            'hcaptcha.com/1/api.js',
            'h-captcha-response',
        ],
        CAPTCHAType.TURNSTILE: [
            'cf-turnstile',
            'challenges.cloudflare.com/turnstile',
            'cf-chl-widget',
            'turnstile/v0/api.js',
        ],
        CAPTCHAType.FUNCAPTCHA: [
            'funcaptcha',
            'arkoselabs.com',
            'arkose',
        ],
        CAPTCHAType.CLOUDFLARE_CHALLENGE: [
            'Just a moment...',
            'Checking your browser',
            'cf-browser-verification',
            'jschl_vc',
            'jschl_answer',
            '_cf_chl_opt',
        ],
    }

    # Sitekey extraction patterns
    SITEKEY_PATTERNS = {
        CAPTCHAType.RECAPTCHA_V2: [
            re.compile(r'data-sitekey="([^"]+)"'),
            re.compile(r"data-sitekey='([^']+)'"),
            re.compile(r'grecaptcha\.execute\(["\']([^"\']+)'),
        ],
        CAPTCHAType.RECAPTCHA_V3: [
            re.compile(r'recaptcha/api\.js\?render=([^&"\']+)'),
            re.compile(r'recaptcha/enterprise\.js\?render=([^&"\']+)'),
            re.compile(r'grecaptcha\.execute\(["\']([^"\']+)'),
        ],
        CAPTCHAType.HCAPTCHA: [
            re.compile(r'data-sitekey="([^"]+)"'),
            re.compile(r"data-sitekey='([^']+)'"),
        ],
        CAPTCHAType.TURNSTILE: [
            re.compile(r'data-sitekey="([^"]+)"'),
            re.compile(r"data-sitekey='([^']+)'"),
            re.compile(r'sitekey:\s*["\']([^"\']+)'),
        ],
    }

    def detect(self, html: str, url: str = "", headers: Optional[Dict] = None) -> CAPTCHADetection:
        """Detect if a page contains a CAPTCHA challenge."""
        if not html:
            return CAPTCHADetection(detected=False, captcha_type=CAPTCHAType.UNKNOWN)

        html_lower = html.lower()

        # Check headers for Cloudflare challenge indicators
        if headers:
            cf_mitigated = headers.get('cf-mitigated', '')
            if cf_mitigated == 'challenge':
                return CAPTCHADetection(
                    detected=True,
                    captcha_type=CAPTCHAType.CLOUDFLARE_CHALLENGE,
                    page_url=url,
                    confidence=0.95,
                )

        # Check each CAPTCHA type
        for captcha_type, signatures in self.SIGNATURES.items():
            matches = sum(1 for sig in signatures if sig.lower() in html_lower)
            if matches >= 2:  # require at least 2 signature matches
                sitekey = self._extract_sitekey(html, captcha_type)
                return CAPTCHADetection(
                    detected=True,
                    captcha_type=captcha_type,
                    sitekey=sitekey,
                    page_url=url,
                    confidence=min(0.5 + matches * 0.15, 0.99),
                )

        # Single-match with high-confidence signatures
        for captcha_type, signatures in self.SIGNATURES.items():
            for sig in signatures:
                if sig.lower() in html_lower:
                    sitekey = self._extract_sitekey(html, captcha_type)
                    return CAPTCHADetection(
                        detected=True,
                        captcha_type=captcha_type,
                        sitekey=sitekey,
                        page_url=url,
                        confidence=0.6,
                    )

        return CAPTCHADetection(detected=False, captcha_type=CAPTCHAType.UNKNOWN)

    def _extract_sitekey(self, html: str, captcha_type: CAPTCHAType) -> Optional[str]:
        """Extract the sitekey from HTML for a given CAPTCHA type."""
        patterns = self.SITEKEY_PATTERNS.get(captcha_type, [])
        for pattern in patterns:
            match = pattern.search(html)
            if match:
                return match.group(1)
        return None


class CAPTCHASolver:
    """Solve CAPTCHAs using configured services.

    Usage:
        solver = CAPTCHASolver()
        detection = detector.detect(html, url)
        if detection.detected:
            solution = await solver.solve(detection)
            if solution.solved:
                # inject token or cookies
    """

    def __init__(
        self,
        capsolver_key: Optional[str] = None,
        flaresolverr_url: Optional[str] = None,
    ):
        # Load from env if not provided
        self.capsolver_key = capsolver_key or os.environ.get("CAPSOLVER_API_KEY", "")
        self.flaresolverr_url = flaresolverr_url or os.environ.get(
            "FLARESOLVERR_URL", ""
        )
        self._capsolver = None

    def _get_capsolver(self):
        """Lazy-load capsolver SDK."""
        if self._capsolver is None and self.capsolver_key:
            try:
                import capsolver
                capsolver.api_key = self.capsolver_key
                self._capsolver = capsolver
                logger.info("CapSolver initialized")
            except ImportError:
                logger.warning("capsolver not installed. Run: pip install capsolver")
        return self._capsolver

    async def solve(self, detection: CAPTCHADetection) -> CAPTCHASolution:
        """Attempt to solve a detected CAPTCHA using the solving chain."""
        start = time.time()

        # Cloudflare challenges -> try FlareSolverr first
        if detection.captcha_type == CAPTCHAType.CLOUDFLARE_CHALLENGE:
            solution = await self._solve_with_flaresolverr(detection)
            if solution.solved:
                solution.solve_time = time.time() - start
                return solution

        # Try CapSolver API for standard CAPTCHAs
        if self.capsolver_key and detection.sitekey:
            solution = await self._solve_with_capsolver(detection)
            if solution.solved:
                solution.solve_time = time.time() - start
                return solution

        # Fallback: try FlareSolverr for any challenge
        if self.flaresolverr_url and detection.page_url:
            solution = await self._solve_with_flaresolverr(detection)
            if solution.solved:
                solution.solve_time = time.time() - start
                return solution

        return CAPTCHASolution(
            solved=False,
            error="No solver available or all solvers failed",
            solve_time=time.time() - start,
        )

    async def _solve_with_capsolver(self, detection: CAPTCHADetection) -> CAPTCHASolution:
        """Solve using CapSolver API."""
        cs = self._get_capsolver()
        if not cs:
            return CAPTCHASolution(solved=False, error="CapSolver not available")

        try:
            task_type_map = {
                CAPTCHAType.RECAPTCHA_V2: "ReCaptchaV2TaskProxyLess",
                CAPTCHAType.RECAPTCHA_V3: "ReCaptchaV3TaskProxyLess",
                CAPTCHAType.HCAPTCHA: "HCaptchaTaskProxyLess",
                CAPTCHAType.TURNSTILE: "AntiTurnstileTaskProxyLess",
                CAPTCHAType.FUNCAPTCHA: "FunCaptchaTaskProxyLess",
            }

            task_type = task_type_map.get(detection.captcha_type)
            if not task_type:
                return CAPTCHASolution(
                    solved=False,
                    error=f"Unsupported CAPTCHA type for CapSolver: {detection.captcha_type}",
                )

            task = {
                "type": task_type,
                "websiteURL": detection.page_url or "",
                "websiteKey": detection.sitekey or "",
            }

            # Add action for reCAPTCHA v3
            if detection.captcha_type == CAPTCHAType.RECAPTCHA_V3 and detection.action:
                task["pageAction"] = detection.action

            solution = cs.solve(task)
            token = solution.get("gRecaptchaResponse") or solution.get("token") or solution.get("solution", {}).get("token")

            if token:
                logger.info(
                    f"CapSolver solved {detection.captcha_type.value} "
                    f"for {detection.page_url}"
                )
                return CAPTCHASolution(
                    solved=True,
                    token=token,
                    method="capsolver",
                )

            return CAPTCHASolution(solved=False, error="CapSolver returned no token")

        except Exception as e:
            logger.warning(f"CapSolver failed: {e}")
            return CAPTCHASolution(solved=False, error=str(e), method="capsolver")

    async def _solve_with_flaresolverr(self, detection: CAPTCHADetection) -> CAPTCHASolution:
        """Solve Cloudflare challenge using FlareSolverr."""
        if not self.flaresolverr_url:
            return CAPTCHASolution(solved=False, error="FlareSolverr URL not configured")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{self.flaresolverr_url}/v1",
                    json={
                        "cmd": "request.get",
                        "url": detection.page_url,
                        "maxTimeout": 60000,
                    },
                )
                data = response.json()

                if data.get("status") == "ok":
                    solution_data = data.get("solution", {})
                    cookies = {
                        c["name"]: c["value"]
                        for c in solution_data.get("cookies", [])
                    }
                    cf_clearance = cookies.get("cf_clearance")

                    if cf_clearance:
                        logger.info(
                            f"FlareSolverr solved Cloudflare challenge for {detection.page_url}"
                        )
                        return CAPTCHASolution(
                            solved=True,
                            cookies=cookies,
                            user_agent=solution_data.get("userAgent"),
                            method="flaresolverr",
                        )

                return CAPTCHASolution(
                    solved=False,
                    error=f"FlareSolverr: {data.get('message', 'unknown error')}",
                    method="flaresolverr",
                )

        except ImportError:
            return CAPTCHASolution(solved=False, error="httpx not installed for FlareSolverr")
        except Exception as e:
            logger.warning(f"FlareSolverr failed: {e}")
            return CAPTCHASolution(solved=False, error=str(e), method="flaresolverr")


def load_env_file(env_path: Optional[str] = None):
    """Load .env file into os.environ. Simple parser, no dependencies."""
    if env_path is None:
        # Look for .env in common locations
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).parent.parent.parent.parent / ".env",  # repo root
        ]
        for candidate in candidates:
            if candidate.exists():
                env_path = str(candidate)
                break

    if not env_path or not Path(env_path).exists():
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:  # don't override existing
                    os.environ[key] = value
