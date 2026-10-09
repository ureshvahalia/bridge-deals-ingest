"""Tests for Play normalisation and PlayDD play analysis."""

import csv
import shutil
import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

pytest.importorskip("playdd")

from lin_parse import parse_lin_file  # noqa: E402
from play_analysis import create_play_analysis, normalize_db, normalize_play_column, repair_plays  # noqa: E402

# 20th European Champions Cup, board 8 (also in PlayDD's test data): 3NT by S
HANDS = "W:Q3.K875.T.JT9632 KT7.4.AKJ8732.A8 J96.QJ932.Q965.7 A8542.AT6.4.KQ54"
PLAY = "CJ-C8-C7-CK-D4-DT-DA-D5-DK-D6-H6-H5-CA-H3-C4-C2-SK-S6-S2-S3-ST-SJ-SA-SQ-S8-C3-S7-S9".split("-")
# The same play as ingest's PBN parser stores it: seat columns from the leader (W N E S)
PBN = ("CJ-C8-C7-CK, DT-DA-D5-D4, H5-DK-D6-H6, C2-CA-H3-C4, S3-SK-S6-S2, "
       "SQ-ST-SJ-SA, C3-S7-S9-S8")


def frame(plays, contract="3N", declarer="S"):
    return pl.DataFrame({"Play": plays, "Hands": [HANDS] * len(plays),
                         "Contract": [contract] * len(plays), "Declarer": [declarer] * len(plays)})


class TestNormalize:
    def test_encodings(self):
        df = normalize_play_column(frame([
            "_".join(PLAY), "-".join(PLAY), PBN,
            "".join(PLAY[:4]) + "_" + "".join(PLAY[4:]),    # LIN tokens with cards run together
            "", "SX-SY",
        ]))
        expected = "_".join(PLAY)
        assert df["Play"].to_list() == [expected, expected, expected, expected, "", "SX-SY"]
        assert df["PlayEncoding"].to_list() == ["order", "order", "pbn", "order", "", "bad"]

    def test_pbn_without_contract_is_kept(self):
        df = normalize_play_column(frame([PBN], contract="", declarer=""))
        assert df.row(0, named=True)["Play"] == PBN and df["PlayEncoding"][0] == "pbn_raw"

    def test_idempotent(self):
        once = normalize_play_column(frame([PBN]))
        twice = normalize_play_column(once.drop("PlayEncoding"))
        assert twice["Play"].to_list() == once["Play"].to_list()


def test_create_play_analysis(tmp_path):
    processed = pl.DataFrame({"BoardUID": [1, 2, 3], "DealUID": [7, 7, 7], "Contract": ["3N", "3N", "AP"],
                              "Declarer": ["S", "S", None], "TricksMade": [10, None, None]})
    boards = pl.DataFrame({"BoardUID": [1, 2, 3], "Play": [PBN, "_".join(PLAY[:4]), ""],
                           "Claim": [10, None, None]})
    deals = pl.DataFrame({"DealUID": [7], "Hands": [HANDS]})
    stats = create_play_analysis(processed, boards, deals, tmp_path, workers=1)
    assert stats["statuses"] == {"ok": 2, "passed_out": 1} and stats["positions_rows"] == 32
    summary = {r["id"]: r for r in csv.DictReader(open(tmp_path / "play" / "summary.csv"))}
    assert summary["1"]["lead_loss"] == "2" and summary["1"]["end_difference"] == "0"
    assert summary["1"]["claim"] == "10" and summary["1"]["decisions_decl"] == "11"
    assert summary["2"]["stop_reason"] == "stopped_early" and summary["3"]["status"] == "passed_out"
    assert (tmp_path / "play" / "cards.csv").exists() and (tmp_path / "play" / "positions.csv").exists()


def test_normalize_db(tmp_path):
    # An ingest DB from before normalisation: PBN seat columns; board 2 has no
    # contract of its own, only the validated one in ProcessedBoards.
    pl.DataFrame({"BoardUID": ["1", "2", "3"], "DealUID": ["7", "7", "7"], "TableID": ["O", "C", "X"],
                  "Contract": ["3N", None, "AP"], "Declarer": ["S", None, None], "Lead": ["CJ", "CJ", None],
                  "Play": [PBN, PBN, None], "BiddingMD": ["", "", ""]}).write_csv(tmp_path / "boards.csv")
    pl.DataFrame({"DealUID": ["7"], "Hands": [HANDS]}).write_csv(tmp_path / "deals.csv")
    pl.DataFrame({"BoardUID": ["1", "2", "3"], "Contract": ["3N", "3N", "AP"],
                  "Declarer": ["S", "S", None]}).write_csv(tmp_path / "ProcessedBoards.csv")
    pl.DataFrame({"BoardUID": ["2", "1", "3"], "Hands": [HANDS] * 3, "Play": [PBN, PBN, None],
                  "Commentary": ["a", "b", "c"]}).write_csv(tmp_path / "all.csv")
    out = tmp_path / "out"
    stats = normalize_db(tmp_path, out)
    assert stats["boards"] == 3 and stats["all_rows"] == 3

    b = pl.read_csv(out / "boards.csv", infer_schema_length=0)
    assert b.columns == ["BoardUID", "DealUID", "TableID", "Contract", "Declarer", "Lead", "Play",
                         "PlayEncoding", "Claim", "BiddingMD"]
    assert b["Play"].to_list() == ["_".join(PLAY)] * 2 + [None]
    assert b["PlayEncoding"].to_list() == ["pbn", "pbn", None]
    assert b["Contract"].to_list() == ["3N", None, "AP"]          # other columns unchanged
    a = pl.read_csv(out / "all.csv", infer_schema_length=0)
    assert a["BoardUID"].to_list() == ["2", "1", "3"] and a["Commentary"].to_list() == ["a", "b", "c"]
    assert a["Play"].to_list()[:2] == ["_".join(PLAY)] * 2

    for name in ("deals", "ProcessedBoards"):
        shutil.copy(tmp_path / f"{name}.csv", out)
    normalize_db(out)                                               # idempotent, in place
    again = pl.read_csv(out / "boards.csv", infer_schema_length=0)
    assert again.equals(b.with_columns(pl.Series("PlayEncoding", ["order", "order", None])))


def test_rbn_rank_after_discard_follows_suit_led():
    from rbn_parse import parse_play
    # rpbridge S00.RBN board 2: in "SJQH47" the 7 follows spades after the H4 discard
    assert parse_play("SK8A4:C8A23:SJQH47:S9D3DTH3") == [
        "SK", "S8", "SA", "S4", "C8", "CA", "C2", "C3", "SJ", "SQ", "H4", "S7", "S9", "D3", "DT", "H3"]


def test_repair_plays(tmp_path, monkeypatch):
    from process_records import process_records
    from rbn_parse import parse_rbn_file

    fixture = Path(__file__).parent / "S00_part.rbn"      # first records of rpbridge S00.RBN
    db, out = tmp_path / "db", tmp_path / "out"
    db.mkdir()
    process_records(parse_rbn_file(fixture), False, db)

    # Recreate the old RBN parser's output: "SJQH47" read as SJ SQ H4 H7
    def corrupt(df):
        return df.with_columns(pl.col("Play").str.replace("SQ([-_])H4([-_])S7", "SQ${1}H4${2}H7"))
    for name in ("RawData", "all", "boards"):
        corrupt(pl.read_csv(db / f"{name}.csv", infer_schema_length=0)).write_csv(db / f"{name}.csv")
    before = {n: pl.read_csv(db / f"{n}.csv", infer_schema_length=0) for n in ("RawData", "all", "boards")}
    assert before["RawData"]["Play"].str.contains("H4-H7").sum() == 2

    monkeypatch.chdir(fixture.parent)
    stats = repair_plays(db, [fixture], out, reader=lambda paths: parse_rbn_file(paths[0]))
    assert stats["reparsed"] == stats["matched"] == len(before["RawData"]) and stats["play_changed"] == 2

    for name, frame_before in before.items():
        after = pl.read_csv(out / f"{name}.csv", infer_schema_length=0)
        others = [c for c in frame_before.columns if c not in ("Play", "PlayEncoding", "Claim")]
        assert after.select(others).equals(frame_before.select(others))
        assert not after["Play"].fill_null("").str.contains("H4.H7").any()
    raw_after = pl.read_csv(out / "RawData.csv", infer_schema_length=0)
    assert raw_after["Play"].str.contains("H4-S7").sum() == 2    # RawData keeps the parser's "-" form


@pytest.mark.parametrize("name,first,position,expected", [
    ("o27", 25, 2, 4),      # pairs file, open room only: rs has two entries per board
    ("c27", 25, 3, 5),
    ("o67", 64, 0, 6),      # file starts after the segment's first board
    ("o1", None, 3, 3),     # no vg| header: position in the file
    ("x0", 1, 5, 5),        # board name without room/number: position in the file
])
def test_lin_result_index(name, first, position, expected):
    from lin_parse import _result_index
    assert _result_index(name, first, position) == expected


def test_lin_claim_is_read():
    records = parse_lin_file(Path(__file__).parent / "68917.lin")
    assert any(r.Claim is not None for r in records)
    assert all(r.Claim is None or 0 <= r.Claim <= 13 for r in records)
