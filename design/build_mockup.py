"""Inject real figures into the Revenue page mockup.

    python design/build_mockup.py

Runs etl/revenue_expected.py for every year pair the page can show and writes
design/revenue-mockup.html from design/revenue-mockup.src.html.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [(2022, 2021), (2023, 2022), (2023, 2021), (2024, 2023), (2024, 2022)]


def main() -> None:
    data = {}
    for year, comp in PAIRS:
        out = subprocess.run([sys.executable, str(ROOT / "etl" / "revenue_expected.py"), str(year), str(comp)],
                             check=True, capture_output=True, text=True).stdout
        data[f"{year}_{comp}"] = json.loads(out)
    src = (ROOT / "design" / "revenue-mockup.src.html").read_text(encoding="utf-8")
    html = src.replace("/*DATA*/", json.dumps(data))
    (ROOT / "design" / "revenue-mockup.html").write_text(html, encoding="utf-8", newline="\n")
    print(f"design/revenue-mockup.html  ({len(PAIRS)} year pairs)")


if __name__ == "__main__":
    main()
