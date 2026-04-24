"""Shared HTTP fetching utilities for the Church Music Library scrapers.

Both find_music_links.py (collection-index scraping) and scrape_lyrics.py
(song-page scraping) hit www.churchofjesuschrist.org. Those requests
occasionally fail at TLS handshake from bare Python (Akamai / Cloudflare
fingerprinting), so we fall back to driving a real Chrome via Playwright.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}

# Candidate paths for a system Chrome/Chromium to use as Playwright's executable
CHROME_PATHS = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
]


def fetch_html_via_playwright(url: str) -> str:
    """Fetch page HTML using a real Chrome browser (bypasses TLS fingerprinting)."""
    from playwright.sync_api import sync_playwright

    chrome = next((p for p in CHROME_PATHS if Path(p).exists()), None)
    launch_opts: dict = {'headless': True}
    if chrome:
        launch_opts['executable_path'] = chrome
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_opts)
        try:
            page = browser.new_page()
            page.goto(url, timeout=30000)
            return page.content()
        finally:
            browser.close()


def fetch_html(url: str, *, timeout: int = 20) -> str:
    """Fetch *url* as UTF-8 HTML, falling back to Playwright on TLS errors.

    Exits the process (SystemExit) on HTTP errors or when Playwright is also
    unable to fetch the page.
    """
    import requests

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        # Force UTF-8 — requests sometimes guesses wrong for CJK pages
        return resp.content.decode('utf-8', errors='replace')
    except requests.exceptions.ConnectionError:
        log.debug("requests failed (TLS?), trying Playwright for %s", url)
    except requests.exceptions.Timeout:
        raise SystemExit(f"Error: request timed out for {url}")
    except requests.exceptions.HTTPError as e:
        raise SystemExit(f"Error: HTTP {e.response.status_code} fetching {url}")

    try:
        return fetch_html_via_playwright(url)
    except Exception as e:
        raise SystemExit(
            f"Error: couldn't fetch {url}\n"
            f"  requests failed and Playwright fallback also failed: {e}\n"
            f"  Install playwright: pip install playwright && playwright install chromium"
        )
