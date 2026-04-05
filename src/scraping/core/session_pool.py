"""
Session Pool — Coherent identity management for scraping sessions.

Each session ties together proxy + user agent + TLS fingerprint +
browser fingerprint + cookies into a single believable user identity.
Sessions are assigned per-domain and persist across requests.

Optional:
    pip install browserforge  (for realistic fingerprint generation)
"""

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("death_star_v2.session_pool")

# Fallback user agents if browserforge not available
_FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
]


@dataclass
class ScraperSession:
    """A coherent scraping identity."""
    id: str
    user_agent: str
    proxy: Optional[str] = None
    cookies: Dict[str, str] = field(default_factory=dict)
    fingerprint: Dict[str, Any] = field(default_factory=dict)
    cf_clearance: Optional[str] = None
    cf_clearance_ua: Optional[str] = None  # UA used when getting cf_clearance

    # Tracking
    created_at: float = field(default_factory=time.time)
    last_used: float = 0.0
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    domains_used: Set[str] = field(default_factory=set)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0

    def record_use(self, domain: str, success: bool):
        self.last_used = time.time()
        self.request_count += 1
        self.domains_used.add(domain)
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

    def add_cookies(self, cookies: Dict[str, str]):
        """Merge new cookies into this session."""
        self.cookies.update(cookies)

    def set_cf_clearance(self, clearance: str, user_agent: str):
        """Set Cloudflare clearance cookie with its associated UA."""
        self.cf_clearance = clearance
        self.cf_clearance_ua = user_agent
        self.cookies["cf_clearance"] = clearance


class SessionPool:
    """Pool of coherent scraping sessions.

    Usage:
        pool = SessionPool(proxy_list=["http://proxy1:8080"])
        session = pool.get_session("example.com")
        # Use session.user_agent, session.proxy, session.cookies consistently
        session.record_use("example.com", success=True)
    """

    def __init__(
        self,
        proxy_list: Optional[List[str]] = None,
        max_sessions: int = 10,
        max_failures: int = 5,
        session_ttl: float = 3600.0,  # 1 hour
    ):
        self.proxy_list = proxy_list or []
        self.max_sessions = max_sessions
        self.max_failures = max_failures
        self.session_ttl = session_ttl

        self._sessions: Dict[str, ScraperSession] = {}  # id -> session
        self._domain_sessions: Dict[str, str] = {}  # domain -> session_id
        self._fingerprint_gen = None
        self._proxy_index = 0

    def _get_fingerprint_gen(self):
        """Lazy-load BrowserForge fingerprint generator."""
        if self._fingerprint_gen is None:
            try:
                from browserforge.fingerprints import FingerprintGenerator
                self._fingerprint_gen = FingerprintGenerator(
                    browser="chrome",
                    os="windows",
                )
                logger.debug("BrowserForge fingerprint generator loaded")
            except ImportError:
                logger.debug("browserforge not available, using fallback fingerprints")
        return self._fingerprint_gen

    def _generate_fingerprint(self) -> Dict[str, Any]:
        """Generate a realistic browser fingerprint."""
        gen = self._get_fingerprint_gen()
        if gen:
            try:
                fp = gen.generate()
                return {
                    "user_agent": fp.navigator.userAgent,
                    "platform": fp.navigator.platform,
                    "viewport": {
                        "width": fp.screen.width,
                        "height": fp.screen.height,
                    },
                    "screen": {
                        "width": fp.screen.width,
                        "height": fp.screen.height,
                        "availWidth": fp.screen.availWidth,
                        "availHeight": fp.screen.availHeight,
                        "colorDepth": fp.screen.colorDepth,
                    },
                }
            except Exception as e:
                logger.debug(f"BrowserForge generation failed: {e}")

        # Fallback: basic fingerprint
        ua = random.choice(_FALLBACK_USER_AGENTS)
        return {
            "user_agent": ua,
            "platform": "Win32" if "Windows" in ua else "MacIntel",
            "viewport": {"width": 1920, "height": 1080},
        }

    def _next_proxy(self) -> Optional[str]:
        """Get next proxy from pool (round-robin)."""
        if not self.proxy_list:
            return None
        proxy = self.proxy_list[self._proxy_index % len(self.proxy_list)]
        self._proxy_index += 1
        return proxy

    def _create_session(self) -> ScraperSession:
        """Create a new session with consistent identity."""
        fingerprint = self._generate_fingerprint()
        session = ScraperSession(
            id=str(uuid.uuid4())[:8],
            user_agent=fingerprint.get("user_agent", random.choice(_FALLBACK_USER_AGENTS)),
            proxy=self._next_proxy(),
            fingerprint=fingerprint,
        )
        self._sessions[session.id] = session
        logger.debug(f"Created session {session.id} (UA: {session.user_agent[:60]}...)")
        return session

    def get_session(self, domain: str) -> ScraperSession:
        """Get or create a session for a domain.

        Returns an existing session if one is assigned to this domain,
        or creates a new one. Sessions are reused per-domain to maintain
        cookie/fingerprint consistency.
        """
        # Check if domain already has a session
        session_id = self._domain_sessions.get(domain)
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]

            # Check if session is still healthy
            if self._is_session_healthy(session):
                return session
            else:
                # Retire unhealthy session
                self._retire_session(session_id)

        # Find an existing session with capacity, or create new one
        session = self._find_available_session() or self._create_session()
        self._domain_sessions[domain] = session.id
        return session

    def _find_available_session(self) -> Optional[ScraperSession]:
        """Find an existing healthy session that can take on more domains."""
        for session in self._sessions.values():
            if (
                self._is_session_healthy(session)
                and len(session.domains_used) < 5  # don't overload sessions
            ):
                return session
        return None

    def _is_session_healthy(self, session: ScraperSession) -> bool:
        """Check if a session is still usable."""
        if session.failure_count >= self.max_failures:
            return False
        if session.age_seconds > self.session_ttl:
            return False
        if session.success_rate < 0.3 and session.request_count > 5:
            return False
        return True

    def _retire_session(self, session_id: str):
        """Remove a session from the pool."""
        session = self._sessions.pop(session_id, None)
        if session:
            # Remove domain mappings
            for domain, sid in list(self._domain_sessions.items()):
                if sid == session_id:
                    del self._domain_sessions[domain]
            logger.debug(
                f"Retired session {session_id} "
                f"(requests={session.request_count}, "
                f"success_rate={session.success_rate:.0%})"
            )

    def retire_domain(self, domain: str):
        """Retire the session associated with a domain (e.g., after getting blocked)."""
        session_id = self._domain_sessions.pop(domain, None)
        if session_id:
            self._retire_session(session_id)

    def get_stats(self) -> Dict:
        """Get pool statistics."""
        return {
            "total_sessions": len(self._sessions),
            "domain_mappings": len(self._domain_sessions),
            "sessions": {
                sid: {
                    "requests": s.request_count,
                    "success_rate": f"{s.success_rate:.0%}",
                    "domains": list(s.domains_used),
                    "age_minutes": f"{s.age_seconds / 60:.1f}",
                    "has_proxy": s.proxy is not None,
                    "has_cf_clearance": s.cf_clearance is not None,
                }
                for sid, s in self._sessions.items()
            },
        }
