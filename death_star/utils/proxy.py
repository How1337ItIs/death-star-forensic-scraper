"""
Proxy Pool Manager
==================

Intelligent proxy rotation with health tracking.
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProxyPool:
    """
    Intelligent proxy rotation with health tracking.
    
    Features:
    - Load proxies from file or list
    - Track proxy health/failures
    - Automatic rotation with cooldown
    - Geographic selection (if tagged)
    
    Usage:
        pool = ProxyPool(proxy_file="proxies.txt")
        
        proxy = pool.get_proxy()
        # Use proxy...
        pool.report_success(proxy["url"])
        # or
        pool.report_failure(proxy["url"])
    """
    
    def __init__(self, proxies: List[str] = None, proxy_file: str = None):
        self.proxies: List[Dict[str, Any]] = []
        self._current_index = 0
        self._failures: Dict[str, int] = {}
        self._cooldowns: Dict[str, float] = {}
        
        if proxy_file:
            self._load_from_file(proxy_file)
        elif proxies:
            self.proxies = [self._parse_proxy(p) for p in proxies]
    
    def _load_from_file(self, filepath: str):
        """Load proxies from file (one per line)."""
        path = Path(filepath)
        if not path.exists():
            return
        
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    self.proxies.append(self._parse_proxy(line))
                except Exception:
                    pass
    
    def _parse_proxy(self, proxy_str: str) -> Dict[str, Any]:
        """Parse proxy string into structured format."""
        proxy = {
            "url": proxy_str,
            "protocol": "http",
            "host": "",
            "port": 8080,
            "auth": None,
            "location": None,
        }
        
        if "://" in proxy_str:
            proxy["protocol"], rest = proxy_str.split("://", 1)
        else:
            rest = proxy_str
        
        # Check for location tag
        if "@" in rest and rest.count("@") > 1:
            rest, proxy["location"] = rest.rsplit("@", 1)
        
        # Check for auth
        if "@" in rest:
            auth, hostport = rest.rsplit("@", 1)
            if ":" in auth:
                user, passwd = auth.split(":", 1)
                proxy["auth"] = (user, passwd)
        else:
            hostport = rest
        
        # Parse host:port
        if ":" in hostport:
            proxy["host"], port = hostport.rsplit(":", 1)
            proxy["port"] = int(port)
        else:
            proxy["host"] = hostport
        
        return proxy
    
    def get_proxy(self, location: str = None) -> Optional[Dict[str, Any]]:
        """Get next available proxy."""
        if not self.proxies:
            return None
        
        now = time.time()
        available = []
        
        for proxy in self.proxies:
            url = proxy["url"]
            
            # Check cooldown
            if url in self._cooldowns and self._cooldowns[url] > now:
                continue
            
            # Check failure count
            if self._failures.get(url, 0) >= 5:
                continue
            
            # Check location filter
            if location and proxy.get("location") != location:
                continue
            
            available.append(proxy)
        
        if not available:
            return None
        
        # Round-robin
        proxy = available[self._current_index % len(available)]
        self._current_index += 1
        
        return proxy
    
    def report_failure(self, proxy_url: str):
        """Report a proxy failure."""
        self._failures[proxy_url] = self._failures.get(proxy_url, 0) + 1
        self._cooldowns[proxy_url] = time.time() + 60
    
    def report_success(self, proxy_url: str):
        """Report successful use."""
        self._failures[proxy_url] = 0
    
    def get_playwright_proxy(self, location: str = None) -> Optional[Dict]:
        """Get proxy in Playwright format."""
        proxy = self.get_proxy(location)
        if not proxy:
            return None
        
        result = {
            "server": f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"
        }
        if proxy.get("auth"):
            result["username"], result["password"] = proxy["auth"]
        
        return result
    
    def get_httpx_proxy(self, location: str = None) -> Optional[str]:
        """Get proxy URL for httpx/requests."""
        proxy = self.get_proxy(location)
        if not proxy:
            return None
        
        if proxy.get("auth"):
            return f"{proxy['protocol']}://{proxy['auth'][0]}:{proxy['auth'][1]}@{proxy['host']}:{proxy['port']}"
        return f"{proxy['protocol']}://{proxy['host']}:{proxy['port']}"
