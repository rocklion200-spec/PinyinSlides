#!/usr/bin/env python3
"""
generate.py — Build a PowerPoint deck from a lyrics .txt file.

Takes a lyrics file with one or more [song] blocks and produces a 16:9 .pptx.
Chinese songs render pinyin above each character as an image; English songs
use native text boxes.

Usage:
    python3 generate.py worship_lyrics.txt
    python3 generate.py worship_lyrics.txt -o worship.pptx
    python3 generate.py worship_lyrics.txt --columns 1 --max-lines 6

Lyrics file format
──────────────────
Each song is a [song] block with optional per-song config keys (columns,
language, etc.) followed by [chinese]/[pinyin] sections or an [english]
section. A single-song lyrics file is just a file with one [song] block.

Example:
    [song]
    columns: 2

    [chinese]
    我時時需要主
    1. 我時時需要主，慈悲之神；

    [pinyin]
    Wǒ shíshí xūyào Zhǔ
    1. Wǒ shí­shí xū­yào Zhǔ, cí­bēi zhī Shén;

See test_data/keximani_deck.txt for a full example and SPEC.md for the
complete format reference.
"""

import argparse
import logging
import re
import sys
from pathlib import Path

from pinyin_slides.cli import (
    build_pptx_from_lyrics,
    load_config_file,
    log_song_summary,
    make_slide_config,
    read_lyrics_or_exit,
)

log = logging.getLogger(__name__)

# Matches a trailing "lyrics", "lyric", "deck" suffix, any capitalization,
# optionally preceded by a single '_' or '-' separator.
_LYRICS_DECK_SUFFIX_RE = re.compile(r'[-_]?(?:lyrics?|deck)$', re.IGNORECASE)


def _strip_lyrics_deck_suffix(stem: str) -> str:
    stripped = _LYRICS_DECK_SUFFIX_RE.sub('', stem)
    return stripped or stem


def _default_output_path(lyrics_path: Path) -> Path:
    return lyrics_path.with_name(f"{_strip_lyrics_deck_suffix(lyrics_path.stem)}.pptx")


def main():
    parser = argparse.ArgumentParser(
        description="Generate PowerPoint slides with pinyin above Chinese characters.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument('lyrics',
                        help='Lyrics file ([song]/[chinese]/[pinyin]/[english] blocks; '
                             'use a single [song] block for a single song)')

    parser.add_argument('-o', '--output', default=None,
                        help='Output .pptx file path '
                             '(default: <input-stem without lyrics/deck suffix>.pptx)')

    # Font options
    parser.add_argument('--pinyin-font', default=None,
                        help='Path to .otf/.ttf/.ttc font for pinyin (default: Inter 28pt Regular)')
    parser.add_argument('--pinyin-font-index', type=int, default=None,
                        help='Font index within a .ttc collection for pinyin (default: 0)')
    parser.add_argument('--char-font', default=None,
                        help='Path to .otf/.ttf/.ttc font for characters (default: bundled Noto Sans SC Regular)')
    parser.add_argument('--char-font-index', type=int, default=None,
                        help='Font index within a .ttc collection for characters (default: 0)')

    parser.add_argument('--pinyin-size', type=int, default=68,
                        help='Pinyin font size in render pixels')
    parser.add_argument('--char-size', type=int, default=96,
                        help='Character font size in render pixels')

    # Colors
    parser.add_argument('--text-color', default='#000000',
                        help='Text color hex (slide background is set in Keynote/PowerPoint)')

    # Layout
    parser.add_argument('--max-lines', type=int, default=8,
                        help='Max lines per verse before splitting')
    parser.add_argument('--columns', type=int, default=2,
                        help='Number of columns per slide')
    parser.add_argument('--rows', type=int, default=None,
                        help='Verse rows per column (default: auto)')
    parser.add_argument('--min-char-pt', type=int, default=None,
                        help='Minimum Chinese character height in pt (default: 28). '
                             'Lower this to allow denser packing on songs with many sections.')
    parser.add_argument('--english-size', type=int, default=28,
                        help='Starting target English font size in pt')

    # Chorus deduplication
    parser.add_argument('--dedup-chorus', action=argparse.BooleanOptionalAction,
                        default=None,
                        help='Collapse repeated choruses (first occurrence labeled '
                             '"* Chorus:", later references indicated by trailing "*"). '
                             'Default: off. Use --no-dedup-chorus to force off when '
                             'TOML would enable it.')

    parser.add_argument('--config', default=None, metavar='FILE',
                        help='TOML config file for default SlideConfig values '
                             '(auto-discovered from config.toml or '
                             '~/.pinyin-slides/config.toml if omitted)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose (debug) logging')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(message)s',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    toml = load_config_file(args.config)
    config = make_slide_config(args, toml)

    lyrics_path = Path(args.lyrics)
    lyrics_text = read_lyrics_or_exit(lyrics_path, log)

    output_path = Path(args.output) if args.output else _default_output_path(lyrics_path)

    log.info("Parsing lyrics...")
    try:
        pptx_bytes, song_configs = build_pptx_from_lyrics(lyrics_text, config)
    except ValueError as e:
        log.error("%s", e)
        sys.exit(1)

    log_song_summary(song_configs, log)

    output_path.write_bytes(pptx_bytes)
    log.info("Saved: %s  (%d KB)", output_path, len(pptx_bytes) // 1024)


if __name__ == '__main__':
    main()
