#!/usr/bin/env python3
"""
Forensic Capture Example
========================

Shows how to perform complete forensic capture of a web page.
"""

import asyncio
from pathlib import Path

from death_star import ForensicCapture


async def main():
    # Create forensic capture
    capture = ForensicCapture(output_dir=Path("./forensic_data"))
    
    # Capture page with all options
    result = await capture.capture_page(
        "https://example.com",
        capture_assets=True,      # Download all images, CSS, JS
        capture_storage=True,     # Capture cookies, localStorage
        capture_screenshot=True,  # Take full-page screenshot
        capture_pdf=True,         # Generate PDF of page
        capture_certificate=True, # Capture SSL certificate
        generate_warc=True,       # Generate WARC archive
        generate_har=True,        # Generate HAR file
    )
    
    print("\n" + "=" * 50)
    print("FORENSIC CAPTURE COMPLETE")
    print("=" * 50)
    print(f"URL: {result.url}")
    print(f"Timestamp: {result.timestamp}")
    print()
    print("Network:")
    print(f"  Requests captured: {len(result.requests)}")
    print(f"  Responses captured: {len(result.responses)}")
    print()
    print("Content:")
    print(f"  Assets downloaded: {len(result.assets)}")
    print(f"  HTML size: {len(result.html)} bytes")
    print()
    print("Storage:")
    print(f"  Cookies: {len(result.cookies)}")
    print(f"  localStorage keys: {len(result.local_storage)}")
    print(f"  sessionStorage keys: {len(result.session_storage)}")
    print()
    print("Links:")
    print(f"  Internal: {len(result.internal_links)}")
    print(f"  External: {len(result.external_links)}")
    print()
    print("Files:")
    print(f"  WARC: {result.warc_path}")
    print(f"  HAR: {result.har_path}")
    print(f"  Screenshot: {result.screenshot_path}")
    print(f"  PDF: {result.pdf_path}")


if __name__ == "__main__":
    asyncio.run(main())
