from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path
import logging

_log = logging.getLogger(__name__)

# Chinese/CJK and ASCII punctuation characters that should not consume pinyin
PUNCTUATION = set('，。！？；：、…（）「」《》【】·～—""''()[]{}.,!?;:')

SectionType = Literal['verse', 'chorus', 'refrain', 'bridge']


@dataclass
class Token:
    """A single character with its optional pinyin."""
    char: str
    pinyin: Optional[str] = None
    is_punctuation: bool = False


@dataclass
class Word:
    """A group of tokens forming a single word (based on pinyin word boundaries)."""
    tokens: list[Token]


@dataclass
class Line:
    """A line of text composed of words."""
    words: list[Word]


@dataclass
class Section:
    """A section of lyrics (verse, chorus, bridge, refrain) with optional verse number."""
    lines: list[Line]
    type: SectionType = 'verse'
    number: Optional[str] = None  # only set when type == 'verse'


@dataclass
class Song:
    """A complete song with title and sections."""
    title_zh: str = ""
    title_py: str = ""
    sections: list[Section] = field(default_factory=list)
    language: str = 'chinese'


# Font directory bundled with the project
_FONT_DIR = Path(__file__).parent.parent / "fonts"

# Primary defaults: bundled Roboto Condensed (pinyin) + bundled Noto Sans HK (characters).
# Both ship in fonts/ so PIL works offline. Override via --pinyin-font / --char-font.
_DEFAULT_PINYIN_FONT = str(_FONT_DIR / "RobotoCondensed-Regular.ttf")
_DEFAULT_PINYIN_FONT_INDEX = 0
_DEFAULT_CHAR_FONT = str(_FONT_DIR / "NotoSansHK-Regular.otf")
_DEFAULT_CHAR_FONT_INDEX = 0


def _resolve_font(path: str, index: int, label: str) -> tuple[str, int]:
    """Return (path, index), falling back to bundled fonts if the primary path is missing."""
    if Path(path).exists():
        return path, index

    # Fallbacks: prefer same-family alternatives, then any bundled font of the right type.
    fallbacks = {
        _DEFAULT_PINYIN_FONT: [
            str(Path.home() / "Library/Fonts/Inter_28pt-Regular.ttf"),
            str(Path.home() / "Library/Fonts/Inter-Regular.ttf"),
            str(_FONT_DIR / "EncodeSansSemiCondensed-Regular.ttf"),
        ],
        _DEFAULT_CHAR_FONT: [
            str(_FONT_DIR / "NotoSansSC-Regular.otf"),
        ],
    }
    for fallback in fallbacks.get(path, []):
        if Path(fallback).exists():
            return fallback, 0

    _log.warning(
        "Warning: %s font not found at '%s'. "
        "Pass --pinyin-font / --char-font to specify a font.",
        label, path,
    )
    return path, index


@dataclass
class SlideConfig:
    """Configuration for slide rendering."""

    # Font paths and indices (index is used for .ttc collections)
    pinyin_font_path: str = _DEFAULT_PINYIN_FONT
    pinyin_font_index: int = _DEFAULT_PINYIN_FONT_INDEX
    char_font_path: str = _DEFAULT_CHAR_FONT
    char_font_index: int = _DEFAULT_CHAR_FONT_INDEX

    def __post_init__(self):
        self.pinyin_font_path, self.pinyin_font_index = _resolve_font(
            self.pinyin_font_path, self.pinyin_font_index, "pinyin"
        )
        self.char_font_path, self.char_font_index = _resolve_font(
            self.char_font_path, self.char_font_index, "character"
        )

    # Font sizes (pixels at render resolution — tune these to taste)
    pinyin_font_size: int = 68   # ~68% of char size for good legibility
    char_font_size: int = 96

    # Spacing (pixels at render resolution)
    pinyin_char_gap: int = 4        # tight gap between pinyin and its character
    intra_word_padding: int = 8     # extra padding between syllables within a word
    inter_word_gap: int = 18        # minimum visual gap (px) between the pinyin of adjacent words;
                                    # natural char-width slack is counted first, so no extra gap is
                                    # added when hanzi are already wider than their pinyin
    line_spacing: int = 52          # space between lines (bottom of chars → top of next pinyin)
    top_padding: int = 20           # padding above first pinyin row (prevents tone mark clipping)

    # Colors
    text_color: str = "#000000"
    # Muted grey for verse numbers, chorus labels, slide-header (book/page),
    # and title pinyin — matches the HTML design system.
    muted_color: str = "#707070"

    # PPTX text-box font names (PowerPoint substitutes if not installed locally).
    # PIL pinyin/character rendering uses the bundled font files above; these
    # control the native pptx text runs (titles, English lyrics, labels).
    english_font_name: str = "Roboto"
    pinyin_pptx_font_name: str = "Roboto Condensed"
    chinese_pptx_font_name: str = "Noto Sans HK"

    # Layout: columns × rows_per_column sections per slide
    # rows_per_column=None means auto-determine from section heights
    max_lines_per_verse: int = 8
    columns: int = 2
    rows_per_column: Optional[int] = None

    # English text rendering
    english_font_size_pt: int = 28       # starting target font size for English text
    english_line_height: float = 1.35    # line height = font_pt * this factor

    # When true, repeated choruses are collapsed: the chorus body appears only
    # on its first occurrence (with a '* Chorus:' label) and later references
    # are indicated by a trailing '*' on the preceding verse. When false
    # (default), every chorus is rendered in full with no label or asterisk.
    dedup_chorus: bool = False

    # Book/page reference shown in the top-right corner of each slide.
    # e.g. book="CSB", page="228–29"  or  book="兒童歌本", page="第16-17頁"
    book: str = ""
    page: str = ""

    # Per-song minimum character height floor (pt). When set, overrides the
    # global _MIN_CHAR_PT=28 for Chinese packing. Use a smaller value (e.g. 24)
    # to allow denser packing on songs with many short sections.
    # None = use the global default.
    min_char_pt: Optional[int] = None
