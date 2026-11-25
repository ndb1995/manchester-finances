"""The anchors: every figure the extraction must reproduce before data.js is written."""
from .categorize import categorize, gf_totals
from .model import SCHOOL_CATEGORY, agrees
from .parse import ITEM_START_RE


def check_book(book, year, *, categories=None, totals=None):
    """Every anchor for one parsed book, as year-labelled failure strings (empty when it all
    agrees). Parser warnings and dropped item-shaped lines count as failures."""
    failures = [f"{year.label} {w}" for w in book.warnings]
    item_shaped = [f"p{p} {ln}" for p, ln in book.dropped_lines if ITEM_START_RE.match(ln)]
    if item_shaped:
        failures.append(f"{year.label} dropped item-shaped line(s): {'; '.join(item_shaped)}")
    gf_exp, gf_rev = totals if totals is not None else gf_totals(book)
    if not agrees(gf_exp, year.gf_total):
        failures.append(f"{year.label} GF expense total {gf_exp:,} != expected {year.gf_total:,}")
    if not agrees(gf_rev, year.gf_revenue):
        failures.append(f"{year.label} GF revenue total {gf_rev:,} != expected {year.gf_revenue:,}")
    got = categories if categories is not None else categorize(book)
    for category, expected in year.categories.items():
        if not agrees(got.get(category, 0), expected):
            failures.append(f"{year.label} category {category}: "
                            f"{got.get(category, 0):,} != {expected:,}")
    for category in sorted(set(got) - set(year.categories)):
        failures.append(f"{year.label} unexpected category {category}: {got[category]:,}")
    return failures


def check_payload(data):
    """The identities the site relies on, checked on the payload it will actually load.

    The page adds these figures up in several ways -- categories into the General Fund,
    revenue plus property tax into the General Fund, departments into the General Fund plus
    the transit subsidy -- so each way has to land on the same number here rather than be
    trusted in the browser.
    """
    failures = []
    for y in data["years"]:
        gf = data["generalFund"][y]
        school = data["categories"][SCHOOL_CATEGORY][y]
        parts = [v[y] for c, v in data["categories"].items() if c != SCHOOL_CATEGORY]
        if not agrees(sum(v or 0 for v in parts), gf):
            failures.append(f"{y} categories sum to {sum(v or 0 for v in parts):,}, not {gf:,}")
        if data["citywide"][y] != gf + school:
            failures.append(f"{y} citywide {data['citywide'][y]:,} != GF + schools {gf + school:,}")
        if not data["yearInfo"][y]["extracted"]:
            continue
        tax_plus_revenue = data["propertyTax"]["gf"][y] + sum(
            v[y] or 0 for v in data["revenueGroups"].values())
        if not agrees(tax_plus_revenue, gf):
            failures.append(f"{y} property tax + revenue groups {tax_plus_revenue:,} != {gf:,}")
        depts = sum(d["totals"][y] or 0 for d in data["departments"] if d["generalFund"])
        if not agrees(depts - data["transitSubsidy"][y], gf):
            failures.append(f"{y} general fund departments {depts:,} less transit "
                            f"{data['transitSubsidy'][y]:,} != {gf:,}")
    return failures
