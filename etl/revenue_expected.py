"""Expected figures for the Revenue page, computed in pandas from the star schema.

Two uses: the numbers in the HTML mockup, and the answer key the DAX on the page is checked
against. Every figure is one year against a comparison year, with no other filter.

    python etl/revenue_expected.py                 # 2024 against 2023
    python etl/revenue_expected.py 2024 2022       # 2024 against two years earlier
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
TOP_N = 8


def ranked(frame: pd.DataFrame, key: str, year: int, comp: int) -> pd.DataFrame:
    """Sales in each year by `key`, the change, and only rows that sold in either year."""
    pivot = (frame[frame.Year.isin([year, comp])]
             .pivot_table(index=key, columns="Year", values="Sales", aggfunc="sum", fill_value=0.0))
    for y in (year, comp):
        if y not in pivot:
            pivot[y] = 0.0
    out = pd.DataFrame({"sales": pivot[year], "comp": pivot[comp]})
    out = out[(out.sales + out.comp) > 0]
    out["change"] = out.sales - out.comp
    out["pct"] = out.change / out.comp.where(out.comp != 0)
    return out.sort_values("change", ascending=False)


def rows(frame: pd.DataFrame) -> list[dict]:
    return [{"name": k, "sales": round(r.sales, 2), "comp": round(r.comp, 2),
             "change": round(r.change, 2), "pct": None if pd.isna(r.pct) else round(r.pct, 4)}
            for k, r in frame.iterrows()]


def main() -> None:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    comp = int(sys.argv[2]) if len(sys.argv) > 2 else year - 1

    f = pd.read_csv(DATA / "fact_sales.csv", parse_dates=["OrderDate"])
    f["Year"] = f.OrderDate.dt.year
    f["Month"] = f.OrderDate.dt.month
    f = (f.merge(pd.read_csv(DATA / "dim_customer.csv")[["CustomerID", "Customer"]], on="CustomerID")
          .merge(pd.read_csv(DATA / "dim_product.csv")[["ProductKey", "SubCategory"]], on="ProductKey")
          .merge(pd.read_csv(DATA / "dim_geography.csv")[["GeographyKey", "Region"]], on="GeographyKey"))

    cur, prev = f[f.Year == year], f[f.Year == comp]
    sales, sales_c = cur.Sales.sum(), prev.Sales.sum()
    orders, orders_c = cur.OrderID.nunique(), prev.OrderID.nunique()

    monthly = pd.DataFrame({
        "sales": cur.groupby("Month").Sales.sum(),
        "comp": prev.groupby("Month").Sales.sum(),
    }).reindex(range(1, 13)).fillna(0.0)
    monthly["change"] = monthly.sales - monthly.comp

    customers = ranked(f, "Customer", year, comp)
    subcats = ranked(f, "SubCategory", year, comp)
    regions = ranked(f, "Region", year, comp)

    out = {
        "year": year, "comp": comp,
        "sales": round(sales, 2), "sales_comp": round(sales_c, 2),
        "sales_pct": round((sales - sales_c) / sales_c, 4),
        "orders": int(orders), "orders_comp": int(orders_c),
        "aov": round(sales / orders, 2), "aov_comp": round(sales_c / orders_c, 2),
        "customers_above": int((customers.change > 0).sum()), "customers_in_play": len(customers),
        "regions_above": int((regions.change > 0).sum()), "regions": rows(regions),
        "subcats_above": int((subcats.change > 0).sum()), "subcats_in_play": len(subcats),
        "monthly": [{"month": int(mo), "sales": round(r.sales, 2), "comp": round(r.comp, 2),
                     "change": round(r.change, 2)} for mo, r in monthly.iterrows()],
        "cumulative": [round(v, 2) for v in monthly.sales.cumsum()],
        "cumulative_comp": [round(v, 2) for v in monthly.comp.cumsum()],
        "customers_top": rows(customers.head(TOP_N)),
        "customers_bottom": rows(customers.tail(TOP_N).iloc[::-1]),
        "subcats_top": rows(subcats.head(TOP_N)),
        "subcats_bottom": rows(subcats.tail(TOP_N).iloc[::-1]),
        "max_abs_customer_change": round(customers.change.abs().max(), 2),
        "max_abs_subcat_change": round(subcats.change.abs().max(), 2),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
