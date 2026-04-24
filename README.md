# PinyinSlides

Generates 16:9 PowerPoint decks for projecting worship lyrics with pinyin above Chinese characters. Supports Chinese songs (pinyin-over-character image rendering) and English songs (native text boxes).

## Install

```bash
pip install -r requirements.txt
```

Bundled fonts in `fonts/` are used by default. To use a different font pass `--pinyin-font` / `--char-font`.

## Usage

### Build from a lyrics file

```bash
python3 generate.py test_data/keximani_deck.txt -o worship.pptx
```

A lyrics file can contain any number of `[song]` blocks — use a single block for a single song.

### Scrape lyrics from churchofjesuschrist.org

```bash
# Write lyrics only:
python3 scrape_lyrics.py test_data/sample_links.txt
# Also build slides:
python3 scrape_lyrics.py test_data/sample_links.txt --slides
```

## Lyrics file format

See `test_data/keximani_deck.txt` for a full example. Each song block looks like:

```
[song]
columns: 2

[chinese]
我時時需要主

1. 我時時需要主，慈悲之神；
聲音溫柔無比，令我安寧。

Chorus:
需要主我需要主；時時刻刻要主，
如今求主祝福我，我來就主！

2. 我時時需要主，在主跟前；

[pinyin]
Wǒ shíshí xūyào Zhǔ

1. Wǒ shí­shí xū­yào Zhǔ, cí­bēi zhī Shén;
Shēng­yīn wēn­róu wú­bǐ, lìng wǒ ān­níng.

Chorus:
Xū­yào Zhǔ wǒ xū­yào Zhǔ; shí­shí­kè­kè yào Zhǔ,
Rú­jīn qiú Zhǔ zhù­fú wǒ, wǒ lái jiù Zhǔ!

2. Wǒ shí­shí xū­yào Zhǔ, zài Zhǔ gēn­qián;
```

Section type tags (`Chorus:`, `Bridge:`, `Refrain:`) mark non-verse blocks. The slidebuilder automatically:
- Shows the chorus once per song (deduplicating repeated occurrences)
- Labels it `* Chorus 副歌:` on Chinese slides or `* Chorus:` on English slides
- Appends ` *` to the last line of each section that is followed by the chorus in source order (` * *` if the chorus repeats twice)

English songs use `[english]` instead of `[chinese]` / `[pinyin]`:

```
[song]
language: english

[english]
Keep the Commandments

1. Keep the commandments; keep the commandments!
In this there is safety; in this there is peace.

Chorus:
Keep the commandments.
In this there is safety and peace.
```

## Options

Run `python3 generate.py --help` or `python3 scrape_lyrics.py --help` for all options.

See [SPEC.md](SPEC.md) for the full design specification including the data model, rendering algorithm, and lyrics file format reference.
