"""Render parsed Song data as HTML using native <ruby> markup.

Mirrors renderer.py but emits semantic HTML instead of PIL images. Each pinyin
word becomes a single <ruby> element in jukugo form (one <rt> per character),
so CSS Ruby's spec-default max(base, annotation) column sizing reproduces the
unit_w = max(pinyin_w, char_w) rule from renderer.py:_layout_line for free.

Usage:
    html = render_document([(song, overrides), ...], title="My Deck")
"""

from __future__ import annotations

from typing import Iterable

from .config import Line, Section, Song, Token, Word


DEFAULT_CHINESE_LINES_PER_COL = 6
DEFAULT_ENGLISH_LINES_PER_COL = 10


def _escape(s: str) -> str:
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;'))


def section_line_count(section: Section) -> int:
    """Effective line count for a section (lyric lines + 1 for chorus/etc label)."""
    n = len(section.lines)
    if section.type in ('chorus', 'refrain', 'bridge'):
        n += 1
    return n


def pack_song(song: Song, columns: int, lines_per_col: int) -> list:
    """Greedy-pack a song's sections into slides → columns → sections.

    Fills columns left-to-right; starts a new slide when every column is full.
    A section longer than `lines_per_col` is placed alone in a column and
    allowed to overflow — uncommon, and the CSS safety net handles visuals.

    Returns: list[slide] where slide = list[column], column = list[Section].
    """
    columns = max(1, columns)
    lines_per_col = max(1, lines_per_col)

    slides: list = []
    current = [[] for _ in range(columns)]
    lines = [0] * columns
    col = 0

    def flush():
        nonlocal current, lines, col
        if any(current):
            slides.append(current)
        current = [[] for _ in range(columns)]
        lines = [0] * columns
        col = 0

    for section in song.sections:
        n = section_line_count(section)
        # Advance past any column that can't fit this section (but has content).
        while col < columns and current[col] and lines[col] + n > lines_per_col:
            col += 1
        if col >= columns:
            flush()
        current[col].append(section)
        lines[col] += n + 1  # +1 for visual gap between sections in same column

    flush()
    return slides


def render_word(word: Word) -> str:
    """Emit one <ruby> covering the word's pinyin-bearing tokens in jukugo form.

    Punctuation tokens inside a word are emitted as sibling .punct spans so they
    sit on the Chinese baseline without a pinyin row. Tokens without pinyin
    (e.g. when pinyin ran out mid-line) are emitted as bare .ch spans.
    """
    parts: list[str] = []
    ruby_pairs: list[str] = []

    def flush_ruby():
        if ruby_pairs:
            parts.append(f'<ruby>{"".join(ruby_pairs)}</ruby>')
            ruby_pairs.clear()

    for token in word.tokens:
        if token.is_punctuation:
            flush_ruby()
            parts.append(f'<span class="punct">{_escape(token.char)}</span>')
        elif token.pinyin:
            ruby_pairs.append(
                f'{_escape(token.char)}<rt>{_escape(token.pinyin)}</rt>'
            )
        else:
            flush_ruby()
            parts.append(f'<span class="ch">{_escape(token.char)}</span>')

    flush_ruby()
    return ''.join(parts)


def render_line(line: Line, language: str = 'chinese') -> str:
    if language == 'english':
        text = ' '.join(
            _escape(tok.char) for word in line.words for tok in word.tokens
        )
        return f'<div class="line english">{text}</div>'
    body = ''.join(render_word(w) for w in line.words)
    return f'<div class="line">{body}</div>'


def render_section(section: Section, language: str = 'chinese') -> str:
    classes = ['section', f'section-{section.type}']
    attrs = f' class="{" ".join(classes)}"'
    if section.number:
        attrs += f' data-verse="{_escape(section.number)}"'

    inner: list[str] = []
    if section.type == 'verse' and section.number:
        inner.append(f'<div class="verse-num">{_escape(section.number)}</div>')
    elif section.type in ('chorus', 'refrain', 'bridge'):
        label = {'chorus': 'Chorus', 'refrain': 'Refrain', 'bridge': 'Bridge'}[section.type]
        inner.append(f'<div class="section-label">{label}</div>')

    lines_html = ''.join(render_line(ln, language) for ln in section.lines)
    inner.append(f'<div class="section-body">{lines_html}</div>')

    return f'<div{attrs}>{"".join(inner)}</div>'


def _render_slide(song: Song, slide_cols: list, header_html: str,
                  title_html: str, columns: int) -> str:
    used_cols = [c for c in slide_cols if c] or [[]]
    effective_cols = len(used_cols)
    cols_html_parts = []
    for col in used_cols:
        sections_html = ''.join(render_section(s, song.language) for s in col)
        cols_html_parts.append(f'<div class="column">{sections_html}</div>')
    columns_html = (
        f'<div class="columns" style="--cols: {effective_cols}">'
        f'{"".join(cols_html_parts)}</div>'
    )
    return (
        f'<section class="slide" data-language="{song.language}" '
        f'data-columns="{effective_cols}">'
        f'{header_html}{title_html}{columns_html}'
        f'</section>'
    )


def render_song(song: Song, overrides: dict,
                chinese_lines_per_col: int = DEFAULT_CHINESE_LINES_PER_COL,
                english_lines_per_col: int = DEFAULT_ENGLISH_LINES_PER_COL) -> str:
    """Render a song as one or more <section class="slide"> blocks.

    Sections are packed into slides via `pack_song`. Each packed slide repeats
    the song's title/header. Per-song overrides (`columns:`, `lines:`) take
    precedence over the defaults passed in.
    """
    columns = int(overrides.get('columns', 2) or 2)

    default_lines = (
        english_lines_per_col if song.language == 'english'
        else chinese_lines_per_col
    )
    lines_per_col = int(overrides.get('lines', default_lines) or default_lines)

    book = overrides.get('book', '')
    page = overrides.get('page', '')

    header_parts: list[str] = []
    if book:
        header_parts.append(f'<div class="book">{_escape(book)}</div>')
    if page:
        header_parts.append(f'<div class="page">{_escape(page)}</div>')
    header_html = (
        f'<header class="slide-header">{"".join(header_parts)}</header>'
        if header_parts else ''
    )

    title_parts: list[str] = []
    if song.title_zh:
        title_parts.append(f'<span class="title-zh">{_escape(song.title_zh)}</span>')
    if song.title_py:
        title_parts.append(f'<span class="title-py">{_escape(song.title_py)}</span>')
    title_html = (
        f'<h1 class="title">{"".join(title_parts)}</h1>'
        if title_parts else ''
    )

    slides = pack_song(song, columns, lines_per_col)
    if not slides:
        # No sections → still emit one empty slide with title/header.
        slides = [[[] for _ in range(columns)]]

    return '\n'.join(
        _render_slide(song, slide_cols, header_html, title_html, columns)
        for slide_cols in slides
    )


def render_document(
    songs: Iterable[tuple[Song, dict]],
    title: str = 'Lyrics',
    css_href: str = 'slides.css',
    chinese_lines_per_col: int = DEFAULT_CHINESE_LINES_PER_COL,
    english_lines_per_col: int = DEFAULT_ENGLISH_LINES_PER_COL,
) -> str:
    slides = '\n'.join(
        render_song(song, overrides,
                    chinese_lines_per_col=chinese_lines_per_col,
                    english_lines_per_col=english_lines_per_col)
        for song, overrides in songs
    )
    return (
        '<!doctype html>\n'
        '<html lang="zh">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        f'<title>{_escape(title)}</title>\n'
        f'<link rel="stylesheet" href="{_escape(css_href)}">\n'
        '</head>\n'
        '<body>\n'
        f'{slides}\n'
        '</body>\n'
        '</html>\n'
    )
