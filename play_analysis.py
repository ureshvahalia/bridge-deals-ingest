"""Card-by-card double-dummy play analysis, using PlayDD (E:\\BRIDGE\\DDSolver).

PlayDD is optional: install it with
    python -m pip install -e <path to DDSolver>
Without it, Play is left as recorded and play analysis is unavailable.

Two entry points:
- normalize_play_column(): rewrite Play as "_"-separated play order (PBN
  seat-column plays are reordered) and add PlayEncoding.
- create_play_analysis(): run PlayDD's batch over the boards and write
  <outdir>/play/{boards,positions,cards,summary}.csv, keyed by BoardUID.
"""
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import polars as pl


def _have_playdd() -> bool:
    try:
        import playdd  # noqa: F401
        return True
    except ImportError:
        return False


def _normalize_one(row: Dict[str, Any]) -> Dict[str, Optional[str]]:
    from playdd import ParseError, normalise_play, parse_contract, parse_deal

    text = row["Play"] or ""
    cards, encoding = normalise_play(text)
    if encoding == "pbn_raw":           # seat-column order: needs the deal and contract
        try:
            deal = parse_deal(row["Hands"] or "")
            contract = parse_contract(row["Contract"] or "", row["Declarer"] or None)
            if contract is not None:
                cards, encoding = normalise_play(text, deal, contract)
        except ParseError:
            pass
    if encoding in ("pbn_raw", "bad"):  # keep what was recorded
        return {"Play": text, "PlayEncoding": encoding}
    return {"Play": "_".join(cards), "PlayEncoding": encoding}


def normalize_play_column(df: pl.DataFrame) -> pl.DataFrame:
    """Rewrite Play in play order, "_"-separated; add PlayEncoding.

    PlayEncoding: "" no play, "order" recorded in play order, "pbn" reordered
    from PBN seat columns, "pbn_raw" PBN that could not be reordered (no
    contract/declarer; Play kept), "bad" unparseable (Play kept).
    Needs columns Play, Hands, Contract, Declarer. Idempotent.
    """
    if not _have_playdd():
        logging.warning("playdd not installed: Play left as recorded")
        return df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("PlayEncoding"))
    out = df.select(
        pl.struct(["Play", "Hands", "Contract", "Declarer"])
        .map_elements(_normalize_one, return_dtype=pl.Struct({"Play": pl.Utf8, "PlayEncoding": pl.Utf8}))
        .alias("_play")
    ).unnest("_play")
    counts = out.group_by("PlayEncoding").len().sort("PlayEncoding").rows()
    logging.warning(f"Play normalised: {dict(counts)}")
    return df.with_columns(out["Play"], out["PlayEncoding"])


def create_play_analysis(processed_boards: pl.DataFrame, boards: pl.DataFrame, deals: pl.DataFrame,
                         outdir: Path, depth: str = "full", workers: Optional[int] = None,
                         views: bool = True) -> Dict[str, Any]:
    """Analyse every board's play and write <outdir>/play/*.csv (id = BoardUID).

    processed_boards: validated Contract, Declarer, TricksMade (ProcessedBoards)
    boards: Play and Claim (boards.csv); deals: Hands (deals.csv).
    Play is normalised first, so a DB built before normalisation also works.
    Returns PlayDD's run statistics.
    """
    if not _have_playdd():
        raise RuntimeError("play analysis needs playdd: python -m pip install -e <path to DDSolver>")
    from playdd.batch import analyse_batch, write_results

    play_cols = ["BoardUID", "Play"] + (["Claim"] if "Claim" in boards.columns else [])
    df = (processed_boards.select(["BoardUID", "DealUID", "Contract", "Declarer", "TricksMade"])
          .join(boards.select(play_cols), on="BoardUID", how="left")
          .join(deals.select(["DealUID", "Hands"]), on="DealUID", how="left")
          .sort(["DealUID", "BoardUID"]))          # tables of a deal together: lead cache hits
    if "Claim" not in df.columns:
        df = df.with_columns(pl.lit(None).alias("Claim"))
    df = normalize_play_column(df.with_columns(pl.col("Play").cast(pl.Utf8).fill_null("")))

    records = ({"id": r["BoardUID"], "deal": r["Hands"] or "", "contract": r["Contract"] or "",
                "declarer": r["Declarer"], "play": r["Play"], "tricks_made": r["TricksMade"],
                "claim": r["Claim"], "result_source": "recorded" if r["TricksMade"] not in (None, "") else None}
               for r in df.iter_rows(named=True))
    logging.warning(f"Play analysis ({depth}) of {len(df)} boards")
    stats = write_results(analyse_batch(records, depth, workers=workers), Path(outdir) / "play", "csv",
                          views=views, progress=True)
    logging.warning(f"Play analysis done: {stats}")
    return stats


def _with_play_columns(df: pl.DataFrame, new: pl.DataFrame) -> pl.DataFrame:
    """Replace Play and put PlayEncoding and Claim right after it (the layout of a new ingest)."""
    claim = df["Claim"] if "Claim" in df.columns else pl.Series("Claim", [None] * len(df), dtype=pl.Utf8)
    df = df.drop([c for c in ("PlayEncoding", "Claim") if c in df.columns])
    cols = df.columns
    at = cols.index("Play") + 1
    df = df.with_columns(new["Play"], new["PlayEncoding"], claim)
    return df.select(cols[:at] + ["PlayEncoding", "Claim"] + cols[at:])


def _write_atomic(df: pl.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".csv.tmp")
    df.write_csv(tmp)
    tmp.replace(path)


_KEY = ["_file", "MatchName", "TableID", "DealNum", "Hands", "North", "East", "South", "West"]


def _keyed(df: pl.DataFrame) -> pl.DataFrame:
    """Add the board key (source file name, match, room, board, hands, players)
    and an occurrence number, so keys that still repeat pair up in file order
    (e.g. a JSON file listing two tables of one match as room "O", unnamed)."""
    df = df.with_columns(
        pl.col("FilePath").cast(pl.Utf8).fill_null("").str.replace_all(r"\\", "/")
          .str.split("/").list.last().str.to_lowercase().alias("_file"),
        *[pl.col(c).cast(pl.Utf8).fill_null("") for c in _KEY[1:]])
    return df.with_columns(pl.int_range(pl.len()).over(_KEY).alias("_occ"))


def _take_new(df: pl.DataFrame, had_claim: bool) -> pl.DataFrame:
    """Matched rows (_play not null) get the re-read Play, where it differs, and Claim."""
    matched = pl.col("_play").is_not_null()
    differs = matched & (pl.col("_play") != pl.col("Play").fill_null(""))
    old_claim = pl.col("Claim") if had_claim else pl.lit(None, pl.Utf8)
    return df.with_columns(pl.when(differs).then(pl.col("_play")).otherwise(pl.col("Play")).alias("Play"),
                           pl.when(matched).then(pl.col("_claim")).otherwise(old_claim).alias("Claim"))


def repair_plays(db_dir: Path, files: List[Path], out_dir: Optional[Path] = None,
                 reader: Optional[Callable[[List[Path]], List[Any]]] = None) -> Dict[str, Any]:
    """Re-read source files and replace only Play (and Claim) for their boards.

    For fixing a parser bug without a full re-ingest. Each re-read board is
    matched to its DB rows by source file name, TableID, DealNum, Hands and
    player names. RawData.csv gets the play as parsed; boards.csv and all.csv
    are then normalised (normalize_db). All other columns, rows and files are
    unchanged; UIDs stay the same. Writes to out_dir (default: in place).
    reader(files) -> BoardRecords; default ingest.ingest_files.
    """
    from process_records import normalize_hands

    if reader is None:
        from ingest import ingest_files

        def reader(paths: List[Path]) -> List[Any]:
            return ingest_files(paths, parallelize=True)

    db_dir = Path(db_dir)
    out_dir = Path(out_dir) if out_dir else db_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    def read(name: str) -> pl.DataFrame:
        return pl.read_csv(db_dir / f"{name}.csv", infer_schema_length=0)

    fresh = pl.from_records(reader([Path(f) for f in files]))
    fresh = fresh.with_columns([pl.col(c).str.to_uppercase() for c in ["North", "South", "East", "West"]])
    fresh = fresh.with_columns(pl.col("Play").fill_null(""), pl.col("Claim").cast(pl.Utf8))
    names = set(fresh.select(pl.col("FilePath").str.replace_all(r"\\", "/").str.split("/").list.last()
                             .str.to_lowercase()).to_series())

    raw = _keyed(read("RawData"))
    in_db = raw.filter(pl.col("_file").is_in(list(names)))
    ambiguous = in_db.group_by("_file").agg(pl.col("FilePath").n_unique().alias("n")).filter(pl.col("n") > 1)
    if len(ambiguous):
        raise ValueError(f"file names used by more than one source path: {ambiguous['_file'].to_list()}")

    # RawData: the play as the (fixed) parser produces it
    new_raw = _keyed(fresh).select(_KEY + ["_occ", pl.col("Play").alias("_play"), pl.col("Claim").alias("_claim")])
    raw = raw.join(new_raw, on=_KEY + ["_occ"], how="left", coalesce=True)
    matched = raw.filter(pl.col("_play").is_not_null())
    changed = matched.filter(pl.col("_play") != pl.col("Play").fill_null(""))
    raw_cols = read("RawData").columns
    raw_out = _take_new(raw, "Claim" in raw_cols)
    _write_atomic(raw_out.select(raw_cols + ([] if "Claim" in raw_cols else ["Claim"])), out_dir / "RawData.csv")

    # all.csv / boards.csv: same keys, Hands canonical; then normalise
    new_all = _keyed(fresh.with_columns(
        pl.col("Hands").map_elements(normalize_hands, return_dtype=pl.Utf8))).select(
        _KEY + ["_occ", pl.col("Play").alias("_play"), pl.col("Claim").alias("_claim")])
    alldf = _keyed(read("all")).join(new_all, on=_KEY + ["_occ"], how="left", coalesce=True)
    all_cols = read("all").columns
    alldf = _take_new(alldf, "Claim" in all_cols)
    by_board = (alldf.filter(pl.col("_play").is_not_null())
                .group_by("BoardUID", maintain_order=True).first()
                .select(["BoardUID", "_play", "_claim"]))
    _write_atomic(alldf.select(all_cols + ([] if "Claim" in all_cols else ["Claim"])), out_dir / "all.csv")

    boards = read("boards")
    b_cols = boards.columns
    boards = _take_new(boards.join(by_board, on="BoardUID", how="left"), "Claim" in b_cols)
    _write_atomic(boards.select(b_cols + ([] if "Claim" in b_cols else ["Claim"])), out_dir / "boards.csv")

    norm = normalize_db(db_dir, out_dir, source_dir=out_dir)
    stats = {"reparsed": len(fresh), "matched": len(matched), "play_changed": len(changed),
             "unmatched": len(fresh) - len(matched), "boards_updated": len(by_board), **norm}
    logging.warning(f"Plays repaired in {out_dir}: {stats}")
    return stats


def normalize_db(db_dir: Path, out_dir: Optional[Path] = None, source_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Normalise Play retroactively in an existing DB's boards.csv and all.csv.

    Each board's Play is normalised with its Hands (deals.csv) and its own
    Contract/Declarer, falling back to the validated ones in
    ProcessedBoards.csv. PlayEncoding and an empty Claim column are added after
    Play (Claim needs the source files: re-ingest to fill it). All other
    columns are copied as text, unchanged. Writes to out_dir (default: in
    place, via a temporary file). RawData.csv keeps the recorded Play.
    """
    db_dir = Path(db_dir)
    out_dir = Path(out_dir) if out_dir else db_dir
    source_dir = Path(source_dir) if source_dir else db_dir     # where boards.csv / all.csv are read
    out_dir.mkdir(parents=True, exist_ok=True)

    def read(folder: Path, name: str) -> pl.DataFrame:
        return pl.read_csv(folder / f"{name}.csv", infer_schema_length=0)   # everything as text

    processed = None
    if (db_dir / "ProcessedBoards.csv").exists():
        processed = read(db_dir, "ProcessedBoards").select(
            ["BoardUID", pl.col("Contract").alias("_c"), pl.col("Declarer").alias("_d")])

    def normalised(df: pl.DataFrame) -> pl.DataFrame:
        """Play / PlayEncoding for each row of df (needs BoardUID, Play, Hands, Contract, Declarer)."""
        df = df.with_columns([pl.lit(None, pl.Utf8).alias(c) for c in ("Contract", "Declarer") if c not in df.columns])
        work = df.select(["BoardUID", "Play", "Hands", "Contract", "Declarer"]).with_row_index("_row")
        if processed is not None:
            work = work.join(processed, on="BoardUID", how="left").with_columns(
                pl.coalesce(["Contract", "_c"]).alias("Contract"),     # empty CSV fields read as null
                pl.coalesce(["Declarer", "_d"]).alias("Declarer"))
        work = work.sort("_row").with_columns(pl.col("Play").alias("_orig"), pl.col("Play").fill_null(""))
        work = normalize_play_column(work)
        no_play = pl.col("PlayEncoding") == ""
        return work.with_columns(       # no play: keep the stored text exactly (empty or "")
            pl.when(no_play).then(pl.col("_orig")).otherwise(pl.col("Play")).alias("Play"),
            pl.when(no_play).then(None).otherwise(pl.col("PlayEncoding")).alias("PlayEncoding"))

    boards = read(source_dir, "boards")
    hands = read(db_dir, "deals").select(["DealUID", "Hands"])
    work = normalised(boards.select(["BoardUID", "DealUID", "Play", "Contract", "Declarer"]).with_row_index("_r")
                      .join(hands, on="DealUID", how="left").sort("_r"))
    _write_atomic(_with_play_columns(boards, work), out_dir / "boards.csv")

    stats: Dict[str, Any] = {"boards": len(boards),
                             "encodings": dict(work.group_by("PlayEncoding").len().rows())}
    if (source_dir / "all.csv").exists():
        alldf = read(source_dir, "all")
        _write_atomic(_with_play_columns(alldf, normalised(alldf)), out_dir / "all.csv")
        stats["all_rows"] = len(alldf)
    logging.warning(f"Play normalised in {out_dir}: {stats}")
    return stats


def play_analysis_from_db(db_dir: Path, depth: str = "full", workers: Optional[int] = None) -> Dict[str, Any]:
    """Run play analysis on an existing DB folder (boards.csv, deals.csv, ProcessedBoards.csv)."""
    def read(name: str) -> pl.DataFrame:
        return pl.read_csv(Path(db_dir) / f"{name}.csv", infer_schema_length=0)   # all columns as text

    return create_play_analysis(read("ProcessedBoards"), read("boards"), read("deals"), db_dir, depth, workers)
