"""Render pinyin-over-character text as transparent PNG images using Pillow."""

import unicodedata
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from .config import SlideConfig, Section, Line, Word


# ── Pinyin glyph rendering ────────────────────────────────────────────────────

# All precomposed tone-marked vowels used in Mandarin pinyin
_PINYIN_PRECOMPOSED = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ"

# Reference NFC pairs used to extract combining mark images.
# Each mark lists candidates in priority order; the first pair whose nfc_char
# the font actually supports (i.e., doesn't render as notdef) is used.
_MARK_REFS = {
    '\u030c': [('ě', 'e'), ('š', 's'), ('č', 'c'), ('ž', 'z'), ('ǎ', 'a')],  # caron
    '\u0304': [('ā', 'a'), ('ē', 'e'), ('ō', 'o')],                           # macron
    '\u0301': [('á', 'a'), ('é', 'e'), ('ó', 'o')],                           # acute
    '\u0300': [('à', 'a'), ('è', 'e'), ('ò', 'o')],                           # grave
    '\u0308': [('ä', 'a'), ('ë', 'e'), ('ö', 'o')],                           # diaeresis
}

# Pixel-center of base letters relative to draw origin (measured at runtime)
_BASE_CX_CACHE = {}


def _pixel_cx(img: Image.Image, dx: int, W: int, H: int, threshold: int = 10) -> float:
    """Weighted horizontal pixel center of an image, relative to draw x."""
    cols = []
    data = list(img.getdata())
    for x in range(W):
        col_sum = sum(data[y * W + x] for y in range(H) if data[y * W + x] > threshold)
        cols.append(col_sum)
    total = sum(cols)
    return (sum(x * cols[x] for x in range(W)) / total - dx) if total else 0.0


def _extract_mark_image(font: ImageFont.FreeTypeFont,
                        nfc_char: str, base_char: str) -> tuple:
    """Extract a combining mark as a standalone image from an NFC reference pair."""
    W, H, DX, DY = 300, 200, 80, 100

    def render(text):
        img = Image.new('L', (W, H), 0)
        ImageDraw.Draw(img).text((DX, DY), text, font=font, fill=255)
        return img

    img_base = render(base_char)
    img_full = render(nfc_char)
    mark_data = [max(0, int(b) - int(a))
                 for a, b in zip(img_base.getdata(), img_full.getdata())]
    img_mark = Image.new('L', (W, H), 0)
    img_mark.putdata(mark_data)

    # Erase any mark pixels at or below the base character's top edge — these
    # are anti-aliasing body differences, not part of the diacritic above.
    base_bbox = img_base.getbbox()
    if base_bbox:
        base_top = base_bbox[1]
        mark_arr = list(img_mark.getdata())
        for idx in range(base_top * W, H * W):
            mark_arr[idx] = 0
        img_mark.putdata(mark_arr)

    bbox = img_mark.getbbox()
    if not bbox:
        return None, 0, 0

    crop = img_mark.crop(bbox)
    cx_rel   = (bbox[0] + bbox[2]) / 2 - DX
    y_top_rel = bbox[1] - DY
    return crop, cx_rel, y_top_rel


def _measure_base_cx(font: ImageFont.FreeTypeFont, base_char: str) -> float:
    """Return the weighted horizontal pixel center of base_char relative to draw x."""
    key = (id(font), base_char)
    if key in _BASE_CX_CACHE:
        return _BASE_CX_CACHE[key]
    W, H, DX, DY = 300, 200, 80, 100
    img = Image.new('L', (W, H), 0)
    ImageDraw.Draw(img).text((DX, DY), base_char, font=font, fill=255)
    cx = _pixel_cx(img, DX, W, H)
    _BASE_CX_CACHE[key] = cx
    return cx


def _notdef_pixels(font: ImageFont.FreeTypeFont) -> int:
    """Pixel sum of the font's .notdef box (triggered by a CJK character)."""
    img = Image.new('L', (100, 100), 0)
    ImageDraw.Draw(img).text((10, 10), "我", font=font, fill=255)
    return sum(img.getdata())


def _build_render_map(font: ImageFont.FreeTypeFont) -> dict:
    """Build a char → render-spec map for all precomposed pinyin characters."""
    notdef = _notdef_pixels(font)

    mark_cache = {}

    def get_mark(combining_char):
        if combining_char not in mark_cache:
            candidates = _MARK_REFS.get(combining_char, [])
            result = (None, 0, 0)
            for nfc_char, base_char in candidates:
                # Skip this candidate if nfc_char isn't in the font
                probe = Image.new('L', (100, 100), 0)
                ImageDraw.Draw(probe).text((10, 10), nfc_char, font=font, fill=255)
                if sum(probe.getdata()) == notdef:
                    continue
                result = _extract_mark_image(font, nfc_char, base_char)
                if result[0] is not None:
                    break
            mark_cache[combining_char] = result
        return mark_cache[combining_char]

    render_map = {}
    for ch in _PINYIN_PRECOMPOSED:
        img = Image.new('L', (100, 100), 0)
        ImageDraw.Draw(img).text((10, 10), ch, font=font, fill=255)
        if sum(img.getdata()) != notdef:
            render_map[ch] = ch
            continue

        nfd = unicodedata.normalize('NFD', ch)
        marks     = [c for c in nfd if unicodedata.category(c)[0] == 'M']
        base_str  = ''.join(c for c in nfd if unicodedata.category(c)[0] != 'M')
        base_draw = base_str.replace('i', '\u0131')

        primary_mark = marks[-1] if marks else None
        mark_img, _, mark_y = get_mark(primary_mark) if primary_mark else (None, 0, 0)

        if mark_img is not None:
            base_cx = _measure_base_cx(font, base_draw)
            render_map[ch] = {
                'kind'    : 'split',
                'base'    : base_draw,
                'base_cx' : base_cx,
                'mark_img': mark_img,
                'mark_y'  : mark_y,
            }
        else:
            render_map[ch] = nfd.replace('i', '\u0131')

    return render_map


def _apply_render_map(text: str, render_map: dict) -> str:
    """Return the NFC/NFD render string for width-measurement purposes."""
    parts = []
    for ch in text:
        spec = render_map.get(ch, ch)
        if isinstance(spec, dict):
            parts.append(spec['base'])
        else:
            parts.append(spec)
    return ''.join(parts)


# ── Font loading ──────────────────────────────────────────────────────────────

def _load_fonts(config: SlideConfig):
    """Load pinyin and character fonts; build the pinyin render map."""
    pinyin_font = ImageFont.truetype(config.pinyin_font_path, config.pinyin_font_size,
                                     index=config.pinyin_font_index)
    char_font   = ImageFont.truetype(config.char_font_path, config.char_font_size,
                                     index=config.char_font_index)
    render_map  = _build_render_map(pinyin_font)
    return pinyin_font, char_font, render_map


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _row_height(font: ImageFont.FreeTypeFont, sample: str,
                render_map: dict = None) -> tuple[int, int]:
    """Return (ascent_offset, total_height) for a font using a reference string."""
    s = _apply_render_map(sample, render_map) if render_map else sample
    bbox = font.getbbox(s)
    return bbox[1], bbox[3] - bbox[1]


def _syllable_visual_w(pinyin: str, font: ImageFont.FreeTypeFont,
                       render_map: dict) -> tuple[float, float, object]:
    """Return (visual_width, left_bearing, spec) for a pinyin syllable."""
    render_str = _apply_render_map(pinyin, render_map)
    bbox = font.getbbox(render_str)
    visual_w = bbox[2] - bbox[0]
    left_bearing = bbox[0]
    return visual_w, left_bearing, render_str


def _token_visual_w(token, pinyin_font, char_font, render_map) -> float:
    """Visual pinyin width for word-gap calculations."""
    if token.is_punctuation:
        return char_font.getlength(token.char)
    if not token.pinyin:
        return 0
    vw, _, _ = _syllable_visual_w(token.pinyin, pinyin_font, render_map)
    return vw


# ── Line layout ───────────────────────────────────────────────────────────────

def _layout_line(line: Line, pinyin_font: ImageFont.FreeTypeFont,
                 char_font: ImageFont.FreeTypeFont, config: SlideConfig,
                 render_map: dict):
    """Compute per-token layout for a single line.

    Returns:
        units: list of (token, x_pos, unit_width)
        total_width: total line width in pixels
    """
    units = []
    x = 0
    for word_idx, word in enumerate(line.words):
        for token in word.tokens:
            if token.is_punctuation:
                cw = char_font.getlength(token.char)
                unit_w = cw + 4
                units.append((token, x, unit_w))
                x += unit_w
            else:
                pw, _, _ = (_syllable_visual_w(token.pinyin, pinyin_font, render_map)
                            if token.pinyin else (0, 0, ''))
                cw = char_font.getlength(token.char)
                unit_w = max(pw, cw) + config.intra_word_padding
                units.append((token, x, unit_w))
                x += unit_w

        if word_idx < len(line.words) - 1:
            last_tok, _, last_unit_w = units[-1]

            if not last_tok.is_punctuation:
                last_pw  = _token_visual_w(last_tok,  pinyin_font, char_font, render_map)
                first_tok = line.words[word_idx + 1].tokens[0]
                if first_tok.is_punctuation:
                    first_pw     = _token_visual_w(first_tok, pinyin_font, char_font, render_map)
                    first_unit_w = first_pw + 4
                else:
                    first_pw     = _token_visual_w(first_tok, pinyin_font, char_font, render_map)
                    first_cw     = char_font.getlength(first_tok.char)
                    first_unit_w = max(first_pw, first_cw) + config.intra_word_padding

                natural_gap = (last_unit_w - last_pw) / 2 + (first_unit_w - first_pw) / 2
                x += max(0, config.inter_word_gap - natural_gap)

    return units, x


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _parse_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_pinyin_token(img: Image.Image, draw: ImageDraw.ImageDraw,
                       pinyin: str, x_pos: float, unit_w: float, y_pinyin: float,
                       pinyin_font: ImageFont.FreeTypeFont, render_map: dict,
                       text_color: str):
    """Draw a single pinyin syllable centered in its unit cell."""
    rgb = _parse_rgb(text_color)

    split_spec  = None
    prefix_str  = ''
    render_str  = ''
    for ch in pinyin:
        spec = render_map.get(ch, ch)
        if isinstance(spec, dict):
            if split_spec is None:
                prefix_str = render_str
            split_spec  = spec
            render_str += spec['base']
        else:
            render_str += spec

    bbox         = pinyin_font.getbbox(render_str)
    visual_w     = bbox[2] - bbox[0]
    left_bearing = bbox[0]

    px = x_pos + (unit_w - visual_w) / 2 - left_bearing

    if split_spec is None:
        draw.text((px, y_pinyin), render_str, font=pinyin_font, fill=text_color)
    else:
        draw.text((px, y_pinyin), render_str, font=pinyin_font, fill=text_color)

        mark_img = split_spec['mark_img']
        base_cx  = split_spec['base_cx']
        mark_y   = split_spec['mark_y']

        prefix_advance = pinyin_font.getlength(prefix_str) if prefix_str else 0
        base_center_abs = px + prefix_advance + base_cx

        paste_x = int(round(base_center_abs - mark_img.width / 2))
        paste_y = int(round(y_pinyin + mark_y))

        mark_rgba = Image.new('RGBA', mark_img.size, rgb + (0,))
        mark_rgba.putalpha(mark_img)

        iw, ih = img.size
        if paste_x < iw and paste_y < ih and paste_x + mark_img.width > 0 and paste_y + mark_img.height > 0:
            img.alpha_composite(mark_rgba, dest=(max(0, paste_x), max(0, paste_y)))


# ── Section rendering ─────────────────────────────────────────────────────────

def render_section(section: Section, config: SlideConfig,
                   section_label: str = '',
                   trailing_asterisks: int = 0) -> Image.Image:
    """Render a single section as a transparent-background RGBA image.

    section_label: if set, rendered as a plain-text header line above the
        section content (used for chorus labels like '* Chorus 副歌:').
    trailing_asterisks: number of '*' characters appended after the last
        content line, indicating repeated choruses.
    """
    pinyin_font, char_font, render_map = _load_fonts(config)

    py_ascent, py_row_h = _row_height(pinyin_font, "ĀāÉéǑǒĪīŪūÜüygjpq", render_map)
    ch_ascent, ch_row_h = _row_height(char_font, "我國語")
    line_h = py_row_h + config.pinyin_char_gap + ch_row_h

    line_layouts = []
    max_width = 0
    for line in section.lines:
        units, total_w = _layout_line(line, pinyin_font, char_font, config, render_map)
        line_layouts.append((units, total_w))
        max_width = max(max_width, total_w)

    # Width for trailing asterisks appended to the last content line
    ast_text = ''
    if trailing_asterisks > 0 and line_layouts:
        ast_text = ' ' + ' '.join(['*'] * trailing_asterisks)
        ast_w = char_font.getlength(ast_text)
        last_total_w = line_layouts[-1][1]
        max_width = max(max_width, last_total_w + ast_w)

    # Width and height for the section label line (if any).
    # Use the full bbox of the actual label string so mixed ASCII + CJK (e.g.
    # "* Chorus 副歌:") measures correctly even when the char font lacks
    # complete ASCII glyphs.
    label_bbox = char_font.getbbox(section_label) if section_label else None
    if label_bbox:
        label_w = label_bbox[2] - label_bbox[0]
        label_full_h = label_bbox[3] - label_bbox[1]
        max_width = max(max_width, label_w)
    else:
        label_w = 0
        label_full_h = 0

    # Height: optional label row + top padding + lyric rows
    label_h = (label_full_h + config.line_spacing) if section_label else 0
    num_lines  = len(section.lines)
    img_width  = max(1, int(max_width) + 4)
    img_height = max(1,
        label_h
        + config.top_padding
        + num_lines * line_h
        + max(0, num_lines - 1) * config.line_spacing
    )

    img  = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    text_color = config.text_color

    y = 0

    # Draw section label (e.g. "* Chorus 副歌:") at the top of the image.
    if section_label:
        draw.text((0, y), section_label, font=char_font, fill=text_color)
        y += label_h

    y += config.top_padding

    for i, (units, line_total_w) in enumerate(line_layouts):
        y_pinyin = y - py_ascent
        y_char   = y + py_row_h + config.pinyin_char_gap - ch_ascent

        for token, x_pos, unit_w in units:
            if not token.is_punctuation and token.pinyin:
                _draw_pinyin_token(img, draw, token.pinyin, x_pos, unit_w,
                                   y_pinyin, pinyin_font, render_map, text_color)

            cw = char_font.getlength(token.char)
            cx = x_pos + (unit_w - cw) / 2
            draw.text((cx, y_char), token.char,
                      font=char_font, fill=text_color)

        # Trailing asterisks after the last content line
        if i == len(line_layouts) - 1 and ast_text:
            draw.text((line_total_w, y_char), ast_text,
                      font=char_font, fill=text_color)

        y += line_h + config.line_spacing

    return img


# Backward-compatible alias
render_verse = render_section


# ── Utilities ─────────────────────────────────────────────────────────────────

def char_height_px(config: SlideConfig) -> int:
    """Actual rendered character height in pixels — used by the slide packer."""
    _, char_font, _ = _load_fonts(config)
    _, ch_row_h = _row_height(char_font, "我國語")
    return ch_row_h


def verse_to_png_bytes(section: Section, config: SlideConfig) -> bytes:
    img = render_section(section, config)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
