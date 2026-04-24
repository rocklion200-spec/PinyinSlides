"""Tests for the column-packing algorithm in pinyin_slides.slidebuilder."""
from types import SimpleNamespace
from pinyin_slides.config import SlideConfig
from pinyin_slides.slidebuilder import (
    _best_pack_slide,
    _max_fit_in_col,
    _pack_into_columns,
    _CONTENT_H,
    _ROW_GAP,
    _MIN_CHAR_H_IN,
)


def _img(w, h):
    """Minimal mock of a PIL Image with .width and .height."""
    return SimpleNamespace(width=w, height=h)


def _config(**kwargs):
    cfg = SlideConfig.__new__(SlideConfig)
    # Bypass __post_init__ font resolution — not needed for packing tests
    cfg.columns = kwargs.get('columns', 2)
    cfg.rows_per_column = kwargs.get('rows_per_column', None)
    return cfg


# Fixed geometry used in tests: img_w=5", ch_px so one verse always fits,
# two never shrink below _MIN_CHAR_H_IN.
#
# _max_fit_in_col check: scale = min(img_w/img.width, row_h/img.height)
# ch_px * scale >= _MIN_CHAR_H_IN
# Use a short wide image so width is never the limiting factor.
_IMG_W = 5.0   # inches
_CH_PX = 96    # render char height in pixels

# An image that fits alone but fills one row entirely.
# row_h for 1 verse = _CONTENT_H
# scale = _CONTENT_H / img_h  →  ch_px * scale >= _MIN_CHAR_H_IN
# img_h <= ch_px * _CONTENT_H / _MIN_CHAR_H_IN
_MAX_H = int(_CH_PX * _CONTENT_H / _MIN_CHAR_H_IN)

# A "small" verse (fits many per column)
_SMALL = _img(_IMG_W * 100, _MAX_H // 6)
# A "medium" verse (fits ~2 per column)
_MED   = _img(_IMG_W * 100, _MAX_H // 2)
# A "tall" verse (barely fits alone)
_TALL  = _img(_IMG_W * 100, _MAX_H - 1)


# ── _max_fit_in_col ───────────────────────────────────────────────────────────

def test_max_fit_single_tall_verse():
    imgs = [_TALL]
    cfg = _config()
    assert _max_fit_in_col(imgs, cfg, _IMG_W, _CH_PX, 0, 1, None) == 1


def test_max_fit_multiple_small_verses():
    imgs = [_SMALL] * 6
    cfg = _config()
    count = _max_fit_in_col(imgs, cfg, _IMG_W, _CH_PX, 0, 6, None)
    assert count >= 3  # at least 3 small verses should fit


def test_max_fit_respects_max_rows():
    imgs = [_SMALL] * 6
    cfg = _config(rows_per_column=2)
    count = _max_fit_in_col(imgs, cfg, _IMG_W, _CH_PX, 0, 6, max_rows=2)
    assert count == 2


def test_max_fit_start_offset():
    imgs = [_TALL, _SMALL, _SMALL, _SMALL]
    cfg = _config()
    # Starting after the tall verse, small ones should fit more
    count_from_0 = _max_fit_in_col(imgs, cfg, _IMG_W, _CH_PX, 0, 4, None)
    count_from_1 = _max_fit_in_col(imgs, cfg, _IMG_W, _CH_PX, 1, 4, None)
    assert count_from_1 > count_from_0


# ── _best_pack_slide ──────────────────────────────────────────────────────────

def test_pack_empty():
    assert _best_pack_slide([], _config(), _IMG_W, _CH_PX, 0, 0, 2, None) == []


def test_pack_single_verse_two_cols():
    imgs = [_SMALL]
    result = _best_pack_slide(imgs, _config(columns=2), _IMG_W, _CH_PX, 0, 1, 2, None)
    # One verse in first column, second column empty
    assert sum(len(c) for c in result) == 1
    assert result[0] == [0]


def test_pack_prefers_balanced_columns():
    """Equal-total splits should balance across columns."""
    imgs = [_SMALL, _SMALL]
    result = _best_pack_slide(imgs, _config(columns=2), _IMG_W, _CH_PX, 0, 2, 2, None)
    total = sum(len(c) for c in result)
    assert total == 2
    # Balanced split preferred over filling only the left column.
    assert result[0] == [0]
    assert result[1] == [1]


def test_pack_balanced_three_sections():
    """3 sections in 2 cols should split 2+1 (larger k when diffs tie)."""
    imgs = [_SMALL, _SMALL, _SMALL]
    result = _best_pack_slide(imgs, _config(columns=2), _IMG_W, _CH_PX, 0, 3, 2, None)
    assert result[0] == [0, 1]
    assert result[1] == [2]


def test_pack_forces_tall_verse():
    """A verse too tall to share a column must still be placed (no infinite loop)."""
    # Two tall verses: each needs the full column height
    imgs = [_TALL, _TALL]
    result = _best_pack_slide(imgs, _config(columns=2), _IMG_W, _CH_PX, 0, 2, 2, None)
    total = sum(len(c) for c in result)
    assert total >= 1  # at least one placed


def test_pack_start_offset():
    imgs = [_SMALL, _MED, _SMALL]
    result = _best_pack_slide(imgs, _config(columns=2), _IMG_W, _CH_PX, 1, 3, 2, None)
    # Only indices 1 and 2 should appear
    all_idxs = [vi for col in result for vi in col]
    assert 0 not in all_idxs
    assert all(i in (1, 2) for i in all_idxs)


# ── _pack_into_columns ────────────────────────────────────────────────────────

def test_pack_into_columns_all_placed():
    imgs = [_SMALL] * 4
    cfg = _config(columns=2)
    slides = _pack_into_columns(imgs, cfg, _IMG_W, _CH_PX)
    total = sum(len(vi) for slide in slides for col in slide for vi in [col])
    assert total == 4


def test_pack_into_columns_index_coverage():
    """Every verse index must appear exactly once across all slides."""
    imgs = [_SMALL, _MED, _TALL, _SMALL, _MED]
    cfg = _config(columns=2)
    slides = _pack_into_columns(imgs, cfg, _IMG_W, _CH_PX)
    all_idxs = [vi for slide in slides for col in slide for vi in col]
    assert sorted(all_idxs) == list(range(len(imgs)))


def test_pack_into_columns_respects_rows_per_column():
    imgs = [_SMALL] * 8
    cfg = _config(columns=2, rows_per_column=2)
    slides = _pack_into_columns(imgs, cfg, _IMG_W, _CH_PX)
    for slide in slides:
        for col in slide:
            assert len(col) <= 2


def test_pack_single_column():
    imgs = [_SMALL, _SMALL, _SMALL]
    cfg = _config(columns=1)
    slides = _pack_into_columns(imgs, cfg, _IMG_W, _CH_PX)
    all_idxs = [vi for slide in slides for col in slide for vi in col]
    assert sorted(all_idxs) == [0, 1, 2]


# ── _place_chorus_on_slide ───────────────────────────────────────────────────

from pinyin_slides.slidebuilder import _place_chorus_on_slide


def test_place_chorus_col0_bottom_when_fits():
    """Chorus appended to col 0 when there's room."""
    fits = lambda cols: True  # everything fits
    verse_cols = [[10, 11], [12, 13]]
    cand, ok = _place_chorus_on_slide(verse_cols, 99, fits, n_cols=2)
    assert ok
    assert cand == [[10, 11, 99], [12, 13]]


def test_place_chorus_col1_top_when_col0_full():
    """When col 0 is too full for chorus, chorus becomes first in col 1
    and verses are pulled back to col 0 if they fit there."""
    # Reject when chorus is at col 0 bottom; accept anywhere else.
    def fits(cols):
        if len(cols) >= 1 and cols[0] and cols[0][-1] == 99:
            return False  # chorus at col 0 bottom: reject
        return True
    verse_cols = [[10, 11], [12, 13]]
    cand, ok = _place_chorus_on_slide(verse_cols, 99, fits, n_cols=2)
    assert ok
    # All verses pulled to col 0, chorus alone in col 1.
    assert cand == [[10, 11, 12, 13], [99]]


def test_place_chorus_col1_alone_when_col0_overflows_with_pulled_verses():
    """When even pulling all verses to col 0 doesn't fit, partial pull-back
    with chorus + remaining in col 1."""
    def fits(cols):
        # Reject any layout where col 0 has > 2 entries or chorus is in col 0.
        if cols[0] and cols[0][-1] == 99:
            return False
        if len(cols[0]) > 2:
            return False
        return True
    verse_cols = [[10, 11], [12, 13]]
    cand, ok = _place_chorus_on_slide(verse_cols, 99, fits, n_cols=2)
    assert ok
    assert cand == [[10, 11], [99, 12, 13]]


def test_place_chorus_falls_back_to_col1_bottom():
    """If chorus can't go at col 1 top in any configuration, try col 1 bottom."""
    def fits(cols):
        if cols[0] and cols[0][-1] == 99:
            return False
        if len(cols) > 1 and cols[1] and cols[1][0] == 99:
            return False  # reject col 1 top
        return True
    verse_cols = [[10], [11]]
    cand, ok = _place_chorus_on_slide(verse_cols, 99, fits, n_cols=2)
    assert ok
    assert cand == [[10], [11, 99]]


def test_place_chorus_single_column():
    """In single-column layouts, chorus appends to the only column."""
    fits = lambda cols: True
    verse_cols = [[10, 11, 12]]
    cand, ok = _place_chorus_on_slide(verse_cols, 99, fits, n_cols=1)
    assert ok
    assert cand == [[10, 11, 12, 99]]


def test_place_chorus_returns_failure_when_nothing_fits():
    """If no insertion point fits, return success=False."""
    fits = lambda cols: False
    verse_cols = [[10, 11], [12, 13]]
    cand, ok = _place_chorus_on_slide(verse_cols, 99, fits, n_cols=2)
    assert not ok
