#!/usr/bin/env python3
"""
find_music_links.py — Resolve singing-time songs to Music Library URLs.

Fetches the index of each Music Library collection, matches each song from
the annual list by slug, and writes a links.txt file ready for scrape_lyrics.py.

Usage:
    python3 find_music_links.py [-o links.txt] [-v]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:
    sys.exit(f"Missing dependency: {exc}\nInstall: pip install requests beautifulsoup4")

BASE = "https://www.churchofjesuschrist.org"
MUSIC_SONGS = f"{BASE}/media/music/songs"

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}

# Collection IDs in preference order (earlier = preferred)
COLLECTIONS = [
    "childrens-songbook",
    "hymns-for-home-and-church",
    "hymns",
]

# ─────────────────────────────────────────────────────────────────────────────
# Annual song list for 2026 Primary singing time.
# Each entry:
#   title         – display name
#   eng_study     – Gospel Library English URL (or None)
#   zho_study     – Gospel Library Chinese URL (or None)
#   slug_override – force a specific Music Library slug (or None = auto-detect)
#   notes         – human-readable caveats (printed in output comments)
# ─────────────────────────────────────────────────────────────────────────────
SONGS: list[dict] = [
    # ── January ──────────────────────────────────────────────────────────────
    dict(title="My Heavenly Father Loves Me",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/my-heavenly-father-loves-me?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/my-heavenly-father-loves-me?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="228–29",
         zho_book="兒童歌本", zho_page="第16–17頁"),
    dict(title="I Will Follow God's Plan",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-will-follow-gods-plan?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-will-follow-gods-plan?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="164–65",
         zho_book="兒童歌本", zho_page="第86–87頁"),
    # ── February ─────────────────────────────────────────────────────────────
    dict(title="Follow the Prophet",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/follow-the-prophet?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/follow-the-prophet?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="110–11",
         zho_book="兒童歌本", zho_page="第58–59頁"),
    dict(title="A Child's Prayer",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/a-childs-prayer?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/a-childs-prayer?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="12–13",
         zho_book="兒童歌本", zho_page="第6–7頁"),
    # ── March ────────────────────────────────────────────────────────────────
    dict(title="Kindness Begins with Me",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/kindness-begins-with-me?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/kindness-begins-with-me?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="145",
         zho_book="兒童歌本", zho_page="第83頁"),
    dict(title="I Need Thee Every Hour",
         eng_study="https://www.churchofjesuschrist.org/study/manual/hymns/i-need-thee-every-hour?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/hymns/i-need-thee-every-hour?lang=zho",
         slug_override=None, notes=None,
         eng_book="Hymns", eng_page="No. 98",
         zho_book="聖詩選輯", zho_page="第49首"),
    # ── April ────────────────────────────────────────────────────────────────
    dict(title="Gethsemane",
         eng_study="https://www.churchofjesuschrist.org/study/liahona/2018/03/children/gethsemane?lang=eng",
         zho_study=None,  # Music Library page loads but has no Chinese songData
         slug_override="gethsemane",
         notes="English from Hymns—For Home and Church. Chinese not available in Music Library; use Gospel Library link or manual pinyin.",
         eng_book="Hymns for Home", eng_page="1009",
         zho_book="", zho_page=""),
    dict(title="Keep the Commandments",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/keep-the-commandments?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/keep-the-commandments?lang=zho",
         slug_override="keep-the-commandments-wolford",
         notes="Children's Songbook version uses slug 'keep-the-commandments-wolford' (2 verses).",
         eng_book="CSB", eng_page="146",
         zho_book="兒童歌本", zho_page="第68頁"),
    # ── May ──────────────────────────────────────────────────────────────────
    dict(title="Holy Places",
         eng_study="https://www.churchofjesuschrist.org/study/music/hymns-for-home-and-church/holy-places?lang=eng",
         zho_study=None,
         slug_override="holy-places-release-3",
         notes="English available in Music Library. Chinese not available.",
         eng_book="Hymns for Home", eng_page="1026",
         zho_book="", zho_page=""),
    dict(title="As I Search the Holy Scriptures",
         eng_study="https://www.churchofjesuschrist.org/study/manual/hymns/as-i-search-the-holy-scriptures?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/hymns/as-i-search-the-holy-scriptures?lang=zho",
         slug_override=None, notes=None,
         eng_book="Hymns", eng_page="No. 277",
         zho_book="聖詩選輯", zho_page="第171首"),
    # ── June ─────────────────────────────────────────────────────────────────
    dict(title="I Will Be Valiant",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-will-be-valiant?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-will-be-valiant?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="162",
         zho_book="兒童歌本", zho_page="第85頁"),
    dict(title="Love One Another",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/love-one-another?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/love-one-another?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="136",
         zho_book="兒童歌本", zho_page="第74頁"),
    # ── July ─────────────────────────────────────────────────────────────────
    dict(title="Search, Ponder, and Pray",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/search-ponder-and-pray?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/search-ponder-and-pray?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="109",
         zho_book="兒童歌本", zho_page="第66頁"),
    dict(title="I Pray in Faith",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-pray-in-faith?lang=eng",
         zho_study=None,
         slug_override=None,
         notes="Chinese version references 1991 聖徒之聲 (not Music Library). Chinese/Pinyin require manual sourcing.",
         eng_book="CSB", eng_page="14",
         zho_book="", zho_page=""),
    # ── August ───────────────────────────────────────────────────────────────
    dict(title="Dare to Do Right",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/dare-to-do-right?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/dare-to-do-right?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="158",
         zho_book="兒童歌本", zho_page="第80頁"),
    dict(title="I Feel My Savior's Love",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-feel-my-saviors-love?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-feel-my-saviors-love?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="74–75",
         zho_book="兒童歌本", zho_page="第42–43頁"),
    # ── September ────────────────────────────────────────────────────────────
    dict(title="Teach Me to Walk in the Light",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/teach-me-to-walk-in-the-light?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/teach-me-to-walk-in-the-light?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="177",
         zho_book="兒童歌本", zho_page="第70–71頁"),
    dict(title="Love Is Spoken Here",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/love-is-spoken-here?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/love-is-spoken-here?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="190–91",
         zho_book="兒童歌本", zho_page="第102–103頁"),
    # ── October ──────────────────────────────────────────────────────────────
    dict(title="Seek the Lord Early",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/seek-the-lord-early?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/seek-the-lord-early?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="108",
         zho_book="兒童歌本", zho_page="第67頁"),
    dict(title="I Lived in Heaven",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/i-lived-in-heaven?lang=eng",
         zho_study=None,
         slug_override=None,
         notes="Chinese version references 1999 Liahona. Check if Music Library has Chinese; otherwise manual.",
         eng_book="CSB", eng_page="4",
         zho_book="", zho_page=""),
    # ── November ─────────────────────────────────────────────────────────────
    dict(title="Families Can Be Together Forever",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/families-can-be-together-forever?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/families-can-be-together-forever?lang=zho",
         slug_override=None, notes=None,
         eng_book="CSB", eng_page="188",
         zho_book="兒童歌本", zho_page="第98頁"),
    dict(title="Choose the Right",
         eng_study="https://www.churchofjesuschrist.org/study/manual/hymns/choose-the-right?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/hymns/choose-the-right?lang=zho",
         slug_override=None, notes=None,
         eng_book="Hymns", eng_page="No. 239",
         zho_book="聖詩選輯", zho_page="第148首"),
    # ── December ─────────────────────────────────────────────────────────────
    dict(title="We'll Bring the World His Truth",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/well-bring-the-world-his-truth-army-of-helaman?lang=eng",
         zho_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/well-bring-the-world-his-truth-army-of-helaman?lang=zho",
         slug_override="well-bring-the-world-his-truth",
         notes="Gospel Library slug has '-army-of-helaman' suffix; Music Library uses shorter slug.",
         eng_book="CSB", eng_page="172–73",
         zho_book="兒童歌本", zho_page="第92–93頁"),
    dict(title="The Hearts of the Children",
         eng_study="https://www.churchofjesuschrist.org/study/manual/childrens-songbook/the-hearts-of-the-children?lang=eng",
         zho_study=None,
         slug_override=None,
         notes="Chinese not available (listed as English Children's Songbook only in Chinese schedule).",
         eng_book="CSB", eng_page="92–93",
         zho_book="", zho_page=""),
]


# ─────────────────────────────────────────────────────────────────────────────
# Fetching helpers
# ─────────────────────────────────────────────────────────────────────────────

_CHROME_PATHS = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
]


def _fetch_html(url: str) -> str:
    """Fetch page HTML, falling back to Playwright on TLS/connection errors."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.content.decode('utf-8', errors='replace')
    except requests.exceptions.ConnectionError:
        log.debug("requests failed (TLS?), trying Playwright for %s", url)
    except requests.exceptions.HTTPError as e:
        raise SystemExit(f"HTTP {e.response.status_code} fetching {url}")

    try:
        from playwright.sync_api import sync_playwright
        chrome = next((p for p in _CHROME_PATHS if Path(p).exists()), None)
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
    except Exception as e:
        raise SystemExit(
            f"Couldn't fetch {url}\n"
            f"  Playwright also failed: {e}\n"
            f"  Install: pip install playwright && playwright install chromium"
        )


def _extract_render_data(html: str, url: str):
    """Extract window.renderData from page HTML, or return None."""
    for marker in ('window.renderData = ', 'window.renderData='):
        idx = html.find(marker)
        if idx != -1:
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(html, idx + len(marker))
                return data
            except json.JSONDecodeError:
                log.debug("Failed to parse renderData at %s", url)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Collection index scraping
# ─────────────────────────────────────────────────────────────────────────────

def _slugs_from_render_data(data: dict) -> set[str]:
    """Walk renderData looking for Music Library song slugs."""
    slugs: set[str] = set()

    def _walk(node):
        if isinstance(node, dict):
            # Look for fields that look like song slugs or URLs
            for k, v in node.items():
                if k in ('slug', 'contentPath', 'path', 'uri', 'url', 'href'):
                    if isinstance(v, str):
                        m = re.search(r'/media/music/songs/([^/?#]+)', v)
                        if m:
                            slugs.add(m.group(1))
                        # Also catch bare slug-like values in slug fields
                        elif k == 'slug' and re.match(r'^[a-z0-9-]+$', v):
                            slugs.add(v)
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return slugs


def _slugs_from_html_links(html: str) -> set[str]:
    """Parse HTML for /media/music/songs/SLUG links."""
    soup = BeautifulSoup(html, 'html.parser')
    slugs: set[str] = set()
    for a in soup.find_all('a', href=True):
        m = re.search(r'/media/music/songs/([^/?#]+)', a['href'])
        if m:
            slugs.add(m.group(1))
    return slugs


def fetch_collection_slugs(collection_id: str) -> set[str]:
    """Return all song slugs found in a Music Library collection."""
    url = f"{BASE}/media/music/collections/{collection_id}?lang=eng"
    log.info("  Fetching collection: %s", collection_id)
    html = _fetch_html(url)

    slugs: set[str] = set()

    rd = _extract_render_data(html, url)
    if rd:
        slugs |= _slugs_from_render_data(rd)
        log.debug("    renderData slugs: %d", len(slugs))

    html_slugs = _slugs_from_html_links(html)
    slugs |= html_slugs
    log.debug("    HTML link slugs: %d (total after merge: %d)", len(html_slugs), len(slugs))

    if not slugs:
        log.warning("    No slugs found for collection %s — page may be JS-only", collection_id)
    else:
        log.info("    Found %d song slugs", len(slugs))

    return slugs


# ─────────────────────────────────────────────────────────────────────────────
# Individual song URL verification
# ─────────────────────────────────────────────────────────────────────────────

_page_cache: dict[str, str] = {}


def _fetch_html_cached(url: str) -> str:
    if url not in _page_cache:
        _page_cache[url] = _fetch_html(url)
    return _page_cache[url]


def _check_url_exists(url: str) -> bool:
    """Return True if the URL resolves AND contains valid songData."""
    try:
        html = _fetch_html_cached(url)
        rd = _extract_render_data(html, url)
        if rd is None:
            return False
        return bool(rd.get('data', {}).get('songData'))
    except Exception:
        return False


def _music_url(slug: str, lang: str) -> str:
    return f"{MUSIC_SONGS}/{slug}?lang={lang}"


def verify_language_available(slug: str, lang: str) -> bool:
    """Check whether a given language is actually available for a slug."""
    url = _music_url(slug, lang)
    exists = _check_url_exists(url)
    log.debug("    %s lang=%s → %s", slug, lang, "OK" if exists else "404/missing")
    return exists


# ─────────────────────────────────────────────────────────────────────────────
# Slug extraction from Gospel Library URLs
# ─────────────────────────────────────────────────────────────────────────────

def _study_slug(url: str):
    """Extract the final path component (slug) from a Gospel Library URL."""
    if not url:
        return None
    path = urlparse(url).path.rstrip('/')
    return path.split('/')[-1] if path else None


# ─────────────────────────────────────────────────────────────────────────────
# Main resolution logic
# ─────────────────────────────────────────────────────────────────────────────

def build_collection_index() -> dict[str, str]:
    """Return {slug: collection_id} using collection priority order."""
    index: dict[str, str] = {}
    for collection_id in reversed(COLLECTIONS):  # reversed so higher priority wins
        slugs = fetch_collection_slugs(collection_id)
        for slug in slugs:
            index[slug] = collection_id
    return index


def resolve_song(song: dict, index: dict[str, str]) -> dict:
    """Resolve a song entry to Music Library URLs.

    Returns a result dict with keys:
        title, slug, collection, eng_url, zho_url, py_url, notes, warnings
    """
    title = song['title']
    slug_override = song.get('slug_override')
    eng_study = song.get('eng_study')
    zho_study = song.get('zho_study')
    notes = song.get('notes') or ''
    warnings: list[str] = []

    # Determine candidate slug
    candidate_slug = slug_override or _study_slug(eng_study or zho_study or '')

    if not candidate_slug:
        return dict(title=title, slug=None, collection=None,
                    eng_url=None, zho_url=None, py_url=None,
                    notes=notes, warnings=["No URL or slug available — manual handling required"])

    # Look up in index
    collection = index.get(candidate_slug)
    if not collection:
        # Try a HEAD request to see if the slug works directly even if not in index
        test_url = _music_url(candidate_slug, 'eng')
        if _check_url_exists(test_url):
            collection = "(direct)"
            log.info("    '%s' not in index but URL resolves — using direct", candidate_slug)
        else:
            warnings.append(
                f"Slug '{candidate_slug}' not found in any collection index. "
                "URL may not resolve — verify manually."
            )

    slug = candidate_slug

    # Build URLs, checking language availability
    eng_url = None
    zho_url = None
    py_url = None

    if eng_study is not None:  # song has an English version
        url = _music_url(slug, 'eng')
        if verify_language_available(slug, 'eng'):
            eng_url = url
        else:
            warnings.append(f"English (lang=eng) not available at Music Library for slug '{slug}'")

    if zho_study is not None:  # song has a Chinese version we expect to find
        url = _music_url(slug, 'zho')
        if verify_language_available(slug, 'zho'):
            zho_url = url
            py_url_candidate = _music_url(slug, 'cmn-latn')
            if verify_language_available(slug, 'cmn-latn'):
                py_url = py_url_candidate
            else:
                warnings.append(f"Pinyin (lang=cmn-latn) not available for slug '{slug}'")
        else:
            warnings.append(f"Chinese (lang=zho) not available at Music Library for slug '{slug}'")

    return dict(title=title, slug=slug, collection=collection,
                eng_url=eng_url, zho_url=zho_url, py_url=py_url,
                notes=notes, warnings=warnings,
                eng_book=song.get('eng_book', ''), eng_page=song.get('eng_page', ''),
                zho_book=song.get('zho_book', ''), zho_page=song.get('zho_page', ''))


# ─────────────────────────────────────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────────────────────────────────────

MONTH_NAMES = [
    None,
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December",
]


def format_output(results: list[dict]) -> str:
    """Format resolved links as a commented links.txt file."""
    lines: list[str] = [
        "# 2026 Primary Singing Time — Music Library links",
        "# Generated by find_music_links.py",
        "# Use with: python3 scrape_lyrics.py <this_file> -o worship.pptx",
        "",
    ]

    month_idx = 0
    for i, result in enumerate(results):
        # Print month header every 2 songs
        if i % 2 == 0:
            month_idx += 1
            lines.append(f"# {'─' * 60}")
            lines.append(f"# {MONTH_NAMES[month_idx]}")
            lines.append(f"# {'─' * 60}")

        title = result['title']
        collection = result.get('collection') or '?'
        lines.append(f"# {title}  [{collection}]")

        if result.get('notes'):
            for note_line in result['notes'].splitlines():
                lines.append(f"# NOTE: {note_line}")

        for w in result.get('warnings', []):
            lines.append(f"# WARNING: {w}")

        has_any = bool(result.get('eng_url') or result.get('zho_url'))
        if has_any:
            # Emit all metadata before URLs so scrape_lyrics.py can parse them
            if result.get('eng_url') and result.get('eng_book'):
                lines.append(f"# eng-book: {result['eng_book']}")
            if result.get('eng_url') and result.get('eng_page'):
                lines.append(f"# eng-page: {result['eng_page']}")
            if result.get('zho_url') and result.get('zho_book'):
                lines.append(f"# zho-book: {result['zho_book']}")
            if result.get('zho_url') and result.get('zho_page'):
                lines.append(f"# zho-page: {result['zho_page']}")
        if result.get('eng_url'):
            lines.append(result['eng_url'])
        if result.get('zho_url'):
            lines.append(result['zho_url'])
        if result.get('py_url'):
            lines.append(result['py_url'])

        if not result.get('eng_url') and not result.get('zho_url'):
            lines.append("# (no Music Library URLs resolved — manual handling required)")

        lines.append("")

    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Resolve 2026 singing-time songs to Music Library links.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('-o', '--output', default='singing_time_links.txt',
                    help='Output links file (default: singing_time_links.txt)')
    ap.add_argument('--use-index', action='store_true',
                    help='Attempt to scrape collection index pages (slow; pages are JS-rendered so results are sparse)')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Enable verbose (debug) logging')
    args = ap.parse_args()

    logging.basicConfig(
        format='%(levelname)s: %(message)s' if args.verbose else '%(message)s',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    # Build collection index
    if args.use_index:
        log.info("Building Music Library collection index (%d collections)...", len(COLLECTIONS))
        index: dict[str, str] = build_collection_index()
        log.info("Index complete: %d total slugs across all collections.\n", len(index))
    else:
        index = {}

    # Resolve each song
    results: list[dict] = []
    for song in SONGS:
        log.info("Resolving: %s", song['title'])
        result = resolve_song(song, index)
        results.append(result)

        status_parts = []
        if result['eng_url']:
            status_parts.append('eng')
        if result['zho_url']:
            status_parts.append('zho')
        if result['py_url']:
            status_parts.append('pinyin')
        status = ', '.join(status_parts) if status_parts else 'NONE'
        log.info("  → %s  [%s]  (%s)", result.get('slug', '?'), result.get('collection', '?'), status)
        for w in result.get('warnings', []):
            log.warning("  ! %s", w)

    log.info("")

    # Write output
    output_text = format_output(results)
    out_path = Path(args.output)
    out_path.write_text(output_text, encoding='utf-8')
    log.info("Wrote %d songs → %s", len(results), out_path)

    # Summary of songs needing manual work
    manual = [r for r in results if not (r.get('eng_url') or r.get('zho_url'))]
    if manual:
        log.info("\nSongs requiring manual handling:")
        for r in manual:
            log.info("  • %s", r['title'])


if __name__ == '__main__':
    main()
