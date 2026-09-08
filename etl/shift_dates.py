"""Move the Superstore sample forward in time so it reads as current.

The Kaggle file covers 2015-2018 and the copy this project started from had already been moved
to 2017-2020. Both are old enough that a report built on them looks like an archive. This shifts
every order and ship date forward by a whole number of years - four by default - and re-syncs the
year token inside each Order ID, which in the source already trails the order date and would
otherwise sit six years behind it.

    python etl/shift_dates.py <in.csv> <out.csv> [--years 4] [--backup <path>]

The file's own date format (dd/mm/yyyy) is preserved, so the output is a drop-in replacement for
the input. Every gap between order and ship date is unchanged, and 29 February 2020 lands on
29 February 2024, which exists.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

DATE_COLS = ["OrderDate", "Ship Date"]
DATE_FMT = "%d/%m/%Y"
ORDER_ID = re.compile(r"^([A-Z]{2})-(\d{4})-(\d+)$")


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--years", type=int, default=4)
    ap.add_argument("--backup", help="copy the untouched input here before writing")
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    if args.backup:
        shutil.copy2(src, args.backup)
        print(f"  backed up {src.name} -> {args.backup}")

    df = pd.read_csv(src, dtype=str, keep_default_na=False)
    n = len(df)
    for c in DATE_COLS:
        if c not in df.columns:
            fail(f"{src.name} has no '{c}' column")

    parsed = {c: pd.to_datetime(df[c], format=DATE_FMT, errors="coerce") for c in DATE_COLS}
    bad = {c: int(parsed[c].isna().sum()) for c in DATE_COLS}
    if any(bad.values()):
        fail(f"dates that do not match {DATE_FMT}: {bad}")

    before = {c: (parsed[c].min(), parsed[c].max()) for c in DATE_COLS}
    shifted = {c: parsed[c] + pd.DateOffset(years=args.years) for c in DATE_COLS}
    # The gap between order and ship is the one thing the shift must not touch.
    old_gap = parsed["Ship Date"] - parsed["OrderDate"]
    new_gap = shifted["Ship Date"] - shifted["OrderDate"]
    if not (old_gap == new_gap).all():
        fail("shift changed an order-to-ship gap")

    for c in DATE_COLS:
        df[c] = shifted[c].dt.strftime(DATE_FMT)

    # Order IDs look like CA-2015-103800. Replace the year token with the (shifted) order year.
    n_orders_before = df["Order ID"].nunique()
    ids = df["Order ID"].str.extract(ORDER_ID)
    if ids.isna().any().any():
        fail("an Order ID does not match XX-YYYY-NNNNNN")
    lag = (shifted["OrderDate"].dt.year - ids[1].astype(int)).value_counts().to_dict()
    df["Order ID"] = ids[0] + "-" + shifted["OrderDate"].dt.year.astype(str) + "-" + ids[2]
    if df["Order ID"].nunique() != n_orders_before:
        fail("rewriting Order ID years changed the number of distinct orders")

    df.to_csv(dst, index=False, lineterminator="\n")
    print(f"  {n:,} rows shifted +{args.years} years -> {dst}")
    for c in DATE_COLS:
        print(f"  {c:10s}: {before[c][0]:%Y-%m-%d} .. {before[c][1]:%Y-%m-%d}"
              f"  ->  {shifted[c].min():%Y-%m-%d} .. {shifted[c].max():%Y-%m-%d}")
    print(f"  Order ID year lag before rewrite (order year - id year): {lag}; now 0 everywhere")


if __name__ == "__main__":
    main()
