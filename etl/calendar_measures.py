"""Measures and Date columns behind the Calendar page.

The page is one heat-mapped calendar seen at four grains - Day, Month, Quarter, Year - and each
grain is its own matrix, swapped by a bookmark. A matrix cell is an SVG image measure, because a
plain cell holds one string and the design wants a label in one corner, the value in the middle
and the order count in another.

Three things to know before editing:

* Shade is a rank, not a scale. A cell's band (1-5) is its position among the cells on screen,
  cut into fifths. On a linear scale one freak day turns the rest of the month the same pale blue.
  The arithmetic is integer - INT(below * 5 / (n - 1)) - so DAX and etl/calendar_expected.py
  cannot disagree over a float that lands a hair under a boundary.
* The pool a cell is ranked against is ALLSELECTED('Date'): the matrix's own row and column
  filters come off, the slicers stay on.
* The Month and Year dropdowns only mean something at some grains. The matrices and bar charts
  are cut off from them with visualInteractions in page.json; the measure-only visuals (cards,
  titles, standfirst) cannot rely on that, so their measures take the same filters off in DAX.
  `VIEWS[...]["scope"]` is that list of columns.
"""

from __future__ import annotations

from revenue_measures import svg_uri

USD = "\\$#,0"
INT = "#,0"

GOOD, BAD, INK, BODY, MUTED, RULE, GOLD, NAVY, SLATE, PAPER = (
    "#1E7A4C", "#B3261E", "#0A0917", "#4A5768", "#667284", "#E3E7EF", "#C9A227", "#111F38",
    "#7C8598", "#F4F6FA")

# Magnitude ramp, quiet to busy. Blue-greys to NAVY: green and red are kept for above/below a
# comparison, and a quiet day is not a bad one.
BANDS = ["#E6E9F1", "#BCC1D2", "#7C8598", "#3E4A66", "#111F38"]
DARK_FROM = 3        # bands from here up take white text

FOLDER = "Calendar page"
CARD_W, CARD_H = 476, 152

# Calculated columns added to the Date table: (name, dax, dtype, format, sortBy, hidden, doc)
DATE_COLUMNS = [
    ("Day of Month", "DAY('Date'[Date])", "int64", "0", None, True, None),
    ("Day Short", "LEFT('Date'[Day], 3)", "string", None, "Day of Week", False,
     "Mon to Sun, in that order - the calendar's column headers."),
    ("Week of Month",
     "INT((DAY('Date'[Date]) + WEEKDAY(DATE(YEAR('Date'[Date]), MONTH('Date'[Date]), 1), 2) - 2) / 7) + 1",
     "int64", "0", None, True,
     "Which row of a Monday-first month grid the day sits on: 1 to 6."),
    ("Month in Quarter No", "MOD('Date'[Month No] - 1, 3) + 1", "int64", "0", None, True, None),
    ("Month in Quarter",
     'SWITCH(MOD(\'Date\'[Month No] - 1, 3) + 1, 1, "1st month", 2, "2nd month", "3rd month")',
     "string", None, "Month in Quarter No", False,
     "Position of the month inside its quarter - the Month view's column headers."),
]

# grain: the column with one value per cell. scope: slicer columns that mean nothing at this grain.
VIEWS = {
    "Day": dict(grain="'Date'[Date]", scope=[], w=112, h=88,
                top='FORMAT(DAY(SELECTEDVALUE(\'Date\'[Date])), "00")'),
    "Month": dict(grain="'Date'[Month No]", scope=["'Date'[Month]"], w=266, h=138,
                  top="SELECTEDVALUE('Date'[Month Short])"),
    "Quarter": dict(grain="'Date'[Quarter Year Sort]", scope=["'Date'[Month]", "'Date'[Year]"], w=196, h=138,
                    top="SELECTEDVALUE('Date'[Quarter Year])"),
    "Year": dict(grain="'Date'[Year]", scope=["'Date'[Month]", "'Date'[Year]"], w=196, h=230,
                 top='FORMAT(SELECTEDVALUE(\'Date\'[Year]), "0")'),
}


def M(name, dax, fmt=None, doc=None, category=None):
    return {"name": name, "dax": dax.strip("\n"), "fmt": fmt, "doc": doc,
            "category": category, "folder": FOLDER}


def short_money(v: str) -> str:
    """$1.23M / $12.3k / $1.23k / $123 - the same cuts as the mockup's money()."""
    return (f'SWITCH(TRUE(), {v} >= 1000000, "$" & FORMAT({v} / 1000000, "0.00") & "M", '
            f'{v} >= 10000, "$" & FORMAT({v} / 1000, "0.0") & "k", '
            f'{v} >= 1000, "$" & FORMAT({v} / 1000, "0.00") & "k", "$" & FORMAT({v}, "0"))')


def scoped(expr: str, view: str) -> str:
    cols = VIEWS[view]["scope"]
    return f"CALCULATE({expr}, REMOVEFILTERS({', '.join(cols)}))" if cols else expr


def pool(view: str) -> str:
    """Every cell of this view with its sales, under the slicers but not the matrix's own axes."""
    return f"CALCULATETABLE(ADDCOLUMNS(VALUES({VIEWS[view]['grain']}), \"@v\", [Sales]), ALLSELECTED('Date'))"


def cell_measures(view: str) -> list[dict]:
    spec = VIEWS[view]
    w, h = spec["w"], spec["h"]
    band = f"[Cal Band {view}]"
    fills = ", ".join(f'{i + 1}, "{c}"' for i, c in enumerate(BANDS))
    return [
        M(f"Cal Band {view}", f"""
VAR Me = [Sales]
VAR Live = FILTER({pool(view)}, [@v] > 0)
VAR N = COUNTROWS(Live)
VAR Below = COUNTROWS(FILTER(Live, [@v] < Me))
RETURN
    IF(
        HASONEVALUE({spec['grain']}),
        IF(Me > 0, MIN(5, INT(DIVIDE(Below * 5, N - 1, 5)) + 1), 0)
    )""", "0",
          "1 (quietest fifth of the cells on screen) to 5 (busiest); 0 for a cell with no sales;\n"
          "blank where the grid has no such cell. Rank-based so one outlier cannot flatten the rest."),
        M(f"Cal Colour {view}", f"""
VAR Band = {band}
RETURN
    IF(NOT ISBLANK(Band), SWITCH(Band, {fills}, "{PAPER}"))""", None,
          "Cell background for the band. Bound to the matrix's background colour."),
        M(f"Cal Cell {view}", f"""
VAR Band = {band}
VAR V = [Sales]
VAR N = [Orders]
VAR Fg = SWITCH(TRUE(), Band = 0, "{MUTED}", Band >= {DARK_FROM}, "#FFFFFF", "{INK}")
VAR Bg = [Cal Colour {view}]
VAR Svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}' font-family='Segoe UI, sans-serif'>"
        & "<rect width='{w}' height='{h}' fill='" & Bg & "'/>"
        & "<text x='8' y='17' font-size='11.5' font-weight='600' fill='" & Fg & "' opacity='0.85'>" & {spec['top']} & "</text>"
        & IF(
            Band = 0,
            "<text x='{w // 2}' y='{h // 2 + 5}' font-size='13' text-anchor='middle' fill='{MUTED}'>&#8211;</text>",
            "<text x='{w // 2}' y='{h // 2 + 6}' font-size='17' font-weight='700' text-anchor='middle' fill='" & Fg & "'>" & {short_money('V')} & "</text>"
                & "<text x='{w - 8}' y='{h - 8}' font-size='10.5' text-anchor='end' fill='" & Fg & "' opacity='0.8'>" & FORMAT(N, "#,0") & IF(N = 1, " order", " orders") & "</text>"
        )
        & "</svg>"
RETURN
    IF(NOT ISBLANK(Band), {svg_uri()})""", None,
          f"One calendar cell at the {view} grain, drawn at {w}x{h}: label top left, sales in the\n"
          "middle, orders bottom right, on the band's colour. A cell with no sales shows a dash.",
          category="ImageUrl"),
    ]


def card(label: str, value: str, note: str, rows: list[tuple[str, str]]) -> str:
    """The Calendar page's KPI card frame, 476x152. Arguments are DAX text expressions; `note` may
    carry <tspan> markup. Up to three (left, right) rows under the rule."""
    ys = [111, 128, 145][:len(rows)] if len(rows) == 3 else [114, 134][:len(rows)]
    body = [
        f'"<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'{CARD_W}\' height=\'{CARD_H}\' viewBox=\'0 0 {CARD_W} {CARD_H}\' font-family=\'Segoe UI, sans-serif\'>"',
        f'& "<rect x=\'0.5\' y=\'0.5\' width=\'{CARD_W - 1}\' height=\'{CARD_H - 1}\' rx=\'4\' fill=\'#FFFFFF\' stroke=\'{RULE}\'/><rect width=\'3\' height=\'{CARD_H}\' fill=\'{GOLD}\'/>"',
        f'& "<text x=\'16\' y=\'24\' font-size=\'11\' font-weight=\'700\' fill=\'{MUTED}\' letter-spacing=\'0.4\'>" & {label} & "</text>"',
        f'& "<text x=\'16\' y=\'58\' font-size=\'28\' font-weight=\'700\' fill=\'{INK}\'>" & {value} & "</text>"',
        f'& "<text x=\'16\' y=\'77\' font-size=\'11.5\' fill=\'{MUTED}\'>" & {note} & "</text>"',
        f'& "<line x1=\'16\' y1=\'90\' x2=\'{CARD_W - 16}\' y2=\'90\' stroke=\'{RULE}\'/>"',
    ]
    for y, (left, right) in zip(ys, rows):
        body.append(f'& "<text x=\'16\' y=\'{y}\' font-size=\'11.5\' fill=\'{BODY}\'>" & {left} & "</text>'
                    f'<text x=\'{CARD_W - 16}\' y=\'{y}\' font-size=\'11.5\' font-weight=\'600\' text-anchor=\'end\' fill=\'{INK}\'>" & {right} & "</text>"')
    body.append('& "</svg>"')
    return "\n".join(body)


def change_tspan(change: str) -> str:
    """'▲ 49.2%' in green or '▼ 4.3%' in red, as an SVG tspan."""
    return (f'"<tspan font-weight=\'700\' fill=\'" & IF({change} >= 0, "{GOOD}", "{BAD}") & "\'>" & '
            f'IF({change} >= 0, "&#9650; ", "&#9660; ") & FORMAT(ABS({change}), "0.0%") & "</tspan>"')


def change_words(change: str) -> str:
    return f'IF({change} >= 0, "up ", "down ") & FORMAT(ABS({change}), "0.0%")'


def indent(text: str, n: int = 1) -> str:
    return "\n".join(("    " * n + line) if line else line for line in text.split("\n"))


ORDINAL = ('VAR Sfx = SWITCH(TRUE(), MOD(BestDay, 100) IN {11, 12, 13}, "th", MOD(BestDay, 10) = 1, "st", '
           'MOD(BestDay, 10) = 2, "nd", MOD(BestDay, 10) = 3, "rd", "th")')


def measures() -> list[dict]:
    out: list[dict] = []
    for view in VIEWS:
        out += cell_measures(view)

    # ---- period labels and whole-view totals ------------------------------------------------
    out += [
        M("Cal Trading Days", "COUNTROWS(FILTER(VALUES('Date'[Date]), [Sales] > 0))", INT,
          "Days with at least one order. 228 of the 1,458 days in the data have none."),
        M("Avg Sales per Trading Day", "DIVIDE([Sales], [Cal Trading Days])", USD,
          "Sales divided by the days that had orders, so a weekday is not marked down for the\n"
          "weeks it happened to be empty."),
        M("Cal Weekday Colour", f'IF(SELECTEDVALUE(\'Date\'[Is Weekend]) = "Yes", "{SLATE}", "{NAVY}")', None,
          "Weekends in slate on the weekday bars."),
        M("Cal Month Label", "SELECTEDVALUE('Date'[Month], \"All months\") & \" \" & SELECTEDVALUE('Date'[Year], \"all years\")"),
    ]

    # ---- total card ---------------------------------------------------------------------------
    for view, prev_label in (("Day", 'FORMAT(EDATE(MIN(\'Date\'[Date]), -12), "mmm yyyy")'),
                             ("Month", 'FORMAT(MAX(\'Date\'[Year]) - 1, "0")')):
        out.append(M(f"Card Cal Total {view}", scoped(f"""
VAR Cur = [Sales]
VAR Prev = [Sales PY]
VAR Change = DIVIDE(Cur - Prev, Prev)
VAR NoteText =
    IF(
        Prev > 0,
        {change_tspan('Change')} & " on " & {prev_label} & " (" & {short_money('Prev')} & ")",
        "No sales a year earlier to compare with"
    )
VAR Svg =
{indent(card('"SALES IN VIEW"', short_money('Cur'), 'NoteText',
             [('"Orders"', 'FORMAT([Orders], "#,0")'), ('"Average order"', '"$" & FORMAT([Average Order Value], "#,0")')]), 1)}
RETURN
    {svg_uri()}""", view), None,
                     f"Sales for what the {view} view shows, against the same period a year earlier.",
                     category="ImageUrl"))
    out.append(M("Card Cal Total All", scoped(f"""
VAR Cur = [Sales]
VAR YearCount = COUNTROWS(VALUES('Date'[Year]))
VAR Svg =
{indent(card('"SALES IN VIEW"', short_money('Cur'),
             '"All " & YearCount & " years - nothing earlier to compare with"',
             [('"Orders"', 'FORMAT([Orders], "#,0")'), ('"Average order"', '"$" & FORMAT([Average Order Value], "#,0")')]), 1)}
RETURN
    {svg_uri()}""", "Quarter"), None,
                 "Sales across every year, for the Quarter and Year views.", category="ImageUrl"))

    # ---- peak cards ---------------------------------------------------------------------------
    out.append(M("Card Cal Peak Day", f"""
VAR Pool = ADDCOLUMNS(VALUES('Date'[Date]), "@v", [Sales])
VAR Best = MAXX(Pool, [@v])
VAR BestDate = MINX(FILTER(Pool, [@v] = Best), 'Date'[Date])
VAR DaysAll = COUNTROWS(Pool)
VAR Quiet = DaysAll - [Cal Trading Days]
VAR Svg =
{indent(card('"BUSIEST DAY"', short_money('Best'), 'FORMAT(BestDate, "ddd d mmmm yyyy")',
             [('"Average per trading day"', short_money('[Avg Sales per Trading Day]')),
              ('"Days with no orders"', 'Quiet & " of " & DaysAll'),
              ('"Busiest day&apos;s share of the month"', 'FORMAT(DIVIDE(Best, [Sales]), "0.0%")')]), 1)}
RETURN
    {svg_uri()}""", None, "The best single day of the month on screen.", category="ImageUrl"))

    out.append(M("Card Cal Peak Month", scoped(f"""
VAR Pool = FILTER(ADDCOLUMNS(SUMMARIZE('Date', 'Date'[Month No], 'Date'[Month], 'Date'[Month Short]), "@v", [Sales]), [@v] > 0)
VAR Best = MAXX(Pool, [@v])
VAR Worst = MINX(Pool, [@v])
VAR BestName = MINX(FILTER(Pool, [@v] = Best), 'Date'[Month])
VAR WorstName = MINX(FILTER(Pool, [@v] = Worst), 'Date'[Month Short])
VAR Svg =
{indent(card('"BIGGEST MONTH"', short_money('Best'), 'BestName & " " & MAX(\'Date\'[Year])',
             [('"Average per month"', short_money('DIVIDE([Sales], COUNTROWS(Pool))')),
              ('"Smallest month"', 'WorstName & " &#183; " & ' + short_money('Worst')),
              ('"Biggest month&apos;s share of the year"', 'FORMAT(DIVIDE(Best, [Sales]), "0.0%")')]), 1)}
RETURN
    {svg_uri()}""", "Month"), None, "The best month of the year on screen.", category="ImageUrl"))

    out.append(M("Card Cal Peak Quarter", scoped(f"""
VAR Pool = FILTER(ADDCOLUMNS(SUMMARIZE('Date', 'Date'[Quarter Year Sort], 'Date'[Quarter Year]), "@v", [Sales]), [@v] > 0)
VAR Best = MAXX(Pool, [@v])
VAR BestName = MINX(FILTER(Pool, [@v] = Best), 'Date'[Quarter Year])
VAR AllSales = [Sales]
VAR Svg =
{indent(card('"BIGGEST QUARTER"', short_money('Best'), 'BestName',
             [('"Average per quarter"', short_money('DIVIDE(AllSales, COUNTROWS(Pool))')),
              ('"Q4 share of all sales"', 'FORMAT(DIVIDE(CALCULATE([Sales], \'Date\'[Quarter] = "Q4"), AllSales), "0.0%")'),
              ('"Q1 share of all sales"', 'FORMAT(DIVIDE(CALCULATE([Sales], \'Date\'[Quarter] = "Q1"), AllSales), "0.0%")')]), 1)}
RETURN
    {svg_uri()}""", "Quarter"), None, "The best quarter of all, and how lopsided the year is.", category="ImageUrl"))

    out.append(M("Card Cal Peak Year", scoped(f"""
VAR Pool = FILTER(ADDCOLUMNS(VALUES('Date'[Year]), "@v", [Sales]), [@v] > 0)
VAR Best = MAXX(Pool, [@v])
VAR BestYear = MINX(FILTER(Pool, [@v] = Best), 'Date'[Year])
VAR YearLast = MAXX(Pool, 'Date'[Year])
VAR YearFirst = MINX(Pool, 'Date'[Year])
VAR SalesLast = MAXX(FILTER(Pool, 'Date'[Year] = YearLast), [@v])
VAR SalesBefore = MAXX(FILTER(Pool, 'Date'[Year] = YearLast - 1), [@v])
VAR SalesFirst = MAXX(FILTER(Pool, 'Date'[Year] = YearFirst), [@v])
VAR SalesSecond = MAXX(FILTER(Pool, 'Date'[Year] = YearFirst + 1), [@v])
VAR ChangeLast = DIVIDE(SalesLast - SalesBefore, SalesBefore)
VAR ChangeSecond = DIVIDE(SalesSecond - SalesFirst, SalesFirst)
VAR Svg =
{indent(card('"BIGGEST YEAR"', short_money('Best'), 'FORMAT(BestYear, "0")',
             [('"Average per year"', short_money('DIVIDE([Sales], COUNTROWS(Pool))')),
              ('YearLast & " on " & (YearLast - 1)', change_tspan('ChangeLast')),
              ('(YearFirst + 1) & " on " & YearFirst', change_tspan('ChangeSecond'))]), 1)}
RETURN
    {svg_uri()}""", "Year"), None, "The best year, and the two year-on-year moves at either end.", category="ImageUrl"))

    # ---- titles and standfirsts -------------------------------------------------------------------
    out += [
        M("Title Cal Day", f"""
VAR Cur = [Sales]
RETURN
    [Cal Month Label] & ": " & {short_money('Cur')} & " across " & [Cal Trading Days] & " trading days" """,
          None, "Panel title of the Day calendar."),
        M("Title Cal Month", scoped(f"""
VAR Pool = ADDCOLUMNS(SUMMARIZE('Date', 'Date'[Month No], 'Date'[Month]), "@v", [Sales])
VAR Best = MAXX(Pool, [@v])
VAR Cur = [Sales]
RETURN
    MAX('Date'[Year]) & ": " & {short_money('Cur')} & ", and " & MINX(FILTER(Pool, [@v] = Best), 'Date'[Month]) & " was the biggest month" """, "Month"),
          None, "Panel title of the Month calendar."),
        M("Title Cal Quarter", scoped("""
VAR Pool = ADDCOLUMNS(VALUES('Date'[Quarter]), "@v", [Sales])
VAR Best = MAXX(Pool, [@v])
RETURN
    MINX(FILTER(Pool, [@v] = Best), 'Date'[Quarter]) & " brings in " & FORMAT(DIVIDE(Best, [Sales]), "0%") & " of all sales, more than any other quarter" """, "Quarter"),
          None, "Panel title of the Quarter calendar: which quarter number carries the most."),
        M("Title Cal Year", scoped(f"""
VAR Pool = FILTER(ADDCOLUMNS(VALUES('Date'[Year]), "@v", [Sales]), [@v] > 0)
VAR YearLast = MAXX(Pool, 'Date'[Year])
VAR YearFirst = MINX(Pool, 'Date'[Year])
VAR SalesLast = MAXX(FILTER(Pool, 'Date'[Year] = YearLast), [@v])
VAR SalesFirst = MAXX(FILTER(Pool, 'Date'[Year] = YearFirst), [@v])
VAR Change = DIVIDE(SalesLast - SalesFirst, SalesFirst)
RETURN
    YearLast & " closed at " & {short_money('SalesLast')} & ", " & {change_words('Change')} & " on " & YearFirst """, "Year"),
          None, "Panel title of the Year calendar."),
        M("Title Cal Weekday", """
VAR Pool = FILTER(ADDCOLUMNS(SUMMARIZE('Date', 'Date'[Day of Week], 'Date'[Day]), "@v", [Avg Sales per Trading Day]), [@v] > 0)
VAR Best = MAXX(Pool, [@v])
RETURN
    IF(ISEMPTY(Pool), "No sales in this period", MINX(FILTER(Pool, [@v] = Best), 'Date'[Day]) & "s sell the most per trading day")""",
          None, "Title of the weekday bars. Evaluated under the bar chart's own filters."),

        M("Standfirst Cal Day", f"""
VAR Cur = [Sales]
VAR Prev = [Sales PY]
VAR Change = DIVIDE(Cur - Prev, Prev)
VAR Pool = ADDCOLUMNS(VALUES('Date'[Date]), "@v", [Sales])
VAR Best = MAXX(Pool, [@v])
VAR BestDay = DAY(MINX(FILTER(Pool, [@v] = Best), 'Date'[Date]))
{ORDINAL}
VAR DaysAll = COUNTROWS(Pool)
RETURN
    [Cal Month Label] & " took " & {short_money('Cur')} & " from " & FORMAT([Orders], "#,0") & " orders"
        & IF(Prev > 0, ", " & {change_words('Change')} & " on the same month a year earlier", "")
        & ". The busiest day was the " & BestDay & Sfx & " at " & {short_money('Best')} & "; "
        & (DaysAll - [Cal Trading Days]) & " of " & DaysAll & " days had no orders at all." """,
          None, "The Day view's standfirst."),
        M("Standfirst Cal Month", scoped(f"""
VAR Cur = [Sales]
VAR Prev = [Sales PY]
VAR Change = DIVIDE(Cur - Prev, Prev)
VAR Pool = ADDCOLUMNS(SUMMARIZE('Date', 'Date'[Month No], 'Date'[Month]), "@v", [Sales])
VAR Best = MAXX(Pool, [@v])
RETURN
    MAX('Date'[Year]) & " took " & {short_money('Cur')} & " from " & FORMAT([Orders], "#,0") & " orders"
        & IF(Prev > 0, ", " & {change_words('Change')} & " on " & (MAX('Date'[Year]) - 1), "")
        & ". " & MINX(FILTER(Pool, [@v] = Best), 'Date'[Month]) & " alone was " & FORMAT(DIVIDE(Best, Cur), "0.0%")
        & " of the year. Switch to Day to open a month." """, "Month"),
          None, "The Month view's standfirst."),
        M("Standfirst Cal Quarter", scoped(f"""
VAR Cur = [Sales]
RETURN
    MIN('Date'[Year]) & " to " & MAX('Date'[Year]) & " took " & {short_money('Cur')} & " from " & FORMAT([Orders], "#,0")
        & " orders. Read across a row for the shape of a year, down a column for the same quarter growing year on year." """, "Quarter"),
          None, "The Quarter view's standfirst."),
        M("Standfirst Cal Year", scoped(f"""
VAR Cur = [Sales]
VAR YearCount = COUNTROWS(VALUES('Date'[Year]))
RETURN
    YearCount & " years, " & {short_money('Cur')} & " from " & FORMAT([Orders], "#,0")
        & " orders. Switch to Quarter or Month to see where inside a year the growth came from." """, "Year"),
          None, "The Year view's standfirst."),
    ]

    # ---- legend -------------------------------------------------------------------------------------
    swatches = "".join(f"<rect x='{52 + i * 32}' y='5' width='26' height='10' rx='1' fill='{c}'/>" for i, c in enumerate(BANDS))
    out.append(M("Cal Legend", f"""
VAR Svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='520' height='20' viewBox='0 0 520 20' font-family='Segoe UI, sans-serif'>"
        & "<text x='0' y='14' font-size='11' fill='{MUTED}'>Quieter</text>{swatches}"
        & "<text x='{52 + 5 * 32 + 2}' y='14' font-size='11' fill='{MUTED}'>Busier</text>"
        & "<text x='270' y='14' font-size='11' fill='{MUTED}'>Shade = fifths of the cells shown &#183; &#8211; no orders</text>"
        & "</svg>"
RETURN
    {svg_uri()}""", None, "The five-band key under the calendar.", category="ImageUrl"))
    return out
