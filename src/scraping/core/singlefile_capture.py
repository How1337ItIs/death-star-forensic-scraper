"""
SingleFile Capture — Full-fidelity single-HTML page capture.

Uses SingleFile CLI to create self-contained HTML files with all assets
(CSS, fonts, images, JS) inlined as data URIs. Shadow DOM and iframe
content is preserved.

Requires:
    npm install -g single-file-cli

Usage:
    capture = SingleFileCapture(output_dir=Path("data/singlefile"))
    result = await capture.capture_page("https://example.com")
    print(result)  # Path to the captured HTML file
"""

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("death_star_v2.singlefile")


class SingleFileCapture:
    """Capture full-fidelity single-file HTML snapshots.

    Creates self-contained HTML files where all resources are embedded
    as data URIs. The result is a single .html file that renders
    identically to the original page without any external dependencies.
    """

    def __init__(self, output_dir: Path = Path("data/singlefile")):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._available = None

    def is_available(self) -> bool:
        """Check if single-file CLI is installed."""
        if self._available is None:
            self._available = shutil.which("single-file") is not None
            if not self._available:
                logger.debug(
                    "single-file CLI not found. Install: npm install -g single-file-cli"
                )
        return self._available

    async def capture_page(
        self,
        url: str,
        browser_path: Optional[str] = None,
        timeout: int = 60,
        compress: bool = False,
    ) -> Optional[Path]:
        """Capture a page as a single self-contained HTML file.

        Args:
            url: The URL to capture
            browser_path: Optional path to Chrome/Chromium binary
            timeout: Timeout in seconds
            compress: Whether to compress the output

        Returns:
            Path to the captured HTML file, or None on failure
        """
        if not self.is_available():
            logger.warning("SingleFile not available, skipping capture")
            return None

        # Generate output filename from URL
        parsed = urlparse(url)
        safe_name = f"{parsed.netloc}_{parsed.path.strip('/').replace('/', '_')}"
        if not safe_name or safe_name == parsed.netloc + "_":
            safe_name = parsed.netloc
        safe_name = safe_name[:100]  # Limit filename length
        output_file = self.output_dir / f"{safe_name}.html"

        cmd = [
            "single-file",
            url,
            output_file.as_posix(),
        ]

        # Add options
        if browser_path:
            cmd.extend(["--browser-executable-path", browser_path])

        if compress:
            cmd.append("--compress-HTML")

        # Additional useful flags
        cmd.extend([
            "--browser-wait-until", "networkidle0",
            "--browser-load-max-time", str(timeout * 1000),
        ])

        try:
            logger.info(f"SingleFile capturing: {url}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout + 30,  # Extra buffer for startup
            )

            if process.returncode == 0 and output_file.exists():
                size_mb = output_file.stat().st_size / 1024 / 1024
                logger.info(
                    f"SingleFile captured: {output_file.name} ({size_mb:.1f} MB)"
                )
                return output_file
            else:
                error = stderr.decode().strip() if stderr else "Unknown error"
                logger.warning(f"SingleFile failed for {url}: {error}")
                return None

        except asyncio.TimeoutError:
            logger.warning(f"SingleFile timed out for {url}")
            return None
        except FileNotFoundError:
            logger.warning("SingleFile CLI not found in PATH")
            self._available = False
            return None
        except Exception as e:
            logger.warning(f"SingleFile error for {url}: {e}")
            return None

    async def capture_pages(
        self,
        urls: list,
        max_concurrent: int = 3,
        **kwargs,
    ) -> dict:
        """Capture multiple pages concurrently.

        Returns dict mapping URL -> output Path (or None on failure).
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {}

        async def _capture(url):
            async with semaphore:
                results[url] = await self.capture_page(url, **kwargs)

        await asyncio.gather(*[_capture(url) for url in urls])
        return results
