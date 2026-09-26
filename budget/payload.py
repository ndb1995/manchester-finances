"""The payload the site consumes as `window.BUDGET_DATA`, and its rendering as data.js.

Every per-year value in the payload is an object keyed by year label ('FY2026'), in the order
of `years`. A year a figure does not exist for is `null`, never 0: 'not budgeted' and
'budgeted at zero' are different facts, and the site labels them differently.
"""
import json

from .categorize import categorize, department_category, group_revenues, transit_subsidy
from .errors import BudgetError
from .model import EXPENSE, MIXED_CATEGORY, REVENUE, SCHOOL_CATEGORY, UNATTRIBUTED

# The books file airport revenue under the literal agency name 'Various' in the aviation fund
# instead of under 'Aviation'. Merging the two would break the totals the book prints for each,
# so the entry stays separate and only its display name is fixed up here.
DISPLAY_NAME = {"Various": "Aviation - Revenues (Various)"}


def _merge_items(buckets):
    """Pair each year's line items by (object code, description).

    `buckets` is {year: {ItemKey: amount}}, with an empty dict for a year the department is
    absent from, so its items carry `None` for that year.
    """
    keys = sorted(set().union(*buckets.values()))
    return [{"code": code, "desc": desc,
             "amounts": {y: bucket.get((code, desc)) for y, bucket in buckets.items()}}
            for code, desc in keys]


def _org_totals(agencies):
    """{organization: {year: total}} where the book breaks a department into organizations.

    Totals only -- the item-level organization detail restates the department's own line items,
    which the payload already carries. `UNATTRIBUTED` passes through as its literal
    '(unattributed)' so the site can label those sections honestly.
    """
    orgs = {y: (a.org_expenses if a else {}) for y, a in agencies.items()}
    names = sorted(set().union(*orgs.values()))
    return {org: {y: sum(o[org].values()) if org in o else None for y, o in orgs.items()}
            for org in names}


def _department(name, agencies):
    """One department across the extracted years; `agencies` is {year: Agency or None}."""
    present = [a for a in agencies.values() if a]
    latest = present[-1]
    fund = latest.fund_code
    category = department_category(name, fund)
    side = {kind: {y: (a.bucket(kind) if a else {}) for y, a in agencies.items()}
            for kind in (EXPENSE, REVENUE)}
    dept = {"name": DISPLAY_NAME.get(name, name), "bookName": name,
            "code": next((a.code for a in reversed(present) if a.code), None),
            "fund": fund, "generalFund": latest.in_general_fund, "category": category,
            # the departments drawn as their own band in the flow diagram: single-category
            # general fund departments. A split department's money still reaches its
            # categories, just not as one department band.
            "inFlow": latest.in_general_fund and category != MIXED_CATEGORY,
            "expenses": _merge_items(side[EXPENSE]),
            "revenues": _merge_items(side[REVENUE]),
            "totals": {y: sum(b.values()) if agencies[y] else None
                       for y, b in side[EXPENSE].items()},
            "revenueTotals": {y: sum(b.values()) if agencies[y] else None
                              for y, b in side[REVENUE].items()}}
    orgs = _org_totals(agencies)
    if orgs:
        dept["orgs"] = orgs
    return dept


def build_budget_data(years, books):
    """Merge every configured year into the single payload the site draws.

    `years` is every `YearConfig`, oldest first; `books` maps each extracted year's label to
    its parsed `Book`. Hand-entered years contribute their category totals only.
    """
    labels = [y.label for y in years]
    extracted = [y for y in years if y.extracted]
    missing = [y.label for y in extracted if y.label not in books]
    if missing:
        raise BudgetError(f"no parsed book for {', '.join(missing)}")
    parsed = {y.label: categorize(books[y.label]) for y in extracted}

    # the latest year's order first, so a category that only older years carry sorts last
    names = [SCHOOL_CATEGORY] + list(dict.fromkeys(c for y in reversed(years) for c in y.categories))
    categories = {c: {y.label: (y.msd_total if c == SCHOOL_CATEGORY
                                else parsed[y.label].get(c, 0) if y.extracted
                                else y.categories.get(c))
                      for y in years}
                  for c in names}
    revenue = {y.label: group_revenues(books[y.label]) for y in extracted}
    groups = sorted(set().union(*revenue.values()))

    departments = []
    for name in sorted(set().union(*(books[y.label].agencies for y in extracted))):
        departments.append(_department(
            name, {y.label: books[y.label].agencies.get(name) for y in extracted}))
    departments.sort(key=lambda d: d["name"])  # display order, so 'Various' sits with Aviation

    return {
        "years": labels,
        "yearInfo": {y.label: {"period": y.period, "extracted": y.extracted, "asOf": y.as_of}
                     for y in years},
        "meta": {"schoolCategory": SCHOOL_CATEGORY, "unattributedOrg": UNATTRIBUTED},
        "categories": categories,
        "generalFund": {y.label: y.gf_total for y in years},
        "citywide": {y.label: y.citywide for y in years},
        "revenueGroups": {g: {y.label: revenue[y.label].get(g, 0) for y in extracted}
                          for g in groups},
        "propertyTax": {"gf": {y.label: y.gf_total - y.gf_revenue for y in extracted},
                        "msd": {y.label: y.msd_property_tax for y in extracted}},
        "msdOther": {y.label: y.msd_total - y.msd_property_tax for y in extracted},
        "transitSubsidy": {y.label: transit_subsidy(books[y.label]) for y in extracted},
        "departments": departments,
    }


def render_data_js(data):
    """The committed build artifact: a plain assignment, so the site loads from disk with no
    server and no build step."""
    return ("// GENERATED by `python -m budget` -- do not edit by hand.\n"
            "window.BUDGET_DATA = " + json.dumps(data, indent=1) + ";\n")
