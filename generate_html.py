#!/usr/bin/env python3
"""
generate_html.py — Build an HTML/CSS deck from a lyrics .txt file.

Parallel to generate.py, but outputs live HTML text (with native <ruby> markup
for Chinese+pinyin) plus a companion CSS file. Intended as input to Claude
Design, where fonts can be swapped freely without the NFD/diacritic workaround
the PIL image renderer needs.

Usage:
    python3 generate_html.py worship_lyrics.txt
    python3 generate_html.py worship_lyrics.txt -o worship.html
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

from pinyin_slides.cli import (
    load_config_file,
    log_song_summary,
    read_lyrics_or_exit,
)
from pinyin_slides.html_renderer import (
    DEFAULT_CHINESE_LINES_PER_COL,
    DEFAULT_ENGLISH_LINES_PER_COL,
    render_document,
)
from pinyin_slides.parser import parse_lyrics

log = logging.getLogger(__name__)

_DEFAULT_CSS = Path(__file__).parent / 'pinyin_slides' / 'html_assets' / 'slides.css'
_DEFAULT_DECK_STAGE = Path(__file__).parent / 'pinyin_slides' / 'html_assets' / 'deck-stage.js'


def main():
    parser = argparse.ArgumentParser(
        description='Generate an HTML/CSS lyrics deck (for Claude Design).',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('lyrics', help='Lyrics file (same format as generate.py)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output .html path (default: <input-stem>.html)')
    parser.add_argument('--css', default=None,
                        help='Where to write the companion CSS file '
                             '(default: slides.css alongside the .html output)')
    parser.add_argument('--no-css', action='store_true',
                        help="Don't copy the default CSS; the HTML will still "
                             'link to slides.css.')
    parser.add_argument('--chinese-lines-per-col', type=int,
                        default=DEFAULT_CHINESE_LINES_PER_COL,
                        help='Max lyric lines per column on a Chinese slide '
                             'before splitting to a new slide')
    parser.add_argument('--english-lines-per-col', type=int,
                        default=DEFAULT_ENGLISH_LINES_PER_COL,
                        help='Max lyric lines per column on an English slide '
                             'before splitting to a new slide')
    parser.add_argument('--config', default=None, metavar='FILE',
                        help='TOML config file (auto-discovered from config.toml or '
                             '~/.pinyin-slides/config.toml if omitted). Honored keys: '
                             'chinese_lines_per_col, english_lines_per_col.')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(
        format='%(message)s',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    toml = load_config_file(args.config)

    # CLI > TOML > default.
    def _resolve_int(cli_val, cli_default, toml_key):
        if cli_val != cli_default:
            return cli_val
        raw = toml.get(toml_key)
        return int(raw) if raw is not None else cli_val

    chinese_lines_per_col = _resolve_int(
        args.chinese_lines_per_col, DEFAULT_CHINESE_LINES_PER_COL,
        'chinese_lines_per_col')
    english_lines_per_col = _resolve_int(
        args.english_lines_per_col, DEFAULT_ENGLISH_LINES_PER_COL,
        'english_lines_per_col')

    lyrics_path = Path(args.lyrics)
    lyrics_text = read_lyrics_or_exit(lyrics_path, log)

    output_path = (
        Path(args.output) if args.output
        else lyrics_path.with_suffix('.html')
    )
    css_path = Path(args.css) if args.css else output_path.with_name('slides.css')

    try:
        songs = parse_lyrics(lyrics_text)
    except ValueError as e:
        log.error('%s', e)
        sys.exit(1)
    if not songs:
        log.error('No songs found in lyrics file.')
        sys.exit(1)

    title = lyrics_path.stem
    # Link to CSS relative to the HTML output when they share a directory.
    try:
        css_href = css_path.relative_to(output_path.parent).as_posix()
    except ValueError:
        css_href = str(css_path)

    html = render_document(
        songs, title=title, css_href=css_href,
        chinese_lines_per_col=chinese_lines_per_col,
        english_lines_per_col=english_lines_per_col,
    )
    output_path.write_text(html, encoding='utf-8')
    log.info('Saved: %s  (%d KB)', output_path, len(html.encode('utf-8')) // 1024)

    if not args.no_css:
        if _DEFAULT_CSS.exists():
            shutil.copyfile(_DEFAULT_CSS, css_path)
            log.info('Wrote CSS: %s', css_path)
        else:
            log.warning('Default CSS not found at %s; skipping.', _DEFAULT_CSS)

        deck_stage_dest = output_path.with_name('deck-stage.js')
        if _DEFAULT_DECK_STAGE.exists():
            shutil.copyfile(_DEFAULT_DECK_STAGE, deck_stage_dest)
            log.info('Wrote JS:  %s', deck_stage_dest)
        else:
            log.warning('deck-stage.js not found at %s; skipping.', _DEFAULT_DECK_STAGE)

    log_song_summary(songs, log)


if __name__ == '__main__':
    main()
