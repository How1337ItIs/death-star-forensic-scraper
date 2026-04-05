"""
Media Extractor Module
======================

Extract and download media from web pages:
- Videos (via yt-dlp)
- Audio files
- Images
- Documents
"""

import asyncio
import hashlib
import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("death_star.media")


@dataclass
class MediaItem:
    """A media item."""
    url: str
    type: str  # video, audio, image, document
    title: str
    size: int
    local_path: Optional[str] = None


@dataclass
class MediaResult:
    """Result of media extraction."""
    url: str
    videos: List[MediaItem] = field(default_factory=list)
    audios: List[MediaItem] = field(default_factory=list)
    images: List[MediaItem] = field(default_factory=list)
    documents: List[MediaItem] = field(default_factory=list)
    embedded_players: List[Dict] = field(default_factory=list)
    total_size: int = 0


class MediaExtractor:
    """
    Extract and download media from web pages.
    
    Usage:
        extractor = MediaExtractor(output_dir="data/media")
        result = await extractor.extract_all(url, html)
    """
    
    # Video platforms supported by yt-dlp
    VIDEO_PATTERNS = [
        r"youtube\.com/watch",
        r"youtu\.be/",
        r"vimeo\.com/",
        r"soundcloud\.com/",
        r"bandcamp\.com/",
        r"archive\.org/details/",
        r"dailymotion\.com/",
        r"twitch\.tv/",
    ]
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir or "data/media")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def extract_all(self, url: str, html: str) -> MediaResult:
        """
        Extract all media from a page.
        
        Args:
            url: Page URL
            html: Page HTML
        
        Returns:
            MediaResult with all found media
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "lxml")
        domain = urlparse(url).netloc
        
        output_dir = self.output_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        result = MediaResult(url=url)
        
        # Images
        result.images = await self._extract_images(soup, url, output_dir)
        
        # Videos (native)
        result.videos = await self._extract_videos(soup, url, output_dir)
        
        # Audio
        result.audios = await self._extract_audio(soup, url, output_dir)
        
        # Documents
        result.documents = await self._extract_documents(soup, url, output_dir)
        
        # Embedded players (YouTube, Vimeo, etc.)
        result.embedded_players = self._find_embedded_players(soup, html)
        
        # Calculate total size
        for item in result.images + result.videos + result.audios + result.documents:
            result.total_size += item.size
        
        return result
    
    async def _extract_images(self, soup, base_url: str, output_dir: Path) -> List[MediaItem]:
        """Extract and download images."""
        images = []
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)
        
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if not src.startswith("data:"):
                full_url = urljoin(base_url, src)
                
                # Download
                item = await self._download_file(full_url, images_dir, "image")
                if item:
                    images.append(item)
        
        return images[:50]  # Limit
    
    async def _extract_videos(self, soup, base_url: str, output_dir: Path) -> List[MediaItem]:
        """Extract video elements."""
        videos = []
        videos_dir = output_dir / "videos"
        videos_dir.mkdir(exist_ok=True)
        
        for video in soup.find_all("video"):
            sources = video.find_all("source")
            for source in sources:
                src = source.get("src")
                if src:
                    full_url = urljoin(base_url, src)
                    item = await self._download_file(full_url, videos_dir, "video")
                    if item:
                        videos.append(item)
        
        return videos
    
    async def _extract_audio(self, soup, base_url: str, output_dir: Path) -> List[MediaItem]:
        """Extract audio elements."""
        audios = []
        audio_dir = output_dir / "audio"
        audio_dir.mkdir(exist_ok=True)
        
        for audio in soup.find_all("audio"):
            sources = audio.find_all("source")
            for source in sources:
                src = source.get("src")
                if src:
                    full_url = urljoin(base_url, src)
                    item = await self._download_file(full_url, audio_dir, "audio")
                    if item:
                        audios.append(item)
        
        return audios
    
    async def _extract_documents(self, soup, base_url: str, output_dir: Path) -> List[MediaItem]:
        """Extract document links (PDF, DOC, etc.)."""
        documents = []
        docs_dir = output_dir / "documents"
        docs_dir.mkdir(exist_ok=True)
        
        doc_extensions = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]
        
        for a in soup.find_all("a", href=True):
            href = a["href"]
            for ext in doc_extensions:
                if ext in href.lower():
                    full_url = urljoin(base_url, href)
                    item = await self._download_file(full_url, docs_dir, "document")
                    if item:
                        documents.append(item)
                    break
        
        return documents[:20]  # Limit
    
    def _find_embedded_players(self, soup, html: str) -> List[Dict]:
        """Find embedded video/audio players."""
        players = []
        
        # iframes
        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            for pattern in self.VIDEO_PATTERNS:
                if re.search(pattern, src):
                    players.append({
                        "type": "iframe",
                        "url": src,
                        "platform": pattern.split("\\.")[0].replace("\\", ""),
                    })
                    break
        
        # Direct links in HTML
        for pattern in self.VIDEO_PATTERNS:
            for match in re.finditer(f"https?://[^\"' ]*{pattern}[^\"' ]*", html):
                url = match.group(0)
                if url not in [p["url"] for p in players]:
                    players.append({
                        "type": "link",
                        "url": url,
                        "platform": pattern.split("\\.")[0].replace("\\", ""),
                    })
        
        return players
    
    async def _download_file(
        self,
        url: str,
        output_dir: Path,
        media_type: str
    ) -> Optional[MediaItem]:
        """Download a file."""
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30, follow_redirects=True)
                
                if response.status_code != 200:
                    return None
                
                content = response.content
                
                # Generate filename
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                ext = Path(urlparse(url).path).suffix[:10] or ".bin"
                filename = f"{media_type}_{url_hash}{ext}"
                
                filepath = output_dir / filename
                filepath.write_bytes(content)
                
                return MediaItem(
                    url=url,
                    type=media_type,
                    title=filename,
                    size=len(content),
                    local_path=str(filepath),
                )
                
        except Exception as e:
            logger.debug(f"Failed to download {url}: {e}")
            return None
    
    async def download_with_ytdlp(self, url: str, output_dir: Path = None) -> Optional[Path]:
        """
        Download video/audio using yt-dlp.
        
        Args:
            url: Video URL
            output_dir: Output directory
        
        Returns:
            Path to downloaded file
        """
        output_dir = output_dir or self.output_dir / "ytdlp"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-o", str(output_dir / "%(title)s.%(ext)s"),
                url,
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            await process.communicate()
            
            if process.returncode == 0:
                # Find downloaded file
                files = list(output_dir.glob("*"))
                if files:
                    return max(files, key=lambda p: p.stat().st_mtime)
            
            return None
            
        except Exception as e:
            logger.error(f"yt-dlp failed: {e}")
            return None
