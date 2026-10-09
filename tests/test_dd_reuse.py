"""Tests for reusing earlier double-dummy results (--reuse-dd)."""

import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

pytest.importorskip("endplay")

from dds_wrapper import DD_COLUMNS, create_dd_columns, load_dd_cache, reuse_dd_columns  # noqa: E402

HANDS = [
    "W:Q3.K875.T.JT9632 KT7.4.AKJ8732.A8 J96.QJ932.Q965.7 A8542.AT6.4.KQ54",
    "W:JT985.75.A3.QJT3 AK.Q83.QT5.AK652 7632.KJT9.J742.8 Q4.A642.K986.974",
]


def hands_frame():
    return pl.DataFrame({"HandUID": [1, 2, 3], "Dealer": ["N", "E", "N"], "Vulnerability": ["Z", "B", "N"],
                         "Hands": [HANDS[0], HANDS[1], HANDS[0]]})


def test_reuse_matches_fresh_computation(tmp_path):
    fresh = create_dd_columns(hands_frame())
    # earlier DB knew rows 1 and 2 only; row 3 (same hands, other vulnerability) must be computed
    fresh.filter(pl.col("HandUID") < 3).write_csv(tmp_path / "hands.csv")
    out = reuse_dd_columns(hands_frame(), load_dd_cache(tmp_path))
    assert out.columns == fresh.columns
    assert out.equals(fresh.with_columns([pl.col(c).cast(out.schema[c]) for c in DD_COLUMNS]))


def test_cached_values_are_used(tmp_path):
    fresh = create_dd_columns(hands_frame())
    fresh.with_columns(pl.lit(99).alias("DD_W_N")).write_csv(tmp_path / "hands.csv")   # mark as cached
    out = reuse_dd_columns(hands_frame(), load_dd_cache(tmp_path / "hands.csv"))
    assert out["DD_W_N"].to_list() == [99, 99, 99] and out["HandUID"].to_list() == [1, 2, 3]


def test_cache_needs_dd_columns(tmp_path):
    hands_frame().write_csv(tmp_path / "hands.csv")
    with pytest.raises(Exception):
        load_dd_cache(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_dd_cache(tmp_path / "missing")
