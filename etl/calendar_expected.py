"""Answer key for the Calendar page, from the CSVs, and the diff against the live model.

    python etl/calendar_expected.py                      # print the key as view|key|sales|orders|band
    python etl/calendar_expected.py --compare dump.txt   # diff against etl/verify_calendar.ps1 output

Every cell of all four views: sales, distinct orders and the 1-5 shade band. The band is the
cell's rank among the cells on screen cut into fifths, in integer arithmetic, exactly as
[Cal Band ...] does it: min(5, below * 5 // (n - 1) + 1), 0 for a cell with no sales.

Keys: Day 2024-11-17 (every calendar day, selling or not) - Month 2024-11 - Quarter 2024-Q4 -
Year 2024. Day bands are ranked within their month, Month bands within their year, Quarter and
Year bands across the whole data set.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load() -> dict[date, tuple[float, set[str]]]:
    days: dict[date, list] = defaultdict(lambda: [0.0, set()])
    with (ROOT / "data" / "fact_sales.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            d = date.fromisoformat(row["OrderDate"])
            days[d][0] += float(row["Sales"])
            days[d][1].add(row["OrderID"])
    return {d: (v[0], v[1]) for d, v in days.items()}


def bands(cells: dict[str, float]) -> dict[str, int]:
    live = sorted(v for v in cells.values() if v > 0)
    out = {}
    for key, v in cells.items():
        if not v > 0:
            out[key] = 0
            continue
        below = sum(1 for x in live if x < v)
        out[key] = 5 if len(live) == 1 else min(5, below * 5 // (len(live) - 1) + 1)
    return out


def expected() -> dict[tuple[str, str], tuple[float, int, int]]:
    days = load()
    first, last = date(min(days).year, 1, 1), date(max(days).year, 12, 31)
    out: dict[tuple[str, str], tuple[float, int, int]] = {}

    def add(view: str, groups: dict[str, dict[str, tuple[float, set[str]]]]) -> None:
        # groups: pool name -> {cell key: (sales, order ids)}; bands are ranked within a pool
        for cells in groups.values():
            b = bands({k: v[0] for k, v in cells.items()})
            for k, (s, o) in cells.items():
                out[(view, k)] = (round(s, 2), len(o), b[k])

    def roll(key_of, pool_of) -> dict[str, dict[str, tuple[float, set[str]]]]:
        groups: dict[str, dict[str, list]] = defaultdict(dict)
        d = first
        while d <= last:
            cell = groups[pool_of(d)].setdefault(key_of(d), [0.0, set()])
            if d in days:
                cell[0] += days[d][0]
                cell[1] |= days[d][1]
            d += timedelta(days=1)
        return {p: {k: (v[0], v[1]) for k, v in cells.items()} for p, cells in groups.items()}

    add("Day", roll(lambda d: d.isoformat(), lambda d: d.strftime("%Y-%m")))
    add("Month", roll(lambda d: d.strftime("%Y-%m"), lambda d: str(d.year)))
    add("Quarter", roll(lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}", lambda d: "all"))
    add("Year", roll(lambda d: str(d.year), lambda d: "all"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", help="output of etl/verify_calendar.ps1")
    args = ap.parse_args()
    key = expected()

    if not args.compare:
        for (view, k), (s, o, b) in sorted(key.items()):
            print(f"{view}|{k}|{s:.2f}|{o}|{b}")
        return

    seen, bad = set(), []
    for line in Path(args.compare).read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split("|")
        if len(parts) != 5 or parts[0] not in ("Day", "Month", "Quarter", "Year"):
            continue
        view, k = parts[0], parts[1]
        s = float(parts[2] or 0)
        o = int(float(parts[3] or 0))
        b = int(float(parts[4])) if parts[4] != "" else None
        seen.add((view, k))
        if (view, k) not in key:
            bad.append(f"{view} {k}: in the model, not in the key")
            continue
        es, eo, eb = key[(view, k)]
        if abs(es - s) > 0.011 or eo != o or eb != b:
            bad.append(f"{view} {k}: model {s:.2f}/{o}/band {b}  key {es:.2f}/{eo}/band {eb}")
    missing = [f"{v} {k}: in the key, not in the model" for (v, k) in key if (v, k) not in seen]
    checks = len(seen) * 3
    for line in (bad + missing)[:40]:
        print("  MISMATCH", line)
    print(f"{len(seen)} cells, {checks} checks, {len(bad) + len(missing)} mismatches")
    sys.exit(1 if bad or missing else 0)


if __name__ == "__main__":
    main()
