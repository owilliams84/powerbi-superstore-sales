"""Emit the compact JSON the milestonebi.com interactive page reads.

The web page is a hand-built HTML/SVG version of the Power BI report, so it must show the same
numbers. It reads this file rather than the star schema: the schema is 1.3 MB and the page needs
about 20 KB of it, and every figure here is computed with the same definitions as the DAX
measures - distinct orders, first-ever-order for "new", cohort retention against cohort size,
ship mode share of orders - so the two agree to the cent.

    python etl/build_web_data.py [-o <path>]

Writes web/superstore-sales.json by default.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load() -> pd.DataFrame:
    fact = pd.read_csv(DATA / "fact_sales.csv", parse_dates=["OrderDate", "ShipDate"])
    cust = pd.read_csv(DATA / "dim_customer.csv", parse_dates=["FirstOrderDate"])
    prod = pd.read_csv(DATA / "dim_product.csv")
    geo = pd.read_csv(DATA / "dim_geography.csv")
    ship = pd.read_csv(DATA / "dim_ship_mode.csv")
    f = (fact.merge(cust[["CustomerID", "Customer", "Segment", "FirstOrderYear", "OrderBand",
                          "OrderBandSort"]])
             .merge(prod[["ProductKey", "Product", "Category", "SubCategory"]])
             .merge(geo[["GeographyKey", "Region", "State", "StateCode", "City"]])
             .merge(ship[["ShipModeKey", "ShipMode", "SortOrder"]]))
    f["Year"] = f.OrderDate.dt.year
    f["Month"] = f.OrderDate.dt.month
    return f


def r2(x) -> float:
    return round(float(x), 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(ROOT / "web" / "superstore-sales.json"))
    args = ap.parse_args()

    f = load()
    years = sorted(int(y) for y in f.Year.unique())
    total = float(f.Sales.sum())
    n_orders = int(f.OrderID.nunique())
    n_cust = int(f.CustomerID.nunique())
    per_cust = f.groupby("CustomerID").agg(orders=("OrderID", "nunique"), years=("Year", "nunique"))

    out: dict = {
        "meta": {
            "source": "https://github.com/owilliams84/powerbi-superstore-sales",
            "firstOrder": f.OrderDate.min().strftime("%Y-%m-%d"),
            "lastOrder": f.OrderDate.max().strftime("%Y-%m-%d"),
            "years": years,
            "rows": int(len(f)),
            "orders": n_orders,
            "customers": n_cust,
            "products": int(f.ProductKey.nunique()),
            "states": int(f.State.nunique()),
            "cities": int(f.groupby(["State", "City"]).ngroups),
        },
        "headline": {
            "sales": r2(total),
            "orders": n_orders,
            "customers": n_cust,
            "aov": r2(total / n_orders),
            "salesPerCustomer": r2(total / n_cust),
            "repeatShare": round(float((per_cust.orders >= 2).mean()), 4),
            "activeEveryYear": int((per_cust.years == len(years)).sum()),
        },
    }

    # --- sales by month, one series per year ------------------------------------------------
    piv = f.pivot_table(index="Month", columns="Year", values="Sales", aggfunc="sum").reindex(range(1, 13))
    out["monthly"] = {"months": MONTHS,
                      "series": {str(y): [r2(v) for v in piv[y].fillna(0)] for y in years}}

    # --- year by year, with new and returning -----------------------------------------------
    rows = []
    prev = None
    for y in years:
        g = f[f.Year == y]
        sales = float(g.Sales.sum())
        orders = int(g.OrderID.nunique())
        customers = int(g.CustomerID.nunique())
        new = int(g[g.FirstOrderYear == y].CustomerID.nunique())
        rows.append({"year": y, "sales": r2(sales),
                     "yoy": None if prev is None else round(sales / prev - 1, 4),
                     "orders": orders, "customers": customers, "aov": r2(sales / orders),
                     "newCustomers": new, "returning": customers - new})
        prev = sales
    out["years"] = rows

    # --- product mix ------------------------------------------------------------------------
    cat = f.groupby("Category").Sales.sum().sort_values(ascending=False)
    out["categories"] = [{"category": k, "sales": r2(v), "share": round(v / total, 4)}
                         for k, v in cat.items()]
    sub = f.groupby(["SubCategory", "Category"]).Sales.sum().sort_values(ascending=False)
    last, before = years[-1], years[-2]
    s_last = f[f.Year == last].groupby("SubCategory").Sales.sum()
    s_before = f[f.Year == before].groupby("SubCategory").Sales.sum()
    cum = 0.0
    subs = []
    for (name, category), v in sub.items():
        cum += float(v)
        subs.append({"subCategory": name, "category": category, "sales": r2(v),
                     "share": round(v / total, 4), "cumShare": round(cum / total, 4),
                     "yoy": round(float(s_last.get(name, 0)) / float(s_before.get(name, 1)) - 1, 4)})
    out["subCategories"] = subs
    out["yoyYears"] = [before, last]

    top = (f.groupby(["Product", "SubCategory"]).agg(sales=("Sales", "sum"), orders=("OrderID", "nunique"))
            .sort_values("sales", ascending=False).head(20).reset_index())
    out["topProducts"] = [{"rank": i + 1, "product": r.Product, "subCategory": r.SubCategory,
                           "sales": r2(r.sales), "orders": int(r.orders), "share": round(r.sales / total, 4)}
                          for i, r in top.iterrows()]

    # --- customers --------------------------------------------------------------------------
    cohorts = []
    for c in years:
        size = int(f[f.FirstOrderYear == c].CustomerID.nunique())
        ret = []
        for y in years:
            if y < c:
                ret.append(None)
            else:
                active = int(f[(f.FirstOrderYear == c) & (f.Year == y)].CustomerID.nunique())
                ret.append(round(active / size, 4))
        cohorts.append({"cohort": c, "size": size, "retention": ret})
    out["cohorts"] = {"years": years, "rows": cohorts}

    bands = (f.drop_duplicates("CustomerID").groupby(["OrderBandSort", "OrderBand"]).size())
    out["bands"] = [{"band": b, "customers": int(n)} for (_, b), n in bands.items()]

    seg = f.groupby("Segment").agg(sales=("Sales", "sum"), orders=("OrderID", "nunique"),
                                   customers=("CustomerID", "nunique")).sort_values("sales", ascending=False)
    out["segments"] = [{"segment": k, "sales": r2(r.sales), "share": round(r.sales / total, 4),
                        "customers": int(r.customers), "aov": r2(r.sales / r.orders)}
                       for k, r in seg.iterrows()]

    tc = (f.groupby(["Customer", "Segment"]).agg(sales=("Sales", "sum"), orders=("OrderID", "nunique"))
            .sort_values("sales", ascending=False).head(10).reset_index())
    out["topCustomers"] = [{"rank": i + 1, "customer": r.Customer, "segment": r.Segment,
                            "sales": r2(r.sales), "orders": int(r.orders)} for i, r in tc.iterrows()]

    # --- geography and shipping -------------------------------------------------------------
    reg = f.groupby("Region").Sales.sum().sort_values(ascending=False)
    out["regions"] = [{"region": k, "sales": r2(v), "share": round(v / total, 4)} for k, v in reg.items()]
    st = (f.groupby(["State", "StateCode"]).agg(sales=("Sales", "sum"), orders=("OrderID", "nunique"))
            .sort_values("sales", ascending=False).reset_index())
    out["states"] = [{"state": r.State, "code": r.StateCode, "sales": r2(r.sales),
                      "share": round(r.sales / total, 4), "orders": int(r.orders)} for _, r in st.iterrows()]
    ct = (f.groupby(["City", "State"]).Sales.sum().sort_values(ascending=False).head(10).reset_index())
    out["cities"] = [{"city": r.City, "state": r.State, "sales": r2(r.Sales)} for _, r in ct.iterrows()]

    sm = f.groupby(["SortOrder", "ShipMode"]).agg(orders=("OrderID", "nunique"), days=("ShipDays", "mean"))
    out["shipModes"] = [{"mode": k, "orders": int(r.orders), "orderShare": round(r.orders / n_orders, 4),
                         "avgDays": round(float(r.days), 2)} for (_, k), r in sm.iterrows()]

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8", newline="\n")
    kb = dest.stat().st_size / 1024
    h = out["headline"]
    print(f"wrote {dest} ({kb:.0f} KB)")
    print(f"  ${h['sales']:,.0f} | {h['orders']:,} orders | {h['customers']} customers | "
          f"AOV ${h['aov']:,.0f} | repeat {h['repeatShare']:.1%} | every year {h['activeEveryYear']}")


if __name__ == "__main__":
    main()
