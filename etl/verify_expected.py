"""The report's headline figures, computed from the CSVs in pandas with no DAX involved.

Run this next to etl/verify_measures.ps1 (which asks the live model the same questions over
XMLA). Two independent computations that agree are the cheapest proof there is that a measure
means what its name says - and the only thing that catches a DATEADD returning blank, or a
CALCULATE filter that quietly overwrote the row it was meant to respect.

    python etl/verify_expected.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def main() -> None:
    fact = pd.read_csv(DATA / "fact_sales.csv", parse_dates=["OrderDate", "ShipDate"])
    cust = pd.read_csv(DATA / "dim_customer.csv", parse_dates=["FirstOrderDate"])
    prod = pd.read_csv(DATA / "dim_product.csv")
    geo = pd.read_csv(DATA / "dim_geography.csv")
    ship = pd.read_csv(DATA / "dim_ship_mode.csv")
    f = (fact.merge(cust[["CustomerID", "Segment", "FirstOrderDate", "FirstOrderYear"]])
             .merge(prod[["ProductKey", "Product", "Category", "SubCategory"]])
             .merge(geo[["GeographyKey", "Region", "State"]])
             .merge(ship[["ShipModeKey", "ShipMode"]]))
    f["Year"] = f.OrderDate.dt.year

    print("== Headline, whole period")
    print(f"   Sales {f.Sales.sum():,.2f} | Orders {f.OrderID.nunique():,} | "
          f"Customers {f.CustomerID.nunique()} | AOV {f.Sales.sum() / f.OrderID.nunique():,.2f} | "
          f"Products sold {f.ProductKey.nunique():,}")

    print("== By year: sales, PY, YoY, orders, new, returning")
    by = f.groupby("Year").agg(Sales=("Sales", "sum"), Orders=("OrderID", "nunique"),
                               Customers=("CustomerID", "nunique"))
    for y, r in by.iterrows():
        py = by.Sales.get(y - 1)
        new = f[(f.Year == y) & (f.FirstOrderYear == y)].CustomerID.nunique()
        yoy = "" if py is None else f"{(r.Sales / py - 1):.4f}"
        print(f"   {y} | {r.Sales:,.2f} | {'' if py is None else f'{py:,.2f}'} | {yoy} | "
              f"{r.Orders:,} | {new} | {r.Customers - new}")

    print("== Category share, whole period")
    c = f.groupby("Category").Sales.sum().sort_values(ascending=False)
    for k, v in c.items():
        print(f"   {k} | {v:,.2f} | {v / c.sum():.4f}")

    print("== Sub-categories 2024, top 5 with cumulative share")
    s = f[f.Year == 2024].groupby("SubCategory").Sales.sum().sort_values(ascending=False)
    cum = s.cumsum() / s.sum()
    for k in s.index[:5]:
        print(f"   {k} | {s[k]:,.2f} | {cum[k]:.4f}")

    print("== Cohort retention (rows = first-order year, columns = active year)")
    for cohort in sorted(f.FirstOrderYear.unique()):
        size = cust[cust.FirstOrderYear == cohort].CustomerID.nunique()
        cells = []
        for y in sorted(f.Year.unique()):
            if y < cohort:
                cells.append("     ")
                continue
            active = f[(f.FirstOrderYear == cohort) & (f.Year == y)].CustomerID.nunique()
            cells.append(f"{active / size:.4f}")
        print(f"   {cohort} (n={size}) | " + " | ".join(cells))

    print("== Ship mode, whole period: share of orders, average ship days")
    orders = f.groupby("ShipMode").OrderID.nunique()
    for k in ship.ShipMode:
        print(f"   {k} | {orders[k] / f.OrderID.nunique():.4f} | "
              f"{f[f.ShipMode == k].ShipDays.mean():.4f}")

    print("== Standard Class share by region (the KEEPFILTERS check)")
    for reg, g in f.groupby("Region"):
        std = g[g.ShipMode == "Standard Class"].OrderID.nunique()
        print(f"   {reg} | {std / g.OrderID.nunique():.4f}")

    print("== Top states 2024")
    st = f[f.Year == 2024].groupby("State").Sales.sum().sort_values(ascending=False)
    for i, (k, v) in enumerate(st.head(3).items(), start=1):
        print(f"   {i} | {k} | {v:,.2f} | {v / st.sum():.4f}")

    print("== Top product, whole period")
    p = f.groupby("Product").Sales.sum().sort_values(ascending=False)
    print(f"   {p.index[0]} | {p.iloc[0]:,.2f}")


if __name__ == "__main__":
    main()
