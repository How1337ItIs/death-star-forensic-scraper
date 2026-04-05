#!/usr/bin/env python3
"""
X (Twitter) Community Scraper
==============================

Specialized scraper for X/Twitter communities.

X communities require:
1. Authentication (logged-in session)
2. Playwright stealth browser
3. Infinite scroll handling
4. API interception

Usage:
------
    # With cookies file (exported from browser)
    python x_community_scraper.py --target https://x.com/i/communities/2012672579388022846 --cookies x_cookies.json

    # With session token
    python x_community_scraper.py --target https://x.com/i/communities/2012672579388022846 --auth-token YOUR_AUTH_TOKEN

Export cookies from browser:
    1. Install "EditThisCookie" or similar extension
    2. Log into x.com
    3. Export cookies as JSON
    4. Save to x_cookies.json

Author: SOL-CANNABIS Death Star
"""

import argparse
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("x_community_scraper")


@dataclass
class XPost:
    """A post from X/Twitter."""
    id: str
    author_handle: str
    author_name: str
    author_avatar: str
    content: str
    timestamp: str
    likes: int
    reposts: int
    replies: int
    views: int
    media: List[str]
    quoted_post: Optional[Dict] = None
    url: str = ""


@dataclass
class XCommunityMember:
    """Community member info."""
    handle: str
    name: str
    avatar: str
    role: str  # admin, moderator, member
    bio: str


@dataclass
class XCommunityData:
    """Complete community data."""
    id: str
    name: str
    description: str
    rules: List[str]
    member_count: int
    created_at: str
    banner_image: str
    posts: List[XPost]
    members: List[XCommunityMember]
    scraped_at: str


class XCommunityScraper:
    """
    Specialized scraper for X/Twitter communities.
    
    Uses Playwright with stealth to scrape authenticated X content.
    """
    
    def __init__(
        self,
        output_dir: Path = None,
        cookies_file: str = None,
        auth_token: str = None,
    ):
        self.output_dir = Path(output_dir or "data/x_communities")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.cookies_file = cookies_file
        self.auth_token = auth_token
        
        self._browser = None
        self._context = None
        self._playwright = None
        self._page = None
        
        # Captured API responses
        self._api_responses: List[Dict] = []
        self._posts: Dict[str, XPost] = {}
        self._members: Dict[str, XCommunityMember] = {}
    
    async def _setup_browser(self):
        """Set up Playwright browser with stealth."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        
        self._playwright = await async_playwright().start()
        
        # Launch with stealth settings
        self._browser = await self._playwright.chromium.launch(
            headless=False,  # Use headed mode for X (better success rate)
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-size=1920,1080',
            ]
        )
        
        # Create context with realistic settings
        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
            permissions=['geolocation'],
        )
        
        # Apply stealth scripts
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)
        
        # Load cookies if provided
        if self.cookies_file:
            await self._load_cookies()
        elif self.auth_token:
            await self._set_auth_token()
        
        self._page = await self._context.new_page()
        
        # Set up response interception for API calls
        self._page.on('response', self._handle_response)
        
        return True
    
    async def _load_cookies(self):
        """Load cookies from file."""
        path = Path(self.cookies_file)
        if not path.exists():
            logger.warning(f"Cookie file not found: {self.cookies_file}")
            return
        
        try:
            cookies = json.loads(path.read_text())
            
            # Normalize cookies for Playwright
            playwright_cookies = []
            for cookie in cookies:
                pc = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain', '.x.com'),
                    'path': cookie.get('path', '/'),
                }
                if cookie.get('expirationDate'):
                    pc['expires'] = int(cookie['expirationDate'])
                if cookie.get('httpOnly'):
                    pc['httpOnly'] = cookie['httpOnly']
                if cookie.get('secure'):
                    pc['secure'] = cookie['secure']
                
                # Normalize sameSite - Playwright expects Strict, Lax, or None
                same_site = cookie.get('sameSite', '')
                if same_site:
                    same_site_lower = same_site.lower()
                    if same_site_lower == 'strict':
                        pc['sameSite'] = 'Strict'
                    elif same_site_lower == 'lax':
                        pc['sameSite'] = 'Lax'
                    elif same_site_lower in ('none', 'no_restriction'):
                        pc['sameSite'] = 'None'
                    # Skip 'unspecified' or unknown values - let Playwright use default
                
                playwright_cookies.append(pc)
            
            await self._context.add_cookies(playwright_cookies)
            logger.info(f"Loaded {len(playwright_cookies)} cookies")
            
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
    
    async def _set_auth_token(self):
        """Set auth_token cookie directly."""
        await self._context.add_cookies([
            {
                'name': 'auth_token',
                'value': self.auth_token,
                'domain': '.x.com',
                'path': '/',
                'secure': True,
                'httpOnly': True,
            }
        ])
        logger.info("Set auth_token cookie")
    
    async def _handle_response(self, response):
        """Handle API responses to capture data."""
        url = response.url
        
        # Capture community-related API calls
        if '/Communities' in url or '/CommunityTweets' in url or 'TweetDetail' in url:
            try:
                data = await response.json()
                self._api_responses.append({
                    'url': url,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Parse posts from response
                self._parse_api_response(data)
                
            except Exception as e:
                logger.debug(f"Could not parse API response: {e}")
    
    def _parse_api_response(self, data: Dict):
        """Parse X API response to extract posts."""
        try:
            # Navigate the nested response structure
            instructions = (
                data.get('data', {})
                .get('community', {})
                .get('community_timeline', {})
                .get('timeline', {})
                .get('instructions', [])
            )
            
            if not instructions:
                # Try alternate path for tweets
                instructions = (
                    data.get('data', {})
                    .get('communityResults', {})
                    .get('result', {})
                    .get('ranked_community_timeline', {})
                    .get('timeline', {})
                    .get('instructions', [])
                )
            
            for instruction in instructions:
                entries = instruction.get('entries', [])
                for entry in entries:
                    self._parse_entry(entry)
                    
        except Exception as e:
            logger.debug(f"Error parsing API response: {e}")
    
    def _parse_entry(self, entry: Dict):
        """Parse a timeline entry to extract post data."""
        try:
            content = entry.get('content', {})
            item_content = content.get('itemContent', {})
            
            tweet_results = item_content.get('tweet_results', {})
            result = tweet_results.get('result', {})
            
            if result.get('__typename') != 'Tweet':
                return
            
            legacy = result.get('legacy', {})
            user = result.get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {})
            
            post_id = legacy.get('id_str', '')
            if not post_id or post_id in self._posts:
                return
            
            # Extract media
            media = []
            extended_entities = legacy.get('extended_entities', {})
            for m in extended_entities.get('media', []):
                if m.get('type') == 'photo':
                    media.append(m.get('media_url_https', ''))
                elif m.get('type') == 'video':
                    variants = m.get('video_info', {}).get('variants', [])
                    # Get highest quality video
                    video_urls = [v['url'] for v in variants if v.get('content_type') == 'video/mp4']
                    if video_urls:
                        media.append(video_urls[-1])
            
            post = XPost(
                id=post_id,
                author_handle=user.get('screen_name', ''),
                author_name=user.get('name', ''),
                author_avatar=user.get('profile_image_url_https', ''),
                content=legacy.get('full_text', ''),
                timestamp=legacy.get('created_at', ''),
                likes=legacy.get('favorite_count', 0),
                reposts=legacy.get('retweet_count', 0),
                replies=legacy.get('reply_count', 0),
                views=result.get('views', {}).get('count', 0),
                media=media,
                url=f"https://x.com/{user.get('screen_name')}/status/{post_id}"
            )
            
            self._posts[post_id] = post
            logger.debug(f"Captured post: {post_id[:8]}... by @{post.author_handle}")
            
        except Exception as e:
            logger.debug(f"Error parsing entry: {e}")
    
    async def _scroll_and_load(self, max_scrolls: int = 20, scroll_delay: float = 2.0):
        """Scroll to load more content."""
        logger.info(f"Scrolling to load content (max {max_scrolls} scrolls)...")
        
        last_post_count = 0
        stale_count = 0
        
        for i in range(max_scrolls):
            # Scroll down
            await self._page.evaluate('window.scrollBy(0, window.innerHeight)')
            await asyncio.sleep(scroll_delay)
            
            # Check if we got new posts
            current_count = len(self._posts)
            if current_count == last_post_count:
                stale_count += 1
                if stale_count >= 3:
                    logger.info("No new content after 3 scrolls, stopping")
                    break
            else:
                stale_count = 0
                logger.info(f"Scroll {i+1}: {current_count} posts captured")
            
            last_post_count = current_count
        
        logger.info(f"Finished scrolling. Total posts: {len(self._posts)}")
    
    async def scrape_community(
        self,
        url: str,
        max_posts: int = 100,
        max_scrolls: int = 20,
    ) -> Optional[XCommunityData]:
        """
        Scrape an X community.
        
        Args:
            url: Community URL (e.g., https://x.com/i/communities/2012672579388022846)
            max_posts: Maximum posts to scrape
            max_scrolls: Maximum scroll iterations
        
        Returns:
            XCommunityData with all scraped content
        """
        if not await self._setup_browser():
            return None
        
        # Extract community ID
        match = re.search(r'/communities/(\d+)', url)
        if not match:
            logger.error(f"Invalid community URL: {url}")
            return None
        
        community_id = match.group(1)
        logger.info(f"🎯 Targeting X Community: {community_id}")
        
        try:
            # Navigate to community
            logger.info(f"Navigating to {url}...")
            # Use 'domcontentloaded' instead of 'networkidle' - X never stops loading
            await self._page.goto(url, wait_until='domcontentloaded', timeout=90000)
            # Wait for content to render
            await asyncio.sleep(5)
            
            # Check if logged in
            if 'login' in self._page.url.lower() or 'signin' in self._page.url.lower():
                logger.error("Not logged in! Please provide valid cookies or auth_token.")
                logger.info("To get cookies:")
                logger.info("  1. Install 'EditThisCookie' browser extension")
                logger.info("  2. Log into x.com")
                logger.info("  3. Export cookies as JSON")
                logger.info("  4. Run with: --cookies path/to/cookies.json")
                return None
            
            # Wait for content to load
            await asyncio.sleep(2)
            
            # Extract community metadata from page
            community_name = await self._extract_text('[data-testid="communityName"]')
            community_desc = await self._extract_text('[data-testid="communityDescription"]')
            
            # If selectors fail, try alternatives
            if not community_name:
                community_name = await self._page.title()
                community_name = community_name.replace(' / X', '').strip()
            
            # Get member count
            member_count = 0
            member_text = await self._extract_text('[data-testid="memberCount"]')
            if member_text:
                nums = re.findall(r'[\d,]+', member_text)
                if nums:
                    member_count = int(nums[0].replace(',', ''))
            
            # Take screenshot
            screenshot_path = self.output_dir / f"{community_id}_screenshot.png"
            await self._page.screenshot(path=str(screenshot_path), full_page=False)
            logger.info(f"Screenshot saved: {screenshot_path}")
            
            # Scroll to load posts
            await self._scroll_and_load(max_scrolls=max_scrolls)
            
            # Convert posts dict to list
            posts = list(self._posts.values())[:max_posts]
            
            # Build result
            result = XCommunityData(
                id=community_id,
                name=community_name or f"Community {community_id}",
                description=community_desc or "",
                rules=[],
                member_count=member_count,
                created_at="",
                banner_image="",
                posts=posts,
                members=list(self._members.values()),
                scraped_at=datetime.now().isoformat()
            )
            
            # Save results
            await self._save_results(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            await self.close()
    
    async def _extract_text(self, selector: str) -> str:
        """Safely extract text from selector."""
        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.inner_text()
        except Exception:
            pass
        return ""
    
    async def _save_results(self, data: XCommunityData):
        """Save scraped data to files."""
        output_dir = self.output_dir / data.id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON
        json_path = output_dir / "community_data.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'id': data.id,
                'name': data.name,
                'description': data.description,
                'rules': data.rules,
                'member_count': data.member_count,
                'created_at': data.created_at,
                'scraped_at': data.scraped_at,
                'posts': [
                    {
                        'id': p.id,
                        'author_handle': p.author_handle,
                        'author_name': p.author_name,
                        'content': p.content,
                        'timestamp': p.timestamp,
                        'likes': p.likes,
                        'reposts': p.reposts,
                        'replies': p.replies,
                        'views': p.views,
                        'media': p.media,
                        'url': p.url,
                    }
                    for p in data.posts
                ]
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved community data: {json_path}")
        
        # Save posts as markdown for easy reading
        md_path = output_dir / "posts.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# {data.name}\n\n")
            f.write(f"**Community ID:** {data.id}\n")
            f.write(f"**Members:** {data.member_count:,}\n")
            f.write(f"**Description:** {data.description}\n")
            f.write(f"**Scraped:** {data.scraped_at}\n\n")
            f.write("---\n\n")
            
            for post in data.posts:
                f.write(f"## @{post.author_handle} ({post.author_name})\n\n")
                f.write(f"{post.content}\n\n")
                f.write(f"- Likes: {post.likes} | Reposts: {post.reposts} | Replies: {post.replies}\n")
                f.write(f"- Posted: {post.timestamp}\n")
                f.write(f"- [Link]({post.url})\n\n")
                if post.media:
                    f.write("**Media:**\n")
                    for m in post.media:
                        f.write(f"- {m}\n")
                f.write("\n---\n\n")
        
        logger.info(f"Saved posts markdown: {md_path}")
        
        # Save raw API responses for debugging
        api_path = output_dir / "raw_api_responses.json"
        with open(api_path, 'w', encoding='utf-8') as f:
            json.dump(self._api_responses, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved API responses: {api_path}")
    
    async def close(self):
        """Clean up browser resources."""
        if self._page:
            await self._page.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


async def main():
    parser = argparse.ArgumentParser(
        description="X (Twitter) Community Scraper - Death Star Module",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # With cookies (recommended)
    python x_community_scraper.py --target https://x.com/i/communities/123456 --cookies x_cookies.json

    # With auth token
    python x_community_scraper.py --target https://x.com/i/communities/123456 --auth-token YOUR_TOKEN

How to get cookies:
    1. Install "EditThisCookie" Chrome extension (or similar)
    2. Log into x.com in your browser
    3. Click the cookie icon and export as JSON
    4. Save the file and use with --cookies flag
        """
    )
    
    parser.add_argument("--target", "-t", required=True, 
                       help="X Community URL")
    parser.add_argument("--cookies", "-c",
                       help="Path to cookies JSON file (exported from browser)")
    parser.add_argument("--auth-token", 
                       help="X auth_token cookie value")
    parser.add_argument("--max-posts", type=int, default=100,
                       help="Maximum posts to scrape (default: 100)")
    parser.add_argument("--max-scrolls", type=int, default=20,
                       help="Maximum scroll iterations (default: 20)")
    parser.add_argument("--output", "-o",
                       help="Output directory")
    
    args = parser.parse_args()
    
    if not args.cookies and not args.auth_token:
        logger.warning("No authentication provided. X communities require login.")
        logger.info("Use --cookies or --auth-token to authenticate.")
    
    output_dir = Path(args.output) if args.output else None
    
    scraper = XCommunityScraper(
        output_dir=output_dir,
        cookies_file=args.cookies,
        auth_token=args.auth_token,
    )
    
    result = await scraper.scrape_community(
        url=args.target,
        max_posts=args.max_posts,
        max_scrolls=args.max_scrolls,
    )
    
    if result:
        print(f"\n{'='*60}")
        print(f"[TARGET] COMMUNITY SCRAPED: {result.name}")
        print(f"   ID: {result.id}")
        print(f"   Members: {result.member_count:,}")
        print(f"   Posts captured: {len(result.posts)}")
        print(f"{'='*60}")
    else:
        print("\n[X] Scraping failed. Check logs above for details.")


if __name__ == "__main__":
    asyncio.run(main())
