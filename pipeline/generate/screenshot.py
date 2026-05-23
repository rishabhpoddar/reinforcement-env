"""Screenshot capture using Playwright.

Captures reference screenshots of generated websites at multiple viewports.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from pipeline.config import VIEWPORTS


async def capture_screenshots(
    site_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, list[str]]:
    """Capture screenshots of all HTML pages at all viewports.

    Args:
        site_dir: Directory containing the HTML files.
        output_dir: Directory to save screenshots to.

    Returns:
        Dict mapping page names to lists of screenshot paths.
    """
    site_dir = Path(site_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all HTML files
    html_files = sorted(site_dir.glob("*.html"))
    if not html_files:
        raise FileNotFoundError(f"No HTML files found in {site_dir}")

    screenshots: dict[str, list[str]] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for html_file in html_files:
            page_name = html_file.stem
            screenshots[page_name] = []

            for viewport_name, viewport_size in VIEWPORTS.items():
                context = await browser.new_context(
                    viewport=viewport_size,
                    device_scale_factor=1,
                )
                page = await context.new_page()

                file_url = f"file://{html_file.resolve()}"
                await page.goto(file_url, wait_until="networkidle")

                # Wait a bit for any CSS transitions/rendering
                await page.wait_for_timeout(500)

                # Full-page screenshot
                screenshot_name = f"{page_name}-{viewport_name}.png"
                screenshot_path = output_dir / screenshot_name
                await page.screenshot(
                    path=str(screenshot_path),
                    full_page=True,
                )
                screenshots[page_name].append(str(screenshot_path))

                await context.close()

        await browser.close()

    return screenshots


def capture_screenshots_sync(
    site_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, list[str]]:
    """Synchronous wrapper for capture_screenshots."""
    return asyncio.run(capture_screenshots(site_dir, output_dir))
