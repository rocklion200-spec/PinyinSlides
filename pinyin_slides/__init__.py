"""Pinyin slides — generate PPTX and HTML lyric decks with pinyin over Chinese.

See SPEC.md for the lyrics file format and data model.
"""

from .config import Line, Section, SlideConfig, Song, Token, Word
from .html_renderer import render_document
from .parser import parse_lyrics, parse_song
from .slidebuilder import build_deck

__all__ = [
    "Line",
    "Section",
    "SlideConfig",
    "Song",
    "Token",
    "Word",
    "build_deck",
    "parse_lyrics",
    "parse_song",
    "render_document",
]
