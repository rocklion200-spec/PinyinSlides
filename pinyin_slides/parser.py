"""Parse Chinese text and pinyin into structured Song data."""

import re
import unicodedata
from typing import Optional

from .config import PUNCTUATION, Token, Word, Line, Section, Song


_STRIP_CHARS = '.,;:!?"\'""''()[]{}「」《》【】，。！？；：、…（）·～—'

# Regex for matching one Mandarin pinyin syllable (case-insensitive).
# Used as a fallback when the valid-syllable tokenizer can't split cleanly.
_SYLLABLE_RE = re.compile(
    r'(?:zh|ch|sh|[bpmfdtnlgkhjqxrzcsyw])?'
    r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜaeiouüv]+'
    r'(?:ng|n(?!g)|r(?![āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜaeiouüv]))?',
    re.IGNORECASE,
)

# Regex to detect section-type tag lines: "Chorus:", "Bridge:", "Refrain:"
# Matches the line by itself (possibly with trailing whitespace).
_SECTION_TAG_RE = re.compile(r'^(Chorus|Refrain|Bridge)\s*:\s*$', re.IGNORECASE)


def _build_valid_syllables() -> frozenset:
    """Return the set of valid Mandarin pinyin syllables (plain ASCII, lowercase).

    Built from (initial, final) combinations filtered by Mandarin phonotactics
    and orthographic rules. Covers the canonical ~410 syllables.
    """
    initials = ['', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
                'g', 'k', 'h', 'j', 'q', 'x',
                'zh', 'ch', 'sh', 'r', 'z', 'c', 's']
    finals = [
        'a', 'o', 'e', 'ai', 'ei', 'ao', 'ou',
        'an', 'en', 'ang', 'eng', 'ong', 'er',
        'i', 'ia', 'ie', 'iao', 'iu', 'ian', 'in', 'iang', 'ing', 'iong',
        'u', 'ua', 'uo', 'uai', 'ui', 'uan', 'un', 'uang', 'ueng',
        'v', 've', 'van', 'vn',
    ]
    out = set()
    for ini in initials:
        for fin in finals:
            syl = _compose_syllable(ini, fin)
            if syl:
                out.add(syl)
    # Interjections and minor extras.
    out.update(['m', 'n', 'ng', 'hm', 'hng', 'lo', 'io', 'eh'])
    return frozenset(out)


def _compose_syllable(ini: str, fin: str) -> Optional[str]:
    """Compose a syllable from initial+final per Mandarin spelling rules,
    returning None if the combination is illegal."""
    v_finals = {'v': 'ü', 've': 'üe', 'van': 'üan', 'vn': 'ün'}

    if ini == '':
        # Zero-initial spelling: i- → yi/y-, u- → wu/w-, ü- → yu-
        if fin in v_finals:
            return 'y' + v_finals[fin].replace('ü', 'u')
        if fin == 'i':
            return 'yi'
        if fin == 'in':
            return 'yin'
        if fin == 'ing':
            return 'ying'
        if fin.startswith('i'):
            return 'y' + fin[1:]
        if fin == 'u':
            return 'wu'
        if fin == 'ueng':
            return 'weng'
        if fin.startswith('u'):
            return 'w' + fin[1:]
        if fin in ('a', 'o', 'e', 'ai', 'ei', 'ao', 'ou',
                   'an', 'en', 'ang', 'eng', 'er'):
            return fin
        return None

    # ü-finals: allowed only after j/q/x (spelled plain u) or n/l (spelled ü).
    if fin in v_finals:
        if ini in ('j', 'q', 'x'):
            return ini + v_finals[fin].replace('ü', 'u')
        if ini in ('n', 'l'):
            return ini + v_finals[fin]
        return None

    # Palatals j/q/x take no u-class finals
    if ini in ('j', 'q', 'x') and fin.startswith('u'):
        return None

    # Retroflex/sibilant initials don't take i-class finals except bare 'i'
    if ini in ('zh', 'ch', 'sh', 'r', 'z', 'c', 's'):
        if fin.startswith('i') and fin != 'i':
            return None

    # g/k/h take no i-class finals
    if ini in ('g', 'k', 'h') and fin.startswith('i'):
        return None

    # 'ueng' only legal with no initial (→ weng)
    if fin == 'ueng':
        return None

    # Labials b/p/m/f: limited u-finals
    if ini in ('b', 'p', 'm', 'f'):
        if fin in ('ua', 'uai', 'uang', 'un', 'uo', 'ui', 'uan'):
            return None
        if fin in ('ia', 'iang', 'iong', 'iu'):
            if not (ini == 'm' and fin == 'iu'):
                return None
        if ini == 'f' and fin in ('ie', 'ian', 'in', 'ing', 'iao'):
            return None

    # d/t: no -ua, -uai, -uang
    if ini in ('d', 't') and fin in ('ua', 'uai', 'uang'):
        return None

    return ini + fin


_VALID_SYLLABLES = _build_valid_syllables()

_TONE_MAP = {
    'ā': 'a', 'á': 'a', 'ǎ': 'a', 'à': 'a',
    'ē': 'e', 'é': 'e', 'ě': 'e', 'è': 'e',
    'ī': 'i', 'í': 'i', 'ǐ': 'i', 'ì': 'i',
    'ō': 'o', 'ó': 'o', 'ǒ': 'o', 'ò': 'o',
    'ū': 'u', 'ú': 'u', 'ǔ': 'u', 'ù': 'u',
    'ǖ': 'u', 'ǘ': 'u', 'ǚ': 'u', 'ǜ': 'u',
    'ü': 'u',
}


def _strip_tone(s: str) -> str:
    """Lowercase and strip tone marks for syllable-set lookup."""
    s = unicodedata.normalize('NFC', s.lower())
    return ''.join(_TONE_MAP.get(c, c) for c in s)


def _clean_syllable(syl: str) -> str:
    """Strip leading/trailing punctuation from a pinyin syllable."""
    return syl.strip(_STRIP_CHARS)


def _tokenize_against_valid(token: str) -> Optional[list]:
    """Try to split token into valid syllables via longest-match with backtrack.

    Returns a list of original-case substrings if every piece is a valid
    syllable (tone-stripped); returns None if no full decomposition exists.
    """
    plain = _strip_tone(token)
    n = len(plain)
    if n == 0:
        return None

    # memoized DP: for each start index, list of (end_idx) where plain[start:end]
    # is a valid syllable, preferring longer matches first.
    memo: dict = {}

    def solve(start: int) -> Optional[list]:
        if start == n:
            return []
        if start in memo:
            return memo[start]
        # Try longest match first (up to 6 chars — longest Mandarin syllable is
        # 'zhuang'/'chuang'/'shuang' at 6).
        for end in range(min(n, start + 6), start, -1):
            piece = plain[start:end]
            if piece in _VALID_SYLLABLES:
                rest = solve(end)
                if rest is not None:
                    result = [(start, end)] + rest
                    memo[start] = result
                    return result
        memo[start] = None
        return None

    spans = solve(0)
    if spans is None:
        return None
    return [token[s:e] for s, e in spans]


def _split_pinyin_syllables(token: str) -> list:
    """Split a concatenated multi-syllable pinyin token into individual syllables."""
    # First try the valid-syllable tokenizer (longest match with backtracking).
    parts = _tokenize_against_valid(token)
    if parts is not None and len(parts) >= 1:
        return parts

    # Fallback: regex-based split (legacy behavior for malformed input).
    matches = list(_SYLLABLE_RE.finditer(token))
    if len(matches) <= 1:
        return [token]
    total_len = sum(m.end() - m.start() for m in matches)
    if total_len == len(token):
        return [m.group(0) for m in matches]
    return [token]


def parse_song(chinese_text: str, pinyin_text: Optional[str] = None) -> Song:
    """Parse Chinese text and optional pinyin into a Song structure.

    Section type tags (Chorus:, Bridge:, Refrain:) on a line by themselves mark
    the following block as that section type.  Blocks without a tag default to
    'verse'.  Verse blocks starting with "N." get a verse number.

    Chinese and pinyin files must have matching section-type tags at identical
    block positions; a mismatch raises ValueError.
    """
    zh_lines = chinese_text.strip().split('\n')
    py_lines = None
    if pinyin_text and pinyin_text.strip():
        py_lines = pinyin_text.strip().split('\n')

    title_zh = ""
    title_py = ""
    zh_start = 0
    py_start = 0

    # Detect title: first non-section-tag line that is followed by a blank line
    # or by a verse-numbered line.
    if zh_lines:
        first = zh_lines[0].strip()
        if first and not re.match(r'^\d+[\.\、\:]', first) and not _SECTION_TAG_RE.match(first):
            first_line_followed_by_blank = (
                len(zh_lines) > 1 and not zh_lines[1].strip()
            )
            next_content = next(
                (zh_lines[i].strip() for i in range(1, len(zh_lines))
                 if zh_lines[i].strip()),
                None,
            )
            next_is_numbered = bool(
                next_content and re.match(r'^\d+[\.\、\:]', next_content)
            )
            if first_line_followed_by_blank or next_is_numbered:
                title_zh = first
                zh_start = 1
                while zh_start < len(zh_lines) and not zh_lines[zh_start].strip():
                    zh_start += 1

    zh_content_lines = zh_lines[zh_start:]

    if py_lines:
        if title_zh and py_lines:
            title_py = py_lines[0].strip()
            py_start = 1
            while py_start < len(py_lines) and not py_lines[py_start].strip():
                py_start += 1
        py_content_lines = py_lines[py_start:]
    else:
        py_content_lines = []

    zh_typed = _split_into_typed_blocks(zh_content_lines)
    py_typed = _split_into_typed_blocks(py_content_lines) if py_content_lines else None

    if py_typed is None:
        # Auto-generate pinyin for each block
        zh_blocks_only = [b for _, b in zh_typed]
        py_blocks = _auto_generate_pinyin_blocks(zh_blocks_only)
        py_typed = [(t, pb) for (t, _), pb in zip(zh_typed, py_blocks)]
    else:
        # Enforce matching section types between Chinese and pinyin
        if len(py_typed) != len(zh_typed):
            raise ValueError(
                f"Chinese has {len(zh_typed)} block(s) but pinyin has {len(py_typed)}."
            )
        for i, ((zt, _), (pt, _)) in enumerate(zip(zh_typed, py_typed)):
            if zt != pt:
                raise ValueError(
                    f"Section type mismatch at block {i + 1}: "
                    f"Chinese is '{zt}' but pinyin is '{pt}'."
                )

    sections = []
    for (zh_type, zh_block), (_, py_block) in zip(zh_typed, py_typed):
        section = _parse_section(zh_block, py_block, zh_type)
        sections.append(section)

    return Song(title_zh=title_zh, title_py=title_py, sections=sections)


def _split_into_typed_blocks(lines: list) -> list:
    """Split lines into blocks separated by blank lines.

    Returns list of (section_type, content_lines) tuples.
    A block whose first line matches _SECTION_TAG_RE is tagged with that type
    and the tag line is consumed; otherwise the type defaults to 'verse'.
    """
    raw_blocks = []
    current = []
    for line in lines:
        if line.strip():
            current.append(line)
        else:
            if current:
                raw_blocks.append(current)
                current = []
    if current:
        raw_blocks.append(current)

    typed_blocks = []
    for block in raw_blocks:
        m = _SECTION_TAG_RE.match(block[0].strip())
        if m:
            section_type = m.group(1).lower()
            typed_blocks.append((section_type, block[1:]))
        else:
            typed_blocks.append(('verse', block))

    return typed_blocks


def _auto_generate_pinyin_blocks(zh_blocks: list) -> list:
    """Generate pinyin for each block of Chinese text using pypinyin."""
    from pypinyin import pinyin, Style

    py_blocks = []
    for block in zh_blocks:
        py_block = []
        for zh_line in block:
            clean = re.sub(r'^\d+[\.\、\:]\s*', '', zh_line.strip())
            chars = list(clean)
            syllables = []
            for ch in chars:
                if ch in PUNCTUATION:
                    continue
                elif ch.strip() == '':
                    continue
                else:
                    py = pinyin(ch, style=Style.TONE)
                    if py and py[0]:
                        syllables.append(py[0][0])
            py_block.append(' '.join(syllables))
        py_blocks.append(py_block)
    return py_blocks


def _build_syllable_map(py_text: str, word_idx_base: int = 0) -> list:
    """Flatten pinyin text into a list of (syllable, word_idx) pairs.

    Each whitespace-separated token in `py_text` is a word; hyphens and
    apostrophes within a word further split it into syllables, and
    multi-syllable concatenations get split by the valid-syllable tokenizer.
    """
    syllable_map = []
    for word_offset, py_word in enumerate(py_text.split()):
        word_idx = word_idx_base + word_offset
        syllables = re.split(r"[\u00ad\-\'\u2019]", py_word)
        for syl in syllables:
            syl = _clean_syllable(syl)
            if syl:
                for subsyl in _split_pinyin_syllables(syl):
                    syllable_map.append((subsyl, word_idx))
    return syllable_map


def _consume_zh_line(zh_text: str, syllable_map: list, syl_idx: int,
                     current_word_idx: int) -> tuple:
    """Build a Line from `zh_text`, consuming syllables from `syllable_map`
    starting at `syl_idx`. Returns (line, new_syl_idx, new_current_word_idx)."""
    current_tokens = []
    words = []

    for ch in zh_text:
        if ch.strip() == '':
            continue

        if ch in PUNCTUATION:
            token = Token(char=ch, pinyin=None, is_punctuation=True)
            if current_tokens:
                current_tokens.append(token)
            else:
                words.append(Word(tokens=[token]))
            continue

        if syl_idx >= len(syllable_map):
            token = Token(char=ch, pinyin=None, is_punctuation=False)
            if current_tokens:
                current_tokens.append(token)
            else:
                words.append(Word(tokens=[token]))
            continue

        syllable, word_idx = syllable_map[syl_idx]
        syl_idx += 1

        if word_idx != current_word_idx:
            if current_tokens:
                words.append(Word(tokens=current_tokens))
                current_tokens = []
            current_word_idx = word_idx

        token = Token(char=ch, pinyin=syllable, is_punctuation=False)
        current_tokens.append(token)

    if current_tokens:
        words.append(Word(tokens=current_tokens))

    return Line(words=words), syl_idx, current_word_idx


def _parse_section(zh_lines: list, py_lines: Optional[list],
                   section_type: str = 'verse') -> Section:
    """Parse a single section from Chinese and pinyin line lists.

    When Chinese and pinyin have the same number of lines, each zh line uses
    its own pinyin line. When line counts differ, the section's pinyin is
    flattened into a single syllable queue and consumed across zh lines.
    """
    verse_number = None

    # Strip each zh line and extract verse number from the first line.
    zh_stripped = [ln.strip() for ln in zh_lines]
    if section_type == 'verse' and zh_stripped:
        m = re.match(r'^(\d+)[\.\、\:]\s*', zh_stripped[0])
        if m:
            verse_number = m.group(1)
            zh_stripped[0] = zh_stripped[0][m.end():]

    # Strip pinyin lines and drop leading verse number from the first.
    py_stripped = None
    if py_lines:
        py_stripped = [ln.strip() for ln in py_lines]
        if py_stripped:
            pm = re.match(r'^(\d+)[\.\、\:]\s*', py_stripped[0])
            if pm:
                py_stripped[0] = py_stripped[0][pm.end():]

    parsed_lines = []

    if not py_stripped:
        for zh in zh_stripped:
            line, _, _ = _consume_zh_line(zh, [], 0, -1)
            parsed_lines.append(line)
        return Section(lines=parsed_lines, type=section_type, number=verse_number)

    same_line_count = len(zh_stripped) == len(py_stripped)

    if same_line_count:
        for zh, py in zip(zh_stripped, py_stripped):
            syllable_map = _build_syllable_map(py)
            line, _, _ = _consume_zh_line(zh, syllable_map, 0, -1)
            parsed_lines.append(line)
    else:
        # Flatten all pinyin syllables and consume across zh lines. Each
        # pinyin line advances the word-index base so word boundaries are
        # preserved across the section.
        syllable_map = []
        base = 0
        for py in py_stripped:
            piece = _build_syllable_map(py, word_idx_base=base)
            syllable_map.extend(piece)
            if piece:
                base = piece[-1][1] + 1
        syl_idx = 0
        current_word_idx = -1
        for zh in zh_stripped:
            line, syl_idx, current_word_idx = _consume_zh_line(
                zh, syllable_map, syl_idx, current_word_idx)
            parsed_lines.append(line)

    return Section(lines=parsed_lines, type=section_type, number=verse_number)


def _parse_line(zh_text: str, py_text: Optional[str]) -> Line:
    """Parse a single line into Words containing Tokens. Kept for API compat."""
    syllable_map = _build_syllable_map(py_text) if py_text else []
    line, _, _ = _consume_zh_line(zh_text, syllable_map, 0, -1)
    return line


def parse_english_song(text: str) -> Song:
    """Parse English lyrics into a Song with language='english'.

    Supports Chorus:, Bridge:, Refrain: section type tags.
    """
    lines = text.strip().split('\n') if text.strip() else []
    if not lines:
        return Song(language='english')

    title = ""
    content_start = 0

    first = lines[0].strip()
    if first and not re.match(r'^\d+[\.\、\:]', first) and not _SECTION_TAG_RE.match(first):
        first_followed_by_blank = len(lines) > 1 and not lines[1].strip()
        next_content = next(
            (lines[i].strip() for i in range(1, len(lines)) if lines[i].strip()), None
        )
        next_is_numbered = bool(next_content and re.match(r'^\d+[\.\、\:]', next_content))
        if first_followed_by_blank or next_is_numbered:
            title = first
            content_start = 1
            while content_start < len(lines) and not lines[content_start].strip():
                content_start += 1

    content_lines = lines[content_start:]
    typed_blocks = _split_into_typed_blocks(content_lines)

    sections = []
    for section_type, block in typed_blocks:
        sections.append(_parse_english_section(block, section_type))

    return Song(title_zh=title, title_py='', sections=sections, language='english')


def _parse_english_section(lines: list, section_type: str = 'verse') -> Section:
    """Parse an English section block. Each line → Line(Word([Token(char=text)]))."""
    verse_number = None
    parsed_lines = []

    for i, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if i == 0 and section_type == 'verse':
            m = re.match(r'^(\d+)[\.\、\:]\s*', stripped)
            if m:
                verse_number = m.group(1)
                stripped = stripped[m.end():]
        if stripped:
            token = Token(char=stripped, pinyin=None, is_punctuation=False)
            word = Word(tokens=[token])
            parsed_lines.append(Line(words=[word]))

    return Section(lines=parsed_lines, type=section_type, number=verse_number)


def parse_lyrics(text: str) -> list:
    """Parse a multi-song lyrics file into a list of (Song, dict) tuples."""
    raw_blocks = _split_lyrics_by_song(text)
    result = []
    for block_text in raw_blocks:
        if block_text.strip():
            pair = _parse_lyrics_song_block(block_text)
            if pair is not None:
                result.append(pair)
    return result


def _split_lyrics_by_song(text: str) -> list:
    """Split lyrics text into per-song blocks at [song] markers."""
    lines = text.split('\n')
    blocks = []
    current = []
    for line in lines:
        if re.match(r'^\[song\]\s*$', line.strip(), re.IGNORECASE):
            if any(l.strip() for l in current):
                blocks.append('\n'.join(current))
            current = []
        else:
            current.append(line)
    if any(l.strip() for l in current):
        blocks.append('\n'.join(current))
    return blocks


def _parse_lyrics_song_block(text: str) -> tuple:
    """Parse one song block → (Song, overrides_dict)."""
    lines = text.split('\n')
    overrides = {}
    sections = {}
    current_section = 'config'
    section_lines = []

    for line in lines:
        m = re.match(r'^\[(\w+)\]\s*$', line.strip())
        if m:
            if current_section == 'config':
                for cfg_line in section_lines:
                    km = re.match(r'^([\w][\w\-]*)\s*:\s*(.+)$', cfg_line.strip())
                    if km:
                        overrides[km.group(1).lower().replace('-', '_')] = km.group(2).strip()
            elif section_lines:
                sections[current_section] = '\n'.join(section_lines)
            current_section = m.group(1).lower()
            section_lines = []
        else:
            section_lines.append(line)

    # flush last section
    if current_section == 'config':
        for cfg_line in section_lines:
            km = re.match(r'^([\w][\w\-]*)\s*:\s*(.+)$', cfg_line.strip())
            if km:
                overrides[km.group(1).lower().replace('-', '_')] = km.group(2).strip()
    elif section_lines:
        sections[current_section] = '\n'.join(section_lines)

    language = overrides.get('language', 'chinese').lower()

    if language == 'english':
        eng_text = sections.get('english', '')
        song = parse_english_song(eng_text)
    else:
        zh_text = sections.get('chinese', '')
        py_text = sections.get('pinyin') or None
        if not zh_text.strip():
            return None
        song = parse_song(zh_text, py_text)

    return (song, overrides)
