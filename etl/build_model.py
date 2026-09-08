"""Generate the TMDL semantic model - tables, relationships, measures.

TMDL is indentation-sensitive (tabs) and forbids blank lines inside an object, and every object
needs a stable lineageTag. Writing seven files by hand is how those slip; this owns the format
and the tags (uuid5 of the object's path, so re-running never churns them), and the table
definitions below read as a schema.

    python etl/build_model.py            # partitions read the CSVs from GitHub over HTTPS
    python etl/build_model.py --local    # partitions read data/ on this machine (offline builds)

Rewrites <model>/definition/ from scratch every run.
"""

from __future__ import annotations

import argparse
import shutil
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "Superstore Sales.SemanticModel"
DEFN = MODEL / "definition"
DATA = ROOT / "data"

RAW = "https://raw.githubusercontent.com/owilliams84/powerbi-superstore-sales/main/data/"
NS = uuid.UUID("6b1a9c2e-5d3f-4b8a-9e1c-2f7d8a6b4c10")


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "superstore:" + ":".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL identifier when it needs it."""
    return name if name.replace("_", "").isalnum() else f"'{name}'"


def doc(text: str | None, indent: int) -> list[str]:
    if not text:
        return []
    pad = "\t" * indent
    return [f"{pad}/// {para}".rstrip() for para in text.strip("\n").split("\n")]


# --------------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------------

def col(name, source, dtype, **o):
    return dict(name=name, source=source, dtype=dtype, **o)


TABLES = {
    "Date": dict(
        file="dim_date.csv", date_table=True,
        doc="One row per day, 2021 to 2024, contiguous and complete, and marked as the date table\n"
            "so DATEADD and TOTALYTD have a calendar to walk. Orders join here on Order Date.\n"
            "Ship dates are not related - shipping is analysed as days-to-ship on the fact.",
        columns=[
            col("Date", "Date", "dateTime", key=True, format="d mmm yyyy"),
            col("Year", "Year", "int64", format="0"),
            col("Quarter", "Quarter", "string"),
            col("Quarter Year", "QuarterYear", "string", sortBy="Quarter Year Sort"),
            col("Quarter Year Sort", "QuarterYearSort", "int64", hidden=True, format="0"),
            col("Month No", "MonthNumber", "int64", hidden=True, format="0"),
            col("Month", "MonthName", "string", sortBy="Month No"),
            col("Month Short", "MonthShort", "string", sortBy="Month No"),
            col("Month Year", "MonthYear", "string", sortBy="Month Year Sort"),
            col("Month Year Sort", "MonthYearSort", "int64", hidden=True, format="0"),
            col("Month Start", "MonthStart", "dateTime", hidden=True, format="mmm yyyy",
                doc="First day of the month, for continuous month axes."),
            col("Day of Week", "DayOfWeek", "int64", hidden=True, format="0"),
            col("Day", "DayName", "string", sortBy="Day of Week"),
            col("Is Weekend", "IsWeekend", "string"),
        ],
        types={"Date": "type date", "Year": "Int64.Type", "Quarter": "type text",
               "QuarterYear": "type text", "QuarterYearSort": "Int64.Type",
               "MonthNumber": "Int64.Type", "MonthName": "type text", "MonthShort": "type text",
               "MonthYear": "type text", "MonthYearSort": "Int64.Type", "MonthStart": "type date",
               "DayOfWeek": "Int64.Type", "DayName": "type text", "IsWeekend": "type text"},
    ),
    "Customer": dict(
        file="dim_customer.csv",
        doc="One row per customer. No geography here on purpose: 777 of the 793 customers order\n"
            "from more than one state, so where an order went belongs to the order line.\n"
            "\n"
            "'First Order Date' is what makes new-versus-returning possible: a customer is new in\n"
            "whatever period contains their first ever order. 'Order Band' is a lifetime count,\n"
            "fixed at build time, so the same customer cannot sit in two bands across two years.",
        columns=[
            col("Customer ID", "CustomerID", "string", key=True),
            col("Customer", "Customer", "string"),
            col("Segment", "Segment", "string", doc="Consumer, Corporate or Home Office."),
            col("First Order Date", "FirstOrderDate", "dateTime", hidden=True, format="d mmm yyyy"),
            col("Last Order Date", "LastOrderDate", "dateTime", hidden=True, format="d mmm yyyy"),
            col("Lifetime Orders", "LifetimeOrders", "int64", hidden=True, format="0"),
            col("Cohort", "FirstOrderYear", "int64", format="0",
                doc="The year of the customer's first order."),
            col("Order Band", "OrderBand", "string", sortBy="Order Band Sort",
                doc="Lifetime orders, banded: 1, 2-3, 4-6, 7+."),
            col("Order Band Sort", "OrderBandSort", "int64", hidden=True, format="0"),
        ],
        types={"CustomerID": "type text", "Customer": "type text", "Segment": "type text",
               "FirstOrderDate": "type date", "LastOrderDate": "type date",
               "LifetimeOrders": "Int64.Type", "FirstOrderYear": "Int64.Type",
               "OrderBand": "type text", "OrderBandSort": "Int64.Type"},
    ),
    "Product": dict(
        file="dim_product.csv",
        doc="One row per (Product ID, Product Name) pair - 1,893 of them. Product ID is not a\n"
            "key in this extract: 32 IDs carry two different names and 16 names sit under two IDs,\n"
            "so keying on either would merge products that differ or split ones that do not. The\n"
            "surrogate key keeps every pair distinct; Product ID stays visible for reference.",
        columns=[
            col("Product Key", "ProductKey", "int64", key=True, hidden=True, format="0"),
            col("Product ID", "ProductID", "string"),
            col("Product", "Product", "string"),
            col("Category", "Category", "string", doc="Furniture, Office Supplies or Technology."),
            col("Sub-Category", "SubCategory", "string"),
        ],
        types={"ProductKey": "Int64.Type", "ProductID": "type text", "Product": "type text",
               "Category": "type text", "SubCategory": "type text"},
    ),
    "Geography": dict(
        file="dim_geography.csv",
        doc="One row per place an order shipped to: country, region, state, city, postal code.\n"
            "Postal codes are text, re-padded to five digits - the source stored them as numbers\n"
            "and dropped the leading zero from 429 New England and New Jersey codes. Eleven rows\n"
            "(Burlington, Vermont) have no code in the source and stay blank.",
        columns=[
            col("Geography Key", "GeographyKey", "int64", key=True, hidden=True, format="0"),
            col("Country", "Country", "string"),
            col("Region", "Region", "string", doc="Central, East, South or West."),
            col("State", "State", "string"),
            col("State Code", "StateCode", "string"),
            col("City", "City", "string"),
            col("Postal Code", "PostalCode", "string"),
        ],
        types={"GeographyKey": "Int64.Type", "Country": "type text", "Region": "type text",
               "State": "type text", "StateCode": "type text", "City": "type text",
               "PostalCode": "type text"},
    ),
    "Ship Mode": dict(
        file="dim_ship_mode.csv",
        doc="Four shipping services, sorted fastest first so a chart reads Same Day to Standard.",
        columns=[
            col("Ship Mode Key", "ShipModeKey", "int64", key=True, hidden=True, format="0"),
            col("Ship Mode", "ShipMode", "string", sortBy="Sort Order"),
            col("Sort Order", "SortOrder", "int64", hidden=True, format="0"),
        ],
        types={"ShipModeKey": "Int64.Type", "ShipMode": "type text", "SortOrder": "Int64.Type"},
    ),
    "Sales": dict(
        file="fact_sales.csv",
        doc="One row per order line, 9,800 of them. Every column is hidden: Sales is the only\n"
            "amount, and the measures in Metrics own how it is aggregated and compared.",
        columns=[
            col("Row ID", "RowID", "int64", hidden=True, format="0"),
            col("Order ID", "OrderID", "string", hidden=True),
            col("Order Date", "OrderDate", "dateTime", hidden=True, format="yyyy-mm-dd"),
            col("Ship Date", "ShipDate", "dateTime", hidden=True, format="yyyy-mm-dd"),
            col("Ship Days", "ShipDays", "int64", hidden=True, format="0",
                doc="Calendar days from order to ship, 0 to 8."),
            col("Customer ID", "CustomerID", "string", hidden=True),
            col("Product Key", "ProductKey", "int64", hidden=True, format="0"),
            col("Geography Key", "GeographyKey", "int64", hidden=True, format="0"),
            col("Ship Mode Key", "ShipModeKey", "int64", hidden=True, format="0"),
            col("Sales", "Sales", "double", hidden=True, format="#,0.00"),
        ],
        types={"RowID": "Int64.Type", "OrderID": "type text", "OrderDate": "type date",
               "ShipDate": "type date", "ShipDays": "Int64.Type", "CustomerID": "type text",
               "ProductKey": "Int64.Type", "GeographyKey": "Int64.Type",
               "ShipModeKey": "Int64.Type", "Sales": "type number"},
    ),
}

RELATIONSHIPS = [
    ("Date to Sales", "Sales.'Order Date'", "Date.Date"),
    ("Customer to Sales", "Sales.'Customer ID'", "Customer.'Customer ID'"),
    ("Product to Sales", "Sales.'Product Key'", "Product.'Product Key'"),
    ("Geography to Sales", "Sales.'Geography Key'", "Geography.'Geography Key'"),
    ("Ship Mode to Sales", "Sales.'Ship Mode Key'", "'Ship Mode'.'Ship Mode Key'"),
]

# --------------------------------------------------------------------------------------------
# Measures: (name, dax, format, doc)
# --------------------------------------------------------------------------------------------
USD = "\\$#,0"
USD2 = "\\$#,0.00"
INT = "#,0"
PCT = "0.0%"
DEC1 = "0.0"

# "In the period" everywhere below means the Date filter context of the visual: a year on a
# slicer, a month on an axis, or the whole calendar on a card.
NEW_FILTER = (
    "FILTER(\n"
    "        ALL(Customer[First Order Date]),\n"
    "        Customer[First Order Date] >= PeriodStart && Customer[First Order Date] <= PeriodEnd\n"
    "    )"
)

MEASURES = [
    ("Sales", "SUM(Sales[Sales])", USD, None),
    ("Order Lines", "COUNTROWS(Sales)", INT, None),
    ("Orders", "DISTINCTCOUNT(Sales[Order ID])", INT,
     "Distinct orders, not lines. An order averages two lines, so counting rows overstates it."),
    ("Customers", "DISTINCTCOUNT(Sales[Customer ID])", INT,
     "Customers with at least one order in the period. Counted on the fact so every filter -\n"
     "product, region, ship mode - narrows it."),
    ("Products Sold", "DISTINCTCOUNT(Sales[Product Key])", INT, None),
    ("Average Order Value", "DIVIDE([Sales], [Orders])", USD, None),
    ("Average Line Value", "DIVIDE([Sales], [Order Lines])", USD2, None),
    ("Sales per Customer", "DIVIDE([Sales], [Customers])", USD, None),
    ("Orders per Customer", "DIVIDE([Orders], [Customers])", "0.00", None),
    ("Lines per Order", "DIVIDE([Order Lines], [Orders])", "0.00", None),

    ("Sales PY", "CALCULATE([Sales], DATEADD('Date'[Date], -1, YEAR))", USD,
     "The same period a year earlier. Needs the marked date table - without it DATEADD returns\n"
     "blank for every row and the YoY column looks like 2021 forever."),
    ("Sales YoY %", "DIVIDE([Sales] - [Sales PY], [Sales PY])", PCT,
     "Blank in 2021, the first year, rather than a meaningless comparison to nothing."),
    ("Orders PY", "CALCULATE([Orders], DATEADD('Date'[Date], -1, YEAR))", INT, None),
    ("Orders YoY %", "DIVIDE([Orders] - [Orders PY], [Orders PY])", PCT, None),
    ("Customers PY", "CALCULATE([Customers], DATEADD('Date'[Date], -1, YEAR))", INT, None),
    ("Customers YoY %", "DIVIDE([Customers] - [Customers PY], [Customers PY])", PCT, None),
    ("Sales YTD", "TOTALYTD([Sales], 'Date'[Date])", USD, None),
    ("Sales 12M",
     "CALCULATE([Sales], DATESINPERIOD('Date'[Date], MAX('Date'[Date]), -12, MONTH))", USD,
     "Rolling twelve months to the end of the period - the only volume figure that compares\n"
     "like with like when the year on screen is not a full one."),

    ("Sales Share",
     "DIVIDE(\n"
     "    [Sales],\n"
     "    CALCULATE(\n"
     "        [Sales],\n"
     "        REMOVEFILTERS('Product'), REMOVEFILTERS('Customer'),\n"
     "        REMOVEFILTERS('Geography'), REMOVEFILTERS('Ship Mode')\n"
     "    )\n"
     ")", PCT,
     "This row's share of all sales in the same period. Every non-date filter is cleared, so a\n"
     "sub-category's share is of the whole company, not of its category."),
    ("Sales Share of Selection", "DIVIDE([Sales], CALCULATE([Sales], ALLSELECTED()))", PCT,
     "Share of whatever is on the visual, for a 100% breakdown inside a filtered view."),
    ("Cumulative Sales Share",
     "VAR ThisSales = [Sales]\n"
     "VAR Total = CALCULATE([Sales], ALLSELECTED('Product'[Sub-Category]))\n"
     "VAR Above =\n"
     "    SUMX(\n"
     "        FILTER(ALLSELECTED('Product'[Sub-Category]), [Sales] >= ThisSales),\n"
     "        [Sales]\n"
     "    )\n"
     "RETURN\n"
     "    DIVIDE(Above, Total)", PCT,
     "Pareto line over sub-categories: the share of sales from this sub-category and every one\n"
     "selling more than it. Reads left to right on a chart sorted by sales."),
    ("Product Rank", "RANKX(ALLSELECTED('Product'), [Sales], , DESC, Dense)", "0", None),
    ("Customer Rank", "RANKX(ALLSELECTED('Customer'), [Sales], , DESC, Dense)", "0", None),
    ("State Rank", "RANKX(ALLSELECTED('Geography'[State]), [Sales], , DESC, Dense)", "0", None),

    ("New Customers",
     "VAR PeriodStart = MIN('Date'[Date])\n"
     "VAR PeriodEnd = MAX('Date'[Date])\n"
     "RETURN\n"
     f"    CALCULATE([Customers], {NEW_FILTER})", INT,
     "Customers whose first ever order falls in the period. Because it filters the fact rather\n"
     "than counting the Customer table, a product or region on the visual still applies: it\n"
     "becomes 'new customers who bought this'."),
    ("Returning Customers", "[Customers] - [New Customers]", INT,
     "Customers active in the period whose first order was before it."),
    ("New Customer Share", "DIVIDE([New Customers], [Customers])", PCT, None),
    ("Sales from New Customers",
     "VAR PeriodStart = MIN('Date'[Date])\n"
     "VAR PeriodEnd = MAX('Date'[Date])\n"
     "RETURN\n"
     f"    CALCULATE([Sales], {NEW_FILTER})", USD, None),
    ("Sales from Returning Customers", "[Sales] - [Sales from New Customers]", USD, None),
    ("Returning Sales Share", "DIVIDE([Sales from Returning Customers], [Sales])", PCT, None),
    ("Repeat Customer Share",
     "VAR PerCustomer =\n"
     "    ADDCOLUMNS(VALUES(Sales[Customer ID]), \"@Orders\", CALCULATE(DISTINCTCOUNT(Sales[Order ID])))\n"
     "RETURN\n"
     "    DIVIDE(COUNTROWS(FILTER(PerCustomer, [@Orders] >= 2)), [Customers])", PCT,
     "Share of active customers who ordered at least twice in the period."),
    ("Customers Active Every Year",
     "VAR YearsInPeriod = COUNTROWS(VALUES('Date'[Year]))\n"
     "RETURN\n"
     "    COUNTROWS(\n"
     "        FILTER(\n"
     "            VALUES(Sales[Customer ID]),\n"
     "            CALCULATE(COUNTROWS(SUMMARIZE(Sales, 'Date'[Year]))) = YearsInPeriod\n"
     "        )\n"
     "    )", INT,
     "Customers with at least one order in every year of the period. With one year selected\n"
     "it equals active customers, which is the right answer to the question it then asks.\n"
     "Counted through SUMMARIZE on the fact: DISTINCTCOUNT on the Date table would return\n"
     "the whole calendar for every customer, because a fact cannot filter its dimension."),
    ("Cohort Size", "CALCULATE([Customers], REMOVEFILTERS('Date'))", INT,
     "Every customer in the cohort on the row, whatever year the column is - the denominator\n"
     "for retention."),
    ("Retention %", "DIVIDE([Customers], [Cohort Size])", PCT,
     "On a cohort-by-year matrix: the share of a cohort that ordered again in each year. The\n"
     "cohort's own year is 100% by definition, and years before it are blank."),

    ("Average Ship Days", "AVERAGE(Sales[Ship Days])", DEC1,
     "Calendar days from order to ship, averaged over order lines."),
    ("Ship Mode Share", "DIVIDE([Orders], CALCULATE([Orders], REMOVEFILTERS('Ship Mode')))", PCT,
     "Share of orders, not sales, so a single large Same Day order does not dominate."),
    ("Standard Class Share",
     "DIVIDE(CALCULATE([Orders], KEEPFILTERS('Ship Mode'[Ship Mode] = \"Standard Class\")), [Orders])",
     PCT,
     "KEEPFILTERS matters: without it the filter would overwrite a ship mode already on the\n"
     "visual and repeat the grand total down a breakdown."),

    ("Report Period",
     "VAR First = MIN('Date'[Date])\n"
     "VAR Last = MAX('Date'[Date])\n"
     "VAR WholeYears = MONTH(First) = 1 && DAY(First) = 1 && MONTH(Last) = 12 && DAY(Last) = 31\n"
     "RETURN\n"
     "    SWITCH(\n"
     "        TRUE(),\n"
     "        WholeYears && YEAR(First) = YEAR(Last), FORMAT(Last, \"yyyy\"),\n"
     "        WholeYears, FORMAT(First, \"yyyy\") & \" to \" & FORMAT(Last, \"yyyy\"),\n"
     "        FORMAT(First, \"mmm yyyy\") & \" to \" & FORMAT(Last, \"mmm yyyy\")\n"
     "    )", None,
     "A label for the period on screen: '2024', '2021 to 2024', or 'Mar 2023 to Jun 2023'."),
    ("Period End Label", "FORMAT(MAX('Date'[Date]), \"mmmm yyyy\")", None, None),
    ("Latest Order Date", "MAX(Sales[Order Date])", "d mmm yyyy", None),
]


# --------------------------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------------------------

def m_partition(table: str, spec: dict, local: bool) -> list[str]:
    if local:
        path = str((DATA / spec["file"]).resolve()).replace("\\", "\\\\")
        src = f'File.Contents("{path}")'
    else:
        src = f'Web.Contents("{RAW}{spec["file"]}")'
    n = len(spec["types"])
    types = ", ".join(f'{{"{c}", {t}}}' for c, t in spec["types"].items())
    return [
        f"\tpartition {q(table)} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document({src}, [Delimiter=",", Columns={n}, '
        f'Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        '\t\t\t\t    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'\t\t\t\t    #"Applied Types" = Table.TransformColumnTypes(#"Promoted Headers", {{{types}}})',
        "\t\t\t\tin",
        '\t\t\t\t    #"Applied Types"',
    ]


def write_table(name: str, spec: dict, local: bool) -> None:
    lines: list[str] = []
    lines += doc(spec.get("doc"), 0)
    lines.append(f"table {q(name)}")
    lines.append(f"\tlineageTag: {tag('table', name)}")
    if spec.get("date_table"):
        lines.append("\tdataCategory: Time")
    for c in spec["columns"]:
        lines.append("")
        lines += doc(c.get("doc"), 1)
        lines.append(f"\tcolumn {q(c['name'])}")
        lines.append(f"\t\tdataType: {c['dtype']}")
        if c.get("hidden"):
            lines.append("\t\tisHidden")
        if c.get("key"):
            lines.append("\t\tisKey")
        if c.get("format"):
            lines.append(f"\t\tformatString: {c['format']}")
        lines.append(f"\t\tlineageTag: {tag('column', name, c['name'])}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {c['source']}")
        if c.get("sortBy"):
            lines.append(f"\t\tsortByColumn: {q(c['sortBy'])}")
    lines.append("")
    lines += m_partition(name, spec, local)
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    write(DEFN / "tables" / f"{name}.tmdl", lines)


def write_metrics() -> None:
    lines: list[str] = []
    lines += doc("Measure-only table. Nothing here stores data; the hidden column exists because a\n"
                 "table needs one. Every number on the report comes from here.", 0)
    lines.append("table Metrics")
    lines.append(f"\tlineageTag: {tag('table', 'Metrics')}")
    for name, dax, fmt, d in MEASURES:
        lines.append("")
        lines += doc(d, 1)
        body = dax.split("\n")
        if len(body) == 1:
            lines.append(f"\tmeasure {q(name)} = {body[0]}")
        else:
            lines.append(f"\tmeasure {q(name)} =")
            for b in body:
                lines.append(("\t\t\t" + b) if b.strip() else "\t\t\t")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {tag('measure', name)}")
    lines.append("")
    lines.append("\tcolumn Column")
    lines.append("\t\tdataType: string")
    lines.append("\t\tisHidden")
    lines.append(f"\t\tlineageTag: {tag('column', 'Metrics', 'Column')}")
    lines.append("\t\tsummarizeBy: none")
    lines.append("\t\tsourceColumn: Column")
    lines.append("")
    lines.append("\tpartition Metrics = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\t\tlet")
    lines.append('\t\t\t\t    Source = #table(type table [Column = text], {})')
    lines.append("\t\t\t\tin")
    lines.append("\t\t\t\t    Source")
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    write(DEFN / "tables" / "Metrics.tmdl", lines)


def write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_json(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip("\n") + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="read data/ from disk instead of GitHub")
    args = ap.parse_args()

    if DEFN.exists():
        # OneDrive (and an open Desktop) intermittently hold a directory handle; retry, then
        # fall back to ignore_errors - by then the files are gone and the writers recreate the tree.
        for attempt in range(5):
            try:
                shutil.rmtree(DEFN)
                break
            except PermissionError:
                if attempt == 4:
                    shutil.rmtree(DEFN, ignore_errors=True)
                else:
                    time.sleep(0.5)

    for name, spec in TABLES.items():
        write_table(name, spec, args.local)
    write_metrics()

    write(DEFN / "database.tmdl", ["database", "\tcompatibilityLevel: 1606"])

    order = ", ".join(f'"{t}"' for t in TABLES)
    write(DEFN / "model.tmdl", [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "",
        f"annotation PBI_QueryOrder = [{order}]",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
    ] + [f"ref table {q(t)}" for t in list(TABLES) + ["Metrics"]])

    rel_lines: list[str] = []
    for i, (name, frm, to) in enumerate(RELATIONSHIPS):
        if i:
            rel_lines.append("")
        rel_lines += [f"relationship {q(name)}", f"\tfromColumn: {frm}", f"\ttoColumn: {to}"]
    write(DEFN / "relationships.tmdl", rel_lines)

    write_json(MODEL / "definition.pbism", """
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
  "version": "4.2",
  "settings": {
    "qnaEnabled": true
  }
}""")
    write_json(MODEL / ".platform", f"""
{{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
  "metadata": {{
    "type": "SemanticModel",
    "displayName": "Superstore Sales"
  }},
  "config": {{
    "version": "2.0",
    "logicalId": "{tag('platform', 'model')}"
  }}
}}""")

    n_cols = sum(len(s["columns"]) for s in TABLES.values())
    print(f"{len(TABLES) + 1} tables, {n_cols} columns, {len(MEASURES)} measures, "
          f"{len(RELATIONSHIPS)} relationships -> {MODEL.name} "
          f"({'local files' if args.local else 'GitHub raw'})")


if __name__ == "__main__":
    main()
