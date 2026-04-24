"""Tests for pinyin_slides.parser."""
import pytest
from pinyin_slides.parser import (
    parse_song, parse_english_song, parse_lyrics, _split_pinyin_syllables,
)
from pinyin_slides.config import Token


# ── syllable splitter ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("token,expected", [
    ("xiǎoniǎo", ["xiǎo", "niǎo"]),
    ("nián", ["nián"]),
    ("niánnián", ["nián", "nián"]),
    ("xīnnián", ["xīn", "nián"]),
    ("ānníng", ["ān", "níng"]),
    ("chángān", ["cháng", "ān"]),
    ("fānàn", ["fān", "àn"]),
    ("wǒshíshí", ["wǒ", "shí", "shí"]),
    ("xūyào", ["xū", "yào"]),
])
def test_split_pinyin_syllables(token, expected):
    assert _split_pinyin_syllables(token) == expected


# ── parse_song ────────────────────────────────────────────────────────────────

HAIZI_ZH = """\
孩子的祈禱

1. 親愛的天父，祢住在哪裡？
祢是否回答每個小孩的祈禱？
"""

HAIZI_PY = """\
Háizi di qídǎo

1. Qīn'ài di Tiān­fù, nǐ zhù zài nǎ­lǐ?
Nǐ shì­fǒu huí­dá měi gè xiǎo­hái di qí­dǎo?
"""


def test_parse_song_title():
    song = parse_song(HAIZI_ZH, HAIZI_PY)
    assert song.title_zh == "孩子的祈禱"
    assert "Háizi" in song.title_py


def test_parse_song_section_count():
    song = parse_song(HAIZI_ZH, HAIZI_PY)
    assert len(song.sections) == 1
    assert song.sections[0].number == "1"


def test_parse_song_line_count():
    song = parse_song(HAIZI_ZH, HAIZI_PY)
    section = song.sections[0]
    assert len(section.lines) == 2


def test_parse_song_pinyin_attached():
    song = parse_song(HAIZI_ZH, HAIZI_PY)
    line = song.sections[0].lines[0]
    chars = [tok.char for word in line.words for tok in word.tokens]
    assert "親" in chars
    py_tokens = [
        tok for word in line.words
        for tok in word.tokens
        if not tok.is_punctuation
    ]
    assert all(tok.pinyin for tok in py_tokens)


def test_parse_song_punctuation_no_pinyin():
    song = parse_song(HAIZI_ZH, HAIZI_PY)
    line = song.sections[0].lines[0]
    punct_tokens = [
        tok for word in line.words
        for tok in word.tokens
        if tok.is_punctuation
    ]
    assert punct_tokens, "Expected punctuation tokens in first line"
    assert all(tok.pinyin is None for tok in punct_tokens)


def test_parse_song_auto_pinyin():
    """When no pinyin text given, parse_song auto-generates via pypinyin."""
    song = parse_song(HAIZI_ZH)
    assert song.title_zh == "孩子的祈禱"
    line = song.sections[0].lines[0]
    py_tokens = [
        tok for word in line.words
        for tok in word.tokens
        if not tok.is_punctuation
    ]
    assert all(tok.pinyin for tok in py_tokens)


def test_parse_song_two_verses():
    zh = "歌曲\n\n1. 第一節\n\n2. 第二節\n"
    song = parse_song(zh)
    assert len(song.sections) == 2
    assert song.sections[0].number == "1"
    assert song.sections[1].number == "2"


def test_parse_song_language_default():
    song = parse_song(HAIZI_ZH, HAIZI_PY)
    assert song.language == "chinese"


# ── Section type parsing ──────────────────────────────────────────────────────

CHORUS_ZH = """\
我時時需要主

1. 我時時需要主，慈悲之神；
聲音溫柔無比，令我安寧。

Chorus:
需要主我需要主；時時刻刻要主，
如今求主祝福我，我來就主！

2. 我時時需要主，在主跟前；
不怕任何試探，有主同在。

Chorus:
需要主我需要主；時時刻刻要主，
如今求主祝福我，我來就主！
"""

CHORUS_PY = """\
Wǒ shíshí xūyào Zhǔ

1. Wǒ shí­shí xū­yào Zhǔ, cí­bēi zhī Shén;
Shēng­yīn wēn­róu wú­bǐ, lìng wǒ ān­níng.

Chorus:
Xū­yào Zhǔ wǒ xū­yào Zhǔ; shí­shí­kè­kè yào Zhǔ,
Rú­jīn qiú Zhǔ zhù­fú wǒ, wǒ lái jiù Zhǔ!

2. Wǒ shí­shí xū­yào Zhǔ, zài Zhǔ gēn­qián;
Bú­pà rèn­hé shì­tàn, yǒu Zhǔ tóngzài.

Chorus:
Xū­yào Zhǔ wǒ xū­yào Zhǔ; shí­shí­kè­kè yào Zhǔ,
Rú­jīn qiú Zhǔ zhù­fú wǒ, wǒ lái jiù Zhǔ!
"""


def test_parse_chorus_section_types():
    song = parse_song(CHORUS_ZH, CHORUS_PY)
    types = [s.type for s in song.sections]
    assert types == ['verse', 'chorus', 'verse', 'chorus']


def test_parse_chorus_section_numbers():
    song = parse_song(CHORUS_ZH, CHORUS_PY)
    assert song.sections[0].number == "1"
    assert song.sections[1].number is None   # chorus has no number
    assert song.sections[2].number == "2"
    assert song.sections[3].number is None


def test_parse_chorus_line_count():
    song = parse_song(CHORUS_ZH, CHORUS_PY)
    assert len(song.sections[1].lines) == 2   # chorus has 2 lines


def test_parse_chorus_pinyin():
    """Chorus sections still have pinyin on non-punctuation tokens."""
    song = parse_song(CHORUS_ZH, CHORUS_PY)
    chorus = song.sections[1]
    py_tokens = [
        tok for line in chorus.lines
        for word in line.words
        for tok in word.tokens
        if not tok.is_punctuation
    ]
    assert all(tok.pinyin for tok in py_tokens)


def test_parse_section_type_mismatch_raises():
    """Mismatched section type tags between zh and pinyin files raise ValueError."""
    zh = "歌\n\n1. 一節\n\nChorus:\n副歌\n"
    py = "Gē\n\n1. Yī jié\n\nBridge:\nFùgē\n"
    with pytest.raises(ValueError, match="Section type mismatch"):
        parse_song(zh, py)


def test_parse_bridge_section_type():
    zh = "歌\n\n1. 一節\n\nBridge:\n過橋段\n"
    song = parse_song(zh)
    assert song.sections[1].type == 'bridge'
    assert song.sections[1].number is None


def test_parse_refrain_section_type():
    zh = "歌\n\n1. 一節\n\nRefrain:\n副歌\n"
    song = parse_song(zh)
    assert song.sections[1].type == 'refrain'


# ── parse_english_song ────────────────────────────────────────────────────────

ENG_TEXT = """\
Keep the Commandments

1. Keep the commandments; keep the commandments!
In this there is safety; in this there is peace.

2. Love one another; dear brothers, press forward,
Till you and I see the Savior's face.
"""

ENG_WITH_CHORUS = """\
My Song

1. First verse line one.
First verse line two.

Chorus:
This is the chorus.
It has two lines.

2. Second verse line.
"""


def test_parse_english_title():
    song = parse_english_song(ENG_TEXT)
    assert song.title_zh == "Keep the Commandments"
    assert song.language == "english"


def test_parse_english_section_count():
    song = parse_english_song(ENG_TEXT)
    assert len(song.sections) == 2


def test_parse_english_section_numbers():
    song = parse_english_song(ENG_TEXT)
    assert song.sections[0].number == "1"
    assert song.sections[1].number == "2"


def test_parse_english_line_content():
    song = parse_english_song(ENG_TEXT)
    first_line = song.sections[0].lines[0]
    text = " ".join(
        tok.char for word in first_line.words for tok in word.tokens
    )
    assert "Keep the commandments" in text


def test_parse_english_chorus_type():
    song = parse_english_song(ENG_WITH_CHORUS)
    types = [s.type for s in song.sections]
    assert types == ['verse', 'chorus', 'verse']
    assert song.sections[1].number is None
    assert len(song.sections[1].lines) == 2


# ── parse_lyrics ──────────────────────────────────────────────────────────────

LYRICS_TEXT = """\
[song]
language: english

[english]
Gethsemane

1. Jesus climbed the hill to the garden still.

[song]
columns: 2

[chinese]
孩子的祈禱

1. 親愛的天父，祢住在哪裡？

[pinyin]
Háizi di qídǎo

1. Qīn'ài di Tiān­fù, nǐ zhù zài nǎ­lǐ?
"""

LYRICS_AUTO = """\
[song]
auto_pinyin: true

[chinese]
孩子的祈禱

1. 親愛的天父，祢住在哪裡？
"""

LYRICS_WITH_CHORUS = """\
[song]
columns: 2

[chinese]
歌名

1. 一節歌詞

Chorus:
副歌歌詞

[pinyin]
Gēmíng

1. Yī jié gēcí

Chorus:
Fùgē gēcí
"""


def test_parse_lyrics_count():
    songs = parse_lyrics(LYRICS_TEXT)
    assert len(songs) == 2


def test_parse_lyrics_languages():
    songs = parse_lyrics(LYRICS_TEXT)
    langs = [overrides.get('language', 'chinese') for _, overrides in songs]
    assert langs[0] == 'english'
    assert langs[1] == 'chinese'


def test_parse_lyrics_overrides():
    songs = parse_lyrics(LYRICS_TEXT)
    _, overrides = songs[1]
    assert overrides.get('columns') == '2'


def test_parse_lyrics_chinese_with_pinyin():
    songs = parse_lyrics(LYRICS_TEXT)
    song, _ = songs[1]
    assert song.title_zh == "孩子的祈禱"
    line = song.sections[0].lines[0]
    py_tokens = [
        tok for word in line.words
        for tok in word.tokens
        if not tok.is_punctuation
    ]
    assert all(tok.pinyin for tok in py_tokens)


def test_parse_lyrics_auto_pinyin():
    """auto_pinyin: true entry should still produce pinyin via pypinyin."""
    songs = parse_lyrics(LYRICS_AUTO)
    assert len(songs) == 1
    song, overrides = songs[0]
    assert overrides.get('auto_pinyin') == 'true'
    line = song.sections[0].lines[0]
    py_tokens = [
        tok for word in line.words
        for tok in word.tokens
        if not tok.is_punctuation
    ]
    assert all(tok.pinyin for tok in py_tokens)


def test_parse_lyrics_missing_pinyin_falls_back_to_auto():
    """A Chinese entry with no [pinyin] section auto-generates pinyin."""
    lyrics = "[song]\n\n[chinese]\n孩子的祈禱\n\n1. 親愛的天父\n"
    songs = parse_lyrics(lyrics)
    assert len(songs) == 1
    song, _ = songs[0]
    line = song.sections[0].lines[0]
    py_tokens = [
        tok for word in line.words
        for tok in word.tokens
        if not tok.is_punctuation
    ]
    assert all(tok.pinyin for tok in py_tokens)


def test_parse_lyrics_chorus_section_type():
    """Chorus: tag in lyrics file produces chorus-type sections."""
    songs = parse_lyrics(LYRICS_WITH_CHORUS)
    assert len(songs) == 1
    song, _ = songs[0]
    types = [s.type for s in song.sections]
    assert types == ['verse', 'chorus']
    assert song.sections[1].number is None
