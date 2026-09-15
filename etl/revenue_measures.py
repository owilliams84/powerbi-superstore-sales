"""Measures and disconnected tables behind the Revenue page.

The page compares one year with a comparison year chosen on a button slicer, and everything on it
- the four KPI cards, the table bars, the titles - is a measure. Kept apart from build_model.py
because most of it is SVG assembled in DAX, which drowns the ordinary measures if mixed in.

Three techniques live here:

* Disconnected tables (Comparison, Line View, the two Ranking tables) have no relationships.
  A button slicer on one filters nothing; measures read it with SELECTEDVALUE.
* SVG measures carry dataCategory ImageUrl and return a data URI. An image visual renders one as
  a card; a table renders one per row. '%' and '#' must be percent-encoded in a utf8 data URI or
  the browser reads '%20' in "20%" as an escape and '#' as the end of the URI, so every SVG
  measure passes through the same SUBSTITUTE pair, '%' first.
* Top/Bottom tables rank inside a measure and the table keeps rows ranked 1-8 with a visual-level
  measure filter, so the direction can flip without a TopN filter.
"""

from __future__ import annotations

USD = "\\$#,0"
PCT = "0.0%"
INT = "#,0"

GOOD, BAD, INK, BODY, MUTED, RULE, GOLD, NAVY = (
    "#1E7A4C", "#B3261E", "#0A0917", "#4A5768", "#667284", "#E3E7EF", "#C9A227", "#111F38")

TOP_N = 8
FOLDER = "Revenue page"

# --------------------------------------------------------------------------------------------
# Disconnected tables: name -> (doc, columns [(name, dtype, sortBy)], rows)
# --------------------------------------------------------------------------------------------
DISCONNECTED = {
    "Comparison": (
        "Button slicer values for what the Revenue page compares against. No relationships:\n"
        "measures read the selection with SELECTEDVALUE.",
        [("Comparison", "string", "Years Back"), ("Years Back", "int64", None)],
        [("Prior year", 1), ("Two years earlier", 2)],
    ),
    "Line View": (
        "Month-by-month or running total, for the Revenue page line chart.",
        [("View", "string", "View Order"), ("View Order", "int64", None)],
        [("Month", 1), ("Cumulative", 2)],
    ),
    "Customer Ranking": (
        "Top or Bottom for the Revenue page customer table.",
        [("Show", "string", "Show Order"), ("Show Order", "int64", None)],
        [("Top", 1), ("Bottom", 2)],
    ),
    "Sub-category Ranking": (
        "Top or Bottom for the Revenue page sub-category table.",
        [("Show", "string", "Show Order"), ("Show Order", "int64", None)],
        [("Top", 1), ("Bottom", 2)],
    ),
}


def M(name, dax, fmt=None, doc=None, category=None):
    return {"name": name, "dax": dax.strip("\n"), "fmt": fmt, "doc": doc,
            "category": category, "folder": FOLDER}


def svg_uri(body_var: str = "Svg") -> str:
    """The encoding every SVG measure ends with. '%' before '#', or '%23' becomes '%2523'."""
    return f'"data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE({body_var}, "%", "%25"), "#", "%23")'


def money(expr: str, signed: bool = False) -> str:
    """'$1,234' or, signed, '+$1,234' / '&#8722;$1,234'. The minus is an entity so the SVG text
    stays ASCII inside the data URI."""
    if signed:
        return (f'IF({expr} < 0, "&#8722;$", "+$") & FORMAT(ABS({expr}), "#,0")')
    return f'"$" & FORMAT({expr}, "#,0")'


def pct(expr: str) -> str:
    return (f'IF(ISBLANK({expr}), "new", IF(ABS({expr}) >= 10, IF({expr} > 0, ">+999%", "<-999%"), '
            f'IF({expr} < 0, "&#8722;", "+") & FORMAT(ABS({expr}), "0.0%")))')


def escape_xml(expr: str) -> str:
    return f'SUBSTITUTE(SUBSTITUTE({expr}, "&", "&amp;"), "<", "&lt;")'


def pool(column: str, selected: bool = False) -> str:
    """Members that sold in either year - the set every count, rank and scale is taken over.

    ALL by default: the ranked tables keep ranks 1-8 with a visual-level measure filter, and that
    filter narrows ALLSELECTED to the eight rows on screen - the subtitle read "among 8 customers"
    and every bar was scaled to its own eight. A slicer on a *different* column still applies,
    because the [Sales] test runs in the outer filter context.

    But ALL(column) also discards a slicer on *that* column: with Region = West on the filter
    panel, the regions card still read "3 of 4 regions". So a column a slicer can target, and that
    never sits in a measure-filtered table, passes selected=True for ALLSELECTED."""
    fn = "ALLSELECTED" if selected else "ALL"
    return f"FILTER({fn}({column}), [Sales] + [Sales Comparison] > 0)"


def ring(cx: int, cy: int, r: int, share: str, colour: str, over: str | None = None) -> str:
    """DAX expression for an SVG ring gauge: a grey track, `share` (0-1) in `colour`, and an
    optional `over` share drawn on top in gold for the part above 100%."""
    def arc(s: str, col: str) -> str:
        return (
            f'IF({s} > 0, "<path d=\'M{cx},{cy - r} A{r},{r} 0 " & IF({s} > 0.5, "1", "0") & " 1 " & '
            f'FORMAT({cx} + {r} * COS(2 * PI() * MIN({s}, 0.9999) - PI() / 2), "0.00") & "," & '
            f'FORMAT({cy} + {r} * SIN(2 * PI() * MIN({s}, 0.9999) - PI() / 2), "0.00") & '
            f'"\' stroke=\'{col}\' stroke-width=\'7\' fill=\'none\'/>")'
        )
    out = f'"<circle cx=\'{cx}\' cy=\'{cy}\' r=\'{r}\' stroke=\'{RULE}\' stroke-width=\'7\' fill=\'none\'/>" & {arc(share, colour)}'
    if over:
        out += f" & {arc(over, GOLD)}"
    return out


def card(label: str, value: str, note: str, row1: tuple[str, str, str], row2: tuple[str, str, str],
         graphic: str) -> str:
    """The shared KPI card frame, 336x140. Arguments are DAX text expressions; each row is
    (left text, right text, right colour)."""
    def row(y: int, r: tuple[str, str, str]) -> str:
        return (f'"<text x=\'16\' y=\'{y}\' font-size=\'11.5\' fill=\'{BODY}\'>" & {r[0]} & "</text>'
                f'<text x=\'320\' y=\'{y}\' font-size=\'11.5\' font-weight=\'600\' text-anchor=\'end\' fill=\'" & {r[2]} & "\'>" & {r[1]} & "</text>"')
    return "\n".join([
        f'"<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'336\' height=\'140\' viewBox=\'0 0 336 140\' font-family=\'Segoe UI, sans-serif\'>"',
        f'& "<rect x=\'0.5\' y=\'0.5\' width=\'335\' height=\'139\' rx=\'4\' fill=\'#FFFFFF\' stroke=\'{RULE}\'/><rect width=\'3\' height=\'140\' fill=\'{GOLD}\'/>"',
        f'& "<text x=\'16\' y=\'24\' font-size=\'11\' font-weight=\'700\' fill=\'{MUTED}\' letter-spacing=\'0.4\'>" & {label} & "</text>"',
        f'& "<text x=\'16\' y=\'58\' font-size=\'28\' font-weight=\'700\' fill=\'{INK}\'>" & {value} & "</text>"',
        f'& "<text x=\'16\' y=\'76\' font-size=\'11.5\' fill=\'{MUTED}\'>" & {note} & "</text>"',
        f'& "<line x1=\'16\' y1=\'88\' x2=\'320\' y2=\'88\' stroke=\'{RULE}\'/>"',
        f"& {row(107, row1)}",
        f"& {row(127, row2)}",
        f"& {graphic}",
        '& "</svg>"',
    ])


def tone(expr: str) -> str:
    return f'IF({expr} >= 0, "{GOOD}", "{BAD}")'


def no_comparison_card(label: str) -> str:
    return (f'"<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'336\' height=\'140\' viewBox=\'0 0 336 140\' font-family=\'Segoe UI, sans-serif\'>'
            f'<rect x=\'0.5\' y=\'0.5\' width=\'335\' height=\'139\' rx=\'4\' fill=\'#FFFFFF\' stroke=\'{RULE}\'/>'
            f'<text x=\'16\' y=\'24\' font-size=\'11\' font-weight=\'700\' fill=\'{MUTED}\'>{label}</text>'
            f'<text x=\'16\' y=\'64\' font-size=\'13\' fill=\'{BODY}\'>No sales in " & [Comparison Year] & " to compare with.</text></svg>"')


def indent(text: str, n: int = 1) -> str:
    return "\n".join(("    " * n + line) if line else line for line in text.split("\n"))


# --------------------------------------------------------------------------------------------
# Ranked tables: rank, filter-friendly, and the diverging SVG bar
# --------------------------------------------------------------------------------------------


def ranking_measures(label: str, column: str, ranking_table: str) -> list[dict]:
    rank = f"{label} Change Rank"
    return [
        M(rank, f"""
VAR Direction = SELECTEDVALUE('{ranking_table}'[Show], "Top")
VAR Pool = {pool(column)}
VAR Me = [Sales vs Comparison]
RETURN
    IF(
        HASONEVALUE({column}) && [Comparison Available] && [Sales] + [Sales Comparison] > 0,
        IF(
            Direction = "Top",
            COUNTROWS(FILTER(Pool, [Sales vs Comparison] > Me)) + 1,
            COUNTROWS(FILTER(Pool, [Sales vs Comparison] < Me)) + 1
        )
    )""", "0",
          f"Position by change on the comparison year, from the top or the bottom as the\n"
          f"'{ranking_table}' button says. Blank for anything that sold in neither year. The table\n"
          f"keeps ranks 1 to {TOP_N} with a visual-level filter on this measure."),
        M(f"{label} Change Bar", f"""
VAR Change = [Sales vs Comparison]
VAR Scale = MAXX({pool(column)}, ABS([Sales vs Comparison]))
VAR W = DIVIDE(ABS(Change), Scale) * 76
VAR X = IF(Change >= 0, 80, 80 - W)
VAR Svg =
    "<svg xmlns='http://www.w3.org/2000/svg' width='160' height='16' viewBox='0 0 160 16'>"
        & "<line x1='80' y1='0' x2='80' y2='16' stroke='{MUTED}'/>"
        & "<rect x='" & FORMAT(X, "0.0") & "' y='3' width='" & FORMAT(W, "0.0") & "' height='10' fill='" & {tone("Change")} & "'/>"
        & "</svg>"
RETURN
    IF(NOT ISBLANK([{rank}]), {svg_uri()})""", None,
          "Diverging bar for the change. Every row shares one scale - the largest move either way\n"
          "in the pool - so a Top and a Bottom view can be compared by eye.",
          category="ImageUrl"),
    ]


# --------------------------------------------------------------------------------------------
# All measures
# --------------------------------------------------------------------------------------------


def measures() -> list[dict]:
    out = [
        M("Comparison Years Back", "SELECTEDVALUE(Comparison[Years Back], 1)", "0",
          "1 for the prior year, 2 for two years earlier. Defaults to 1 with nothing selected."),
        M("Selected Year", "MAX('Date'[Year])", "0",
          "The year on screen. The page forces a single year, so MAX is that year."),
        M("Comparison Year", "[Selected Year] - [Comparison Years Back]", "0"),
        M("Comparison Available",
          "[Comparison Year] >= CALCULATE(MIN('Date'[Year]), REMOVEFILTERS('Date'))", None,
          "False when the comparison year is before the calendar starts - 2022 against two years\n"
          "earlier. Everything comparative returns blank rather than a change against nothing."),
        M("Sales Comparison", """
VAR YearsBack = [Comparison Years Back]
RETURN
    IF([Comparison Available], CALCULATE([Sales], DATEADD('Date'[Date], -YearsBack, YEAR)))""", USD,
          "Sales in the same dates, one or two years earlier. DATEADD takes the offset from a\n"
          "variable, so one measure serves both buttons."),
        M("Sales vs Comparison", "IF([Comparison Available], [Sales] - [Sales Comparison])", USD),
        M("Sales vs Comparison %", "DIVIDE([Sales vs Comparison], [Sales Comparison])", PCT),
        M("Orders Comparison", """
VAR YearsBack = [Comparison Years Back]
RETURN
    IF([Comparison Available], CALCULATE([Orders], DATEADD('Date'[Date], -YearsBack, YEAR)))""", INT),
        M("Orders vs Comparison %", "DIVIDE([Orders] - [Orders Comparison], [Orders Comparison])", PCT),
        M("Average Order Value Comparison", "DIVIDE([Sales Comparison], [Orders Comparison])", USD),
        M("Average Order Value vs Comparison %",
          "DIVIDE([Average Order Value] - [Average Order Value Comparison], [Average Order Value Comparison])", PCT),

        M("Line View Selected", "SELECTEDVALUE('Line View'[View], \"Month\")", None),
        M("Sales Line",
          "IF([Line View Selected] = \"Cumulative\", CALCULATE([Sales], DATESYTD('Date'[Date])), [Sales])", USD,
          "The selected year on the line chart: each month, or the running total to that month."),
        M("Comparison Line", """
VAR YearsBack = [Comparison Years Back]
RETURN
    IF(
        [Comparison Available],
        IF(
            [Line View Selected] = "Cumulative",
            CALCULATE([Sales YTD], DATEADD('Date'[Date], -YearsBack, YEAR)),
            [Sales Comparison]
        )
    )""", USD),
        M("Variance Colour", f"IF([Sales vs Comparison] >= 0, \"{GOOD}\", \"{BAD}\")", None,
          "Fill for the monthly variance columns, bound as a field value."),

        M("Customers In Play", f"IF([Comparison Available], COUNTROWS({pool('Customer[Customer]')}))", INT,
          "Customers who bought in the selected year, the comparison year, or both."),
        M("Customers Above Comparison",
          "IF([Comparison Available], COUNTROWS(FILTER(ALL(Customer[Customer]), [Sales] > [Sales Comparison])))",
          INT, "Customers whose sales beat the comparison year, including customers new since."),
        M("Regions Above Comparison",
          "IF([Comparison Available], COUNTROWS(FILTER(ALLSELECTED(Geography[Region]), [Sales] > [Sales Comparison])))", INT,
          "ALLSELECTED, not ALL: Region is on the filter panel, and ALL would count all four regions\n"
          "under a West filter."),
        M("Sub-categories In Play", f"IF([Comparison Available], COUNTROWS({pool('Product[Sub-Category]')}))", INT),
        M("Sub-categories Above Comparison",
          "IF([Comparison Available], COUNTROWS(FILTER(ALL(Product[Sub-Category]), [Sales] > [Sales Comparison])))", INT),
        M("Sales vs Comparison % Label", """
VAR P = [Sales vs Comparison %]
RETURN
    IF(
        [Comparison Available] && [Sales] + [Sales Comparison] > 0,
        SWITCH(
            TRUE(),
            ISBLANK(P), "new",
            P >= 10, ">+999%",
            FORMAT(P, "+0.0%;-0.0%;0.0%")
        )
    )""", None,
          "The change as text for the ranked tables: 'new' where there was nothing to compare with,\n"
          "and capped at >+999% so a customer who went from $27 to $5,821 does not read 21268%."),
        M("Title Variance Chart",
          "IF([Comparison Available], \"Which months beat \" & [Comparison Year] & \", and by how much\", "
          "\"Which months moved the year\")", None),
    ]

    out += ranking_measures("Customer", "Customer[Customer]", "Customer Ranking")
    out += ranking_measures("Sub-category", "Product[Sub-Category]", "Sub-category Ranking")

    # ---- Titles and text that rewrite themselves ------------------------------------------
    out += [
        M("Title Standfirst", """
VAR Y = [Selected Year]
VAR C = [Comparison Year]
VAR S = [Sales vs Comparison %]
VAR O = [Orders vs Comparison %]
VAR A = [Average Order Value vs Comparison %]
VAR Moved = S >= 0
RETURN
    IF(
        NOT [Comparison Available],
        "There are no sales before 2021, so " & Y & " has no " & C & " sales to compare with. Pick a later year or the prior year.",
        Y & " sales were " & IF(Moved, "up ", "down ") & FORMAT(ABS(S), "0.0%") & " on " & C & ". Orders "
            & IF(O >= 0, "rose ", "fell ") & FORMAT(ABS(O), "0.0%") & " and the average order "
            & IF(A >= 0, "rose ", "fell ") & FORMAT(ABS(A), "0.0%") & ": the change came from "
            & IF(ABS(O) > ABS(A), "the number of orders, not their size.", "order size more than order count.")
    )""", None, "The page standfirst, rewritten for whatever year and comparison is selected."),
        M("Title Line Chart", """
IF(
    [Comparison Available],
    [Selected Year] & " against " & [Comparison Year]
        & IF([Line View Selected] = "Cumulative", ", running total", ", month by month"),
    [Selected Year] & ", with no comparison year"
)""", None),
        M("Subtitle Line Chart", """
VAR C = [Comparison Year]
VAR MonthsAbove = COUNTROWS(FILTER(VALUES('Date'[Month No]), [Sales vs Comparison] > 0))
VAR Gap = [Sales vs Comparison]
RETURN
    IF(
        [Comparison Available],
        IF(
            [Line View Selected] = "Cumulative",
            FORMAT(ABS(Gap), "$#,0") & IF(Gap >= 0, " ahead of ", " behind ") & C & " by the year end",
            "Above " & C & " in " & MonthsAbove & " of " & COUNTROWS(VALUES('Date'[Month No])) & " months"
        )
    )""", None),
        M("Subtitle Variance Chart", """
VAR ByMonth = ADDCOLUMNS(VALUES('Date'[Month No]), "@Change", [Sales vs Comparison])
VAR Best = TOPN(1, ByMonth, [@Change], DESC)
VAR Worst = TOPN(1, ByMonth, [@Change], ASC)
VAR BestMonth = FORMAT(DATE(2000, MAXX(Best, 'Date'[Month No]), 1), "mmm")
VAR WorstMonth = FORMAT(DATE(2000, MAXX(Worst, 'Date'[Month No]), 1), "mmm")
VAR BestValue = MAXX(Best, [@Change])
VAR WorstValue = MAXX(Worst, [@Change])
RETURN
    IF(
        [Comparison Available],
        "Sales less " & [Comparison Year] & ": " & BestMonth & " added most ("
            & IF(BestValue < 0, "-", "+") & FORMAT(ABS(BestValue), "$#,0") & "), "
            & WorstMonth & IF(WorstValue < 0, " lost most (-", " added least (+") & FORMAT(ABS(WorstValue), "$#,0") & ")"
    )""", None),
        M("Title Customer Table", f"""
IF(
    SELECTEDVALUE('Customer Ranking'[Show], "Top") = "Top",
    "The {TOP_N} customers who grew most on " & [Comparison Year],
    "The {TOP_N} customers who fell furthest below " & [Comparison Year]
)""", None),
        M("Subtitle Customer Table", """
IF(
    [Comparison Available],
    "Bars share one scale: the largest move either way among " & FORMAT([Customers In Play], "#,0") & " customers"
)""", None),
        M("Title Sub-category Table", f"""
IF(
    SELECTEDVALUE('Sub-category Ranking'[Show], "Top") = "Top",
    "The {TOP_N} sub-categories that grew most on " & [Comparison Year],
    "The {TOP_N} sub-categories that did worst against " & [Comparison Year]
)""", None),
        M("Subtitle Sub-category Table", """
IF(
    [Comparison Available],
    [Sub-categories In Play] - [Sub-categories Above Comparison] & " of " & [Sub-categories In Play]
        & " were below " & [Comparison Year]
)""", None),
        M("Filter Summary", """
VAR Names =
    FILTER(
        {
            ("segment", ISFILTERED(Customer[Segment]), 1),
            ("region", ISFILTERED(Geography[Region]), 2),
            ("category", ISFILTERED(Product[Category]), 3)
        },
        [Value2]
    )
RETURN
    IF(
        COUNTROWS(Names) = 0,
        "No filters applied",
        "Filtered by " & CONCATENATEX(Names, [Value1], ", ", [Value3], ASC)
    )""", None, "Shown under the Filters button so a closed panel still says what it is doing."),
    ]

    # ---- The four KPI cards -----------------------------------------------------------------
    out.append(M("Card Sales", indent(f"""
VAR Y = [Selected Year]
VAR C = [Comparison Year]
VAR S = [Sales]
VAR SC = [Sales Comparison]
VAR SP = [Sales vs Comparison %]
VAR OP = [Orders vs Comparison %]
VAR AP = [Average Order Value vs Comparison %]
VAR Ratio = DIVIDE(S, SC)
VAR Svg =
{indent(card(
    '"SALES, " & Y',
    money("S"),
    f'{pct("SP")} & " on " & C & " (" & {money("SC")} & ")"',
    ('"Orders " & FORMAT([Orders], "#,0")', pct("OP"), tone("OP")),
    ('"Average order " & ' + money("[Average Order Value]"), pct("AP"), tone("AP")),
    ring(286, 42, 26, "MIN(Ratio, 1)", NAVY, "Ratio - 1")
    + f' & "<text x=\'286\' y=\'47\' font-size=\'13\' font-weight=\'700\' text-anchor=\'middle\' fill=\'{INK}\'>" & FORMAT(Ratio, "0%") & "</text>"',
), 1)}
VAR NoComparison = {no_comparison_card('SALES')}
RETURN
    {svg_uri("IF([Comparison Available], Svg, NoComparison)")}""", 0), None,
        "KPI card as one SVG: sales, the change on the comparison year, and a ring showing sales\n"
        "as a share of the comparison, the part above 100% in gold.", category="ImageUrl"))

    cust_pool = pool("Customer[Customer]")
    out.append(M("Card Customers", f"""
VAR C = [Comparison Year]
VAR Above = [Customers Above Comparison]
VAR InPlay = [Customers In Play]
VAR Changes = ADDCOLUMNS({cust_pool}, "@Change", [Sales vs Comparison])
VAR BestRow = TOPN(1, Changes, [@Change], DESC, Customer[Customer], ASC)
VAR WorstRow = TOPN(1, Changes, [@Change], ASC, Customer[Customer], ASC)
VAR BestName = {escape_xml("MAXX(BestRow, Customer[Customer])")}
VAR WorstName = {escape_xml("MAXX(WorstRow, Customer[Customer])")}
VAR BestValue = MAXX(BestRow, [@Change])
VAR WorstValue = MAXX(WorstRow, [@Change])
VAR Share = DIVIDE(Above, InPlay)
VAR Svg =
{indent(card(
    '"CUSTOMERS ABOVE " & C',
    'FORMAT(Above, "#,0")',
    '"of " & FORMAT(InPlay, "#,0") & " who bought in either year"',
    ('"Biggest gain &#183; " & LEFT(BestName, 24)', money("BestValue", True), tone("BestValue")),
    ('"Biggest fall &#183; " & LEFT(WorstName, 24)', money("WorstValue", True), tone("WorstValue")),
    ring(286, 42, 26, "Share", NAVY)
    + f' & "<text x=\'286\' y=\'47\' font-size=\'13\' font-weight=\'700\' text-anchor=\'middle\' fill=\'{INK}\'>" & FORMAT(Share, "0%") & "</text>"',
), 1)}
VAR NoComparison = {no_comparison_card('CUSTOMERS')}
RETURN
    {svg_uri("IF([Comparison Available], Svg, NoComparison)")}""", None,
        "How many customers beat the comparison year, with the biggest move each way.",
        category="ImageUrl"))

    out.append(M("Card Regions", f"""
VAR C = [Comparison Year]
VAR Regions = ADDCOLUMNS({pool("Geography[Region]", selected=True)}, "@Change", [Sales vs Comparison], "@Pct", [Sales vs Comparison %])
VAR N = COUNTROWS(Regions)
VAR BestRow = TOPN(1, Regions, [@Change], DESC, Geography[Region], ASC)
VAR WorstRow = TOPN(1, Regions, [@Change], ASC, Geography[Region], ASC)
VAR BestValue = MAXX(BestRow, [@Change])
VAR WorstValue = MAXX(WorstRow, [@Change])
VAR BestPct = MAXX(BestRow, [@Pct])
VAR WorstPct = MAXX(WorstRow, [@Pct])
VAR Tiles =
    CONCATENATEX(
        Regions,
        VAR RegionName = Geography[Region]
        VAR I = COUNTROWS(FILTER(Regions, Geography[Region] < RegionName))
        VAR X = 176 + I * 38
        RETURN
            "<rect x='" & X & "' y='22' width='32' height='40' rx='3' fill='" & {tone("[@Change]")} & "'/>"
                & "<text x='" & X + 16 & "' y='40' font-size='10' font-weight='700' text-anchor='middle' fill='#FFFFFF'>" & LEFT(RegionName, 1) & "</text>"
                & "<text x='" & X + 16 & "' y='55' font-size='9' text-anchor='middle' fill='#FFFFFF'>"
                & IF(ISBLANK([@Pct]), "new", IF([@Pct] < 0, "-", "+") & FORMAT(ABS([@Pct]), "0%")) & "</text>",
        ""
    )
VAR Svg =
{indent(card(
    '"REGIONS ABOVE " & C',
    'FORMAT([Regions Above Comparison], "0")',
    '"of " & N & IF(N = 1, " region", " regions")',
    ('"Best &#183; " & MAXX(BestRow, Geography[Region])', f'{money("BestValue", True)} & " (" & {pct("BestPct")} & ")"', tone("BestValue")),
    ('"Weakest &#183; " & MAXX(WorstRow, Geography[Region])', f'{money("WorstValue", True)} & " (" & {pct("WorstPct")} & ")"', tone("WorstValue")),
    "Tiles",
), 1)}
VAR NoComparison = {no_comparison_card('REGIONS')}
RETURN
    {svg_uri("IF([Comparison Available], Svg, NoComparison)")}""", None,
        "One tile per region, green above the comparison year and red below, alphabetical.",
        category="ImageUrl"))

    out.append(M("Card Sub-categories", f"""
VAR C = [Comparison Year]
VAR Subs = ADDCOLUMNS({pool("Product[Sub-Category]")}, "@Change", [Sales vs Comparison])
VAR Scale = MAXX(Subs, ABS([@Change]))
VAR BestRow = TOPN(1, Subs, [@Change], DESC, Product[Sub-Category], ASC)
VAR WorstRow = TOPN(1, Subs, [@Change], ASC, Product[Sub-Category], ASC)
VAR BestValue = MAXX(BestRow, [@Change])
VAR WorstValue = MAXX(WorstRow, [@Change])
VAR Bars =
    "<line x1='206' y1='58' x2='320' y2='58' stroke='{RULE}'/>"
        & CONCATENATEX(
            Subs,
            VAR Change = [@Change]
            VAR I = COUNTROWS(FILTER(Subs, [@Change] > Change))
            VAR H = MAX(1.5, 20 * DIVIDE(ABS(Change), Scale))
            RETURN
                "<rect x='" & FORMAT(206 + I * 6.8, "0.0") & "' y='" & FORMAT(IF(Change >= 0, 58 - H, 58), "0.0")
                    & "' width='5' height='" & FORMAT(H, "0.0") & "' fill='" & {tone("Change")} & "'/>",
            ""
        )
VAR Svg =
{indent(card(
    '"SUB-CATEGORIES ABOVE " & C',
    'FORMAT([Sub-categories Above Comparison], "0")',
    '"of " & [Sub-categories In Play] & " sub-categories"',
    ('"Best &#183; " & MAXX(BestRow, Product[Sub-Category])', money("BestValue", True), tone("BestValue")),
    ('"Weakest &#183; " & MAXX(WorstRow, Product[Sub-Category])', money("WorstValue", True), tone("WorstValue")),
    "Bars",
), 1)}
VAR NoComparison = {no_comparison_card('SUB-CATEGORIES')}
RETURN
    {svg_uri("IF([Comparison Available], Svg, NoComparison)")}""", None,
        "Every sub-category as a bar, sorted from the biggest gain to the biggest fall.",
        category="ImageUrl"))

    return out
