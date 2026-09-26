"""How the budget books' departments and revenue lines map onto the site's categories.

Everything here is a rule about names and codes the books print. The dollar figures those
rules have to reproduce live in `years/*.json`, not here.
"""
import re

from .errors import BudgetError
from .model import UNATTRIBUTED

# Keys are the agency names `parse_book` produces -- i.e. the names printed on the book's
# detail-page footers, which differ from the summary pages' ('Human Resources Department',
# not 'Human Resources'). An agency missing from here and from `SPLIT_RULES` is a hard error,
# not a default, so a renamed or new department shows up as a failure instead of a silently
# dropped budget. 'Housing Stability' appears in FY2025 only; every other key is in both books.
AGENCY_CATEGORY = {
    "Aldermen": "General Government",
    "Board of Assessors": "General Government",
    "Central Fleet Management": "General Government",
    "City Clerk's Office": "General Government",
    "City Solicitor's Office": "General Government",
    "Finance Department": "General Government",
    "Housing Stability": "General Government",
    "Human Resources Department": "General Government",
    "Information Systems": "General Government",
    "Mayor's Office": "General Government",
    "Office of Youth Services": "General Government",
    "Planning & Community Development": "General Government",
    "Tax Collector's Office": "General Government",
    "Fire Department": "Public Safety",
    "Police Department": "Public Safety",
    "Health Department - City": "Health & Welfare",
    "Welfare Department": "Health & Welfare",
    "Library Department": "Culture & Recreation",
    "Manchester Economic Development Office": "Economic Development",
}


def nondepartmental_object_category(code, desc):
    """Split the Non-Departmental Items department by object code.

    It is a single agency holding the city-wide costs no department carries, so the object
    code -- not the organization -- is what separates them. The remainder (FICA, workers'
    comp, severance, insurance premiums, street lighting, civic contributions, CIP) is what
    the site labels 'Other'; the expected totals confirm that residual to the dollar.
    """
    if code in ("0224", "0225", "0228"):  # fire/police state retirement, city contributory
        return "Retirement"
    if code in ("0211", "0212", "0213"):  # health, dental, life
        return "Health, Dental & Insurance"
    if code in ("0919", "0920"):  # maturing debt and its interest
        return "Debt Service"
    return "Other"


def public_works_org_category(org_name):
    """Split Public Works, the one department feeding three categories.

    The book names every PW organization with a division prefix ('Highway-Administration',
    'Facilities-Custodial', 'Parks-City Parks'), so the prefix is the whole rule. Cemetery
    organizations sit under Parks, Recreation & Cemeteries. The two sections the parser
    cannot label -- Parks - West Side Arena and Parks - Derryfield, whose printed totals are
    split across lines on the same page -- are Parks organizations as well.
    """
    n = org_name.casefold()
    if n == UNATTRIBUTED:
        return "Culture & Recreation"
    if n.startswith("highway"):
        return "Highway & Streets"
    if n.startswith("facilit"):
        return "General Government"
    if n.startswith(("park", "cemeter")):
        return "Culture & Recreation"
    raise BudgetError(f"Public Works organization not mapped to a category: {org_name!r}")


def split_by_object(rule):
    """A split that files each of the agency's line items by `rule(code, desc)`."""
    def split(agency):
        for key, amt in agency.expenses.items():
            yield rule(*key), key, amt
    return split


def split_by_organization(rule):
    """A split that files each organization's line items by `rule(org_name)`.

    Uses the `org_expenses` breakdown instead of the flat bucket; the two are equal by
    construction, which the aggregation tests check.
    """
    def split(agency):
        for org, items in agency.org_expenses.items():
            category = rule(org)
            for key, amt in items.items():
                yield category, key, amt
    return split


# The departments that feed more than one category, and how each one is divided. Each rule
# yields (category, item key, amount). Both the categorization and the per-department label
# consult this one table, so a department cannot be split in one place and not the other.
SPLIT_RULES = {
    "Public Works": split_by_organization(public_works_org_category),
    "Non-Departmental Items": split_by_object(nondepartmental_object_category),
}

FEE_WORDS = ("fee", "permit", "license", "rent", "copies", "receipt", "parking",
             "application", "country club", "arena", "aquatic", "drop-off", "admission",
             # 'Food Service Establishments' and 'Mech Devices - Each Additional' are license
             # revenue; they need their own keywords because they used to qualify only through
             # the letters inside 'Serv(ice)' and 'Dev(ice)s'.
             "establishment", "mech devices")
# 'ice' must match as a whole word. As a bare substring it also hits 'Service', 'Devices' and
# 'Police', which would file unrelated lines as fees by coincidence.
FEE_WORD_RE = re.compile(r"\bice\b")


def revenue_group(code, desc):
    """Coarse grouping for the general fund's ~170 revenue lines.

    Order matters. The largest single sources are named explicitly and tested first because
    the generic keyword sweep below would otherwise claim them: 'Motor Vehicle Title Fee'
    contains 'fee', and 'Dividend (Parking Division)' contains 'parking'.
    """
    d = desc.casefold()
    if code == "4083":
        return "Meals & Rooms Tax"
    if code == "4680" or "auto registration" in d or "motor vehicle" in d:
        return "Motor Vehicle Fees"
    # 4820 is matched by code, not description: the book calls the same line 'Dividend' in
    # FY2026 and 'Transfer' in FY2025, and a description rule split it across two groups.
    if code == "4820" or "dividend" in d or "invested funds" in d:
        return "Investment & Dividend Income"
    if "grant" in d or "state aid" in d or code in ("4094", "4109", "4035"):
        return "State Aid & Grants"
    if "reimburse" in d or "chargeback" in d or "charge back" in d or "recover" in d:
        return "Chargebacks & Reimbursements"
    if "in lieu of taxes" in d or "tax lien" in d or "interest on tax" in d:
        return "Other Taxes & PILOTs"
    if FEE_WORD_RE.search(d) or any(w in d for w in FEE_WORDS):
        return "Fees, Permits & Charges"
    return "Other Revenue"
