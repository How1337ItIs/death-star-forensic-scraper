#!/usr/bin/env python3
"""
Advanced Capture Module
=======================

Enhanced capture capabilities for deep forensic analysis.

Features:
---------
1. WebSocket message capture
2. Form extraction and analysis
3. Iframe recursive capture
4. JavaScript source map downloading
5. Technology stack detection
6. Third-party script inventory
7. Contact info extraction (email, phone, social)
8. API endpoint extraction from JavaScript
9. CSS analysis

Usage:
------
    from advanced_capture import AdvancedCapture
    
    capture = AdvancedCapture()
    result = await capture.capture_advanced(page, url)
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("advanced_capture")


def safe_path_component(value: str) -> str:
    """Make a string safe for cross-platform file and directory names."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class WebSocketMessage:
    """Captured WebSocket message."""
    url: str
    direction: str  # 'sent' or 'received'
    payload: str
    opcode: int
    timestamp: float


@dataclass
class FormData:
    """Extracted form data."""
    action: str
    method: str
    enctype: str
    id: str
    name: str
    fields: List[Dict]  # {name, type, value, required, placeholder, etc.}
    hidden_fields: List[Dict]  # Likely CSRF tokens, etc.


@dataclass
class TechnologyStack:
    """Detected technology stack."""
    cms: List[str]  # WordPress, Drupal, etc.
    frameworks: List[str]  # React, Vue, Angular, etc.
    js_libraries: List[str]  # jQuery, Lodash, etc.
    css_frameworks: List[str]  # Bootstrap, Tailwind, etc.
    server: List[str]  # nginx, Apache, etc.
    analytics: List[str]  # Google Analytics, etc.
    advertising: List[str]  # Google Ads, etc.
    cdn: List[str]  # Cloudflare, Fastly, etc.
    hosting: List[str]  # AWS, Vercel, etc.
    ecommerce: List[str]  # Shopify, WooCommerce, etc.
    other: List[str]


@dataclass
class ThirdPartyScript:
    """Third-party script information."""
    url: str
    domain: str
    category: str  # analytics, ads, social, cdn, other
    name: str  # Google Analytics, Facebook Pixel, etc.
    hash: str


@dataclass
class SourceMap:
    """JavaScript source map."""
    js_url: str
    map_url: str
    map_content: Dict
    original_sources: List[str]


@dataclass
class ContactInfo:
    """Extracted contact information."""
    emails: List[str]
    phones: List[str]
    social_links: Dict[str, List[str]]  # platform -> urls


@dataclass
class CSSAnalysis:
    """CSS analysis results."""
    fonts: List[str]
    colors: List[str]
    frameworks_detected: List[str]
    custom_properties: Dict[str, str]
    media_queries: List[str]


@dataclass
class AdvancedCaptureResult:
    """Complete advanced capture result."""
    url: str
    timestamp: str
    
    # WebSocket
    websocket_connections: List[str]
    websocket_messages: List[WebSocketMessage]
    
    # Forms
    forms: List[FormData]
    
    # Iframes
    iframes: List[Dict]  # {src, content, nested_iframes}
    
    # Technology
    tech_stack: TechnologyStack
    third_party_scripts: List[ThirdPartyScript]
    
    # Source maps
    source_maps: List[SourceMap]
    
    # Contact info
    contact_info: ContactInfo
    
    # API endpoints
    api_endpoints: List[str]
    
    # CSS
    css_analysis: CSSAnalysis


# =============================================================================
# TECHNOLOGY DETECTION SIGNATURES
# =============================================================================

TECH_SIGNATURES = {
    # CMS
    'wordpress': {
        'patterns': [r'/wp-content/', r'/wp-includes/', r'wp-json'],
        'meta': {'generator': r'WordPress'},
        'headers': {},
    },
    'drupal': {
        'patterns': [r'Drupal\.settings', r'/sites/default/', r'/modules/'],
        'meta': {'generator': r'Drupal'},
        'headers': {'x-drupal-cache': r'.*'},
    },
    'joomla': {
        'patterns': [r'/components/com_', r'/media/jui/'],
        'meta': {'generator': r'Joomla'},
        'headers': {},
    },
    'shopify': {
        'patterns': [r'cdn\.shopify\.com', r'Shopify\.theme'],
        'meta': {},
        'headers': {'x-shopify-stage': r'.*'},
    },
    'squarespace': {
        'patterns': [r'squarespace\.com', r'static\.squarespace'],
        'meta': {'generator': r'Squarespace'},
        'headers': {},
    },
    'wix': {
        'patterns': [r'wix\.com', r'wixstatic\.com'],
        'meta': {'generator': r'Wix'},
        'headers': {},
    },
    
    # Frameworks
    'react': {
        'patterns': [r'react\.production\.min\.js', r'react-dom', r'_reactRootContainer', r'__NEXT_DATA__'],
        'meta': {},
        'headers': {},
    },
    'vue': {
        'patterns': [r'vue\.js', r'vue\.min\.js', r'__vue__', r'Vue\.config'],
        'meta': {},
        'headers': {},
    },
    'angular': {
        'patterns': [r'angular\.js', r'ng-version', r'ng-app', r'\[ng-'],
        'meta': {},
        'headers': {},
    },
    'svelte': {
        'patterns': [r'svelte', r'__svelte'],
        'meta': {},
        'headers': {},
    },
    'nextjs': {
        'patterns': [r'__NEXT_DATA__', r'/_next/', r'next/dist'],
        'meta': {},
        'headers': {'x-nextjs-cache': r'.*'},
    },
    'nuxt': {
        'patterns': [r'__NUXT__', r'/_nuxt/'],
        'meta': {},
        'headers': {},
    },
    'gatsby': {
        'patterns': [r'gatsby', r'/static/d/'],
        'meta': {'generator': r'Gatsby'},
        'headers': {},
    },
    
    # JS Libraries
    'jquery': {
        'patterns': [r'jquery[\.-]', r'jQuery\.fn'],
        'meta': {},
        'headers': {},
    },
    'lodash': {
        'patterns': [r'lodash', r'_\.VERSION'],
        'meta': {},
        'headers': {},
    },
    'moment': {
        'patterns': [r'moment\.js', r'moment\.min\.js'],
        'meta': {},
        'headers': {},
    },
    
    # CSS Frameworks
    'bootstrap': {
        'patterns': [r'bootstrap\.css', r'bootstrap\.min\.css', r'class="[^"]*\bcontainer\b'],
        'meta': {},
        'headers': {},
    },
    'tailwind': {
        'patterns': [r'tailwindcss', r'class="[^"]*\b(flex|grid|bg-|text-|p-|m-)'],
        'meta': {},
        'headers': {},
    },
    'bulma': {
        'patterns': [r'bulma\.css', r'bulma\.min\.css'],
        'meta': {},
        'headers': {},
    },
    
    # Analytics
    'google_analytics': {
        'patterns': [r'google-analytics\.com', r'googletagmanager\.com', r'gtag\(', r'ga\('],
        'meta': {},
        'headers': {},
    },
    'mixpanel': {
        'patterns': [r'mixpanel\.com', r'mixpanel\.init'],
        'meta': {},
        'headers': {},
    },
    'hotjar': {
        'patterns': [r'hotjar\.com', r'hj\('],
        'meta': {},
        'headers': {},
    },
    'segment': {
        'patterns': [r'segment\.com', r'analytics\.load'],
        'meta': {},
        'headers': {},
    },
    
    # Advertising
    'google_ads': {
        'patterns': [r'googlesyndication\.com', r'googleads\.g\.doubleclick'],
        'meta': {},
        'headers': {},
    },
    'facebook_pixel': {
        'patterns': [r'connect\.facebook\.net', r'fbevents\.js', r'fbq\('],
        'meta': {},
        'headers': {},
    },
    
    # CDN
    'cloudflare': {
        'patterns': [r'cloudflare\.com', r'cdnjs\.cloudflare\.com'],
        'meta': {},
        'headers': {'cf-ray': r'.*', 'server': r'cloudflare'},
    },
    'fastly': {
        'patterns': [],
        'meta': {},
        'headers': {'x-served-by': r'cache-', 'via': r'.*fastly'},
    },
    'akamai': {
        'patterns': [r'akamai\.net', r'akamaized\.net'],
        'meta': {},
        'headers': {'x-akamai': r'.*'},
    },
    'cloudfront': {
        'patterns': [r'cloudfront\.net'],
        'meta': {},
        'headers': {'x-amz-cf-id': r'.*'},
    },
    
    # Servers
    'nginx': {
        'patterns': [],
        'meta': {},
        'headers': {'server': r'nginx'},
    },
    'apache': {
        'patterns': [],
        'meta': {},
        'headers': {'server': r'Apache'},
    },
    'iis': {
        'patterns': [],
        'meta': {},
        'headers': {'server': r'Microsoft-IIS'},
    },
}

THIRD_PARTY_DOMAINS = {
    # Analytics
    'google-analytics.com': ('analytics', 'Google Analytics'),
    'googletagmanager.com': ('analytics', 'Google Tag Manager'),
    'mixpanel.com': ('analytics', 'Mixpanel'),
    'hotjar.com': ('analytics', 'Hotjar'),
    'segment.com': ('analytics', 'Segment'),
    'amplitude.com': ('analytics', 'Amplitude'),
    'heap.io': ('analytics', 'Heap'),
    'fullstory.com': ('analytics', 'FullStory'),
    
    # Advertising
    'googlesyndication.com': ('ads', 'Google AdSense'),
    'doubleclick.net': ('ads', 'Google Ads'),
    'facebook.net': ('ads', 'Facebook Pixel'),
    'adsrvr.org': ('ads', 'The Trade Desk'),
    'criteo.com': ('ads', 'Criteo'),
    
    # Social
    'twitter.com': ('social', 'Twitter'),
    'facebook.com': ('social', 'Facebook'),
    'instagram.com': ('social', 'Instagram'),
    'linkedin.com': ('social', 'LinkedIn'),
    'pinterest.com': ('social', 'Pinterest'),
    
    # CDN
    'cdnjs.cloudflare.com': ('cdn', 'Cloudflare CDN'),
    'unpkg.com': ('cdn', 'unpkg'),
    'jsdelivr.net': ('cdn', 'jsDelivr'),
    'bootstrapcdn.com': ('cdn', 'Bootstrap CDN'),
    'cloudfront.net': ('cdn', 'CloudFront'),
    'akamaized.net': ('cdn', 'Akamai'),
    
    # Fonts
    'fonts.googleapis.com': ('fonts', 'Google Fonts'),
    'fonts.gstatic.com': ('fonts', 'Google Fonts'),
    'use.typekit.net': ('fonts', 'Adobe Fonts'),
    
    # Other
    'recaptcha.net': ('security', 'reCAPTCHA'),
    'hcaptcha.com': ('security', 'hCaptcha'),
    'sentry.io': ('monitoring', 'Sentry'),
    'newrelic.com': ('monitoring', 'New Relic'),
}


# =============================================================================
# ADVANCED CAPTURE CLASS
# =============================================================================

class AdvancedCapture:
    """
    Advanced capture for deep forensic analysis.
    """
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/advanced_capture")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self._websocket_messages: List[WebSocketMessage] = []
        self._websocket_urls: List[str] = []
    
    async def capture_advanced(
        self,
        page,  # Playwright page
        url: str,
        headers: Dict[str, str] = None,
        capture_iframes: bool = True,
        capture_source_maps: bool = True,
        max_iframe_depth: int = 3,
    ) -> AdvancedCaptureResult:
        """
        Perform advanced capture on a page.
        
        Args:
            page: Playwright page object
            url: Page URL
            headers: Response headers
            capture_iframes: Recursively capture iframe content
            capture_source_maps: Download JavaScript source maps
            max_iframe_depth: Maximum iframe nesting depth
        
        Returns:
            AdvancedCaptureResult with all captured data
        """
        headers = headers or {}
        
        # Reset state
        self._websocket_messages = []
        self._websocket_urls = []
        
        # Set up WebSocket capture
        await self._setup_websocket_capture(page)
        
        # Get page content
        html = await page.content()
        
        # Extract forms
        forms = await self._extract_forms(page)
        
        # Extract iframes
        iframes = []
        if capture_iframes:
            iframes = await self._extract_iframes(page, url, max_iframe_depth)
        
        # Detect technology stack
        tech_stack = self._detect_tech_stack(html, headers)
        
        # Inventory third-party scripts
        third_party = await self._inventory_third_party(page, url)
        
        # Download source maps
        source_maps = []
        if capture_source_maps:
            source_maps = await self._download_source_maps(page, url)
        
        # Extract contact info
        contact_info = self._extract_contact_info(html)
        
        # Extract API endpoints from JavaScript
        api_endpoints = await self._extract_api_endpoints(page, html)
        
        # Analyze CSS
        css_analysis = await self._analyze_css(page)
        
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
            css_analysis=css_analysis
        )
    
    async def _setup_websocket_capture(self, page):
        """Set up WebSocket message capture."""
        
        def handle_websocket(ws):
            self._websocket_urls.append(ws.url)
            
            def on_message(payload):
                self._websocket_messages.append(WebSocketMessage(
                    url=ws.url,
                    direction='received',
                    payload=payload if isinstance(payload, str) else payload.hex(),
                    opcode=1,  # Text
                    timestamp=datetime.now().timestamp()
                ))
            
            def on_sent(payload):
                self._websocket_messages.append(WebSocketMessage(
                    url=ws.url,
                    direction='sent',
                    payload=payload if isinstance(payload, str) else payload.hex(),
                    opcode=1,
                    timestamp=datetime.now().timestamp()
                ))
            
            ws.on('framereceived', lambda data: on_message(data['payload']))
            ws.on('framesent', lambda data: on_sent(data['payload']))
        
        page.on('websocket', handle_websocket)
    
    async def _extract_forms(self, page) -> List[FormData]:
        """Extract all forms from the page."""
        forms = []
        
        form_data = await page.evaluate('''
            () => {
                const forms = [];
                document.querySelectorAll('form').forEach(form => {
                    const fields = [];
                    const hiddenFields = [];
                    
                    form.querySelectorAll('input, select, textarea').forEach(field => {
                        const fieldData = {
                            tagName: field.tagName.toLowerCase(),
                            type: field.type || '',
                            name: field.name || '',
                            id: field.id || '',
                            value: field.value || '',
                            placeholder: field.placeholder || '',
                            required: field.required || false,
                            pattern: field.pattern || '',
                            maxLength: field.maxLength || -1,
                            options: field.tagName === 'SELECT' ? 
                                Array.from(field.options).map(o => ({value: o.value, text: o.text})) : []
                        };
                        
                        if (field.type === 'hidden') {
                            hiddenFields.push(fieldData);
                        } else {
                            fields.push(fieldData);
                        }
                    });
                    
                    forms.push({
                        action: form.action || '',
                        method: form.method || 'get',
                        enctype: form.enctype || '',
                        id: form.id || '',
                        name: form.name || '',
                        fields: fields,
                        hiddenFields: hiddenFields
                    });
                });
                return forms;
            }
        ''')
        
        for fd in form_data:
            forms.append(FormData(
                action=fd['action'],
                method=fd['method'].upper(),
                enctype=fd['enctype'],
                id=fd['id'],
                name=fd['name'],
                fields=fd['fields'],
                hidden_fields=fd['hiddenFields']
            ))
        
        return forms
    
    async def _extract_iframes(
        self,
        page,
        base_url: str,
        max_depth: int,
        current_depth: int = 0
    ) -> List[Dict]:
        """Recursively extract iframe content."""
        if current_depth >= max_depth:
            return []
        
        iframes = []
        
        iframe_data = await page.evaluate('''
            () => {
                const iframes = [];
                document.querySelectorAll('iframe').forEach(iframe => {
                    iframes.push({
                        src: iframe.src || '',
                        id: iframe.id || '',
                        name: iframe.name || '',
                        sandbox: iframe.sandbox ? iframe.sandbox.toString() : '',
                        width: iframe.width || '',
                        height: iframe.height || ''
                    });
                });
                return iframes;
            }
        ''')
        
        for iframe in iframe_data:
            src = iframe['src']
            if not src or src.startswith('about:') or src.startswith('javascript:'):
                continue
            
            full_src = urljoin(base_url, src)
            iframe_info = {
                'src': full_src,
                'id': iframe['id'],
                'name': iframe['name'],
                'sandbox': iframe['sandbox'],
                'dimensions': f"{iframe['width']}x{iframe['height']}",
                'content': None,
                'nested_iframes': []
            }
            
            # Try to get iframe content
            try:
                frame = page.frame(url=re.compile(re.escape(src)))
                if frame:
                    iframe_info['content'] = await frame.content()
                    # Recursively get nested iframes
                    # Note: Would need frame's page object, simplified here
            except Exception as e:
                logger.debug(f"Could not capture iframe {src}: {e}")
            
            iframes.append(iframe_info)
        
        return iframes
    
    def _detect_tech_stack(self, html: str, headers: Dict[str, str]) -> TechnologyStack:
        """Detect the technology stack used by the page."""
        detected = {
            'cms': [],
            'frameworks': [],
            'js_libraries': [],
            'css_frameworks': [],
            'server': [],
            'analytics': [],
            'advertising': [],
            'cdn': [],
            'hosting': [],
            'ecommerce': [],
            'other': []
        }
        
        html_lower = html.lower()
        
        for tech_name, signatures in TECH_SIGNATURES.items():
            is_detected = False
            
            # Check HTML patterns
            for pattern in signatures.get('patterns', []):
                if re.search(pattern, html, re.IGNORECASE):
                    is_detected = True
                    break
            
            # Check meta tags
            for meta_name, meta_pattern in signatures.get('meta', {}).items():
                if re.search(f'<meta[^>]*name=["\']?{meta_name}["\']?[^>]*content=["\']([^"\']+)', html, re.I):
                    match = re.search(meta_pattern, html, re.I)
                    if match:
                        is_detected = True
                        break
            
            # Check headers
            for header_name, header_pattern in signatures.get('headers', {}).items():
                header_value = headers.get(header_name, '')
                if header_value and re.search(header_pattern, header_value, re.I):
                    is_detected = True
                    break
            
            if is_detected:
                # Categorize
                if tech_name in ['wordpress', 'drupal', 'joomla', 'squarespace', 'wix']:
                    detected['cms'].append(tech_name)
                elif tech_name in ['react', 'vue', 'angular', 'svelte', 'nextjs', 'nuxt', 'gatsby']:
                    detected['frameworks'].append(tech_name)
                elif tech_name in ['jquery', 'lodash', 'moment']:
                    detected['js_libraries'].append(tech_name)
                elif tech_name in ['bootstrap', 'tailwind', 'bulma']:
                    detected['css_frameworks'].append(tech_name)
                elif tech_name in ['google_analytics', 'mixpanel', 'hotjar', 'segment']:
                    detected['analytics'].append(tech_name)
                elif tech_name in ['google_ads', 'facebook_pixel']:
                    detected['advertising'].append(tech_name)
                elif tech_name in ['cloudflare', 'fastly', 'akamai', 'cloudfront']:
                    detected['cdn'].append(tech_name)
                elif tech_name in ['nginx', 'apache', 'iis']:
                    detected['server'].append(tech_name)
                elif tech_name in ['shopify']:
                    detected['ecommerce'].append(tech_name)
                else:
                    detected['other'].append(tech_name)
        
        return TechnologyStack(**detected)
    
    async def _inventory_third_party(self, page, base_url: str) -> List[ThirdPartyScript]:
        """Inventory all third-party scripts."""
        scripts = []
        base_domain = urlparse(base_url).netloc
        
        script_urls = await page.evaluate('''
            () => Array.from(document.querySelectorAll('script[src]')).map(s => s.src)
        ''')
        
        for script_url in script_urls:
            parsed = urlparse(script_url)
            domain = parsed.netloc
            
            # Check if third-party
            if domain and domain != base_domain and not domain.endswith(f'.{base_domain}'):
                category = 'other'
                name = domain
                
                # Check known domains
                for known_domain, (cat, n) in THIRD_PARTY_DOMAINS.items():
                    if known_domain in domain:
                        category = cat
                        name = n
                        break
                
                scripts.append(ThirdPartyScript(
                    url=script_url,
                    domain=domain,
                    category=category,
                    name=name,
                    hash=hashlib.md5(script_url.encode()).hexdigest()[:8]
                ))
        
        return scripts
    
    async def _download_source_maps(self, page, base_url: str) -> List[SourceMap]:
        """Download JavaScript source maps."""
        source_maps = []
        
        # Get all script URLs
        script_contents = await page.evaluate('''
            async () => {
                const scripts = [];
                for (const script of document.querySelectorAll('script[src]')) {
                    try {
                        const response = await fetch(script.src);
                        const text = await response.text();
                        scripts.push({url: script.src, content: text});
                    } catch (e) {
                        scripts.push({url: script.src, content: ''});
                    }
                }
                // Also inline scripts
                document.querySelectorAll('script:not([src])').forEach(s => {
                    scripts.push({url: '', content: s.textContent || ''});
                });
                return scripts;
            }
        ''')
        
        for script in script_contents:
            content = script['content']
            js_url = script['url']
            
            # Look for source map reference
            match = re.search(r'//[#@]\s*sourceMappingURL=(\S+)', content)
            if match:
                map_path = match.group(1)
                
                # Resolve map URL
                if js_url:
                    map_url = urljoin(js_url, map_path)
                else:
                    map_url = urljoin(base_url, map_path)
                
                # Download source map
                try:
                    map_content = await page.evaluate(f'''
                        async () => {{
                            const response = await fetch("{map_url}");
                            return await response.json();
                        }}
                    ''')
                    
                    if map_content:
                        source_maps.append(SourceMap(
                            js_url=js_url or 'inline',
                            map_url=map_url,
                            map_content=map_content,
                            original_sources=map_content.get('sources', [])
                        ))
                except Exception as e:
                    logger.debug(f"Could not download source map {map_url}: {e}")
        
        return source_maps
    
    def _extract_contact_info(self, html: str) -> ContactInfo:
        """Extract emails, phones, and social links."""
        # Email regex
        emails = list(set(re.findall(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            html
        )))
        
        # Phone regex (various formats)
        phones = list(set(re.findall(
            r'(?:\+1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}',
            html
        )))
        
        # Social links
        social_patterns = {
            'twitter': r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)',
            'facebook': r'facebook\.com/([a-zA-Z0-9.]+)',
            'instagram': r'instagram\.com/([a-zA-Z0-9_.]+)',
            'linkedin': r'linkedin\.com/(?:in|company)/([a-zA-Z0-9_-]+)',
            'youtube': r'youtube\.com/(?:c/|channel/|user/)?([a-zA-Z0-9_-]+)',
            'github': r'github\.com/([a-zA-Z0-9_-]+)',
            'tiktok': r'tiktok\.com/@([a-zA-Z0-9_.]+)',
        }
        
        social_links = {}
        for platform, pattern in social_patterns.items():
            matches = re.findall(pattern, html, re.I)
            if matches:
                social_links[platform] = list(set(matches))
        
        return ContactInfo(
            emails=emails[:50],  # Limit
            phones=phones[:20],
            social_links=social_links
        )
    
    async def _extract_api_endpoints(self, page, html: str) -> List[str]:
        """Extract API endpoints from JavaScript code."""
        endpoints = set()
        
        # Common API patterns
        api_patterns = [
            r'["\']/(api|v\d+)/[^"\']+["\']',
            r'fetch\s*\(\s*["\']([^"\']+)["\']',
            r'axios\.[a-z]+\s*\(\s*["\']([^"\']+)["\']',
            r'\$\.(?:ajax|get|post)\s*\(\s*["\']([^"\']+)["\']',
            r'XMLHttpRequest.*?open\s*\(\s*["\'][A-Z]+["\']\s*,\s*["\']([^"\']+)["\']',
            r'endpoint["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'url["\']?\s*[:=]\s*["\']([^"\']+/api[^"\']*)["\']',
        ]
        
        # Search in all scripts
        scripts = await page.evaluate('''
            () => {
                const scripts = [];
                document.querySelectorAll('script').forEach(s => {
                    scripts.push(s.textContent || '');
                });
                return scripts;
            }
        ''')
        
        all_js = '\n'.join(scripts)
        
        for pattern in api_patterns:
            for match in re.finditer(pattern, all_js, re.I):
                endpoint = match.group(1) if match.lastindex else match.group(0)
                endpoint = endpoint.strip('"\'')
                if endpoint.startswith('/') or endpoint.startswith('http'):
                    endpoints.add(endpoint)
        
        return list(endpoints)[:100]  # Limit
    
    async def _analyze_css(self, page) -> CSSAnalysis:
        """Analyze CSS used on the page."""
        css_data = await page.evaluate('''
            () => {
                const fonts = new Set();
                const colors = new Set();
                const customProps = {};
                const mediaQueries = new Set();
                
                // Get computed styles
                const body = document.body;
                const computedStyle = getComputedStyle(body);
                
                // Get all stylesheets
                for (const sheet of document.styleSheets) {
                    try {
                        for (const rule of sheet.cssRules || []) {
                            // Font families
                            if (rule.style && rule.style.fontFamily) {
                                rule.style.fontFamily.split(',').forEach(f => 
                                    fonts.add(f.trim().replace(/['"]/g, ''))
                                );
                            }
                            
                            // Colors
                            if (rule.style) {
                                ['color', 'backgroundColor', 'borderColor'].forEach(prop => {
                                    const val = rule.style[prop];
                                    if (val && val !== 'initial' && val !== 'inherit') {
                                        colors.add(val);
                                    }
                                });
                            }
                            
                            // Media queries
                            if (rule.type === CSSRule.MEDIA_RULE) {
                                mediaQueries.add(rule.conditionText);
                            }
                        }
                    } catch (e) {
                        // Cross-origin stylesheets
                    }
                }
                
                // Get CSS custom properties
                const rootStyle = getComputedStyle(document.documentElement);
                for (const prop of rootStyle) {
                    if (prop.startsWith('--')) {
                        customProps[prop] = rootStyle.getPropertyValue(prop).trim();
                    }
                }
                
                return {
                    fonts: Array.from(fonts),
                    colors: Array.from(colors).slice(0, 50),
                    customProps: customProps,
                    mediaQueries: Array.from(mediaQueries)
                };
            }
        ''')
        
        # Detect CSS frameworks
        frameworks = []
        html = await page.content()
        
        if 'bootstrap' in html.lower():
            frameworks.append('Bootstrap')
        if re.search(r'class="[^"]*\b(flex|grid|bg-|text-|p-|m-)\w+', html):
            frameworks.append('Tailwind CSS')
        if 'bulma' in html.lower():
            frameworks.append('Bulma')
        if 'foundation' in html.lower():
            frameworks.append('Foundation')
        
        return CSSAnalysis(
            fonts=css_data['fonts'][:20],
            colors=css_data['colors'],
            frameworks_detected=frameworks,
            custom_properties=css_data['customProps'],
            media_queries=css_data['mediaQueries'][:20]
        )
    
    def save_result(self, result: AdvancedCaptureResult, domain: str):
        """Save advanced capture result to disk."""
        output_dir = self.output_dir / safe_path_component(domain)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert to JSON-serializable format
        data = {
            'url': result.url,
            'timestamp': result.timestamp,
            'websocket_connections': result.websocket_connections,
            'websocket_messages': [
                {
                    'url': m.url,
                    'direction': m.direction,
                    'payload': m.payload[:1000],  # Truncate
                    'timestamp': m.timestamp
                }
                for m in result.websocket_messages
            ],
            'forms': [
                {
                    'action': f.action,
                    'method': f.method,
                    'fields': f.fields,
                    'hidden_fields': f.hidden_fields
                }
                for f in result.forms
            ],
            'iframes': result.iframes,
            'tech_stack': {
                'cms': result.tech_stack.cms,
                'frameworks': result.tech_stack.frameworks,
                'js_libraries': result.tech_stack.js_libraries,
                'css_frameworks': result.tech_stack.css_frameworks,
                'analytics': result.tech_stack.analytics,
                'advertising': result.tech_stack.advertising,
                'cdn': result.tech_stack.cdn,
                'server': result.tech_stack.server,
            },
            'third_party_scripts': [
                {
                    'url': s.url,
                    'domain': s.domain,
                    'category': s.category,
                    'name': s.name
                }
                for s in result.third_party_scripts
            ],
            'source_maps': [
                {
                    'js_url': sm.js_url,
                    'map_url': sm.map_url,
                    'original_sources': sm.original_sources
                }
                for sm in result.source_maps
            ],
            'contact_info': {
                'emails': result.contact_info.emails,
                'phones': result.contact_info.phones,
                'social_links': result.contact_info.social_links
            },
            'api_endpoints': result.api_endpoints,
            'css_analysis': {
                'fonts': result.css_analysis.fonts,
                'colors': result.css_analysis.colors,
                'frameworks': result.css_analysis.frameworks_detected,
                'custom_properties': result.css_analysis.custom_properties,
                'media_queries': result.css_analysis.media_queries
            }
        }
        
        with open(output_dir / 'advanced_capture.json', 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Advanced capture saved to: {output_dir}")
        return output_dir


if __name__ == "__main__":
    print("Advanced Capture Module - Use with Playwright page object")
    print("See death_star_v2.py for integration")
