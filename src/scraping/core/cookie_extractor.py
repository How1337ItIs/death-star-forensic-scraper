"""
Cookie Extractor — Extract cookies from browser profile databases.

Extracts authenticated sessions from Chrome/Firefox/Edge without
needing CDP or manual cookie export. Uses browser-cookie3 to read
the browser's SQLite cookie database directly.

Requires:
    pip install browser-cookie3

Usage:
    extractor = CookieExtractor()
    cookies = extractor.from_chrome(domain="walmart.com")
    # Returns dict of {name: value} cookies for that domain
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("death_star_v2.cookie_extractor")


class CookieExtractor:
    """Extract cookies from installed browsers.

    Supports Chrome, Firefox, Edge, Brave, Opera, Vivaldi, LibreWolf.
    Reads the browser's SQLite cookie database directly.
    """

    def __init__(self):
        self._bc3 = None

    def _get_bc3(self):
        """Lazy-load browser_cookie3."""
        if self._bc3 is None:
            try:
                import browser_cookie3
                self._bc3 = browser_cookie3
            except ImportError:
                logger.warning(
                    "browser-cookie3 not installed. Run: pip install browser-cookie3"
                )
        return self._bc3

    def from_chrome(self, domain: Optional[str] = None) -> Dict[str, str]:
        """Extract cookies from Chrome."""
        return self._extract("chrome", domain)

    def from_firefox(self, domain: Optional[str] = None) -> Dict[str, str]:
        """Extract cookies from Firefox."""
        return self._extract("firefox", domain)

    def from_edge(self, domain: Optional[str] = None) -> Dict[str, str]:
        """Extract cookies from Edge."""
        return self._extract("edge", domain)

    def from_brave(self, domain: Optional[str] = None) -> Dict[str, str]:
        """Extract cookies from Brave."""
        return self._extract("brave", domain)

    def from_any(self, domain: Optional[str] = None) -> Dict[str, str]:
        """Try all browsers, return first successful extraction."""
        for browser in ["chrome", "firefox", "edge", "brave", "opera", "vivaldi"]:
            try:
                cookies = self._extract(browser, domain)
                if cookies:
                    logger.info(f"Extracted {len(cookies)} cookies from {browser}")
                    return cookies
            except Exception:
                continue
        logger.warning("Could not extract cookies from any browser")
        return {}

    def _extract(self, browser: str, domain: Optional[str] = None) -> Dict[str, str]:
        """Extract cookies from a specific browser."""
        bc3 = self._get_bc3()
        if not bc3:
            return {}

        browser_funcs = {
            "chrome": bc3.chrome,
            "firefox": bc3.firefox,
            "edge": bc3.edge,
            "brave": getattr(bc3, "brave", None),
            "opera": bc3.opera,
            "vivaldi": getattr(bc3, "vivaldi", None),
        }

        func = browser_funcs.get(browser)
        if not func:
            logger.warning(f"Browser {browser} not supported")
            return {}

        try:
            cj = func(domain_name=domain) if domain else func()
            cookies = {cookie.name: cookie.value for cookie in cj}
            if cookies:
                logger.debug(f"Extracted {len(cookies)} cookies from {browser}" +
                           (f" for {domain}" if domain else ""))
            return cookies
        except Exception as e:
            logger.debug(f"Failed to extract cookies from {browser}: {e}")
            return {}

    def to_playwright_cookies(
        self, cookies: Dict[str, str], domain: str
    ) -> List[Dict]:
        """Convert cookie dict to Playwright cookie format.

        Usage:
            pw_cookies = extractor.to_playwright_cookies(cookies, "walmart.com")
            await context.add_cookies(pw_cookies)
        """
        return [
            {
                "name": name,
                "value": value,
                "domain": f".{domain}" if not domain.startswith(".") else domain,
                "path": "/",
            }
            for name, value in cookies.items()
        ]

    def to_httpx_cookies(self, cookies: Dict[str, str]) -> Dict[str, str]:
        """Convert to httpx/requests cookie format (identity — already a dict)."""
        return cookies

    def to_curl_cffi_cookies(self, cookies: Dict[str, str]) -> Dict[str, str]:
        """Convert to curl_cffi cookie format (identity — already a dict)."""
        return cookies

    def to_netscape_string(self, cookies: Dict[str, str], domain: str) -> str:
        """Convert to Netscape cookie file format (wget, curl compatible)."""
        lines = ["# Netscape HTTP Cookie File"]
        for name, value in cookies.items():
            # domain  flag  path  secure  expiry  name  value
            lines.append(
                f".{domain}\tTRUE\t/\tFALSE\t0\t{name}\t{value}"
            )
        return "\n".join(lines)
