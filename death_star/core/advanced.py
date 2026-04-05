"""
Advanced Capture Module
=======================

Enhanced capture capabilities for deep forensic analysis:
- WebSocket message capture
- Form extraction
- Technology stack detection
- Source map downloading
- Third-party script inventory
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("death_star.advanced")


@dataclass
class TechnologyStack:
    """Detected technology stack."""
    cms: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    js_libraries: List[str] = field(default_factory=list)
    css_frameworks: List[str] = field(default_factory=list)
    analytics: List[str] = field(default_factory=list)
    advertising: List[str] = field(default_factory=list)
    cdn: List[str] = field(default_factory=list)
    server: List[str] = field(default_factory=list)


@dataclass
class FormData:
    """Extracted form data."""
    action: str
    method: str
    fields: List[Dict]
    hidden_fields: List[Dict]


@dataclass
class AdvancedCaptureResult:
    """Complete advanced capture result."""
    url: str
    timestamp: str
    
    websocket_connections: List[str]
    websocket_messages: List[Dict]
    forms: List[FormData]
    iframes: List[Dict]
    tech_stack: TechnologyStack
    third_party_scripts: List[Dict]
    source_maps: List[Dict]
    contact_info: Dict[str, List[str]]
    api_endpoints: List[str]


# Technology detection signatures
TECH_SIGNATURES = {
    "wordpress": [r"/wp-content/", r"/wp-includes/"],
    "react": [r"react\.production", r"_reactRootContainer", r"__NEXT_DATA__"],
    "vue": [r"vue\.js", r"__vue__"],
    "angular": [r"ng-version", r"ng-app"],
    "jquery": [r"jquery[\.-]"],
    "bootstrap": [r"bootstrap\.css", r"bootstrap\.min\.css"],
    "tailwind": [r"tailwindcss"],
    "google_analytics": [r"google-analytics\.com", r"googletagmanager\.com"],
    "cloudflare": [r"cloudflare\.com"],
}


class AdvancedCapture:
    """
    Advanced capture for deep forensic analysis.
    
    Usage:
        capture = AdvancedCapture()
        result = await capture.capture_advanced(page, url)
    """
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/advanced")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._websocket_messages = []
        self._websocket_urls = []
    
    async def capture_advanced(
        self,
        page,  # Playwright page
        url: str,
        headers: Dict[str, str] = None,
        capture_source_maps: bool = True,
    ) -> AdvancedCaptureResult:
        """
        Perform advanced capture on a page.
        
        Args:
            page: Playwright page object
            url: Page URL
            headers: Response headers
            capture_source_maps: Download source maps
        
        Returns:
            AdvancedCaptureResult
        """
        headers = headers or {}
        
        # Reset state
        self._websocket_messages = []
        self._websocket_urls = []
        
        # Set up WebSocket capture
        self._setup_websocket_capture(page)
        
        # Get page content
        html = await page.content()
        
        # Extract forms
        forms = await self._extract_forms(page)
        
        # Extract iframes
        iframes = await self._extract_iframes(page)
        
        # Detect technology
        tech_stack = self._detect_tech_stack(html, headers)
        
        # Third-party scripts
        third_party = await self._inventory_third_party(page, url)
        
        # Source maps
        source_maps = []
        if capture_source_maps:
            source_maps = await self._find_source_maps(page, html)
        
        # Contact info
        contact_info = self._extract_contact_info(html)
        
        # API endpoints
        api_endpoints = await self._extract_api_endpoints(page)
        
        return AdvancedCaptureResult(
            url=url,
            timestamp=datetime.now().isoformat(),
            websocket_connections=self._websocket_urls,
            websocket_messages=self._websocket_messages,
            forms=forms,
            iframes=iframes,
            tech_stack=tech_stack,
            third_party_scripts=third_party,
            source_maps=source_maps,
            contact_info=contact_info,
            api_endpoints=api_endpoints,
        )
    
    def _setup_websocket_capture(self, page):
        """Set up WebSocket message capture."""
        def handle_websocket(ws):
            self._websocket_urls.append(ws.url)
            
            def on_message(payload):
                self._websocket_messages.append({
                    "url": ws.url,
                    "direction": "received",
                    "payload": payload if isinstance(payload, str) else "<binary>",
                    "timestamp": datetime.now().timestamp(),
                })
            
            def on_sent(payload):
                self._websocket_messages.append({
                    "url": ws.url,
                    "direction": "sent",
                    "payload": payload if isinstance(payload, str) else "<binary>",
                    "timestamp": datetime.now().timestamp(),
                })
            
            ws.on("framereceived", lambda d: on_message(d.get("payload", "")))
            ws.on("framesent", lambda d: on_sent(d.get("payload", "")))
        
        page.on("websocket", handle_websocket)
    
    async def _extract_forms(self, page) -> List[FormData]:
        """Extract all forms from the page."""
        form_data = await page.evaluate("""
            () => {
                const forms = [];
                document.querySelectorAll('form').forEach(form => {
                    const fields = [];
                    const hiddenFields = [];
                    
                    form.querySelectorAll('input, select, textarea').forEach(field => {
                        const data = {
                            type: field.type || '',
                            name: field.name || '',
                            id: field.id || '',
                            required: field.required || false,
                        };
                        
                        if (field.type === 'hidden') {
                            hiddenFields.push(data);
                        } else {
                            fields.push(data);
                        }
                    });
                    
                    forms.push({
                        action: form.action || '',
                        method: (form.method || 'get').toUpperCase(),
                        fields: fields,
                        hiddenFields: hiddenFields
                    });
                });
                return forms;
            }
        """)
        
        return [
            FormData(
                action=f["action"],
                method=f["method"],
                fields=f["fields"],
                hidden_fields=f["hiddenFields"]
            )
            for f in form_data
        ]
    
    async def _extract_iframes(self, page) -> List[Dict]:
        """Extract iframe information."""
        return await page.evaluate("""
            () => {
                const iframes = [];
                document.querySelectorAll('iframe').forEach(iframe => {
                    iframes.push({
                        src: iframe.src || '',
                        id: iframe.id || '',
                        name: iframe.name || '',
                    });
                });
                return iframes;
            }
        """)
    
    def _detect_tech_stack(self, html: str, headers: Dict[str, str]) -> TechnologyStack:
        """Detect technology stack."""
        detected = TechnologyStack()
        
        for tech_name, patterns in TECH_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, html, re.I):
                    # Categorize
                    if tech_name == "wordpress":
                        detected.cms.append("WordPress")
                    elif tech_name in ("react", "vue", "angular"):
                        detected.frameworks.append(tech_name.title())
                    elif tech_name == "jquery":
                        detected.js_libraries.append("jQuery")
                    elif tech_name in ("bootstrap", "tailwind"):
                        detected.css_frameworks.append(tech_name.title())
                    elif tech_name == "google_analytics":
                        detected.analytics.append("Google Analytics")
                    elif tech_name == "cloudflare":
                        detected.cdn.append("Cloudflare")
                    break
        
        # Check headers
        server = headers.get("server", "")
        if "nginx" in server.lower():
            detected.server.append("nginx")
        elif "apache" in server.lower():
            detected.server.append("Apache")
        
        return detected
    
    async def _inventory_third_party(self, page, base_url: str) -> List[Dict]:
        """Inventory third-party scripts."""
        base_domain = urlparse(base_url).netloc
        
        scripts = await page.evaluate("""
            () => Array.from(document.querySelectorAll('script[src]')).map(s => s.src)
        """)
        
        third_party = []
        for script_url in scripts:
            domain = urlparse(script_url).netloc
            if domain and domain != base_domain:
                third_party.append({
                    "url": script_url,
                    "domain": domain,
                })
        
        return third_party
    
    async def _find_source_maps(self, page, html: str) -> List[Dict]:
        """Find source map references."""
        source_maps = []
        
        # Look for sourceMappingURL in inline scripts
        pattern = r"//[#@]\s*sourceMappingURL=(\S+)"
        for match in re.finditer(pattern, html):
            source_maps.append({
                "map_url": match.group(1),
                "source": "inline",
            })
        
        return source_maps
    
    def _extract_contact_info(self, html: str) -> Dict[str, List[str]]:
        """Extract contact information."""
        # Emails
        emails = list(set(re.findall(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            html
        )))[:20]
        
        # Phones
        phones = list(set(re.findall(
            r"\+?[0-9]{1,3}[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}",
            html
        )))[:10]
        
        # Social links
        social = {}
        social_patterns = {
            "twitter": r"twitter\.com/([a-zA-Z0-9_]+)",
            "facebook": r"facebook\.com/([a-zA-Z0-9.]+)",
            "instagram": r"instagram\.com/([a-zA-Z0-9_.]+)",
            "linkedin": r"linkedin\.com/(?:in|company)/([a-zA-Z0-9_-]+)",
        }
        
        for platform, pattern in social_patterns.items():
            matches = re.findall(pattern, html, re.I)
            if matches:
                social[platform] = list(set(matches))[:5]
        
        return {
            "emails": emails,
            "phones": phones,
            "social": social,
        }
    
    async def _extract_api_endpoints(self, page) -> List[str]:
        """Extract API endpoints from JavaScript."""
        scripts = await page.evaluate("""
            () => Array.from(document.querySelectorAll('script'))
                .map(s => s.textContent || '').join('\\n')
        """)
        
        # API patterns
        patterns = [
            r'["\']/(api|v\d+)/[^"\']+["\']',
            r'fetch\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        endpoints = set()
        for pattern in patterns:
            for match in re.finditer(pattern, scripts, re.I):
                endpoint = match.group(1) if match.lastindex else match.group(0)
                endpoint = endpoint.strip("\"'")
                if endpoint.startswith("/") or endpoint.startswith("http"):
                    endpoints.add(endpoint)
        
        return list(endpoints)[:50]
    
    def save_result(self, result: AdvancedCaptureResult, domain: str):
        """Save advanced capture result."""
        output_dir = self.output_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "url": result.url,
            "timestamp": result.timestamp,
            "websocket_connections": result.websocket_connections,
            "websocket_message_count": len(result.websocket_messages),
            "forms": [
                {"action": f.action, "method": f.method, "field_count": len(f.fields)}
                for f in result.forms
            ],
            "iframes": result.iframes,
            "tech_stack": {
                "cms": result.tech_stack.cms,
                "frameworks": result.tech_stack.frameworks,
                "analytics": result.tech_stack.analytics,
            },
            "third_party_scripts": len(result.third_party_scripts),
            "source_maps": result.source_maps,
            "contact_info": result.contact_info,
            "api_endpoints": result.api_endpoints,
        }
        
        with open(output_dir / "advanced_capture.json", "w") as f:
            json.dump(data, f, indent=2)
