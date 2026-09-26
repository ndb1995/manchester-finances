"""General fund spending by category, revenue by source group, and the totals they must hit."""
from .categories import AGENCY_CATEGORY, SPLIT_RULES, revenue_group
from .errors import BudgetError
from .model import (ENTERPRISE_CATEGORY, EXPENSE, GENERAL_FUND, MIXED_CATEGORY, REVENUE,
                    TRANSIT_OBJECT)


def category_items(agency):
    """Yield (category, amount) for one general fund agency's expense items.

    Most departments belong to a single category; the ones in `SPLIT_RULES` are divided by
    their own rule. The transit subsidy is dropped for every agency, matching `gf_totals`, so
    the categories still add up to the general fund total the book prints.
    """
    if agency.name in SPLIT_RULES:
        rows = SPLIT_RULES[agency.name](agency)
    elif agency.name in AGENCY_CATEGORY:
        category = AGENCY_CATEGORY[agency.name]
        rows = ((category, key, amt) for key, amt in agency.expenses.items())
    else:
        raise BudgetError(f"Agency not mapped to a category: {agency.name!r}")
    for category, (code, _), amt in rows:
        if code != TRANSIT_OBJECT:
            yield category, amt


def categorize(book):
    """General fund expenses by spending category. Enterprise funds are excluded by fund
    code, not by name: they are separately funded and never part of the tax-supported total."""
    out = {}
    for agency in book.general_fund():
        for category, amt in category_items(agency):
            out[category] = out.get(category, 0) + amt
    return out


def group_revenues(book):
    """General fund revenues by source group. Every line lands in exactly one group, so the
    groups sum to the general fund revenue total."""
    out = {}
    for agency in book.general_fund():
        for (code, desc), amt in agency.revenues.items():
            group = revenue_group(code, desc)
            out[group] = out.get(group, 0) + amt
    return out


def gf_totals(book):
    """(expense, revenue) for the general fund, transit subsidy excluded as the book directs."""
    gf = book.general_fund()
    expense = sum(v for a in gf for (code, _), v in a.bucket(EXPENSE).items()
                  if code != TRANSIT_OBJECT)
    return expense, sum(sum(a.bucket(REVENUE).values()) for a in gf)


def transit_subsidy(book):
    """The general fund transit appropriation the book lists but leaves out of its total."""
    return sum(v for a in book.general_fund() for (code, _), v in a.expenses.items()
               if code == TRANSIT_OBJECT)


def department_category(name, fund):
    """The site's spending category for one department, or a hard error for a new one.

    Enterprise funds are their own band: they are separately funded and outside the
    tax-supported total. Within the general fund, the departments in `SPLIT_RULES` get the
    label that says so rather than a single category. Naming one of Non-Departmental Items'
    four categories would be a misstatement on a transparency site: its 76,452,422 is split
    across Retirement, Health, Dental & Insurance, Debt Service and Other, and the smallest
    of those, 'Other', is the 11,050,579 band the site draws next to it. Anything else
    unmapped is a failure, not a default -- a renamed department would otherwise reach the
    flow diagram with a null category and silently disappear.
    """
    if fund != GENERAL_FUND:
        return ENTERPRISE_CATEGORY
    if name in SPLIT_RULES:
        return MIXED_CATEGORY
    if name in AGENCY_CATEGORY:
        return AGENCY_CATEGORY[name]
    raise BudgetError(f"Department not mapped to a category: {name!r}")
