"""
Test candidate fonts for precomposed NFC pinyin coverage.
A font passes if every pinyin tone-marked vowel renders as a unique non-notdef glyph,
meaning unicodedata.normalize('NFC', text) alone is sufficient — no split rendering needed.
"""

import unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PINYIN_PRECOMPOSED = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ"

CANDIDATE_FONTS = [
    # Project fonts (in fonts/ directory)
    ("Saira Semi Condensed Regular",    "fonts/SairaSemiCondensed-Regular.ttf"),
    ("Saira Semi Condensed Medium",     "fonts/SairaSemiCondensed-Medium.ttf"),
    # User-installed fonts
    ("Barlow Semi Condensed Regular",   str(Path.home() / "Library/Fonts/BarlowSemiCondensed-Regular.ttf")),
    ("Barlow Semi Condensed Medium",    str(Path.home() / "Library/Fonts/BarlowSemiCondensed-Medium.ttf")),
    ("Roboto SemiCondensed Regular",    str(Path.home() / "Library/Fonts/Roboto_SemiCondensed-Regular.ttf")),
    ("Roboto SemiCondensed Medium",     str(Path.home() / "Library/Fonts/Roboto_SemiCondensed-Medium.ttf")),
    ("Roboto Condensed Regular",        str(Path.home() / "Library/Fonts/Roboto_Condensed-Regular.ttf")),
    ("Inter Regular (28pt)",            str(Path.home() / "Library/Fonts/Inter_28pt-Regular.ttf")),
    ("Inter Medium (28pt)",             str(Path.home() / "Library/Fonts/Inter_28pt-Medium.ttf")),
]


def notdef_pixels(font):
    """Pixel sum of .notdef (triggered by an unmapped char like a private-use codepoint)."""
    img = Image.new('L', (100, 100), 0)
    ImageDraw.Draw(img).text((10, 10), "\uE000", font=font, fill=255)
    return sum(img.getdata())


def check_font(name, path, size=60):
    p = Path(path)
    if not p.exists():
        return name, path, False, [], f"FILE NOT FOUND"

    try:
        font = ImageFont.truetype(path, size)
    except Exception as e:
        return name, path, False, [], str(e)

    notdef = notdef_pixels(font)
    missing = []

    for ch in PINYIN_PRECOMPOSED:
        img = Image.new('L', (100, 100), 0)
        ImageDraw.Draw(img).text((10, 10), ch, font=font, fill=255)
        px = sum(img.getdata())
        if px == 0 or px == notdef:
            missing.append(ch)

    ok = len(missing) == 0
    return name, path, ok, missing, ""


def render_sample(font_path, out_path, size=60):
    """Render a pinyin sample line with NFC normalization."""
    font = ImageFont.truetype(font_path, size)
    # A representative pinyin sentence with all four tones + ü tones
    sample = unicodedata.normalize('NFC',
        "nǐ hǎo  māma  wǒ ài nǐ  lǘ  ěr  ōu  yīng")
    w = int(font.getlength(sample)) + 20
    img = Image.new('RGB', (w, size + 20), (255, 255, 255))
    ImageDraw.Draw(img).text((10, 10), sample, font=font, fill=(0, 0, 0))
    img.save(out_path)
    print(f"  → Sample saved: {out_path}")


print("=" * 70)
print("Pinyin NFC coverage test")
print(f"Characters tested: {PINYIN_PRECOMPOSED}")
print("=" * 70)

passed = []
for name, path, ok, missing, err in [check_font(n, p) for n, p in CANDIDATE_FONTS]:
    status = "PASS ✓" if ok else ("SKIP" if "NOT FOUND" in err else "FAIL ✗")
    print(f"\n{status}  {name}")
    if err:
        print(f"       {err}")
    elif not ok:
        print(f"       Missing glyphs: {''.join(missing)}")
    if ok:
        passed.append((name, path))

print("\n" + "=" * 70)
if passed:
    print("Fonts with full NFC pinyin coverage (no split rendering needed):")
    for name, path in passed:
        print(f"  • {name}")
        render_sample(path, f"font_test_{name.replace(' ', '_')}.png")
else:
    print("No fonts passed. Split rendering fallback is still needed.")
print("=" * 70)
