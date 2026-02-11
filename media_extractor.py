#!/usr/bin/env python3
"""
Media Extractor Module
======================

Downloads all media (video, audio, images) from web pages.
Integrates with yt-dlp for comprehensive video extraction.

Features:
---------
1. Video downloading from 1000+ sites (via yt-dlp)
2. Audio extraction
3. Image gallery downloading
4. Embedded media detection
5. Thumbnail extraction
6. Metadata preservation

Usage:
------
    from media_extractor import MediaExtractor
    
    extractor = MediaExtractor(output_dir="data/media")
    results = await extractor.extract_all(url, html)
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("media_extractor")


def safe_path_component(value: str) -> str:
    """Make a string safe for cross-platform file and directory names."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


@dataclass
class MediaItem:
    """Extracted media item."""
    url: str
    media_type: str  # video, audio, image, document
    source_url: str  # page it was found on
    filename: str
    file_path: Optional[str]
    file_size: int
    file_hash: str
    metadata: Dict[str, Any]
    extracted_at: str


@dataclass
class ExtractionResult:
    """Result of media extraction."""
    source_url: str
    videos: List[MediaItem]
    audios: List[MediaItem]
    images: List[MediaItem]
    documents: List[MediaItem]
    embedded_players: List[Dict]  # YouTube, Vimeo, etc.
    failed: List[Dict]
    total_size: int
    extracted_at: str


class MediaExtractor:
    """
    Comprehensive media extraction from web pages.
    """
    
    # Supported video platforms (yt-dlp handles these)
    VIDEO_PLATFORMS = [
        'youtube.com', 'youtu.be',
        'vimeo.com',
        'dailymotion.com',
        'twitch.tv',
        'facebook.com',
        'twitter.com', 'x.com',
        'instagram.com',
        'tiktok.com',
        'reddit.com',
        'soundcloud.com',
        'bandcamp.com',
        'archive.org',
    ]
    
    # Image extensions
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico', '.avif'}
    
    # Audio extensions
    AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.wma'}
    
    # Video extensions
    VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v'}
    
    # Document extensions
    DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.epub'}
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/media")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        (self.output_dir / "videos").mkdir(exist_ok=True)
        (self.output_dir / "audio").mkdir(exist_ok=True)
        (self.output_dir / "images").mkdir(exist_ok=True)
        (self.output_dir / "documents").mkdir(exist_ok=True)
        (self.output_dir / "thumbnails").mkdir(exist_ok=True)
        
        self._ytdlp_available = self._check_ytdlp()
    
    def _check_ytdlp(self) -> bool:
        """Check if yt-dlp is available."""
        try:
            result = subprocess.run(['yt-dlp', '--version'], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            logger.warning("yt-dlp not available. Install: pip install yt-dlp")
            return False
    
    async def extract_all(
        self,
        url: str,
        html: str,
        download_videos: bool = True,
        download_audio: bool = True,
        download_images: bool = True,
        download_documents: bool = True,
        max_video_size_mb: int = 500,
        max_image_size_mb: int = 50,
    ) -> ExtractionResult:
        """
        Extract all media from a page.
        
        Args:
            url: Source page URL
            html: Page HTML content
            download_videos: Download video files
            download_audio: Download audio files
            download_images: Download image files
            download_documents: Download document files
            max_video_size_mb: Skip videos larger than this
            max_image_size_mb: Skip images larger than this
        
        Returns:
            ExtractionResult with all extracted media
        """
        parsed = urlparse(url)
        domain_raw = (parsed.hostname or parsed.netloc).replace("www.", "")
        domain = safe_path_component(domain_raw)
        
        videos = []
        audios = []
        images = []
        documents = []
        embedded_players = []
        failed = []
        total_size = 0
        
        # Extract embedded video players
        embedded_players = self._find_embedded_players(html, url)
        
        # Download embedded videos via yt-dlp
        if download_videos and self._ytdlp_available:
            for embed in embedded_players:
                try:
                    result = await self._download_with_ytdlp(
                        embed['url'],
                        url,
                        domain,
                        max_size_mb=max_video_size_mb
                    )
                    if result:
                        videos.append(result)
                        if result.file_size:
                            total_size += result.file_size
                except Exception as e:
                    failed.append({'url': embed['url'], 'error': str(e)})
        
        # Extract direct media links
        media_links = self._extract_media_links(html, url)
        
        # Download images
        if download_images:
            for img_url in media_links.get('images', []):
                try:
                    result = await self._download_file(
                        img_url, url, domain, 'image',
                        max_size_mb=max_image_size_mb
                    )
                    if result:
                        images.append(result)
                        total_size += result.file_size
                except Exception as e:
                    failed.append({'url': img_url, 'error': str(e)})
        
        # Download audio
        if download_audio:
            for audio_url in media_links.get('audio', []):
                try:
                    result = await self._download_file(
                        audio_url, url, domain, 'audio'
                    )
                    if result:
                        audios.append(result)
                        total_size += result.file_size
                except Exception as e:
                    failed.append({'url': audio_url, 'error': str(e)})
        
        # Download videos (direct links)
        if download_videos:
            for video_url in media_links.get('videos', []):
                try:
                    result = await self._download_file(
                        video_url, url, domain, 'video',
                        max_size_mb=max_video_size_mb
                    )
                    if result:
                        videos.append(result)
                        total_size += result.file_size
                except Exception as e:
                    failed.append({'url': video_url, 'error': str(e)})
        
        # Download documents
        if download_documents:
            for doc_url in media_links.get('documents', []):
                try:
                    result = await self._download_file(
                        doc_url, url, domain, 'document'
                    )
                    if result:
                        documents.append(result)
                        total_size += result.file_size
                except Exception as e:
                    failed.append({'url': doc_url, 'error': str(e)})
        
        return ExtractionResult(
            source_url=url,
            videos=videos,
            audios=audios,
            images=images,
            documents=documents,
            embedded_players=embedded_players,
            failed=failed,
            total_size=total_size,
            extracted_at=datetime.now().isoformat()
        )
    
    def _find_embedded_players(self, html: str, base_url: str) -> List[Dict]:
        """Find embedded video players in HTML."""
        embeds = []
        
        # YouTube
        youtube_patterns = [
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
            r'youtu\.be/([a-zA-Z0-9_-]{11})',
            r'youtube-nocookie\.com/embed/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in youtube_patterns:
            for match in re.finditer(pattern, html):
                video_id = match.group(1)
                embeds.append({
                    'platform': 'youtube',
                    'video_id': video_id,
                    'url': f'https://www.youtube.com/watch?v={video_id}'
                })
        
        # Vimeo
        vimeo_patterns = [
            r'player\.vimeo\.com/video/(\d+)',
            r'vimeo\.com/(\d+)',
        ]
        for pattern in vimeo_patterns:
            for match in re.finditer(pattern, html):
                video_id = match.group(1)
                embeds.append({
                    'platform': 'vimeo',
                    'video_id': video_id,
                    'url': f'https://vimeo.com/{video_id}'
                })
        
        # Dailymotion
        dm_pattern = r'dailymotion\.com/(?:video|embed/video)/([a-zA-Z0-9]+)'
        for match in re.finditer(dm_pattern, html):
            video_id = match.group(1)
            embeds.append({
                'platform': 'dailymotion',
                'video_id': video_id,
                'url': f'https://www.dailymotion.com/video/{video_id}'
            })
        
        # SoundCloud
        sc_pattern = r'soundcloud\.com/([^"\'>\s]+)'
        for match in re.finditer(sc_pattern, html):
            path = match.group(1)
            if not path.startswith('player'):
                embeds.append({
                    'platform': 'soundcloud',
                    'path': path,
                    'url': f'https://soundcloud.com/{path}'
                })
        
        # Archive.org (Grateful Dead!)
        archive_pattern = r'archive\.org/(?:details|embed)/([^"\'>\s]+)'
        for match in re.finditer(archive_pattern, html):
            identifier = match.group(1)
            embeds.append({
                'platform': 'archive.org',
                'identifier': identifier,
                'url': f'https://archive.org/details/{identifier}'
            })
        
        # Bandcamp
        bc_pattern = r'bandcamp\.com/(?:album|track)/([^"\'>\s]+)'
        for match in re.finditer(bc_pattern, html):
            path = match.group(1)
            # Extract domain from embed src
            domain_match = re.search(r'([a-z0-9-]+)\.bandcamp\.com', html)
            if domain_match:
                embeds.append({
                    'platform': 'bandcamp',
                    'url': f'https://{domain_match.group(1)}.bandcamp.com/{path}'
                })
        
        # Deduplicate
        seen = set()
        unique_embeds = []
        for embed in embeds:
            if embed['url'] not in seen:
                seen.add(embed['url'])
                unique_embeds.append(embed)
        
        return unique_embeds
    
    def _extract_media_links(self, html: str, base_url: str) -> Dict[str, List[str]]:
        """Extract direct media links from HTML."""
        media = {
            'images': [],
            'videos': [],
            'audio': [],
            'documents': []
        }
        
        # Images: <img src> (any URL; CDNs often omit extension) + others with image ext
        seen_img = set()
        for match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
            url = match.group(1).strip()
            if url.startswith('data:'):
                continue
            full_url = urljoin(base_url, url)
            if full_url not in seen_img:
                media['images'].append(full_url)
                seen_img.add(full_url)
        img_patterns = [
            r'<source[^>]+srcset=["\']([^"\']+)["\']',
            r'background-image:\s*url\(["\']?([^"\')\s]+)',
            r'data-src=["\']([^"\']+)["\']',
            r'data-lazy-src=["\']([^"\']+)["\']',
        ]
        for pattern in img_patterns:
            for match in re.finditer(pattern, html, re.I):
                url = match.group(1).strip()
                if url.startswith('data:'):
                    continue
                if any(url.lower().split('?')[0].endswith(ext) for ext in self.IMAGE_EXTENSIONS):
                    full_url = urljoin(base_url, url)
                    if full_url not in seen_img:
                        media['images'].append(full_url)
                        seen_img.add(full_url)
        
        # Videos
        video_patterns = [
            r'<video[^>]+src=["\']([^"\']+)["\']',
            r'<source[^>]+src=["\']([^"\']+)["\'][^>]+type=["\']video/',
        ]
        
        for pattern in video_patterns:
            for match in re.finditer(pattern, html, re.I):
                url = match.group(1)
                full_url = urljoin(base_url, url)
                if full_url not in media['videos']:
                    media['videos'].append(full_url)
        
        # Also find video links in href
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            url = match.group(1)
            if any(url.lower().endswith(ext) for ext in self.VIDEO_EXTENSIONS):
                full_url = urljoin(base_url, url)
                if full_url not in media['videos']:
                    media['videos'].append(full_url)
        
        # Audio
        audio_patterns = [
            r'<audio[^>]+src=["\']([^"\']+)["\']',
            r'<source[^>]+src=["\']([^"\']+)["\'][^>]+type=["\']audio/',
        ]
        
        for pattern in audio_patterns:
            for match in re.finditer(pattern, html, re.I):
                url = match.group(1)
                full_url = urljoin(base_url, url)
                if full_url not in media['audio']:
                    media['audio'].append(full_url)
        
        # Also find audio links in href
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            url = match.group(1)
            if any(url.lower().endswith(ext) for ext in self.AUDIO_EXTENSIONS):
                full_url = urljoin(base_url, url)
                if full_url not in media['audio']:
                    media['audio'].append(full_url)
        
        # Documents
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            url = match.group(1)
            if any(url.lower().endswith(ext) for ext in self.DOCUMENT_EXTENSIONS):
                full_url = urljoin(base_url, url)
                if full_url not in media['documents']:
                    media['documents'].append(full_url)
        
        return media
    
    async def _download_with_ytdlp(
        self,
        url: str,
        source_url: str,
        domain: str,
        max_size_mb: int = 500
    ) -> Optional[MediaItem]:
        """Download video using yt-dlp."""
        output_dir = self.output_dir / "videos" / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get video info first
        info_cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-download',
            url
        ]
        
        try:
            result = subprocess.run(
                info_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.debug(f"yt-dlp info failed for {url}")
                return None
            
            info = json.loads(result.stdout)
            
            # Check size
            filesize = info.get('filesize') or info.get('filesize_approx') or 0
            if filesize > max_size_mb * 1024 * 1024:
                logger.info(f"Skipping {url} - too large ({filesize / 1024 / 1024:.1f}MB)")
                return None
            
            # Download
            output_template = str(output_dir / '%(id)s.%(ext)s')
            download_cmd = [
                'yt-dlp',
                '-f', 'best[filesize<500M]/best',
                '--write-info-json',
                '--write-thumbnail',
                '-o', output_template,
                url
            ]
            
            result = subprocess.run(
                download_cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 min max
            )
            
            if result.returncode != 0:
                logger.debug(f"yt-dlp download failed for {url}")
                return None
            
            # Find downloaded file
            video_id = info.get('id', hashlib.md5(url.encode()).hexdigest()[:8])
            ext = info.get('ext', 'mp4')
            filename = f"{video_id}.{ext}"
            filepath = output_dir / filename
            
            if not filepath.exists():
                # Try to find it
                for f in output_dir.glob(f"{video_id}.*"):
                    if f.suffix not in ['.json', '.jpg', '.png', '.webp']:
                        filepath = f
                        filename = f.name
                        break
            
            if not filepath.exists():
                return None
            
            file_size = filepath.stat().st_size
            file_hash = hashlib.sha256(filepath.read_bytes()).hexdigest()[:16]
            
            return MediaItem(
                url=url,
                media_type='video',
                source_url=source_url,
                filename=filename,
                file_path=str(filepath),
                file_size=file_size,
                file_hash=file_hash,
                metadata={
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                    'upload_date': info.get('upload_date'),
                    'description': info.get('description', '')[:500],
                    'view_count': info.get('view_count'),
                    'platform': info.get('extractor'),
                },
                extracted_at=datetime.now().isoformat()
            )
            
        except subprocess.TimeoutExpired:
            logger.warning(f"yt-dlp timeout for {url}")
            return None
        except json.JSONDecodeError:
            logger.debug(f"Failed to parse yt-dlp output for {url}")
            return None
        except Exception as e:
            logger.debug(f"yt-dlp error for {url}: {e}")
            return None
    
    async def _download_file(
        self,
        url: str,
        source_url: str,
        domain: str,
        media_type: str,
        max_size_mb: int = 100
    ) -> Optional[MediaItem]:
        """Download a direct file."""
        try:
            import httpx
        except ImportError:
            import requests as httpx
        
        # Determine output directory
        type_dirs = {
            'image': 'images',
            'video': 'videos',
            'audio': 'audio',
            'document': 'documents'
        }
        output_dir = self.output_dir / type_dirs.get(media_type, 'other') / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Head request first to check size
            if hasattr(httpx, 'AsyncClient'):
                async with httpx.AsyncClient() as client:
                    head = await client.head(url, follow_redirects=True, timeout=10)
                    content_length = int(head.headers.get('content-length', 0))
                    
                    if content_length > max_size_mb * 1024 * 1024:
                        logger.debug(f"Skipping {url} - too large")
                        return None
                    
                    response = await client.get(url, follow_redirects=True, timeout=60)
            else:
                head = httpx.head(url, allow_redirects=True, timeout=10)
                content_length = int(head.headers.get('content-length', 0))
                
                if content_length > max_size_mb * 1024 * 1024:
                    return None
                
                response = httpx.get(url, allow_redirects=True, timeout=60)
            
            if response.status_code != 200:
                return None
            
            content = response.content
            
            # Generate filename
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix
            if not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext or ""):
                ext = '.bin'
            stem = safe_path_component(Path(parsed.path).stem)[:30]
            filename = f"{stem}_{url_hash}{ext}"
            filepath = output_dir / filename
            
            # Save file
            with open(filepath, 'wb') as f:
                f.write(content)
            
            file_hash = hashlib.sha256(content).hexdigest()[:16]
            
            return MediaItem(
                url=url,
                media_type=media_type,
                source_url=source_url,
                filename=filename,
                file_path=str(filepath),
                file_size=len(content),
                file_hash=file_hash,
                metadata={
                    'content_type': response.headers.get('content-type'),
                },
                extracted_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.debug(f"Failed to download {url}: {e}")
            return None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def extract_media_from_url(url: str, html: str = None) -> ExtractionResult:
    """
    Extract all media from a URL.
    
    If HTML is not provided, fetches the page first.
    """
    if html is None:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=30)
            html = response.text
    
    extractor = MediaExtractor()
    return await extractor.extract_all(url, html)


if __name__ == "__main__":
    def _is_http_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    parser = argparse.ArgumentParser(
        description="Extract media from a single URL."
    )
    parser.add_argument("url", help="Target URL (must include http:// or https://)")
    parser.add_argument(
        "--output",
        "-o",
        default="data/media",
        help="Output directory (default: data/media)",
    )
    args = parser.parse_args()

    if not _is_http_url(args.url):
        parser.error("url must include a valid http:// or https:// scheme")

    async def main():
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for standalone media extraction") from exc

        async with httpx.AsyncClient() as client:
            response = await client.get(args.url, follow_redirects=True, timeout=30)
            response.raise_for_status()

        extractor = MediaExtractor(output_dir=Path(args.output))
        result = await extractor.extract_all(args.url, response.text)

        print("\nMedia extraction complete")
        print(f"   Source: {result.source_url}")
        print(f"   Videos: {len(result.videos)}")
        print(f"   Audio: {len(result.audios)}")
        print(f"   Images: {len(result.images)}")
        print(f"   Documents: {len(result.documents)}")
        print(f"   Embedded players: {len(result.embedded_players)}")
        print(f"   Total size: {result.total_size / 1024 / 1024:.1f} MB")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
