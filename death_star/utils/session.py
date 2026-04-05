"""
Session Manager
===============

Manage cookies and session data for authenticated scraping.
"""

import base64
import json
from pathlib import Path
from typing import Any, Dict, List


class SessionManager:
    """
    Manage cookies and session data for authenticated scraping.
    
    Supports:
    - Netscape cookie format (from browser export)
    - JSON cookie format
    - Raw cookie strings
    
    Usage:
        session = SessionManager(cookie_file="cookies.json")
        
        # Get cookies for a domain
        cookies = session.get_cookies_for_domain("example.com")
        
        # Get Cookie header
        header = session.get_cookie_header("example.com")
        
        # Get Playwright-compatible cookies
        pw_cookies = session.get_playwright_cookies()
    """
    
    def __init__(self, cookie_file: str = None):
        self.cookies: List[Dict] = []
        self.headers: Dict[str, str] = {}
        
        if cookie_file:
            self._load_cookies(cookie_file)
    
    def _load_cookies(self, filepath: str):
        """Load cookies from file."""
        path = Path(filepath)
        if not path.exists():
            return
        
        content = path.read_text()
        
        # Try JSON format first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                self.cookies = data
            elif isinstance(data, dict):
                self.cookies = [data]
            return
        except json.JSONDecodeError:
            pass
        
        # Try Netscape format
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            parts = line.split("\t")
            if len(parts) >= 7:
                self.cookies.append({
                    "domain": parts[0],
                    "httpOnly": parts[1].lower() == "true",
                    "path": parts[2],
                    "secure": parts[3].lower() == "true",
                    "expires": int(parts[4]) if parts[4].isdigit() else 0,
                    "name": parts[5],
                    "value": parts[6],
                })
    
    def get_cookies_for_domain(self, domain: str) -> List[Dict]:
        """Get cookies applicable to a domain."""
        result = []
        for cookie in self.cookies:
            cookie_domain = cookie.get("domain", "")
            if domain.endswith(cookie_domain.lstrip(".")):
                result.append(cookie)
        return result
    
    def get_cookie_header(self, domain: str) -> str:
        """Get Cookie header value for a domain."""
        cookies = self.get_cookies_for_domain(domain)
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    
    def get_playwright_cookies(self, domain: str = None) -> List[Dict]:
        """Get cookies in Playwright format."""
        cookies = self.cookies if not domain else self.get_cookies_for_domain(domain)
        
        result = []
        for c in cookies:
            cookie = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
            }
            if "expires" in c and c["expires"]:
                cookie["expires"] = c["expires"]
            if "httpOnly" in c:
                cookie["httpOnly"] = c["httpOnly"]
            if "secure" in c:
                cookie["secure"] = c["secure"]
            result.append(cookie)
        
        return result
    
    def add_auth_headers(self, username: str, password: str, auth_type: str = "basic"):
        """Add authentication headers."""
        if auth_type == "basic":
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.headers["Authorization"] = f"Basic {credentials}"
    
    def add_cookie(self, name: str, value: str, domain: str, path: str = "/"):
        """Add a cookie manually."""
        self.cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
        })
    
    def clear_cookies(self):
        """Clear all cookies."""
        self.cookies = []
