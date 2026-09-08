"""Turn the flat Superstore extract into the star schema the semantic model loads.

Reads   data/source/Sales.csv        (dates already shifted by etl/shift_dates.py)
Writes  data/dim_date.csv, dim_customer.csv, dim_product.csv, dim_geography.csv,
        dim_ship_mode.csv, fact_sales.csv

Every decision below is listed in README.md. Run it with `python etl/build_star_schema.py` from
the repo root; it prints a reconciliation so a change in the source is visible immediately, and
it refuses to write anything that does not foot back to the source to the cent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "source" / "Sales.csv"
OUT = ROOT / "data"

DATE_FMT = "%d/%m/%Y"

# Same Day first: this is the order a "how fast" chart should read in.
SHIP_MODES = ["Same Day", "First Class", "Second Class", "Standard Class"]

# Lifetime order-count bands for the customer histogram. Fixed at build time on purpose - a band
# that moved with the year slicer would put the same customer in two bands across two years.
ORDER_BANDS = [(1, 1, "1 order"), (2, 3, "2-3 orders"), (4, 6, "4-6 orders"), (7, 99, "7+ orders")]

STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load() -> pd.DataFrame:
    raw = pd.read_csv(SRC, dtype={"Postal Code": str})
    n = len(raw)
    for c in ["OrderDate", "Ship Date"]:
        parsed = pd.to_datetime(raw[c], format=DATE_FMT, errors="coerce")
        if parsed.isna().any():
            fail(f"{int(parsed.isna().sum())} rows in {c} do not parse as {DATE_FMT}")
        raw[c] = parsed
    if (raw["Ship Date"] < raw["OrderDate"]).any():
        fail("a ship date precedes its order date")
    if raw["Row ID"].duplicated().any():
        fail("duplicate Row IDs")

    # Postal codes were stored as numbers upstream, so 429 New England and New Jersey codes have
    # lost their leading zero ("1841" for Lowell MA, which is 01841). Pad back to five digits.
    # Eleven rows (all Burlington, Vermont) have no code at all; they stay blank rather than being
    # looked up, because the source did not record them.
    pc = raw["Postal Code"].str.replace(r"\.0$", "", regex=True)
    pc = pc.where(pc.notna() & (pc != ""), None)
    n_padded = int((pc.dropna().str.len() < 5).sum())
    raw["Postal Code"] = pc.where(pc.isna(), pc.str.zfill(5))

    print(f"  source  : {n:,} rows, {raw['Order ID'].nunique():,} orders, "
          f"{raw['OrderDate'].min():%Y-%m-%d} to {raw['OrderDate'].max():%Y-%m-%d} "
          f"({n_padded} postal codes re-padded, {int(raw['Postal Code'].isna().sum())} missing)")
    return raw


def build_dim_date(first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    # Whole years only, one row per day. Contiguous and complete, which is what lets the model
    # mark it as a date table and use DATEADD / TOTALYTD safely.
    days = pd.date_range(pd.Timestamp(first.year, 1, 1), pd.Timestamp(last.year, 12, 31), freq="D")
    d = pd.DataFrame({"Date": days})
    d["Year"] = d.Date.dt.year
    d["Quarter"] = "Q" + d.Date.dt.quarter.astype(str)
    d["QuarterYear"] = d.Quarter + " " + d.Year.astype(str)
    d["QuarterYearSort"] = d.Year * 10 + d.Date.dt.quarter
    d["MonthNumber"] = d.Date.dt.month
    d["MonthName"] = d.Date.dt.strftime("%B")
    d["MonthShort"] = d.Date.dt.strftime("%b")
    d["MonthYear"] = d.Date.dt.strftime("%b %Y")
    d["MonthYearSort"] = d.Year * 100 + d.MonthNumber
    d["MonthStart"] = d.Date.dt.to_period("M").dt.start_time
    d["DayOfWeek"] = d.Date.dt.dayofweek + 1  # Monday = 1
    d["DayName"] = d.Date.dt.strftime("%A")
    d["IsWeekend"] = d.DayOfWeek.ge(6).map({True: "Yes", False: "No"})
    return d


def build_dim_customer(raw: pd.DataFrame) -> pd.DataFrame:
    if (raw.groupby("Customer ID")["Customer Name"].nunique() > 1).any():
        fail("a Customer ID has more than one name")
    if (raw.groupby("Customer ID")["Segment"].nunique() > 1).any():
        fail("a Customer ID has more than one segment")
    c = (raw.groupby("Customer ID")
            .agg(Customer=("Customer Name", "first"), Segment=("Segment", "first"),
                 FirstOrderDate=("OrderDate", "min"), LastOrderDate=("OrderDate", "max"),
                 LifetimeOrders=("Order ID", "nunique"))
            .reset_index().rename(columns={"Customer ID": "CustomerID"}))
    c["FirstOrderYear"] = c.FirstOrderDate.dt.year
    band = pd.Series(index=c.index, dtype=object)
    band_sort = pd.Series(index=c.index, dtype="Int64")
    for i, (lo, hi, label) in enumerate(ORDER_BANDS, start=1):
        m = c.LifetimeOrders.between(lo, hi)
        band[m] = label
        band_sort[m] = i
    if band.isna().any():
        fail("a customer falls outside every order band")
    c["OrderBand"] = band
    c["OrderBandSort"] = band_sort
    # Geography is deliberately NOT here. 777 of 793 customers order from more than one state, so
    # location belongs to the order line, not the customer.
    return c.sort_values("CustomerID")


def build_dim_product(raw: pd.DataFrame) -> pd.DataFrame:
    # Product ID is not a key in this extract: 32 IDs carry two different names, and 16 names sit
    # under two IDs. Neither side can be the grain without merging products that are different or
    # splitting ones that are the same, so the grain is the (ID, name) pair with a surrogate key.
    pairs = (raw[["Product ID", "Product Name", "Category", "Sub-Category"]]
             .drop_duplicates(["Product ID", "Product Name"]).copy())
    if (raw.groupby(["Product ID", "Product Name"])["Sub-Category"].nunique() > 1).any():
        fail("a product pair spans two sub-categories")
    pairs = (pairs.sort_values(["Category", "Sub-Category", "Product Name", "Product ID"])
                  .reset_index(drop=True))
    pairs.insert(0, "ProductKey", range(1, len(pairs) + 1))
    pairs = pairs.rename(columns={"Product ID": "ProductID", "Product Name": "Product",
                                  "Sub-Category": "SubCategory"})
    n_multi_name = int((raw.groupby("Product ID")["Product Name"].nunique() > 1).sum())
    n_multi_id = int((raw.groupby("Product Name")["Product ID"].nunique() > 1).sum())
    print(f"  products: {len(pairs):,} (ID, name) pairs from {raw['Product ID'].nunique():,} IDs "
          f"and {raw['Product Name'].nunique():,} names "
          f"({n_multi_name} IDs with two names, {n_multi_id} names with two IDs)")
    return pairs


def build_dim_geography(raw: pd.DataFrame) -> pd.DataFrame:
    cols = ["Country", "Region", "State", "City", "Postal Code"]
    g = raw[cols].drop_duplicates().copy()
    unknown = set(g.State) - set(STATE_CODES)
    if unknown:
        fail(f"states without a code: {sorted(unknown)}")
    g["StateCode"] = g.State.map(STATE_CODES)
    g = (g.sort_values(["Region", "State", "City", "Postal Code"], na_position="last")
          .reset_index(drop=True))
    g.insert(0, "GeographyKey", range(1, len(g) + 1))
    return g.rename(columns={"Postal Code": "PostalCode"})


def build_dim_ship_mode(raw: pd.DataFrame) -> pd.DataFrame:
    unknown = set(raw["Ship Mode"]) - set(SHIP_MODES)
    if unknown:
        fail(f"unexpected ship modes: {sorted(unknown)}")
    return pd.DataFrame({"ShipModeKey": range(1, len(SHIP_MODES) + 1), "ShipMode": SHIP_MODES,
                         "SortOrder": range(1, len(SHIP_MODES) + 1)})


def build_fact(raw: pd.DataFrame, product: pd.DataFrame, geo: pd.DataFrame,
               ship: pd.DataFrame) -> pd.DataFrame:
    f = raw.merge(product[["ProductKey", "ProductID", "Product"]],
                  left_on=["Product ID", "Product Name"], right_on=["ProductID", "Product"],
                  how="left")
    f = f.merge(geo, left_on=["Country", "Region", "State", "City", "Postal Code"],
                right_on=["Country", "Region", "State", "City", "PostalCode"], how="left")
    f = f.merge(ship[["ShipModeKey", "ShipMode"]], left_on="Ship Mode", right_on="ShipMode",
                how="left")
    for k in ["ProductKey", "GeographyKey", "ShipModeKey"]:
        if f[k].isna().any():
            fail(f"{int(f[k].isna().sum())} fact rows did not resolve a {k}")
    if len(f) != len(raw):
        fail(f"fact grew from {len(raw)} to {len(f)} rows in the joins")

    fact = pd.DataFrame({
        "RowID": f["Row ID"],
        "OrderID": f["Order ID"],
        "OrderDate": f["OrderDate"],
        "ShipDate": f["Ship Date"],
        "ShipDays": (f["Ship Date"] - f["OrderDate"]).dt.days,
        "CustomerID": f["Customer ID"],
        "ProductKey": f["ProductKey"].astype(int),
        "GeographyKey": f["GeographyKey"].astype(int),
        "ShipModeKey": f["ShipModeKey"].astype(int),
        "Sales": f["Sales"].round(4),
    })
    return fact.sort_values(["OrderDate", "OrderID", "RowID"])


def reconcile(raw: pd.DataFrame, fact: pd.DataFrame, cust: pd.DataFrame, prod: pd.DataFrame,
              geo: pd.DataFrame, date: pd.DataFrame) -> None:
    print("\nReconciliation")
    src_total, fact_total = raw.Sales.sum(), fact.Sales.sum()
    if abs(src_total - fact_total) > 0.005:
        fail(f"sales do not foot: source {src_total:.2f} vs fact {fact_total:.2f}")
    print(f"  sales              : ${fact_total:,.2f} in {len(fact):,} lines, foots to the source")
    by_year = fact.groupby(fact.OrderDate.dt.year).Sales.sum()
    print("  by year            : " + ", ".join(f"{y} ${v:,.0f}" for y, v in by_year.items()))
    print(f"  orders             : {fact.OrderID.nunique():,}   customers: {len(cust):,}   "
          f"products: {len(prod):,}   places: {len(geo):,} in {geo.State.nunique()} states")
    print(f"  calendar           : {date.Date.min():%Y-%m-%d} to {date.Date.max():%Y-%m-%d}, "
          f"{len(date):,} days; orders {fact.OrderDate.min():%Y-%m-%d} to "
          f"{fact.OrderDate.max():%Y-%m-%d}")
    if fact.OrderDate.min() < date.Date.min() or fact.OrderDate.max() > date.Date.max():
        fail("an order date falls outside the calendar")
    print(f"  ship days          : {fact.ShipDays.min()} to {fact.ShipDays.max()}, "
          f"mean {fact.ShipDays.mean():.2f}")
    new_by_year = cust.groupby("FirstOrderYear").size()
    print("  new customers      : " + ", ".join(f"{y} {v}" for y, v in new_by_year.items()))
    bands = cust.groupby("OrderBand").size().reindex([b[2] for b in ORDER_BANDS])
    print("  order bands        : " + ", ".join(f"{b} {n}" for b, n in bands.items()))
    top = (fact.merge(prod[["ProductKey", "Product"]]).groupby("Product").Sales.sum()
               .sort_values(ascending=False))
    print(f"  top product        : {top.index[0]} ${top.iloc[0]:,.0f}")
    st = (fact.merge(geo[["GeographyKey", "State"]]).groupby("State").Sales.sum()
              .sort_values(ascending=False))
    print(f"  top state          : {st.index[0]} ${st.iloc[0]:,.0f} ({st.iloc[0] / st.sum():.1%})")


def main() -> None:
    if not SRC.exists():
        fail(f"missing {SRC}. Run etl/shift_dates.py on the Kaggle file first - see README.md.")

    print("Building star schema")
    raw = load()
    date = build_dim_date(raw.OrderDate.min(), raw.OrderDate.max())
    cust = build_dim_customer(raw)
    prod = build_dim_product(raw)
    geo = build_dim_geography(raw)
    ship = build_dim_ship_mode(raw)
    fact = build_fact(raw, prod, geo, ship)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in [("dim_date", date), ("dim_customer", cust), ("dim_product", prod),
                     ("dim_geography", geo), ("dim_ship_mode", ship), ("fact_sales", fact)]:
        path = OUT / f"{name}.csv"
        # Explicit LF: to_csv defaults to the platform ending, and the repo is normalised to LF.
        df.to_csv(path, index=False, date_format="%Y-%m-%d", lineterminator="\n")
        print(f"  wrote {path.relative_to(ROOT)} ({len(df):,} rows)")

    reconcile(raw, fact, cust, prod, geo, date)


if __name__ == "__main__":
    main()
