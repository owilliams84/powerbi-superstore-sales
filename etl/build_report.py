"""Generate the PBIR report definition - four pages, the Milestone theme and every visual.

PBIR stores one JSON file per visual and wraps every property in the same
{"expr": {"Literal": {"Value": ...}}} envelope. Hand-editing that is how typos get in, so the
report is generated from this file: the helpers own the envelope and the page functions read as
layout.

    python etl/build_report.py

Rewrites <report>/definition/pages from scratch every run. That matters - a renamed visual left
behind on disk still renders, as an empty box.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "Superstore Sales.Report"
PAGES = REPORT / "definition" / "pages"
RESOURCES = REPORT / "StaticResources" / "RegisteredResources"
ASSETS = ROOT / "etl" / "assets"

CANVAS_W, CANVAS_H = 1440, 900

# --------------------------------------------------------------------------------------------
# Palette: milestonebi.com's own tokens. Near-black indigo for text and the brand band, gold for
# the accent, and the site's greys for everything that should recede.
# --------------------------------------------------------------------------------------------
PAPER = "#F4F6FA"
CARD = "#FFFFFF"
RULE = "#E3E7EF"
INK = "#0A0917"       # headlines, and the brand band
BODY = "#4A5768"
MUTED = "#667284"     # axis labels, captions
GOLD = "#C9A227"      # the accent, on both grounds
GOLD_TEXT = "#8A6D14" # gold at text weight, readable on white
NAVY = "#111F38"      # the logo's navy - the primary series fill
SLATE = "#7C8598"     # third series
LIGHT = "#BCC1D2"     # fourth series, and 'everything else'
GOOD = "#1E7A4C"
BAD = "#B3261E"

THEME_NAME = "MilestoneTheme.json"
MARK_NAME = "MilestoneMark.svg"

# --------------------------------------------------------------------------------------------
# Expression envelope helpers
# --------------------------------------------------------------------------------------------


def lit(value) -> dict:
    """Wrap a literal in the expression envelope PBIR expects.

    The suffix is load-bearing: 'D' for a double, 'L' for an integer, quotes for text. Getting it
    wrong makes Desktop drop the property silently rather than complain.
    """
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, int):
        v = f"{value}L"
    elif isinstance(value, float):
        v = f"{value}D"
    else:
        v = f"'{value}'"
    return {"expr": {"Literal": {"Value": v}}}


def colour(hex_code: str) -> dict:
    return {"solid": {"color": lit(hex_code)}}


def obj(**props) -> list:
    return [{"properties": props}]


def obj_for(metadata: str, **props) -> dict:
    """A property block scoped to one measure, for per-series colours and line styles."""
    return {"properties": props, "selector": {"metadata": metadata}}


def obj_for_value(table: str, col: str, value, **props) -> dict:
    """A property block scoped to one category value - a year, a segment, a ship mode."""
    return {"properties": props, "selector": {"data": [{"scopeId": {"Comparison": {
        "ComparisonKind": 0,
        "Left": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "Right": lit(value)["expr"],
    }}}]}}


def measure(table: str, name: str, display: str | None = None) -> dict:
    field = {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }
    if display:
        field["displayName"] = display
    return field


def column(table: str, name: str, display: str | None = None, active: bool = True) -> dict:
    field = {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
        "queryRef": f"{table}.{name}",
        "nativeQueryRef": name,
    }
    if active:
        field["active"] = True
    if display:
        field["displayName"] = display
    return field


def m(name: str, display: str | None = None) -> dict:
    return measure("Metrics", name, display)


def sort_by(field: dict, direction: str = "Descending") -> dict:
    return {"sort": [{"field": field["field"], "direction": direction}], "isDefaultSort": True}


def categorical_filter(name: str, table: str, col: str, values: list, alias: str = "t") -> dict:
    """A visual-level 'this column is one of these values' filter."""
    return {
        "name": name,
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": col}},
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}},
                                            "Property": col}}],
                "Values": [[lit(v)["expr"]] for v in values],
            }}}],
        },
    }


# --------------------------------------------------------------------------------------------
# Container chrome
# --------------------------------------------------------------------------------------------


def chrome(title: str | None = None, transparent: bool = False, subtitle: str | None = None) -> dict:
    """Card background, hairline border and the small bold title every panel shares."""
    show = not transparent
    out = {
        "padding": obj(top=lit(8.0), bottom=lit(8.0), left=lit(10.0), right=lit(10.0)),
        "dropShadow": obj(show=lit(False)),
        "background": obj(show=lit(show), color=colour(CARD), transparency=lit(0.0)),
        "border": obj(show=lit(show), color=colour(RULE), radius=lit(4)),
    }
    if title:
        out["title"] = obj(show=lit(True), text=lit(title), fontSize=lit(10.5), bold=lit(True),
                           fontColor=colour(INK), heading=lit("Heading3"))
        if subtitle:
            out["subTitle"] = obj(show=lit(True), text=lit(subtitle), fontSize=lit(8.5),
                                  fontColor=colour(MUTED))
    else:
        out["title"] = obj(show=lit(False))
    return out


def visual(name: str, vtype: str, x: int, y: int, w: int, h: int, z: int,
           query: dict | None = None, objects: dict | None = None,
           container: dict | None = None, filters: list | None = None) -> dict:
    node: dict = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
        "visual": {"visualType": vtype},
    }
    if query is not None:
        node["visual"]["query"] = query
    if objects:
        node["visual"]["objects"] = objects
    node["visual"]["visualContainerObjects"] = container or chrome()
    if filters:
        # filterConfig is a sibling of "visual" at the root, not a child of it.
        node["filterConfig"] = {"filters": filters}
    return node


# --------------------------------------------------------------------------------------------
# Reusable formatting blocks
# --------------------------------------------------------------------------------------------


def axis(show_title: bool = False, gridlines: bool = False, size: float = 8.5,
         title_size: float | None = None, **extra) -> list:
    return [{"properties": {
        "show": lit(True), "showAxisTitle": lit(show_title), "fontSize": lit(size),
        "labelColor": colour(MUTED), "gridlineShow": lit(gridlines),
        **({"gridlineColor": colour(RULE)} if gridlines else {}),
        **({"titleFontSize": lit(title_size), "titleColor": colour(MUTED)}
           if show_title and title_size else {}),
        **extra,
    }}]


def legend(show: bool = True, position: str = "Top") -> list:
    return [{"properties": {
        "show": lit(show), "position": lit(position), "showTitle": lit(False),
        "fontSize": lit(8.5), "labelColor": colour(MUTED),
    }}]


def no_labels() -> list:
    return [{"properties": {"show": lit(False)}}]


def data_labels(size: float = 8.5, units: str = "1", colour_hex: str = BODY) -> list:
    return [{"properties": {
        "show": lit(True), "fontSize": lit(size), "color": colour(colour_hex),
        "labelDisplayUnits": lit(units),
    }}]


def series_colour(mapping: dict[str, str]) -> list:
    return [obj_for(k, fill=colour(v)) for k, v in mapping.items()]


def value_colours(table: str, col: str, mapping: dict) -> list:
    return [obj_for_value(table, col, k, fill=colour(v)) for k, v in mapping.items()]


def no_chrome() -> dict:
    return {
        "padding": obj(top=lit(0.0), bottom=lit(0.0), left=lit(0.0), right=lit(0.0)),
        "dropShadow": obj(show=lit(False)),
        "background": obj(show=lit(False)),
        "border": obj(show=lit(False)),
        "title": obj(show=lit(False)),
    }


def textbox(name: str, x: int, y: int, w: int, h: int, z: int, paragraphs: list,
            background: str | None = None) -> dict:
    """paragraphs: each is a list of runs [{"text","size","color","bold","family","spacing"}],
    or a single run dict for a one-run paragraph. 'align' on the first run sets the paragraph."""
    out = []
    for para in paragraphs:
        runs = para if isinstance(para, list) else [para]
        text_runs = []
        for run in runs:
            style = {"fontSize": f"{run.get('size', 11)}pt", "color": run.get("color", BODY)}
            if run.get("bold"):
                style["fontWeight"] = "bold"
            if run.get("family"):
                style["fontFamily"] = run["family"]
            if run.get("spacing"):
                style["letterSpacing"] = run["spacing"]
            text_runs.append({"value": run["text"], "textStyle": style})
        node = {"textRuns": text_runs}
        if runs[0].get("align"):
            node["horizontalTextAlignment"] = runs[0]["align"]
        out.append(node)
    container = no_chrome()
    if background:
        container["background"] = obj(show=lit(True), color=colour(background),
                                      transparency=lit(0.0))
        container["padding"] = obj(top=lit(4.0), bottom=lit(4.0), left=lit(10.0), right=lit(10.0))
    node = visual(name, "textbox", x, y, w, h, z, container=container)
    node["visual"]["objects"] = {"general": [{"properties": {"paragraphs": out}}]}
    return node


def image(name: str, x: int, y: int, w: int, h: int, z: int, resource: str) -> dict:
    node = visual(name, "image", x, y, w, h, z, container=no_chrome())
    node["visual"]["objects"] = {
        "general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
            "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": resource}}}}}],
        "imageScaling": [{"properties": {"imageScalingType": lit("Fit")}}],
    }
    return node


def kpi_card(name: str, x: int, y: int, w: int, h: int, z: int, measures: list[dict],
             filters: list | None = None, value_size: float = 17.0) -> dict:
    return visual(
        name, "cardVisual", x, y, w, h, z,
        query={"queryState": {"Data": {"projections": measures}}},
        objects={
            "general": [{"properties": {}}],
            "value": [{"properties": {
                "fontSize": lit(value_size), "bold": lit(True), "fontColor": colour(INK),
                "fontFamily": lit("Segoe UI"), "horizontalAlignment": lit("Left"),
                # Without this the auto units turn 2,261,537 into "2M".
                "labelDisplayUnits": lit("1"),
            }, "selector": {"id": "default"}}],
            "label": [{"properties": {
                "show": lit(True), "fontSize": lit(8.5), "fontColor": colour(MUTED),
                "bold": lit(False), "position": lit("belowValue"),
                "horizontalAlignment": lit("Left"),
            }, "selector": {"id": "default"}}],
            "accentBar": [{"properties": {
                "show": lit(True), "color": colour(GOLD), "width": lit(3),
            }, "selector": {"id": "default"}}],
        },
        filters=filters,
    )


def slicer(name: str, x: int, y: int, w: int, h: int, z: int, table: str, col: str,
           header: str, default: list | None = None, mode: str = "Dropdown") -> dict:
    general: dict = {"orientation": lit(0)}
    if default is not None:
        alias = table[0].lower()
        general["filter"] = {"filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": table, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}},
                                            "Property": col}}],
                "Values": [[lit(v)["expr"]] for v in default],
            }}}],
        }}
    return visual(
        name, "slicer", x, y, w, h, z,
        query={"queryState": {"Values": {"projections": [column(table, col)]}}},
        objects={
            "general": [{"properties": general}],
            "data": [{"properties": {"mode": lit(mode)}}],
            "header": [{"properties": {
                "show": lit(True), "text": lit(header), "textSize": lit(8.5),
                "fontColor": colour(MUTED), "bold": lit(True),
            }}],
            "items": [{"properties": {
                "fontColor": colour(BODY), "textSize": lit(9.5), "background": colour(CARD),
            }}],
        },
    )


def table_visual(name: str, x: int, y: int, w: int, h: int, z: int, fields: list[dict],
                 sort: dict, title: str, subtitle: str | None = None,
                 filters: list | None = None, totals: bool = False) -> dict:
    """A flat ranked table. Built as a matrix with one row field: on Desktop 2.157 a tableEx
    generated this way rendered the column fields and silently dropped every measure."""
    rows = [f for f in fields if "Column" in f["field"]]
    values = [f for f in fields if "Measure" in f["field"]]
    return visual(
        name, "pivotTable", x, y, w, h, z,
        query={"queryState": {"Rows": {"projections": rows}, "Values": {"projections": values}},
               "sortDefinition": sort},
        objects={
            "grid": [{"properties": {
                "gridVertical": lit(False), "gridHorizontal": lit(True),
                "gridHorizontalColor": colour(RULE), "rowPadding": lit(3),
            }}],
            "columnHeaders": [{"properties": {
                "fontSize": lit(9.0), "bold": lit(True), "fontColor": colour(INK),
                "backColor": colour(CARD), "alignment": lit("Right"),
            }}],
            "rowHeaders": [{"properties": {
                "fontSize": lit(9.0), "fontColor": colour(BODY), "backColor": colour(CARD),
            }}],
            "values": [{"properties": {
                "fontSize": lit(9.0), "fontColorPrimary": colour(BODY),
                "backColorPrimary": colour(CARD), "backColorSecondary": colour(CARD),
            }}],
            "subTotals": [{"properties": {"rowSubtotals": lit(totals),
                                          "columnSubtotals": lit(False)}}],
        },
        container=chrome(title, subtitle=subtitle),
        filters=filters,
    )


# --------------------------------------------------------------------------------------------
# Masthead: brand band, then the page title on paper
# --------------------------------------------------------------------------------------------


def masthead(slug: str, title: str, standfirst: str | None, ref: str) -> list[dict]:
    """The brand band every page shares, and under it the section title and one line of
    orientation. 'slug' names the containers and must be filesystem-safe. A page whose standfirst
    is a measure passes None and places a dynamic_text() instead."""
    return [
        # The band is a textbox with a navy background - a shape would do the same, and this is
        # one fewer visual type to get right. The mark sits on top of it.
        textbox(f"vBand{slug}", 0, 0, CANVAS_W, 60, 50, [
            [{"text": "", "size": 6, "color": INK}],
        ], background=INK),
        image(f"vMark{slug}", 24, 12, 44, 38, 60, MARK_NAME),
        textbox(f"vWordmark{slug}", 76, 15, 260, 32, 70, [
            [{"text": "Milestone ", "size": 15, "color": CARD, "bold": True},
             {"text": "BI", "size": 15, "color": GOLD, "bold": True}],
        ]),
        textbox(f"vRef{slug}", 1016, 22, 400, 22, 80, [
            [{"text": ref, "size": 8, "color": GOLD, "bold": True, "family": "Consolas",
              "spacing": "2px", "align": "right"}],
        ]),
        textbox(f"vTitle{slug}", 24, 74, 900, 40, 90, [
            [{"text": title, "size": 22, "color": INK, "bold": True}],
        ]),
    ] + ([] if standfirst is None else [
        textbox(f"vStand{slug}", 24, 114, 1000, 46, 95, [
            [{"text": standfirst, "size": 10, "color": BODY}],
        ]),
    ])


def page(name: str, display: str) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
        "name": name,
        "displayName": display,
        "displayOption": "FitToPage",
        "height": CANVAS_H,
        "width": CANVAS_W,
        "objects": {
            "background": obj(color=colour(PAPER), transparency=lit(0.0)),
            "displayArea": obj(verticalAlignment=lit("Top")),
        },
    }


# --------------------------------------------------------------------------------------------
# Interactive pieces: measure-driven text and images, button slicers, buttons, bookmarks
# --------------------------------------------------------------------------------------------


def mexpr(name: str) -> dict:
    """A measure reference in the expression envelope, for properties bound to a field."""
    return {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": "Metrics"}}, "Property": name}}}


def dynamic_chrome(title: str, subtitle: str | None = None) -> dict:
    """chrome() with the title and subtitle bound to measures, so they rewrite with the slicers."""
    out = chrome("placeholder")
    out["title"] = obj(show=lit(True), text=mexpr(title), fontSize=lit(10.5), bold=lit(True),
                       fontColor=colour(INK), heading=lit("Heading3"))
    if subtitle:
        out["subTitle"] = obj(show=lit(True), text=mexpr(subtitle), fontSize=lit(8.5),
                              fontColor=colour(MUTED))
    return out


def dynamic_text(name: str, x: int, y: int, w: int, h: int, z: int, measure_name: str,
                 size: float = 10.0, color: str = BODY, align: str = "left",
                 bold: bool = False) -> dict:
    """Text from a measure. A textbox cannot bind a field, so this is an invisible shape whose
    container title is the measure, with wrapping on."""
    container = no_chrome()
    container["title"] = obj(show=lit(True), text=mexpr(measure_name), fontSize=lit(size),
                             fontColor=colour(color), bold=lit(bold), titleWrap=lit(True),
                             alignment=lit(align))
    node = visual(name, "shape", x, y, w, h, z, container=container)
    # show=false alone left the theme's navy fill painted under the text; a fully transparent
    # fill, set both bare and on the default selector, is what actually clears it.
    clear_fill = {"show": lit(True), "fillColor": colour(PAPER), "transparency": lit(100.0)}
    no_line = {"show": lit(False)}
    node["visual"]["objects"] = {
        "shape": [{"properties": {"tileShape": lit("rectangle")}, "selector": {"id": "default"}}],
        "fill": [{"properties": clear_fill}, {"properties": clear_fill, "selector": {"id": "default"}}],
        "outline": [{"properties": no_line}, {"properties": no_line, "selector": {"id": "default"}}],
    }
    return node


def svg_image(name: str, x: int, y: int, w: int, h: int, z: int, measure_name: str) -> dict:
    """An image visual showing an SVG measure (dataCategory ImageUrl). The SVG is drawn at the
    visual's size, so fit is Normal and the container adds nothing."""
    node = visual(name, "image", x, y, w, h, z, container=no_chrome())
    node["visual"]["objects"] = {
        "image": [{"properties": {
            "sourceType": lit("imageData"),
            "sourceField": mexpr(measure_name),
            "fit": lit("Normal"),
        }}],
    }
    return node


def button_slicer(name: str, x: int, y: int, w: int, h: int, z: int, table: str, col: str,
                  default, columns: int, header: str | None = None,
                  filters: list | None = None) -> dict:
    """A tile slicer with one choice always selected. On a disconnected table it filters
    nothing - measures read the choice with SELECTEDVALUE."""
    alias = "b"
    container = no_chrome()
    if header:
        container["title"] = obj(show=lit(True), text=lit(header), fontSize=lit(8.5), bold=lit(True),
                                 fontColor=colour(MUTED))
    return visual(
        name, "advancedSlicerVisual", x, y, w, h, z,
        query={"queryState": {"Values": {"projections": [column(table, col)]}}},
        objects={
            "general": [{"properties": {"filter": {"filter": {
                "Version": 2,
                "From": [{"Name": alias, "Entity": table, "Type": 0}],
                "Where": [{"Condition": {"In": {
                    "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}},
                                                "Property": col}}],
                    "Values": [[lit(default)["expr"]]],
                }}}],
            }}}}],
            "selection": [{"properties": {"strictSingleSelect": lit(True),
                                          "selectAllCheckboxEnabled": lit(False)}}],
            "layout": [{"properties": {"rowCount": lit(1), "columnCount": lit(columns),
                                       "cellPadding": lit(0)}}],
            "shapeCustomRectangle": [{"properties": {"tileShape": lit("rectangleRoundedByPixel"),
                                                     "rectangleRoundedCurve": lit(3)},
                                      "selector": {"id": "default"}}],
            "fillCustom": [
                {"properties": {"show": lit(True), "fillColor": colour(CARD)}, "selector": {"id": "default"}},
                {"properties": {"show": lit(True), "fillColor": colour(INK)}, "selector": {"id": "selected"}},
                {"properties": {"show": lit(True), "fillColor": colour(PAPER)}, "selector": {"id": "hover"}},
            ],
            "outline": [
                {"properties": {"show": lit(True), "lineColor": colour(RULE), "weight": lit(1.0)},
                 "selector": {"id": "default"}},
                {"properties": {"show": lit(True), "lineColor": colour(INK), "weight": lit(1.0)},
                 "selector": {"id": "selected"}},
            ],
            "value": [
                {"properties": {"fontColor": colour(BODY), "fontSize": lit(9.0), "bold": lit(True),
                                "horizontalAlignment": lit("center")}, "selector": {"id": "default"}},
                {"properties": {"fontColor": colour(CARD)}, "selector": {"id": "selected"}},
            ],
            "label": [{"properties": {"show": lit(False)}, "selector": {"id": "default"}}],
            "icon": [{"properties": {"show": lit(False)}, "selector": {"id": "default"}}],
            "selectionIcon": [{"properties": {"show": lit(False)}, "selector": {"id": "default"}}],
        },
        container=container,
        filters=filters,
    )


def action_button(name: str, x: int, y: int, w: int, h: int, z: int, text: str | None,
                  bookmark: str, fill: str = CARD, text_colour: str = INK,
                  outline: str | None = INK, transparency: float = 0.0) -> dict:
    """A button that applies a bookmark. PBIR needs each state object twice - once bare and once
    with the 'default' id selector - or Desktop ignores the styling."""
    def dual(props: dict) -> list:
        return [{"properties": props}, {"properties": props, "selector": {"id": "default"}}]

    objects = {
        "shape": [{"properties": {"tileShape": lit("rectangleRoundedByPixel"),
                                  "rectangleRoundedCurve": lit(4)}}],
        "fill": dual({"show": lit(True), "fillColor": colour(fill), "transparency": lit(transparency)}),
        "outline": dual({"show": lit(outline is not None),
                         **({"lineColor": colour(outline), "weight": lit(1.0)} if outline else {})}),
        "icon": dual({"show": lit(False)}),
        "text": dual({"show": lit(text is not None),
                      **({"text": lit(text), "fontColor": colour(text_colour), "fontSize": lit(10.0),
                          "bold": lit(True)} if text else {})}),
    }
    container = no_chrome()
    container["visualLink"] = obj(show=lit(True), type=lit("Bookmark"), bookmark=lit(bookmark))
    node = visual(name, "actionButton", x, y, w, h, z, container=container)
    node["visual"]["objects"] = objects
    node["howCreated"] = "InsertVisualButton"
    return node


def measure_range_filter(name: str, measure_name: str, low: int, high: int) -> dict:
    """Visual-level 'measure is between low and high' filter. Used to keep ranks 1..N of a
    rank measure whose direction a slicer flips - a TopN filter cannot change direction."""
    ref = {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": measure_name}}
    return {
        "name": name,
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Metrics"}}, "Property": measure_name}},
        "type": "Advanced",
        "filter": {
            "Version": 2,
            "From": [{"Name": "m", "Entity": "Metrics", "Type": 0}],
            "Where": [{"Condition": {"And": {
                "Left": {"Comparison": {"ComparisonKind": 2, "Left": ref, "Right": lit(low)["expr"]}},
                "Right": {"Comparison": {"ComparisonKind": 4, "Left": ref, "Right": lit(high)["expr"]}},
            }}}],
        },
    }


def hide(node: dict) -> dict:
    node["isHidden"] = True
    return node


def toggle_bookmarks(page_name: str, prefix: str, display: str, visuals: list[dict]) -> list[dict]:
    """An open/close pair of bookmarks for a hidden panel. Both touch only the panel's visuals
    and carry no data state, so opening the panel never resets a slicer."""
    names = [v["name"] for v in visuals]

    def one(suffix: str, hidden: bool) -> dict:
        containers = {}
        for v in visuals:
            single = {"visualType": v["visual"]["visualType"], "objects": {}}
            if hidden:
                single["display"] = {"mode": "hidden"}
            containers[v["name"]] = {"singleVisual": single}
        return {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/2.1.0/schema.json",
            "displayName": f"{display} {suffix.lower()}",
            "name": f"{prefix}{suffix}",
            "options": {"targetVisualNames": names, "applyOnlyToTargetVisuals": True,
                        "suppressData": True, "suppressActiveSection": True},
            "explorationState": {
                "version": "1.3",
                "activeSection": page_name,
                "sections": {page_name: {"visualContainers": containers}},
            },
        }

    return [one("Open", False), one("Closed", True)]


YEAR_COLOURS = {2021: LIGHT, 2022: SLATE, 2023: GOLD, 2024: NAVY}
CATEGORY_COLOURS = {"Technology": NAVY, "Furniture": GOLD, "Office Supplies": SLATE}
SEGMENT_COLOURS = {"Consumer": NAVY, "Corporate": GOLD, "Home Office": SLATE}
REGION_COLOURS = {"West": NAVY, "East": GOLD, "Central": SLATE, "South": LIGHT}
SHIP_COLOURS = {"Same Day": GOLD, "First Class": NAVY, "Second Class": SLATE,
                "Standard Class": LIGHT}

# Slicer geometry, shared so the top right of every page lines up.
SL_Y, SL_H = 74, 84
SL1_X, SL2_X, SL_W = 1076, 1246, 170


# --------------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------------


def page_overview() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Ovr",
        "Superstore sales, 2021 to 2024",
        "Four years of a US office-supplies retailer: 9,800 order lines, 4,922 orders, 793 "
        "customers, 49 states. Every figure follows the year slicer; with nothing selected it "
        "covers the whole period.",
        "01 / OVERVIEW",
    )
    v.append(slicer("vYearOvr", SL1_X, SL_Y, SL_W, SL_H, 400, "Date", "Year", "YEAR"))
    v.append(kpi_card("vPeriodOvr", SL2_X, SL_Y, SL_W, SL_H, 410,
                      [m("Report Period", "Figures for")], value_size=11.0))

    v.append(kpi_card("vKpiOvr", 24, 176, 1392, 92, 500, [
        m("Sales", "Sales"),
        m("Orders", "Orders"),
        m("Customers", "Customers"),
        m("Average Order Value", "Average order value"),
        m("Sales per Customer", "Sales per customer"),
    ]))

    # One line per year on a January-to-December axis: the seasonal shape and the growth are
    # visible in the same picture, which a single four-year line hides.
    v.append(visual(
        "vSeason", "lineChart", 24, 284, 900, 300, 600,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Month Short", "Month")]},
                "Series": {"projections": [column("Date", "Year", active=False)]},
                "Y": {"projections": [m("Sales")]},
            },
            "sortDefinition": sort_by(column("Date", "Month Short"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(),
            "labels": no_labels(),
            "lineStyles": [{"properties": {
                "strokeWidth": lit(2), "lineStyle": lit("solid"), "showMarker": lit(False),
            }}],
            "dataPoint": value_colours("Date", "Year", YEAR_COLOURS),
        },
        container=chrome("Sales by month, one line per year",
                         "November and December carry every year; 2024 is the first to clear $100k in a month"),
    ))

    v.append(table_visual(
        "vYears", 940, 284, 476, 300, 610,
        [
            column("Date", "Year"),
            m("Sales", "Sales"),
            m("Sales YoY %", "vs prior year"),
            m("Orders", "Orders"),
            m("Customers", "Customers"),
            m("Average Order Value", "Avg order"),
        ],
        sort_by(column("Date", "Year"), "Ascending"),
        "Year by year",
        "Growth arrived in 2023 and compounded; the customer count barely moved",
    ))

    v.append(visual(
        "vSegment", "barChart", 24, 600, 452, 276, 620,
        query={
            "queryState": {
                "Category": {"projections": [column("Customer", "Segment")]},
                "Y": {"projections": [m("Sales")]},
                "Tooltips": {"projections": [m("Sales Share", "Share of sales"),
                                             m("Customers", "Customers")]},
            },
            "sortDefinition": sort_by(m("Sales")),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(),
            "dataPoint": value_colours("Customer", "Segment", SEGMENT_COLOURS),
        },
        container=chrome("Sales by segment"),
    ))

    v.append(visual(
        "vMix", "hundredPercentStackedColumnChart", 492, 600, 452, 276, 630,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Year")]},
                "Series": {"projections": [column("Product", "Category", active=False)]},
                "Y": {"projections": [m("Sales")]},
            },
            "sortDefinition": sort_by(column("Date", "Year"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(),
            "labels": no_labels(),
            "dataPoint": value_colours("Product", "Category", CATEGORY_COLOURS),
        },
        container=chrome("Category mix by year", "A stable third each - the mix does not explain the growth"),
    ))

    v.append(visual(
        "vRegion", "barChart", 960, 600, 456, 276, 640,
        query={
            "queryState": {
                "Category": {"projections": [column("Geography", "Region")]},
                "Y": {"projections": [m("Sales")]},
                "Tooltips": {"projections": [m("Sales Share", "Share of sales"),
                                             m("Orders", "Orders")]},
            },
            "sortDefinition": sort_by(m("Sales")),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(),
            "dataPoint": value_colours("Geography", "Region", REGION_COLOURS),
        },
        container=chrome("Sales by region"),
    ))

    return page("pgOverview", "Overview"), v


def page_products() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Prd",
        "What sells",
        "Three categories, seventeen sub-categories, 1,893 products. Technology and Furniture "
        "carry the ticket sizes; Office Supplies carries the volume. The year defaults to 2024 "
        "so the change columns compare one year with the one before it.",
        "02 / PRODUCTS",
    )
    v.append(slicer("vYearPrd", SL1_X, SL_Y, SL_W, SL_H, 400, "Date", "Year", "YEAR",
                    default=[2024]))
    v.append(slicer("vCatPrd", SL2_X, SL_Y, SL_W, SL_H, 410, "Product", "Category", "CATEGORY"))

    # Columns sorted by sales with the cumulative share as a line: the Pareto in one picture.
    v.append(visual(
        "vPareto", "lineClusteredColumnComboChart", 24, 176, 700, 316, 500,
        query={
            "queryState": {
                "Category": {"projections": [column("Product", "Sub-Category")]},
                "Y": {"projections": [m("Sales")]},
                "Y2": {"projections": [m("Cumulative Sales Share", "Cumulative share")]},
            },
            "sortDefinition": sort_by(m("Sales")),
        },
        objects={
            "categoryAxis": axis(size=8.0),
            "valueAxis": axis(gridlines=True, secShow=lit(True), secStart=lit(0.0),
                              secEnd=lit(1.0), secLabelColor=colour(MUTED), secFontSize=lit(8.5),
                              secShowAxisTitle=lit(False)),
            "legend": legend(), "labels": no_labels(),
            "dataPoint": series_colour({"Metrics.Sales": NAVY,
                                        "Metrics.Cumulative Sales Share": GOLD}),
            "lineStyles": [{"properties": {"strokeWidth": lit(2), "showMarker": lit(True),
                                           "markerSize": lit(3)}}],
        },
        container=chrome("Sub-categories ranked by sales, with the cumulative share",
                         "Five sub-categories are two-thirds of everything"),
    ))

    v.append(visual(
        "vYoY", "columnChart", 24, 508, 700, 368, 510,
        query={
            "queryState": {
                "Category": {"projections": [column("Product", "Sub-Category")]},
                "Y": {"projections": [m("Sales YoY %", "vs prior year")]},
                "Tooltips": {"projections": [m("Sales"), m("Sales PY", "Prior year")]},
            },
            "sortDefinition": sort_by(m("Sales YoY %")),
        },
        objects={
            "categoryAxis": axis(size=8.0), "valueAxis": axis(gridlines=True),
            "legend": legend(False), "labels": data_labels(size=8.0),
            "dataPoint": obj(fill=colour(NAVY)),
        },
        container=chrome("Change on the prior year, by sub-category",
                         "Blank when the year slicer is cleared - a four-year total has no prior year"),
    ))

    v.append(table_visual(
        "vTopProducts", 748, 176, 668, 420, 520,
        [
            m("Product Rank", "#"),
            column("Product", "Product"),
            m("Sales", "Sales"),
            m("Orders", "Orders"),
            m("Sales Share", "Share"),
        ],
        sort_by(m("Sales")),
        "Products ranked by sales",
        "Rank is within the current selection; scroll for all 1,893",
    ))

    v.append(visual(
        "vCatSeg", "barChart", 748, 612, 668, 264, 530,
        query={
            "queryState": {
                "Category": {"projections": [column("Product", "Category")]},
                "Series": {"projections": [column("Customer", "Segment", active=False)]},
                "Y": {"projections": [m("Sales")]},
            },
            "sortDefinition": sort_by(m("Sales")),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(),
            "labels": no_labels(),
            "dataPoint": value_colours("Customer", "Segment", SEGMENT_COLOURS),
        },
        container=chrome("Category by segment", "Consumer is half of every category"),
    ))

    return page("pgProducts", "Products"), v


def page_customers() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Cst",
        "Who buys, and who comes back",
        "793 customers, and the base barely changes: 589 placed their first order in 2021 and "
        "only 11 arrived in 2024. This is a repeat-business dataset - 87% of customers have "
        "four or more orders - so retention is the story, not acquisition.",
        "03 / CUSTOMERS",
    )
    v.append(slicer("vYearCst", SL1_X, SL_Y, SL_W, SL_H, 400, "Date", "Year", "YEAR"))
    v.append(slicer("vSegCst", SL2_X, SL_Y, SL_W, SL_H, 410, "Customer", "Segment", "SEGMENT"))

    v.append(kpi_card("vKpiCst", 24, 176, 1392, 92, 500, [
        m("Customers", "Active customers"),
        m("Orders per Customer", "Orders per customer"),
        m("Sales per Customer", "Sales per customer"),
        m("Repeat Customer Share", "Ordered more than once"),
        m("Customers Active Every Year", "Active in every year shown"),
    ]))

    v.append(visual(
        "vNewRet", "columnChart", 24, 284, 700, 300, 600,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Year")]},
                "Y": {"projections": [m("Returning Customers", "Returning"),
                                      m("New Customers", "New")]},
            },
            "sortDefinition": sort_by(column("Date", "Year"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(),
            "labels": data_labels(size=8.0),
            "dataPoint": series_colour({"Metrics.Returning Customers": NAVY,
                                        "Metrics.New Customers": GOLD}),
        },
        container=chrome("Active customers by year, new against returning",
                         "New means a first ever order in that year"),
    ))

    v.append(visual(
        "vCohort", "pivotTable", 740, 284, 676, 300, 610,
        query={
            "queryState": {
                "Rows": {"projections": [column("Customer", "Cohort", "First order")]},
                "Columns": {"projections": [column("Date", "Year", "Active in")]},
                "Values": {"projections": [m("Retention %", "Retention")]},
            },
        },
        objects={
            "grid": [{"properties": {
                "gridVertical": lit(False), "gridHorizontal": lit(True),
                "gridHorizontalColor": colour(RULE), "rowPadding": lit(10),
            }}],
            "columnHeaders": [{"properties": {
                "fontSize": lit(9.5), "bold": lit(True), "fontColor": colour(INK),
                "backColor": colour(CARD), "alignment": lit("Right"),
            }}],
            "rowHeaders": [{"properties": {
                "fontSize": lit(9.5), "fontColor": colour(INK), "backColor": colour(CARD),
                "bold": lit(True),
            }}],
            "values": [{"properties": {
                "fontSize": lit(10.0), "fontColorPrimary": colour(BODY),
                "backColorPrimary": colour(CARD), "backColorSecondary": colour(CARD),
            }}],
            "subTotals": [{"properties": {"rowSubtotals": lit(False),
                                          "columnSubtotals": lit(False)}}],
        },
        container=chrome("Cohort retention: share of each year's new customers active in later years",
                         "Read across a row. The cohort's own year is 100% by definition"),
    ))

    v.append(visual(
        "vBands", "columnChart", 24, 600, 452, 276, 620,
        query={
            "queryState": {
                "Category": {"projections": [column("Customer", "Order Band", "Lifetime orders")]},
                "Y": {"projections": [m("Customers")]},
                "Tooltips": {"projections": [m("Sales")]},
            },
            "sortDefinition": sort_by(column("Customer", "Order Band"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(),
            "dataPoint": obj(fill=colour(NAVY)),
        },
        container=chrome("Customers by lifetime order count", "Bands are lifetime, the count follows the year"),
    ))

    v.append(visual(
        "vAovSeg", "barChart", 492, 600, 452, 276, 630,
        query={
            "queryState": {
                "Category": {"projections": [column("Customer", "Segment")]},
                "Y": {"projections": [m("Average Order Value", "Average order value")]},
                "Tooltips": {"projections": [m("Orders"), m("Sales per Customer", "Sales per customer")]},
            },
            "sortDefinition": sort_by(m("Average Order Value")),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(),
            "dataPoint": value_colours("Customer", "Segment", SEGMENT_COLOURS),
        },
        container=chrome("Average order value by segment"),
    ))

    v.append(table_visual(
        "vTopCustomers", 960, 600, 456, 276, 640,
        [
            m("Customer Rank", "#"),
            column("Customer", "Customer"),
            m("Sales", "Sales"),
            m("Orders", "Orders"),
        ],
        sort_by(m("Sales")),
        "Customers ranked by sales",
    ))

    return page("pgCustomers", "Customers"), v


def page_geography() -> tuple[dict, list[dict]]:
    v: list[dict] = []
    v += masthead(
        "Geo",
        "Where it goes, and how fast",
        "California and New York are a third of everything. Standard Class carries six in ten "
        "orders and takes five days; Same Day is one order in twenty. Shipping is measured as "
        "calendar days from order to ship, which the source records for every line.",
        "04 / GEOGRAPHY AND SHIPPING",
    )
    v.append(slicer("vYearGeo", SL1_X, SL_Y, SL_W, SL_H, 400, "Date", "Year", "YEAR"))
    v.append(slicer("vRegGeo", SL2_X, SL_Y, SL_W, SL_H, 410, "Geography", "Region", "REGION"))

    v.append(visual(
        "vStates", "barChart", 24, 176, 560, 700, 500,
        query={
            "queryState": {
                "Category": {"projections": [column("Geography", "State")]},
                "Y": {"projections": [m("Sales")]},
                "Tooltips": {"projections": [m("State Rank", "Rank"), m("Sales Share", "Share of sales"),
                                             m("Orders"), m("Customers")]},
            },
            "sortDefinition": sort_by(m("Sales")),
        },
        objects={
            "categoryAxis": axis(size=8.0), "valueAxis": axis(gridlines=True),
            "legend": legend(False), "labels": no_labels(),
            "dataPoint": obj(fill=colour(NAVY)),
        },
        container=chrome("States ranked by sales", "Scroll for all 49"),
    ))

    v.append(visual(
        "vRegionTrend", "lineChart", 600, 176, 816, 230, 510,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Quarter Year", "Quarter")]},
                "Series": {"projections": [column("Geography", "Region", active=False)]},
                "Y": {"projections": [m("Sales")]},
            },
            "sortDefinition": sort_by(column("Date", "Quarter Year"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(size=8.0), "valueAxis": axis(gridlines=True), "legend": legend(),
            "labels": no_labels(),
            "lineStyles": [{"properties": {"strokeWidth": lit(2), "showMarker": lit(False)}}],
            "dataPoint": value_colours("Geography", "Region", REGION_COLOURS),
        },
        container=chrome("Sales by region, by quarter", "West and East pull away from 2023"),
    ))

    v.append(visual(
        "vShipOrders", "barChart", 600, 422, 400, 226, 520,
        query={
            "queryState": {
                "Category": {"projections": [column("Ship Mode", "Ship Mode")]},
                "Y": {"projections": [m("Ship Mode Share", "Share of orders")]},
                "Tooltips": {"projections": [m("Orders"), m("Sales")]},
            },
            "sortDefinition": sort_by(column("Ship Mode", "Ship Mode"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(),
            "dataPoint": value_colours("Ship Mode", "Ship Mode", SHIP_COLOURS),
        },
        container=chrome("Orders by ship mode"),
    ))

    v.append(visual(
        "vShipDays", "barChart", 1016, 422, 400, 226, 530,
        query={
            "queryState": {
                "Category": {"projections": [column("Ship Mode", "Ship Mode")]},
                "Y": {"projections": [m("Average Ship Days", "Days to ship")]},
                "Tooltips": {"projections": [m("Order Lines", "Order lines")]},
            },
            "sortDefinition": sort_by(column("Ship Mode", "Ship Mode"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(),
            "dataPoint": value_colours("Ship Mode", "Ship Mode", SHIP_COLOURS),
        },
        container=chrome("Average days from order to ship"),
    ))

    v.append(visual(
        "vShipMix", "hundredPercentStackedColumnChart", 600, 664, 400, 212, 540,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Year")]},
                "Series": {"projections": [column("Ship Mode", "Ship Mode", active=False)]},
                "Y": {"projections": [m("Orders")]},
            },
            "sortDefinition": sort_by(column("Date", "Year"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(),
            "labels": no_labels(),
            "dataPoint": value_colours("Ship Mode", "Ship Mode", SHIP_COLOURS),
        },
        container=chrome("Ship mode mix by year", "The mix has not moved"),
    ))

    v.append(visual(
        "vCities", "barChart", 1016, 664, 400, 212, 550,
        query={
            "queryState": {
                "Category": {"projections": [column("Geography", "City")]},
                "Y": {"projections": [m("Sales")]},
                "Tooltips": {"projections": [m("Orders"), m("Sales Share", "Share of sales")]},
            },
            "sortDefinition": sort_by(m("Sales")),
        },
        objects={
            "categoryAxis": axis(size=8.0), "valueAxis": axis(gridlines=True),
            "legend": legend(False), "labels": no_labels(),
            "dataPoint": obj(fill=colour(GOLD)),
        },
        container=chrome("Cities ranked by sales", "Scroll for all 529"),
    ))

    return page("pgGeography", "Geography & shipping"), v


REVENUE_BOOKMARKS: list[dict] = []


def ranked_table(name: str, x: int, y: int, label: str, table: str, col: str, display: str) -> dict:
    """Top or Bottom 8 by change on the comparison year, with a diverging SVG bar per row."""
    rank = f"{label} Change Rank"
    node = visual(
        name, "pivotTable", x, y, 688, 264, 700,
        query={"queryState": {
            "Rows": {"projections": [column(table, col, display)]},
            "Values": {"projections": [
                m(rank, "Rank"),
                m("Sales", "Sales"),
                m("Sales Comparison", "Comparison"),
                m("Sales vs Comparison", "Change"),
                m(f"{label} Change Bar", " "),
                m("Sales vs Comparison % Label", "%"),
            ]}},
            "sortDefinition": sort_by(m(rank), "Ascending")},
        objects={
            "grid": [{"properties": {
                "gridVertical": lit(False), "gridHorizontal": lit(True),
                "gridHorizontalColor": colour(RULE), "rowPadding": lit(2),
                "imageHeight": lit(16.0), "imageWidth": lit(160.0),
            }}],
            "columnHeaders": [{"properties": {
                "fontSize": lit(9.0), "bold": lit(True), "fontColor": colour(INK),
                "backColor": colour(CARD), "alignment": lit("Right"),
            }}],
            "rowHeaders": [{"properties": {
                "fontSize": lit(9.0), "fontColor": colour(BODY), "backColor": colour(CARD),
            }}],
            "values": [
                {"properties": {"fontSize": lit(9.0), "fontColorPrimary": colour(BODY),
                                "backColorPrimary": colour(CARD), "backColorSecondary": colour(CARD)}},
                # Green or red change, from the same colour measure the variance columns use.
                {"properties": {"fontColor": {"solid": {"color": mexpr("Variance Colour")}}},
                 "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                              "metadata": "Metrics.Sales vs Comparison"}},
            ],
            "subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}],
        },
        container=dynamic_chrome(f"Title {label} Table", f"Subtitle {label} Table"),
        filters=[measure_range_filter(f"f{name}Top", rank, 1, 8)],
    )
    return node


def page_revenue() -> tuple[dict, list[dict]]:
    """The comparison page: built from design/revenue-mockup.html, every block a measure."""
    pg_name = "pgRevenue"
    v: list[dict] = []
    v += masthead("Rev", "Revenue against the comparison year", None, "05 / REVENUE")
    v.append(dynamic_text("vStandRev", 18, 112, 700, 56, 95, "Title Standfirst", size=10.0))

    v.append(button_slicer("vYearRev", 740, 72, 210, 64, 400, "Date", "Year", 2024, 3, header="YEAR",
                           filters=[categorical_filter("fYearRev", "Date", "Year", [2022, 2023, 2024])]))
    v.append(button_slicer("vCompRev", 966, 72, 280, 64, 410, "Comparison", "Comparison", "Prior year", 2,
                           header="COMPARE WITH"))
    v.append(action_button("vFiltersRev", 1262, 96, 154, 34, 420, "Filters", "bmFiltersOpen"))
    v.append(dynamic_text("vChipRev", 1250, 132, 178, 28, 430, "Filter Summary", size=8.0,
                          color=MUTED, align="center"))

    for i, card_measure in enumerate(["Card Sales", "Card Customers", "Card Regions", "Card Sub-categories"]):
        v.append(svg_image(f"vCard{i + 1}Rev", 24 + i * 352, 176, 336, 140, 500 + i * 10, card_measure))

    v.append(visual(
        "vLineRev", "lineChart", 24, 332, 688, 264, 600,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Month Short", "Month")]},
                "Y": {"projections": [m("Sales Line", "Selected year"),
                                      m("Comparison Line", "Comparison year")]},
            },
            "sortDefinition": sort_by(column("Date", "Month Short"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True, labelDisplayUnits=lit(1000)),
            "legend": legend(position="Top"),
            "labels": no_labels(),
            "dataPoint": series_colour({"Metrics.Sales Line": NAVY, "Metrics.Comparison Line": SLATE}),
            "lineStyles": [
                {"properties": {"strokeWidth": lit(2), "showMarker": lit(False), "lineStyle": lit("solid")}},
                obj_for("Metrics.Comparison Line", lineStyle=lit("dashed"), strokeWidth=lit(2)),
            ],
        },
        container=dynamic_chrome("Title Line Chart", "Subtitle Line Chart"),
    ))
    v.append(button_slicer("vViewRev", 494, 338, 208, 40, 610, "Line View", "View", "Month", 2))

    v.append(visual(
        "vVarRev", "columnChart", 728, 332, 688, 264, 620,
        query={
            "queryState": {
                "Category": {"projections": [column("Date", "Month Short", "Month")]},
                "Y": {"projections": [m("Sales vs Comparison", "Change")]},
                "Tooltips": {"projections": [m("Sales"), m("Sales Comparison", "Comparison")]},
            },
            "sortDefinition": sort_by(column("Date", "Month Short"), "Ascending"),
        },
        objects={
            "categoryAxis": axis(), "valueAxis": axis(gridlines=True), "legend": legend(False),
            "labels": data_labels(size=8.0, units=1000),
            "dataPoint": [{"properties": {"fill": {"solid": {"color": mexpr("Variance Colour")}}},
                           "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}],
        },
        container=dynamic_chrome("Title Variance Chart", "Subtitle Variance Chart"),
    ))

    v.append(ranked_table("vCustRev", 24, 612, "Customer", "Customer", "Customer", "Customer"))
    v.append(button_slicer("vCustShowRev", 554, 618, 148, 40, 710, "Customer Ranking", "Show", "Top", 2))
    v.append(ranked_table("vSubRev", 728, 612, "Sub-category", "Product", "Sub-Category", "Sub-category"))
    v.append(button_slicer("vSubShowRev", 1258, 618, 148, 40, 720, "Sub-category Ranking", "Show", "Top", 2))

    # The filter panel: hidden on load, opened by the Filters button, closed by Done or a click on
    # the scrim. It is plain visuals toggled by two bookmarks - no group, so no relative geometry.
    panel = [
        action_button("vScrimRev", 0, 0, CANVAS_W, CANVAS_H, 2000, None, "bmFiltersClosed",
                      fill=INK, outline=None, transparency=65.0),
        textbox("vPanelRev", 1076, 118, 340, 356, 2010, [[{"text": "", "size": 6}]], background=CARD),
        textbox("vPanelHeadRev", 1092, 128, 300, 52, 2020, [
            [{"text": "Filters", "size": 14, "color": INK, "bold": True}],
            [{"text": "Apply to every number on this page, cards included.", "size": 8.5, "color": MUTED}],
        ]),
        slicer("vSegRev", 1092, 184, 308, 80, 2030, "Customer", "Segment", "SEGMENT"),
        slicer("vRegRev", 1092, 268, 308, 80, 2040, "Geography", "Region", "REGION"),
        slicer("vCatRev", 1092, 352, 308, 80, 2050, "Product", "Category", "CATEGORY"),
        action_button("vDoneRev", 1092, 428, 308, 34, 2060, "Done", "bmFiltersClosed",
                      fill=INK, text_colour=CARD),
    ]
    panel[1]["visual"]["visualContainerObjects"]["border"] = obj(show=lit(True), color=colour(RULE),
                                                                 radius=lit(6))
    v += [hide(p) for p in panel]

    REVENUE_BOOKMARKS[:] = toggle_bookmarks(pg_name, "bmFilters", "Filters", panel)
    return page(pg_name, "Revenue"), v


# --------------------------------------------------------------------------------------------
# Theme and assembly
# --------------------------------------------------------------------------------------------


def theme() -> dict:
    return {
        # Desktop caches themes by name, and the name must match the filename exactly.
        "name": THEME_NAME,
        "dataColors": [NAVY, GOLD, SLATE, LIGHT, GOOD, BAD, GOLD_TEXT, MUTED],
        "background": PAPER,
        "foreground": BODY,
        "tableAccent": INK,
        "good": GOOD,
        "neutral": MUTED,
        "bad": BAD,
        "textClasses": {
            "title": {"fontFace": "Segoe UI Semibold", "fontSize": 14, "color": INK},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 11, "color": INK},
            "label": {"fontFace": "Segoe UI", "fontSize": 9, "color": BODY},
            "callout": {"fontFace": "Segoe UI", "fontSize": 20, "color": INK},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"show": True, "color": {"solid": {"color": CARD}}}],
                    "border": [{"show": True, "color": {"solid": {"color": RULE}}, "radius": 4}],
                    "padding": [{"top": 8, "bottom": 8, "left": 10, "right": 10}],
                    "dropShadow": [{"show": False}],
                }
            }
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # No BOM: a BOM breaks .platform and PBIR parsing. newline="\n" because write_text otherwise
    # uses the platform ending, and the repo is normalised to LF.
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def rmtree_retry(path: Path) -> None:
    """OneDrive intermittently holds a directory handle open; the files are gone by then."""
    for attempt in range(4):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 3:
                shutil.rmtree(path, ignore_errors=True)
                return
            time.sleep(0.4)


def main() -> None:
    if PAGES.exists():
        rmtree_retry(PAGES)

    builders = [page_overview, page_products, page_customers, page_geography, page_revenue]
    order: list[str] = []
    total_visuals = 0

    for build in builders:
        pg, visuals = build()
        page_dir = PAGES / pg["name"]
        write_json(page_dir / "page.json", pg)
        names = set()
        for node in visuals:
            if node["name"] in names:
                print(f"ERROR: duplicate visual name {node['name']} on {pg['name']}", file=sys.stderr)
                sys.exit(1)
            names.add(node["name"])
            write_json(page_dir / "visuals" / node["name"] / "visual.json", node)
        order.append(pg["name"])
        total_visuals += len(visuals)
        print(f"  {pg['name']:14s} {len(visuals):2d} visuals  ({pg['displayName']})")

    stale = [d for d in PAGES.rglob("visuals/*") if d.is_dir() and not (d / "visual.json").exists()]
    for d in stale:
        rmtree_retry(d)
        if d.exists():
            print(f"ERROR: could not remove stale visual directory {d}. "
                  f"Close Power BI Desktop and run again.", file=sys.stderr)
            sys.exit(1)
        print(f"  swept stale visual directory {d.name}")

    write_json(PAGES / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": order,
        "activePageName": order[0],
    })

    bookmarks_dir = REPORT / "definition" / "bookmarks"
    if bookmarks_dir.exists():
        rmtree_retry(bookmarks_dir)
    for bm in REVENUE_BOOKMARKS:
        write_json(bookmarks_dir / f"{bm['name']}.bookmark.json", bm)
    write_json(bookmarks_dir / "bookmarks.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json",
        "items": [{"name": bm["name"]} for bm in REVENUE_BOOKMARKS],
    })

    write_json(REPORT / "definition" / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })

    write_json(REPORT / "definition" / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {
            "baseTheme": {
                "name": "CY25SU12",
                "reportVersionAtImport": {"visual": "2.12.0", "report": "3.4.0", "page": "2.3.1"},
                "type": "SharedResources",
            },
            "customTheme": {
                "name": THEME_NAME,
                "reportVersionAtImport": {"visual": "2.12.0", "report": "3.4.0", "page": "2.3.1"},
                "type": "RegisteredResources",
            },
        },
        "objects": {
            "section": [{"properties": {"verticalAlignment": lit("Top")}}],
            "outspacePane": [{"properties": {"expanded": lit(False)}}],
        },
        "resourcePackages": [
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": THEME_NAME, "path": THEME_NAME, "type": "CustomTheme"},
                       {"name": MARK_NAME, "path": MARK_NAME, "type": "Image"}]},
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY25SU12", "path": "BaseThemes/CY25SU12.json", "type": "BaseTheme"}]},
        ],
        "settings": {"useStylableVisualContainerHeader": True, "useEnhancedTooltips": False},
    })

    write_json(RESOURCES / THEME_NAME, theme())
    RESOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / "milestone-mark.svg", RESOURCES / MARK_NAME)

    write_json(REPORT / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../Superstore Sales.SemanticModel"}},
    })

    write_json(REPORT / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": "Superstore Sales"},
        "config": {"version": "2.0", "logicalId": "3f6c2d1e-8a4b-4c7d-9e2f-5b1a0c8d7e63"},
    })

    write_json(ROOT / "Superstore Sales.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": "Superstore Sales.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })

    print(f"\n{len(order)} pages, {total_visuals} visuals written")


if __name__ == "__main__":
    main()
