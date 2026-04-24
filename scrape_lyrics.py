#!/usr/bin/env python3
"""
scrape_lyrics.py — Scrape song lyrics from churchofjesuschrist.org.

Always writes a lyrics .txt.  Pass --slides to also build a .pptx slide deck.

Default output filenames (derived from the input stem, stripping any _links
suffix):
    singing_time_links.txt → singing_time_lyrics.txt   (lyrics file)
                          → singing_time.pptx          (slides, with --slides)

Usage:
    python3 scrape_lyrics.py singing_time_links.txt
    python3 scrape_lyrics.py singing_time_links.txt --slides
    python3 scrape_lyrics.py links.txt -l lyrics.txt -o worship.pptx

links.txt format
────────────────
One URL per line.  Blank lines and # comments are ignored.

URLs that share the same song path (same URL, different ?lang= parameter) are
automatically grouped into one song:
  • lang=zho  + lang=cmn-latn → one Chinese/Pinyin entry
  • lang=eng                  → one English entry

If a group has both Chinese and English URLs, two entries are emitted in
the order the languages first appear in the file.

Example links.txt:
    # Keep the Commandments
    https://www.churchofjesuschrist.org/media/music/songs/keep-the-commandments-wolford?lang=zho
    https://www.churchofjesuschrist.org/media/music/songs/keep-the-commandments-wolford?lang=cmn-latn
    https://www.churchofjesuschrist.org/media/music/songs/keep-the-commandments-wolford?lang=eng
"""

import argparse
import json
import logging
import re
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

log = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
except ImportError as exc:
    print(f"Missing dependency: {exc}")
    print("Install with:  pip3 install requests beautifulsoup4")
    sys.exit(1)

from pinyin_slides.http_utils import fetch_html as _fetch_html


# ── Verse-type handling ───────────────────────────────────────────────────────

# verseType values that carry a numeric label in the lyrics output
_NUMBERED_TYPES = {"Verse"}

# verseType values we silently discard (performance notes, footnotes, etc.)
_SKIP_TYPES = {"Instructions"}

# Mapping from verseType to a human-readable label for the lyrics file
_TYPE_LABELS = {
    "Chorus":  "Chorus",
    "Refrain": "Refrain",
    "Bridge":  "Bridge",
}


# ── URL helpers ───────────────────────────────────────────────────────────────

def _url_base_key(url: str) -> str:
    """Return URL with lang= stripped — used to group same-song URLs."""
    p = urlparse(url)
    qs = {k: v[0] for k, v in parse_qs(p.query).items() if k != 'lang'}
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(qs), ''))


def _url_lang(url: str) -> str:
    """Extract the lang= value from a URL."""
    return parse_qs(urlparse(url).query).get('lang', [''])[0]


# ── Page scraping ─────────────────────────────────────────────────────────────

def fetch_song_data(url: str) -> dict:
    """Fetch a Church music page and return its songData dict."""
    html = _fetch_html(url)

    # The page embeds data as `window.renderData={...}` (no spaces around =)
    for marker in ('window.renderData = ', 'window.renderData='):
        idx = html.find(marker)
        if idx != -1:
            break
    if idx == -1:
        raise ValueError(f"window.renderData not found on page: {url}")

    decoder = json.JSONDecoder()
    data, _ = decoder.raw_decode(html, idx + len(marker))

    song_data = data.get('data', {}).get('songData')
    if not song_data:
        raise ValueError(f"songData missing in renderData at: {url}")
    return song_data


def _verse_lines(verse_body_html: str) -> list[str]:
    """Extract lyric lines from a verseBody HTML string.

    Each <p> element is one line; <br> inside a <p> splits into sub-lines.
    HTML entities are automatically decoded by BeautifulSoup.
    """
    soup = BeautifulSoup(verse_body_html, 'html.parser')
    lines = []
    for p in soup.find_all('p'):
        parts: list[str] = []
        for child in p.children:
            if getattr(child, 'name', None) == 'br':
                text = ''.join(parts).strip()
                if text:
                    lines.append(text)
                parts = []
            else:
                parts.append(
                    child.get_text() if hasattr(child, 'get_text') else str(child)
                )
        text = ''.join(parts).strip()
        if text:
            lines.append(text)
    return lines


def song_data_to_block(song_data: dict) -> str:
    """Convert a songData dict to a lyrics text block (title + sections).

    • Verse sections get a "N." prefix on their first line.
    • Chorus / Refrain / Bridge get a tag line (e.g. "Chorus:") before their
      content so the parser can recognise the section type.
    • Instructions are dropped.
    """
    title = song_data.get('title', '').strip()
    verses = song_data.get('verses', [])

    output_blocks: list[str] = []
    if title:
        output_blocks.append(title)
        output_blocks.append('')          # blank line after title

    for verse in verses:
        vtype   = verse.get('verseType', '')
        vnum    = verse.get('verseNumber', 0)
        body    = verse.get('verseBody', '')

        if vtype in _SKIP_TYPES or not body.strip():
            continue

        lines = _verse_lines(body)
        if not lines:
            continue

        if vtype in _NUMBERED_TYPES and vnum:
            lines[0] = f"{vnum}. {lines[0]}"
        elif vtype in _TYPE_LABELS:
            lines.insert(0, f"{_TYPE_LABELS[vtype]}:")

        output_blocks.append('\n'.join(lines))
        output_blocks.append('')          # blank separator

    # Strip trailing blanks then rejoin
    while output_blocks and not output_blocks[-1]:
        output_blocks.pop()

    return '\n'.join(output_blocks)


# ── Grouping & lyrics assembly ────────────────────────────────────────────────

def group_urls(urls: list[str], url_meta=None) -> list[dict]:
    """Group URLs by base key (same song), preserving first-seen order.

    Returns a list of dicts:
        {'key': base_url, 'lang_order': [lang, ...], 'langs': {lang: url},
         'meta': {eng-book, eng-page, zho-book, zho-page}}
    """
    groups: OrderedDict[str, dict] = OrderedDict()
    for url in urls:
        key  = _url_base_key(url)
        lang = _url_lang(url)
        if key not in groups:
            meta = (url_meta or {}).get(key, {})
            groups[key] = {'key': key, 'lang_order': [], 'langs': {}, 'meta': meta}
        if lang not in groups[key]['langs']:
            groups[key]['lang_order'].append(lang)
            groups[key]['langs'][lang] = url
    return list(groups.values())


def group_to_fetch_plan(group: dict) -> list[dict]:
    """Return ordered fetch plan for a group.

    Chinese (zho) and Pinyin (cmn-latn) are paired into one entry;
    English (eng) becomes a separate entry.  Order follows first appearance.
    """
    langs      = group['langs']
    lang_order = group['lang_order']

    zh_entry  = None
    eng_entry = None

    meta = group.get('meta', {})
    if 'zho' in langs or 'cmn-latn' in langs:
        zh_entry = {
            'language': 'chinese',
            'zh_url':   langs.get('zho'),
            'py_url':   langs.get('cmn-latn'),
            'book':     meta.get('zho-book', ''),
            'page':     meta.get('zho-page', ''),
        }
    if 'eng' in langs:
        eng_entry = {
            'language': 'english',
            'eng_url':  langs['eng'],
            'book':     meta.get('eng-book', ''),
            'page':     meta.get('eng-page', ''),
        }

    # Order by whichever language appears first in the input file
    def first_seen(entry: dict) -> int:
        if entry is None:
            return 999
        if entry['language'] == 'english':
            return lang_order.index('eng') if 'eng' in lang_order else 999
        # Chinese entry: first of zho / cmn-latn
        idxs = [lang_order.index(l) for l in ('zho', 'cmn-latn') if l in lang_order]
        return min(idxs) if idxs else 999

    entries = [e for e in (zh_entry, eng_entry) if e is not None]
    entries.sort(key=first_seen)
    return entries


def fetch_entry(entry: dict) -> dict:
    """Fetch song data for an entry and attach text blocks. Returns entry."""
    lang = entry['language']
    if lang == 'english':
        data = fetch_song_data(entry['eng_url'])
        entry['eng_text'] = song_data_to_block(data)
        entry['title']    = data.get('title', '')
        log.info("    ✓ English:  %s", entry['title'])
    else:
        entry['zh_text'] = ''
        entry['py_text'] = ''
        if entry.get('zh_url'):
            data = fetch_song_data(entry['zh_url'])
            entry['zh_text'] = song_data_to_block(data)
            entry['title']   = data.get('title', '')
            log.info("    ✓ Chinese:  %s", entry['title'])
        if entry.get('py_url'):
            data = fetch_song_data(entry['py_url'])
            entry['py_text'] = song_data_to_block(data)
            if not entry.get('title'):
                entry['title'] = data.get('title', '')
            log.info("    ✓ Pinyin:   %s", data.get('title', ''))
    return entry


def entries_to_lyrics_text(entries: list[dict]) -> str:
    """Render all fetched entries as a lyrics text file."""
    sections: list[str] = []

    for entry in entries:
        lang = entry['language']
        lines = ['[song]']

        if lang == 'english':
            lines.append('language: english')
        else:
            lines.append('columns: 2')

        if entry.get('book'):
            lines.append(f"book: {entry['book']}")
        if entry.get('page'):
            lines.append(f"page: {entry['page']}")

        if lang == 'english':
            lines.append('')
            lines.append('[english]')
            lines.append(entry.get('eng_text', ''))
        else:
            lines.append('')
            if entry.get('zh_text'):
                lines.append('[chinese]')
                lines.append(entry['zh_text'])
            if entry.get('py_text'):
                lines.append('')
                lines.append('[pinyin]')
                lines.append(entry['py_text'])

        sections.append('\n'.join(lines))

    return '\n\n'.join(sections) + '\n'


# ── CLI ───────────────────────────────────────────────────────────────────────

_META_RE = re.compile(r'^#\s*(eng-book|eng-page|zho-book|zho-page)\s*:\s*(.+)$', re.IGNORECASE)


def parse_links_file(path: Path) -> tuple[list[str], dict[str, dict]]:
    """Read URLs from a file; skip blank lines and plain # comments.

    Also parses special metadata comments of the form:
        # eng-book: CSB
        # eng-page: 228–29
        # zho-book: 兒童歌本
        # zho-page: 第16–17頁

    Returns (urls, url_meta) where url_meta maps each URL's base key
    (URL with lang= stripped) to a dict of the metadata seen immediately
    before its first URL in the file.
    """
    urls: list[str] = []
    url_meta: dict[str, dict] = {}
    current_meta: dict[str, str] = {}
    current_key = None

    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            current_meta = {}
            current_key = None
            continue
        m = _META_RE.match(line)
        if m:
            current_meta[m.group(1).lower()] = m.group(2).strip()
            continue
        if line.startswith('#'):
            continue
        # It's a URL
        urls.append(line)
        key = _url_base_key(line)
        if key != current_key:
            if current_meta:
                url_meta.setdefault(key, {}).update(current_meta)
            current_key = key
            current_meta = {}

    return urls, url_meta


# Matches a trailing "link" or "links" suffix, any capitalization,
# optionally preceded by a single '_' or '-' separator. Examples stripped:
#   _links, _link, -Links, LINKS, Link, links
_LINKS_SUFFIX_RE = re.compile(r'[-_]?links?$', re.IGNORECASE)


def _strip_links_suffix(stem: str) -> str:
    """Remove a trailing link/links token (case-insensitive, optional _/- sep)."""
    stripped = _LINKS_SUFFIX_RE.sub('', stem)
    # Guard against stripping the whole stem (e.g. input file literally named 'links.txt')
    return stripped or stem


def _default_lyrics_path(links_path: Path) -> Path:
    """singing_time_links.txt → singing_time_lyrics.txt."""
    return links_path.with_name(f"{_strip_links_suffix(links_path.stem)}_lyrics.txt")


def _default_slides_path(links_path: Path) -> Path:
    """singing_time_links.txt → singing_time.pptx."""
    return links_path.with_name(f"{_strip_links_suffix(links_path.stem)}.pptx")


def main() -> None:
    ap = argparse.ArgumentParser(
        description='Scrape Church music lyrics into a .txt file and optionally build slides.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('links',
                    help='Text file with one Church music URL per line')
    ap.add_argument('-l', '--lyrics', metavar='FILE', default=None,
                    help='Output path for the lyrics .txt '
                         '(default: <input-stem without _links>_lyrics.txt)')
    ap.add_argument('-s', '--slides', action='store_true',
                    help='Also build a .pptx slide deck')
    ap.add_argument('-o', '--slides-output', metavar='FILE', default=None,
                    help='Output path for the .pptx slide deck (implies --slides). '
                         'Default: <input-stem without _links>.pptx')
    ap.add_argument('--columns', type=int, default=2,
                    help='Columns for Chinese slides (default: 2)')
    ap.add_argument('--config', default=None, metavar='FILE',
                    help='TOML config file for default SlideConfig values '
                         '(auto-discovered from config.toml or '
                         '~/.pinyin-slides/config.toml if omitted)')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='Enable verbose (debug) logging')
    args = ap.parse_args()

    logging.basicConfig(
        format='%(message)s',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    links_path = Path(args.links)
    if not links_path.exists():
        ap.error(f"Links file not found: {links_path}")

    lyrics_path = Path(args.lyrics) if args.lyrics else _default_lyrics_path(links_path)
    build_slides = args.slides or args.slides_output is not None
    slides_path = (Path(args.slides_output) if args.slides_output
                   else _default_slides_path(links_path)) if build_slides else None

    urls, url_meta = parse_links_file(links_path)
    if not urls:
        ap.error("No URLs found in links file.")

    log.info("Found %d URL(s).", len(urls))
    groups = group_urls(urls, url_meta)
    log.info("Grouped into %d song(s).\n", len(groups))

    # Fetch all entries
    all_entries: list[dict] = []
    for i, group in enumerate(groups, 1):
        log.info("Song %d/%d  (%s)", i, len(groups), group['key'].split('/')[-1])
        plan = group_to_fetch_plan(group)
        for entry in plan:
            fetch_entry(entry)
            all_entries.append(entry)
        log.info("")

    # Always write the lyrics file
    lyrics_text = entries_to_lyrics_text(all_entries)
    lyrics_path.write_text(lyrics_text, encoding='utf-8')
    log.info("Lyrics saved → %s", lyrics_path)

    if not build_slides:
        return

    # Build PPTX
    log.info("\nBuilding presentation ...")
    from pinyin_slides.cli import load_config_file, make_slide_config, build_pptx_from_lyrics

    toml      = load_config_file(args.config)
    config    = make_slide_config(args, toml)
    try:
        pptx_bytes, song_cfgs = build_pptx_from_lyrics(lyrics_text, config)
    except ValueError as e:
        log.error("%s", e)
        return

    log.info("  %d song(s) parsed:", len(song_cfgs))
    for i, (song, overrides) in enumerate(song_cfgs, 1):
        lang  = overrides.get('language', 'chinese')
        title = song.title_zh or '(untitled)'
        log.info("    %d. [%s] %s — %d section(s)", i, lang, title, len(song.sections))

    slides_path.write_bytes(pptx_bytes)
    log.info("\nSlides saved → %s  (%d KB)", slides_path, len(pptx_bytes) // 1024)


if __name__ == '__main__':
    main()
