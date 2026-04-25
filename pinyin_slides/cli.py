"""Shared CLI helpers for generate.py, generate_html.py, and scrape_lyrics.py.

Terminology: "lyrics" refers to the .txt input format (with [song]/[chinese]/
[pinyin]/[english] blocks). "Deck" refers to the PowerPoint slide deck output.

Exports:
    load_config_file(path)       — load [slides] section from a TOML file
    make_slide_config(args, toml) — build a SlideConfig from argparse args + TOML
    build_pptx_from_lyrics(text, config) — parse lyrics and build .pptx bytes
    read_lyrics_or_exit(path)    — read a lyrics file or sys.exit(1) on missing
    log_song_summary(song_configs, log) — print a per-song summary (shared by
                                          generate.py and generate_html.py)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── TOML config loading ───────────────────────────────────────────────────────

try:
    import tomllib          # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

# Auto-discovery locations (checked in order)
_CONFIG_SEARCH = [
    Path("config.toml"),
    Path.home() / ".pinyin-slides" / "config.toml",
]


def load_config_file(path: Optional[str] = None) -> dict:
    """Load a TOML config file and return the [slides] section as a dict.

    If *path* is given it is used directly; otherwise the first file found
    among config.toml (cwd) and ~/.pinyin-slides/config.toml is used.
    Returns an empty dict when no file is found or TOML is unavailable.
    """
    if tomllib is None:
        return {}

    candidates = [Path(path)] if path else _CONFIG_SEARCH
    for candidate in candidates:
        if candidate.exists():
            with open(candidate, "rb") as f:
                data = tomllib.load(f)
            result = data.get("slides", {})
            log.debug("Loaded config from %s", candidate)
            return result
    return {}


# ── SlideConfig builder ───────────────────────────────────────────────────────

def make_slide_config(args, toml: dict | None = None):
    """Build a SlideConfig from argparse *args*, with TOML values as fallback.

    Priority order: CLI args > TOML file > SlideConfig defaults.
    Only fields explicitly passed on the CLI override TOML values.
    """
    from pinyin_slides.config import SlideConfig

    toml = toml or {}

    def _pick(cli_val, default, key, cast=None):
        """Return CLI value if it differs from *default*, else fall back to TOML."""
        if cli_val != default:
            return cli_val
        raw = toml.get(key)
        if raw is None:
            return cli_val
        return cast(raw) if cast else raw

    cfg = SlideConfig(
        text_color=_pick(getattr(args, 'text_color', '#000000'), '#000000', 'text_color'),
        pinyin_font_size=_pick(getattr(args, 'pinyin_size', 68), 68, 'pinyin_font_size', int),
        char_font_size=_pick(getattr(args, 'char_size', 96), 96, 'char_font_size', int),
        max_lines_per_verse=_pick(getattr(args, 'max_lines', 8), 8, 'max_lines_per_verse', int),
        columns=_pick(getattr(args, 'columns', 2), 2, 'columns', int),
        rows_per_column=_pick(getattr(args, 'rows', None), None, 'rows_per_column',
                              lambda v: int(v) if v is not None else None),
        min_char_pt=_pick(getattr(args, 'min_char_pt', None), None, 'min_char_pt',
                          lambda v: int(v) if v is not None else None),
        english_font_size_pt=_pick(getattr(args, 'english_size', 28), 28,
                                     'english_font_size_pt', int),
    )
    # dedup_chorus uses argparse.BooleanOptionalAction: None = unset (fall back
    # to TOML then SlideConfig default), True/False = explicit CLI.
    dedup_cli = getattr(args, 'dedup_chorus', None)
    if dedup_cli is not None:
        cfg.dedup_chorus = bool(dedup_cli)
    elif 'dedup_chorus' in toml:
        cfg.dedup_chorus = bool(toml['dedup_chorus'])
    # Font paths: CLI flag → TOML → SlideConfig default (bundled font)
    if getattr(args, 'pinyin_font', None):
        cfg.pinyin_font_path = args.pinyin_font
    elif 'pinyin_font_path' in toml:
        cfg.pinyin_font_path = toml['pinyin_font_path']

    if getattr(args, 'pinyin_font_index', None) is not None:
        cfg.pinyin_font_index = args.pinyin_font_index
    elif 'pinyin_font_index' in toml:
        cfg.pinyin_font_index = int(toml['pinyin_font_index'])

    if getattr(args, 'char_font', None):
        cfg.char_font_path = args.char_font
    elif 'char_font_path' in toml:
        cfg.char_font_path = toml['char_font_path']

    if getattr(args, 'char_font_index', None) is not None:
        cfg.char_font_index = args.char_font_index
    elif 'char_font_index' in toml:
        cfg.char_font_index = int(toml['char_font_index'])

    return cfg


# ── Slide deck building ───────────────────────────────────────────────────────

def build_pptx_from_lyrics(lyrics_text: str, config):
    """Parse *lyrics_text* and build a .pptx.

    Returns (pptx_bytes: bytes, song_configs: list).
    Raises ValueError if no songs are found.
    """
    from pinyin_slides.parser import parse_lyrics
    from pinyin_slides.slidebuilder import build_deck

    song_configs = parse_lyrics(lyrics_text)
    if not song_configs:
        raise ValueError("No songs found in lyrics file.")
    pptx_bytes = build_deck(song_configs, config)
    return pptx_bytes, song_configs


# ── Shared entry-point helpers ────────────────────────────────────────────────

def read_lyrics_or_exit(path: Path, logger: logging.Logger | None = None) -> str:
    """Read a lyrics .txt file as UTF-8, or sys.exit(1) with an error log."""
    logger = logger or log
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)
    return path.read_text(encoding='utf-8')


def log_song_summary(song_configs, logger: logging.Logger | None = None) -> None:
    """Log a one-line-per-song summary of parsed songs."""
    logger = logger or log
    logger.info("  Songs: %d", len(song_configs))
    for i, (song, overrides) in enumerate(song_configs):
        lang = overrides.get('language', song.language)
        title = song.title_zh or "(untitled)"
        section_summary = ', '.join(
            f"{s.type[0].upper()}{s.number or ''}/{len(s.lines)}L"
            for s in song.sections
        )
        logger.info("  Song %d [%s]: %s — %d section(s) (%s)",
                    i + 1, lang, title, len(song.sections), section_summary)
