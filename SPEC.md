# PinyinSlides — Project Specification

## Purpose

PinyinSlides generates 16:9 PowerPoint (`.pptx`) slide decks for church worship projection. It supports two modes:

1. **Chinese songs** — renders pinyin (tone-marked romanisation) above Chinese characters as pixel-perfect PNG images, then embeds them in slides.
2. **English songs** — places lyrics as native pptx text boxes (no image rendering required).

A companion scraper (`scrape_lyrics.py`) fetches lyrics directly from the Church of Jesus Christ of Latter-day Saints music library website and produces a lyrics file automatically.

---

## Repository Layout

```
PinyinSlides/
├── generate.py              # Main CLI entry point
├── scrape_lyrics.py           # Lyrics scraper + slide builder
├── pinyin_slides/
│   ├── __init__.py
│   ├── config.py            # Dataclasses: Token, Word, Line, Section, Song, SlideConfig
│   ├── parser.py            # Text → Song data model; lyrics file parser
│   ├── renderer.py          # PIL-based pinyin-over-character image renderer
│   └── slidebuilder.py      # python-pptx slide assembly
└── test_data/
    ├── sample_links.txt     # Example scraper input
    ├── keximani_deck.txt    # Example multi-song lyrics file
    └── ...
```

---

## Data Model (`config.py`)

All structures are Python `dataclass`es.

```
Token
  char: str               # One Chinese character (or full English line in English mode)
  pinyin: str | None      # Tone-marked pinyin syllable, e.g. "nǐ"
  is_punctuation: bool    # True for CJK punctuation (no pinyin consumed)

Word
  tokens: list[Token]     # One or more characters forming a pinyin "word group"

Line
  words: list[Word]       # Words on one lyric line

SectionType = Literal['verse', 'chorus', 'refrain', 'bridge']

Section
  lines: list[Line]
  type: SectionType       # default 'verse'
  number: str | None      # "1", "2", … set only when type == 'verse'

Song
  title_zh: str           # Chinese title (or English title stored here)
  title_py: str           # Pinyin title (empty for English songs)
  sections: list[Section]
  language: str           # "chinese" | "english"  (default "chinese")
```

### Punctuation set

`PUNCTUATION = set('，。！？；：、…（）「」《》【】·～—""'')`

Punctuation tokens consume no pinyin syllable; they attach to the preceding word's token list.

---

## Input File Formats

### Separate Chinese / Pinyin files (legacy mode)

Two plain-text files with identical verse/line structure:

- **Chinese file**: lines of Chinese characters. Blank lines separate verses. First line is the title if followed by a blank line or if the next non-blank line starts with a verse number (`N.`, `N、`, `N:`).
- **Pinyin file**: mirrors Chinese file line-for-line. Spaces in pinyin separate word groups; hyphens (`-`, soft hyphen U+00AD) or apostrophes join syllables within a word.

### Lyrics file format (multi-song, recommended)

Songs separated by `[song]` markers. Within each song block, content sections are marked by `[chinese]`, `[pinyin]`, or `[english]`. Key:value config lines between `[song]` and the first content marker are per-song overrides.

```
[song]
columns: 2

[chinese]
客西馬尼

1. 耶穌靜靜地往客西馬尼，
...

[pinyin]
Kè xī mǎ ní

1. Yēsū jìng jìng di wǎng Kè xī mǎ ní,
...

[song]
language: english

[english]
Gethsemane

1. Jesus climbed the hill to the garden still.
...
```

**Verse numbering**: a line beginning with `N.` (or `N、` or `N:`) is treated as a verse numbered N; the prefix is stripped before storing.

**Section type tags**: a line containing only `Chorus:`, `Refrain:`, or `Bridge:` (case-insensitive) marks the following block as that section type. The tag line is consumed and does not appear in the lyrics. Blocks without a tag default to `type='verse'`. Example:

```
1. First verse line one.
First verse line two.

Chorus:
This is the chorus.
It has two lines.

2. Second verse line.
```

**Chinese / Pinyin tag alignment**: when a `[chinese]` block contains a section-type tag, the corresponding `[pinyin]` block must have the same tag at the same position. A mismatch raises `ValueError: Section type mismatch at block N`.

**Section blocks**: separated by blank lines.

**Title detection** (same logic for all languages): the first line of a content block is the title if:
- it does not itself start with a verse number or section-type tag, AND
- it is directly followed by a blank line, OR the next non-blank line starts with a verse number or tag.

### Per-song config keys

| Key | Type | Description |
|-----|------|-------------|
| `language` | string | `chinese` (default) or `english` |
| `columns` | int | Number of slide columns |
| `rows` | int | Max verse rows per column (default: auto) |
| `pinyin_size` | int | Pinyin font size in render pixels |
| `char_size` | int | Character font size in render pixels |
| `text_color` | string | Hex colour, e.g. `#000000` |
| `max_lines` | int | Max lines per verse |
| `english_font_size` | int | Starting English font size (pt) |
| `dedup_chorus` | bool | If `true`, collapse repeated choruses (see Per-slide chorus enforcement); default `false` repeats the chorus each occurrence |
| `auto_pinyin` | bool | Auto-generate pinyin from Chinese text |

---

## Parser (`parser.py`)

### `parse_song(chinese_text, pinyin_text=None) → Song`

Parses two separate text strings. If `pinyin_text` is `None`, calls `pypinyin` to auto-generate.

**Pinyin syllable splitting**: the regex `_SYLLABLE_RE` matches one Mandarin syllable (initial + nucleus + optional coda). Multi-syllable tokens like `"Chénzhòng"` are split by applying the regex repeatedly; if the matches don't cover the full token, it is left unsplit (parse error surfaces later).

Word boundaries come from spaces in the pinyin text. Syllable boundaries within a word come from hyphens, soft hyphens, or apostrophes.

### `parse_english_song(text) → Song`

Same title-detection and section-block splitting as Chinese, including section-type tag recognition. Each line becomes a single `Token(char=line_text)` with no pinyin. Returns `Song(language='english')`.

### `parse_lyrics(text) → list[(Song, dict)]`

Splits on `[song]` markers, calls `_parse_lyrics_song_block` for each, returns a list of `(Song, overrides_dict)` pairs.

---

## Renderer (`renderer.py`)

Renders one `Section` as a transparent RGBA PNG image using Pillow.

### Fonts

- **Pinyin**: Barlow Semi Condensed Regular (TTF). Loaded with `ImageFont.truetype`.
- **Characters**: PingFang SC Regular (index 3 in `PingFang.ttc`). System font on macOS.

### Layout within one verse image

Each line occupies a **row** composed of two sub-rows:
1. **Pinyin row** — height `py_row_h` from font metrics (`getbbox("lǐ")`)
2. **Character row** — height `ch_row_h` from font metrics (`getbbox("国")`)

Between pinyin and character: `pinyin_char_gap` pixels.
Between lines: `line_spacing` pixels (bottom of characters → top of next pinyin).
Above first line: `top_padding` pixels (prevents tone mark clipping).

Image width is determined by laying out all words, computing each word's unit width, then summing with inter-word gaps.

### Word / syllable width calculation

For each **word** (group of tokens), the unit width of a syllable is:

```
unit_w = max(char_width, pinyin_width) + intra_word_padding
```

where `char_width` = rendered width of one Chinese character, `pinyin_width` = rendered width of the pinyin string (after NFC/split normalisation). `intra_word_padding` (default 8 px) adds breathing room between syllables in a word.

**Inter-word gap** (`inter_word_gap`, default 18 px): the gap between adjacent words is the natural slack (total unit widths minus actual char widths) plus the semantic minimum. Natural slack is `Σ(unit_w - char_w)` across all tokens in a word; if slack already exceeds `inter_word_gap`, no extra gap is added.

### Pinyin glyph rendering — NFC / split strategy

Barlow Semi Condensed is missing several precomposed Latin Extended-B glyphs: `ǐ ǒ ǖ ǘ ǚ ǜ ǹ` (these render as notdef rectangles).

**Detection**: render candidate char and a known-bad CJK char (U+9999) at the same size; compare non-zero pixel counts. If identical, the glyph is missing.

**Strategy**:
- If the font has the precomposed NFC glyph → use NFC directly.
- If missing → use **split rendering**: draw the base letter (dotless-ı `U+0131` for `ǐ`, plain `o` for `ǒ`, etc.) and stamp an extracted mark image on top.

**Mark extraction** (`_extract_mark_image`): renders a known-good NFC pair (`ǎ` vs `a`) at high resolution; subtracts the base from the combined image to isolate the combining mark pixels; returns the mark as a grayscale PIL Image plus its horizontal and vertical anchor offsets.

**Mark placement** (`_draw_pinyin_token`): when a syllable contains a split character, the renderer:
1. Builds `render_str` = the base letters for all chars (e.g. `"wɨ"` → `"wi"` with dotless-ı).
2. Tracks `prefix_str` = characters rendered before the split character.
3. Draws `render_str` centered in the unit cell.
4. Computes `prefix_advance = font.getlength(prefix_str)` to offset the mark horizontally.
5. Stamps the mark at `x_center_of_base_letter - mark_width / 2`.

This ensures the mark sits correctly over the right letter even in multi-character syllables like "wǒ" or "nǐ".

### `render_section(section, config, section_label='', trailing_asterisks=0) → Image`

- `section_label`: plain-text header rendered above the lyric lines (e.g. `"* Chorus 副歌:"`). Height is `ch_row_h + line_spacing`; the label uses `char_font`.
- `trailing_asterisks`: number of `*` characters appended after the last lyric line (e.g. `1` → ` *`, `2` → ` * *`), drawn with `char_font` at the x-position following the last line's content.

`render_verse` is kept as an alias for backward compatibility.

### `char_height_px(config) → int`

Returns the actual rendered character row height (from PingFang SC metrics) for use in the column-packing legibility threshold. Uses `getbbox("国")` to measure.

---

## Slide Builder (`slidebuilder.py`)

### Slide geometry (inches)

| Constant | Value | Description |
|----------|-------|-------------|
| `_SLIDE_W` | 13.333 | Slide width |
| `_SLIDE_H` | 7.5 | Slide height |
| `_MARGIN_L` | 0.50 | Left margin |
| `_MARGIN_R` | 0.50 | Right margin |
| `_MARGIN_TOP` | 0.20 | Top margin |
| `_TITLE_H` | 0.65 | Title text box height |
| `_TITLE_GAP` | 0.15 | Gap between title and content |
| `_TOPRIGHT_RESERVE` | 2.00 | Width reserved at the right of the title row for future book/page metadata |
| `_CONTENT_TOP` | 1.00 | Top of content area |
| `_CONTENT_H` | 6.20 | Height of content area |
| `_CONTENT_W` | 12.333 | Width of content area |
| `_COL_GAP` | 0.30 | Horizontal gap between columns |
| `_ROW_GAP` | 0.30 | Vertical gap between stacked verse rows |
| `_VERSE_NUM_W` | 0.45 | Width reserved for verse-number text box |
| `_IMG_NO_NUM_INSET` | 0.10 | Extra left inset when no verse numbers |
| `_MIN_CHAR_PT` | 28 | Minimum character point-size floor (display equivalent) |
| `_MIN_CHAR_H_IN` | ≈ 0.272 | `_MIN_CHAR_PT / 72 * 0.7` — min PIL-bbox character height in inches |

### Title text box

One Arial text box spanning the content width minus a `_TOPRIGHT_RESERVE` (2.0″) gap on the right, reserved for future book/page metadata. Two runs in a single paragraph:
- Run 1: Chinese title at 36 pt, not bold
- Run 2: `"  " + pinyin_title` at 36 pt, not bold

For English songs, only Run 1 is used (the English title in `song.title_zh`).

### Verse number text boxes

When any verse on a slide has a number, a separate Arial text box is placed to the left of the verse image/textbox: width `_VERSE_NUM_W`, height equal to the verse height, top-anchored, left-aligned.

### `_compute_display_info(song, dedup_chorus) → (display_sections, labels, trailing_asts, chorus_ref_map)`

Central pre-processing step called by both `_add_chinese_slides` and `_add_english_slides` before any rendering or packing. Behaviour depends on the per-song `dedup_chorus` flag (default `False`).

**Repeat mode (default, `dedup_chorus=False`)**: every section is emitted verbatim in source order. All labels are empty and all trailing-asterisk counts are zero. `chorus_ref_map` is empty. This produces slides in which each chorus occurrence shows its full text, with no `Chorus:` label and no asterisks on verses.

**Dedup mode (`dedup_chorus=True`)**:
- Chorus deduplication: iterates sections in source order. The first occurrence of each unique chorus (keyed by a hash of all token characters) is kept; later occurrences of the same content are dropped.
- Asterisk cues: each non-chorus section gets `trailing_asts[i]` = number of consecutive chorus sections that immediately follow it in source order.
- Labels: kept chorus sections receive `"* Chorus 副歌:"` (Chinese) or `"* Chorus:"` (English); all other sections get `''`.
- `chorus_ref_map: dict[verse_display_idx -> list[chorus_display_idx]]` records, for each verse with trailing asterisks, which chorus body those asterisks reference. This is used by the per-slide chorus enforcement pass (see below).

Returns four parallel structures over the display sections: `display_sections`, `labels`, `trailing_asts`, `chorus_ref_map`.

### Per-slide chorus enforcement (dedup mode only)

After packing produces an initial slide layout, `_enforce_chorus_per_slide_chinese` / `_enforce_chorus_per_slide_english` walks each slide and guarantees that every trailing-`*` reference on that slide has its chorus body present on the same slide.

For each slide:
- If no trailing-asterisk verse on the slide is missing its chorus body, the slide is kept as-is.
- **Downgrade case** — if the slide has exactly one section (a single verse) with `trailing_asts == 1` and the chorus body is missing, the slide is re-rendered in local repeat-mode: the verse is shown with no trailing `*`, followed by the chorus with no `Chorus:` label. (Equivalent to turning dedup off for that one slide.)
- **General case** — the missing chorus section(s) are inserted alongside the slide's existing content (in source order) and the slide is re-packed. If the extra content no longer fits, the packer spills into an additional slide.

### Section rendering on slides

**Chinese slides** (`_add_chinese_slides`): each display section is rendered via `render_section(section, config, section_label=labels[i], trailing_asterisks=trailing_asts[i])`. The chorus label is baked into the top of the PIL image.

**English slides** (`_add_english_slides`): the chorus label is prepended as a paragraph in the native pptx text box; trailing asterisks are appended to the text of the last paragraph in the section.

**Verse numbers**: only sections with `type == 'verse'` and a non-`None` `number` get a verse-number text box. Chorus, bridge, and refrain sections render flush (no number box).

### `build_presentation(song, config) → bytes`

Convenience wrapper that creates a fresh `Presentation`, calls `_add_chinese_slides` or `_add_english_slides`, and returns `.pptx` bytes.

### `build_deck(song_configs, global_config) → bytes`

Accepts a list of `(Song, overrides_dict)` pairs. For each song, calls `apply_config_overrides(global_config, overrides)` then dispatches to the appropriate slide builder. Returns combined `.pptx` bytes.

### `apply_config_overrides(base_config, overrides) → SlideConfig`

Shallow-copies `base_config`, then applies string-valued overrides from the dict, casting to the appropriate type.

---

## Chinese Slide Building

### Rendering

Sections are pre-processed by `_compute_display_info` (chorus dedup + asterisk/label metadata), then each display section is rendered to an RGBA PIL image via `render_section(section, config, section_label, trailing_asterisks)`. Image width is content-determined; height is proportional to line count plus any label row.

### Column packing — `_pack_into_columns`

Uses `_best_pack_slide` recursively to determine how many verses go into each column of each slide.

**Algorithm** (`_best_pack_slide`):
1. Compute `max_col0` = max verses fitting in column 0 at legibility threshold.
2. For `k` in `1..max_col0`, recursively compute optimal packing for remaining `n_cols - 1` columns.
3. Choose `k` that maximises total verses on the slide; break ties by choosing the smallest `k` (puts fewer verses in earlier columns, keeping similar-sized verses grouped in later columns).

**Legibility check** (`_max_fit_in_col`): a verse fits in a column with `R` rows if:

```
ch_px * min(img_w / img.width, row_h / img.height) >= _MIN_CHAR_H_IN
```

where `ch_px` is the actual rendered character height in pixels (from `char_height_px()`), `img_w` is the available column width in inches, and `row_h = (_CONTENT_H - _ROW_GAP * (R-1)) / R`.

### Uniform scaling

All verse images on one slide are scaled by a single factor so text is the same size throughout. The scale is `min(img_w / img.width, row_h / img.height)` across all verses, using each verse's own column row height.

---

## English Slide Building

### Single text box per slide

Sections are pre-processed by `_compute_display_info` before packing. All display sections on a slide are placed in **one native pptx text box** (not a PIL image). Sections are separated by blank-line paragraphs. Verse numbers are embedded as `"N. "` at the start of the first line of numbered verses. Chorus sections prepend their label (`"* Chorus:"`) as a paragraph, and trailing asterisks are appended to the last line of the preceding section.

`tf.word_wrap = True` ensures lines that exceed the box width wrap rather than overflow. The text box has PowerPoint's "Shrink text on overflow" (`<a:normAutofit/>`) enabled so that if the computed font size is still too large after wrapping, PowerPoint scales the text down at display time rather than overflowing the bottom of the slide.

### Column auto-detection

If `config.columns > 1`, the builder checks whether the longest line (by character count) would fit in a 2-column layout at `_MIN_ENGLISH_PT`:

```
line_w_in = max_chars * _MIN_ENGLISH_PT * _ENGLISH_CHAR_W / 72
two_col_w = (_CONTENT_W - _COL_GAP) / 2
```

If `line_w_in <= two_col_w`, use `min(2, config.columns)` columns; otherwise use 1.

### Packing — `_pack_english_slide`

Total line count for a column group = `sum(len(v.lines) for v in group) + (n_verses - 1)` (blank separator lines included). A group fits if the resulting font size ≥ `_MIN_ENGLISH_PT`:

```
font_pt = _CONTENT_H * 72 / (total_lines * _ENGLISH_LINE_H)
```

Same recursive best-split algorithm as Chinese packing.

### Font size — `_compute_english_col_font_pt`

```
font_pt = clamp(_CONTENT_H * 72 / (total_lines * _ENGLISH_LINE_H),
                _MIN_ENGLISH_PT, _MAX_ENGLISH_PT)
```

Because `_CONTENT_H` is constant and the formula is purely a function of `total_lines`, **slides with the same verse-line composition always get the same font size** — ensuring visual consistency across repeated verse types (e.g., two slides each showing one 6-line verse).

### English font constants

| Constant | Value | Description |
|----------|-------|-------------|
| `_MIN_ENGLISH_PT` | 28 | Minimum legible font size |
| `_MAX_ENGLISH_PT` | 40 | Maximum font size cap |
| `_ENGLISH_LINE_H` | 1.35 | Line height = font_pt × this factor |
| `_ENGLISH_CHAR_W` | 0.52 | Avg char width = font_pt × this / 72 in |

Line spacing is set explicitly on each paragraph: `p.line_spacing = Pt(font_pt * _ENGLISH_LINE_H)`.

---

## CLI — `generate.py`

```
python3 generate.py LYRICS_FILE [options]
```

The positional `LYRICS_FILE` argument is a lyrics file with one or more `[song]` blocks. A single-song lyrics file is just a file with one block.

### Options

```
-o / --output FILE     Output .pptx (default: slides.pptx)
--pinyin-font PATH     Pinyin font path (default: BarlowSemiCondensed-Regular.ttf)
--pinyin-font-index N  Font index in .ttc (default: 0)
--char-font PATH       Character font path (default: PingFang SC in PingFang.ttc)
--char-font-index N    Font index in .ttc (default: 3)
--pinyin-size N        Pinyin render size in pixels (default: 68)
--char-size N          Character render size in pixels (default: 96)
--text-color HEX       Text colour (default: #000000)
--columns N            Columns per slide (default: 2)
--rows N               Verse rows per column (default: auto)
--max-lines N          Max lines per verse (default: 8)
```

---

## Scraper — `scrape_lyrics.py`

Fetches lyrics from `churchofjesuschrist.org` music pages and produces a lyrics file and/or `.pptx`.

```
python3 scrape_lyrics.py links.txt                       # write lyrics only
python3 scrape_lyrics.py links.txt --slides              # also build slides
python3 scrape_lyrics.py links.txt -l lyrics.txt -o worship.pptx
```

### Links file format

One URL per line; blank lines and `#` comments ignored. Example:

```
# Keep the Commandments / 遵守神的誡命
https://www.churchofjesuschrist.org/media/music/songs/keep-the-commandments-wolford?lang=zho
https://www.churchofjesuschrist.org/media/music/songs/keep-the-commandments-wolford?lang=cmn-latn
https://www.churchofjesuschrist.org/media/music/songs/keep-the-commandments-wolford?lang=eng
```

### URL grouping

URLs sharing the same path (different `lang=` parameter only) are grouped into one song:
- `lang=zho` (Traditional Chinese) + `lang=cmn-latn` (Pinyin romanisation) → one Chinese/Pinyin entry
- `lang=eng` (English) → one English entry

Entry order follows the order languages first appear in the input file.

### Data extraction

The page embeds song data as `window.renderData={...}` (a JSON object in the page's `<script>` block). Extracted with `json.JSONDecoder().raw_decode()` starting from the marker position.

**TLS fallback**: `fetch_song_data` first attempts a plain `requests.get`. If the connection is reset (Akamai TLS fingerprint blocking), it automatically retries using Playwright with an installed Chrome/Chromium browser. Playwright must be installed (`pip install playwright`) and a browser must be available (either via `playwright install chromium` or a system Chrome at `/Applications/Google Chrome.app`).

Relevant path: `renderData.data.songData.verses[]`

Each verse object:
- `verseType`: `"Verse"` | `"Chorus"` | `"Refrain"` | `"Bridge"` | `"Instructions"`
- `verseNumber`: integer (0 for non-numbered types)
- `verseBody`: HTML string with `<p data-aid="..." data-pid="...">text</p><br><br><p>...</p>` structure

### Section rendering rules

| verseType | Handling |
|-----------|----------|
| `Verse` | `verseNumber` prefixed as `"N. "` on first line |
| `Chorus` | `Chorus:` tag line inserted before content |
| `Refrain` | `Refrain:` tag line inserted before content |
| `Bridge` | `Bridge:` tag line inserted before content |
| `Instructions` | Discarded (performance notes, footnotes) |

All occurrences of chorus/refrain/bridge are emitted into the lyrics file — deduplication is handled by the slidebuilder (see `_compute_display_info`).

HTML is parsed with BeautifulSoup (`html.parser`). Each `<p>` element is one lyric line; `<br>` inside a `<p>` splits into sub-lines. Encoding is forced to UTF-8 (`resp.content.decode('utf-8')`).

### Lyrics output for scraped songs

Chinese song entry:
```
[song]
columns: 2

[chinese]
…

[pinyin]
…
```

English song entry:
```
[song]
language: english

[english]
…
```

---

## Dependencies

| Package | Use |
|---------|-----|
| `Pillow` | PNG rendering (verse images) |
| `python-pptx` | PowerPoint file assembly |
| `pypinyin` | Auto-generation of pinyin from Chinese text |
| `requests` | HTTP fetching in scraper |
| `beautifulsoup4` | HTML parsing in scraper |
| `playwright` | Headless Chrome fallback for TLS-blocked scraping (optional) |

System requirements:
- macOS (PingFang SC font path is macOS-specific; can be overridden with `--char-font`)
- Barlow Semi Condensed Regular installed in `~/Library/Fonts/` (can be overridden with `--pinyin-font`)

---

## Known Quirks & Design Notes

1. **Barlow missing glyphs**: Barlow Semi Condensed lacks precomposed `ǐ ǒ ǖ ǘ ǚ ǜ ǹ`. These are rendered by combining a base letter (dotless-ı for `ǐ`, plain vowel otherwise) with a pixel-extracted combining mark image from a known-good NFC reference pair (`ǎ`/`a`).

2. **`prefix_advance` correction**: In multi-character pinyin syllables (e.g., "wǒ"), the mark must be positioned over the correct base letter, not the start of the full render string. `prefix_advance = font.getlength(prefix_str)` corrects for the width of preceding characters.

3. **`char_height_px` vs nominal size**: The actual rendered character height (measured from PingFang SC font metrics) differs from `config.char_font_size` due to font-specific metrics. The packing algorithm uses the measured value to avoid over-packing.

4. **Column width for partial slides**: if the last slide of a song has fewer populated columns than `n_cols`, the column width is recomputed using the actual populated count (`len(slide_cols)`) so text boxes use the full available width.

5. **English font size consistency**: Because `font_pt` is a pure function of `total_lines` and `_CONTENT_H`, slides with identical verse-line counts always receive the same font size, ensuring visual consistency across repeated structures (e.g., two consecutive 6-line verse slides).
