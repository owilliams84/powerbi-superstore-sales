# Superstore Sales

A Power BI report on four years of a US office-supplies retailer's orders — the sample every
Power BI course starts on, rebuilt properly. A star schema with a marked date table, forty measures
that were checked against pandas before anything was drawn, and a four-page report in the
Milestone BI palette.

![The overview page](screenshots/overview.png)

## Where the data comes from

**Source: [Superstore Sales Dataset](https://www.kaggle.com/datasets/rohitsahoo/sales-forecasting)
on Kaggle** — the 18-column extract of Tableau's Superstore sample: 9,800 order lines, 4,922
orders, 793 customers, 1,893 products, 49 states. It carries sales but not profit, quantity or
discount, so the report can say what sold and to whom, not what it earned.

> **Licence.** Kaggle lists the dataset under GPL-2, which permits redistribution, so both the
> source file and the star schema derived from it are committed under `data/` — clone the repo and
> the model has everything it needs.

**The dates were moved.** The extract covered 2017–2020. `etl/shift_dates.py` moved every order
and ship date forward four whole years so the report reads as 2021–2024. The gap between order and
ship is untouched, and 29 February 2020 lands on 29 February 2024, which exists. The year token
inside each Order ID (`CA-2015-103800`) already trailed its order date by two years and was
re-synced to the shifted year, or it would have sat six behind.

| | |
|---|---|
| Fact rows | 9,800 order lines, $2,261,536.78 — foots to the source to the cent |
| Orders | 4,922 (an order averages two lines) |
| Period | 3 January 2021 to 30 December 2024 |
| Customers | 793, in three segments |
| Products | 1,893 (ID, name) pairs across 17 sub-categories |
| Geography | 628 places in 49 states and four regions |

## What the ETL found

None of this is visible until you go looking, and all of it changes the answer.

**Product ID is not a key.** 32 IDs carry two different product names, and 16 names sit under two
IDs. Keying on either merges products that differ or splits ones that do not, so the product
dimension is the (ID, name) pair with a surrogate key. Product ID stays visible for reference.

**Postal codes lost their leading zero.** The source stored them as numbers, so 429 New England
and New Jersey codes arrived four digits long (`1841` for Lowell MA, which is `01841`). They are
text again, padded back to five. Eleven rows — all Burlington, Vermont — have no code at all and stay
blank rather than being looked up.

**Customers have no address.** 777 of 793 customers order from more than one state. Geography
belongs to the order line, not the customer, and the model is built that way: a customer dimension
with a state on it would have been wrong for nearly all of them.

**The customer base is closed.** New customers fall from 589 in 2021 to 141, 52 and 11, and
retention *rises* over time. Neither happens in a real business; both happen when a sample is drawn
by order rather than by customer. The customer page is built around retention because that is the
only customer story this data can honestly tell.

**Order-to-ship is recorded for every line.** Zero to eight days, mean 3.96, and it never goes
negative — the one thing about the dates that needed no cleaning.

## The model

Six tables around one fact, plus a measure table.

```
    Date ────────┐
    Customer ────┤
    Product ─────┼──────► Sales   (one row per order line)
    Geography ───┤
    Ship Mode ───┘
```

**The date table is marked.** One row per day, 2021 to 2024, contiguous, `dataCategory: Time` —
so `DATEADD` and `TOTALYTD` walk a real calendar. Without the marking `Sales PY` returns blank for
every row and the year-over-year column quietly looks like 2021 forever.

**The fact is hidden end to end.** `Sales[Sales]` is the only amount, and the measures own how it
is aggregated: distinct orders rather than rows, customers counted on the fact so every filter
narrows them, shares computed against a denominator that clears the right filters.

### The measures worth looking at

**`New Customers` filters the fact, not the dimension.** It takes the period's first and last date
and keeps customers whose `First Order Date` falls between them — so a product or region on the
visual still applies and the number becomes "new customers who bought this".

**`Retention %` on a cohort × year matrix.** `Cohort Size` clears the date filter so the
denominator is the whole cohort whatever year the column is; the cohort's own year is 100% by
definition and earlier years are blank.

**`Customers Active Every Year` counts years on the fact.** The first version counted
`DISTINCTCOUNT('Date'[Year])` and returned 793 — the whole calendar for every customer, because a
fact table cannot filter its dimension. `SUMMARIZE(Sales, 'Date'[Year])` returns 293. The number
looked perfectly plausible on screen; the pandas cross-check is what caught it.

**`Standard Class Share` uses `KEEPFILTERS`.** Without it the filter would overwrite a ship mode
already on the visual and repeat the grand total down a breakdown. The verification query checks
that the share differs by region, which it must.

**`Cumulative Sales Share` is the Pareto line.** For each sub-category, the share of sales from it
and every sub-category selling more than it — so on a chart sorted by sales it climbs from 14% to
100%, and the point where it crosses two-thirds is five bars in.

## The report

Six pages, 1440 × 900, in the Milestone BI palette — near-black indigo, gold, and the site's
greys — with the brand mark in a band across the top of every page.

**01 Overview** — headline figures, sales by month with one line per year, a year-by-year table,
and sales by segment, category mix and region.

**02 Products** — sub-categories ranked with the cumulative share, change on the prior year (the
year slicer defaults to 2024 so this has a prior year), every product ranked, and category by
segment.

![The products page](screenshots/products.png)

**03 Customers** — active, new and returning customers by year, cohort retention, customers by
lifetime order count, average order value by segment, and customers ranked.

![The customers page](screenshots/customers.png)

**04 Geography and shipping** — every state ranked, region by quarter, ship mode share and days to
ship, ship mode mix by year, cities ranked.

![The geography page](screenshots/geography.png)

**05 Revenue** — one year against a comparison year, where every block is a measure. Buttons pick
the year (2022–2024), the comparison (prior year or two years earlier), month-by-month or running
total, and Top or Bottom 8 on each table; a Filters button opens a panel of segment, region and
category slicers over a dimmed page.

![The revenue page](screenshots/revenue.png)

It is built from techniques the other pages do not use, each generated rather than placed:

- **KPI cards are SVG.** Each card — ring gauge, region tiles, a bar per sub-category — is one DAX
  measure with `dataCategory: ImageUrl` returning an SVG data URI, shown in an image visual.
  `%` and `#` are percent-encoded, in that order, or "20.3%" breaks the image.
- **Bars inside the tables are SVG too**, one per row, all drawn to one scale.
- **Button slicers on disconnected tables.** `Comparison`, `Line View` and the two ranking tables
  have no relationships; measures read the choice with `SELECTEDVALUE`, and `DATEADD` takes the
  one-or-two-year offset from a variable.
- **Top/Bottom that flips.** A TopN filter has a fixed direction, so the rank is a measure whose
  direction follows the button, and the table keeps ranks 1–8 with a visual-level measure filter.
  That filter also narrows `ALLSELECTED` to the eight rows on screen — the subtitle first read
  "among 8 customers" — so every pool and scale uses `ALL` instead.
- **Titles rewrite themselves.** Panel titles, subtitles and the standfirst are measures; the
  standfirst is a transparent shape whose title is the measure, because a textbox cannot bind one.
- **The filter panel is two bookmarks** that show or hide the panel's visuals and carry no data
  state, so opening it never resets a slicer.

The page was mocked up in HTML first with the real figures (`design/revenue-mockup.html`), then
generated. Every number on it was checked over XMLA against `etl/revenue_expected.py` for 2024
against 2023 and against 2022, to the cent.

![The revenue page with the other states: two years earlier, running total, Bottom 8, filters open](screenshots/revenue-other-states.png)

**06 Calendar** — sales as a heat-mapped calendar, at four grains. Day is a Monday-first month
grid, one cell per order date, under Month and Year dropdowns; Month is the twelve months of a year,
a quarter to a row; Quarter is a year to a row; Year is one cell per year. Buttons switch between
them. Two cards follow the view — sales against the same period a year earlier, and the busiest
day, month, quarter or year — and a bar chart gives average sales per trading day by weekday.

![The calendar page, day view](screenshots/calendar.png)

It is a native matrix rather than a custom visual, so there is nothing to install and it works the
same in the Service:

- **Every cell is an SVG measure**, as on the Revenue page, but at 112 × 88 up to 266 × 138. A
  matrix cell holds one string; the SVG puts the day number in one corner, the sales in the middle
  and the order count in another. The same colour is also bound to the cell background, so a cell
  wider than its image is still one block. Clicking a cell cross-filters the page like any matrix.
- **Shade is a rank, not a scale.** Five bands, each cell placed by its position among the cells
  on screen. On a linear scale one $13k day turns the rest of the month the same pale blue. The
  ramp runs pale to navy; green and red stay reserved for above and below a comparison.
- **The four views are four matrices and four bookmarks.** Each bookmark shows its own matrix,
  cards, bars and standfirst, hides the other three, and carries no data state. Field parameters
  would do it in one matrix, but not in generated PBIR.
- **A dropdown that means nothing at a grain is cut off from that grain.** The Month dropdown is
  hidden in the Month view but still holds a selection. The matrices and bar charts are protected
  by `visualInteractions` in `page.json`; the cards and titles, being measures, also remove the
  filter in DAX.
- **The week rows come from two calculated columns** — `Week of Month` and `Day Short` — written in
  DAX rather than added to the CSV, because the model reads its data from this repository.

Mocked up first (`design/calendar-mockup.html`, clickable), then generated. Every cell of all four
views — 1,529 of them, for sales, distinct orders and shade band — is read out of the live model by
`etl/verify_calendar.ps1` and diffed against pandas by `etl/calendar_expected.py`: 4,587 checks,
no mismatches.

![The calendar page zoomed out to months](screenshots/calendar-month.png)

### Some of what it says

| | |
|---|---|
| Sales, 2021–2024 | $2,261,537 in 4,922 orders — $459 an order |
| 2024 against 2023 | +20.3%, after +30.6% the year before and −4.3% the year before that |
| Customers | 793, of whom 98.4% ordered more than once and 293 ordered in every one of the four years |
| Retention of the 2021 cohort | 72% in 2022, 81% in 2023, 87% in 2024 |
| Top sub-categories | Phones and Chairs, 14% each; five sub-categories are 55% of 2024 |
| Top states | California 19.7%, New York 13.6%, Texas 7.5% |
| Shipping | Standard Class is 59.8% of orders at 5.0 days; Same Day is 5.3% at 0.0 |
| Top product | Canon imageCLASS 2200 Advanced Copier, $61,600 on three orders |
| Where 2024's growth came from | Orders +28.3%, average order −6.2%: more orders, not bigger ones |
| Against 2023 | 445 of 773 customers, 3 of 4 regions (not Central) and 14 of 17 sub-categories grew; Machines fell most, −$12,362 |

## Rebuilding

The model reads its CSVs straight from this repository over HTTPS, so there is no path to repoint:
open `Superstore Sales.pbip` in Power BI Desktop and refresh. Desktop asks once per machine to
confirm anonymous access to `raw.githubusercontent.com`.

Rebuilding the data, model or report from scratch:

```bash
python etl/shift_dates.py <kaggle-train.csv> data/source/Sales.csv --years 4
python etl/build_star_schema.py   # re-derives data/ from data/source/ (needs pandas)
python etl/build_model.py         # regenerates the TMDL model (--local to read data/ from disk)
python etl/build_report.py        # regenerates the PBIR pages, theme and brand mark
```

### Checking your work

```bash
# TMDL parses? Desktop's failure mode for malformed TMDL is a blank window and no error.
powershell -File etl/check_tmdl.ps1

# PBIR valid?
powerbi-report-author validate "Superstore Sales.pbip"

# With the PBIP open in Desktop: load the data, then read the measures back out of the live
# model and compare with the same figures computed in pandas with no DAX involved.
powershell -File etl/refresh_model.ps1
powershell -File etl/verify_measures.ps1
python etl/verify_expected.py

# The revenue page, for any year and comparison
powershell -File etl/verify_revenue.ps1 -Year 2024 -Comparison "Two years earlier"
python etl/revenue_expected.py 2024 2022

# The calendar page: every cell of all four views, diffed automatically
powershell -File etl/verify_calendar.ps1 > calendar_dump.txt
python etl/calendar_expected.py --compare calendar_dump.txt
```

Every figure in `verify_measures.ps1` matched `verify_expected.py` to four decimal places — after
the one that did not was fixed. `verify_revenue.ps1` matched `revenue_expected.py` to the cent. A
separate query against the published model with Region = West pinned is what caught the regions
card ignoring the filter panel.

## Repository layout

```
data/source/Sales.csv             the extract, dates shifted to 2021-2024
data/                             the star schema the model loads
etl/shift_dates.py                the +4 year shift, with the Order ID re-sync
etl/build_star_schema.py          cleaning and dimensional build, with assertions
etl/build_model.py                generates the TMDL semantic model
etl/revenue_measures.py           the revenue page's measures, SVG cards and toggle tables
etl/build_report.py               generates the PBIR report definition, theme, bookmarks and brand mark
etl/build_web_data.py             emits the compact JSON the milestonebi.com page reads
etl/publish_to_service.ps1        publishes model + report to a workspace, sets creds, refreshes
etl/crop_screenshots.py           crops Desktop captures to the report canvas
etl/check_tmdl.ps1                parses the TMDL with Desktop's own serializer
etl/refresh_model.ps1             refreshes the open model over its local XMLA endpoint
etl/verify_measures.ps1           reads the measures back out of the live model
etl/verify_expected.py            the same figures from the CSVs, in pandas
etl/verify_revenue.ps1            reads every revenue-page figure out of the live model
etl/revenue_expected.py           the revenue page's figures from the CSVs, in pandas
etl/calendar_measures.py          the calendar page's SVG cells, shade bands, cards and Date columns
etl/verify_calendar.ps1           dumps every calendar cell out of the live model
etl/calendar_expected.py          the same cells from the CSVs, and the diff
design/                           the HTML mockups the revenue and calendar pages were built from
web/superstore-sales.json         the page's data - about 100x smaller than the star schema
Superstore Sales.SemanticModel/   TMDL: 11 tables, 112 measures
Superstore Sales.Report/          PBIR: 6 pages, 119 visuals, 6 bookmarks, theme, brand mark
```

Both the model and the report are generated rather than hand-edited. TMDL is indentation-sensitive
and forbids blank lines inside an object; PBIR wraps every property in an envelope whose type
suffix is load-bearing. Generating both keeps those rules in one place and lets the schema and the
pages read as what they are.

## Publishing to the Power BI Service

The model's data sources are literal `raw.githubusercontent.com` URLs, one per CSV, which is what
lets the published dataset refresh in the cloud **with no on-premises gateway** - the whole reason
the data is committed rather than read from a local folder.

```bash
az login
powershell -File etl/publish_to_service.ps1 -WorkspaceId <guid>
```

One script does the lot: publishes the semantic model, publishes the report bound to it, sets
anonymous credentials on all six Web datasources, triggers a refresh and waits for it. Three
things it knows that cost time to find out:

- **A personal workspace works.** The Fabric item APIs accept a workspace of `"type": "Personal"`
  - "My workspace" - which the documentation does not say. Get its id from
  `GET https://api.fabric.microsoft.com/v1/workspaces`; it will not appear in
  `/v1.0/myorg/groups`, which lists shared workspaces only.
- **Create is asynchronous, and `az rest` hides the operation id** unless you pass `--verbose`. So
  the script polls for the *item* instead, for five minutes. A shorter wait reports a failure while
  the create is still in flight, and the obvious response - run it again - produces a second item
  with the same name.
- **`/datasources` returns 404 for a minute or so after the definition lands**, while the dataset
  finishes provisioning. That is not a missing dataset; it is a dataset that does not exist yet.

## The same report, on the web

The charts at
**[milestonebi.com/superstore-sales](https://www.milestonebi.com/superstore-sales/)** are this
report redrawn as hand-written SVG, reading `web/superstore-sales.json`. That file is generated by
`etl/build_web_data.py` from the same star schema with the same definitions as the DAX measures, so
the two agree to the cent.

## Licence

Code in this repository is MIT (see [LICENSE](LICENSE)). The data under `data/` is redistributed
under the GPL-2 licence Kaggle lists for the dataset, and originates from Tableau's Superstore sample.
