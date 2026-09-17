"""Inject real daily figures into the Calendar page mockup.

    python design/build_calendar_mockup.py

Reads data/fact_sales.csv, sums Sales and counts distinct orders per order date, and writes
design/calendar-mockup.html from design/calendar-mockup.src.html. Every view in the mockup
(Day, Month, Quarter, Year) is aggregated in the browser from this one daily series, so the
four views cannot disagree with each other.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sales: dict[str, float] = defaultdict(float)
    orders: dict[str, set[str]] = defaultdict(set)
    with (ROOT / "data" / "fact_sales.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sales[row["OrderDate"]] += float(row["Sales"])
            orders[row["OrderDate"]].add(row["OrderID"])
    days = {d: [round(sales[d], 2), len(orders[d])] for d in sorted(sales)}
    src = (ROOT / "design" / "calendar-mockup.src.html").read_text(encoding="utf-8")
    html = src.replace("/*DATA*/", json.dumps(days, separators=(",", ":")))
    (ROOT / "design" / "calendar-mockup.html").write_text(html, encoding="utf-8", newline="\n")
    print(f"design/calendar-mockup.html  ({len(days)} days with sales, "
          f"{min(days)} to {max(days)}, total {sum(v[0] for v in days.values()):,.0f})")


if __name__ == "__main__":
    main()
