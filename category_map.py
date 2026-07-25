"""Mappings and expected values for Manchester NH budget extraction."""
EXPECTED = {
    "FY2025": {"gf_total": 185_760_157, "gf_revenue": 64_074_762,
               "msd_total": 227_982_610, "msd_property_tax": 120_439_237},
    "FY2026": {"gf_total": 196_511_261, "gf_revenue": 66_487_051,
               "msd_total": 237_999_925, "msd_property_tax": 117_531_711},
}
TRANSIT_OBJECT = "0909"  # excluded from GF totals per the book's own footnote

# Organization label the parser stamps on a detail section whose printed total was split
# across lines, leaving it without one. Lives here because both the parser that emits it and
# the mapping below that has to recognize it need the same literal.
UNATTRIBUTED = "(unattributed)"

# The category totals the current site publishes. These are anchors, not estimates: the
# extraction has to reproduce every one of them to the dollar or the mapping is wrong.
EXPECTED_CATEGORIES = {
    "FY2025": {"Public Safety": 57_760_666, "Retirement": 27_291_207,
               "General Government": 25_559_290, "Highway & Streets": 19_968_652,
               "Health, Dental & Insurance": 17_195_489, "Debt Service": 16_100_000,
               "Other": 10_734_674, "Culture & Recreation": 7_618_111,
               "Health & Welfare": 3_308_180, "Economic Development": 223_888},
    "FY2026": {"Public Safety": 61_551_254, "Retirement": 29_706_516,
               "General Government": 26_788_383, "Highway & Streets": 21_545_314,
               "Health, Dental & Insurance": 17_595_489, "Debt Service": 16_100_000,
               "Other": 11_050_579, "Culture & Recreation": 7_764_641,
               "Health & Welfare": 4_104_665, "Economic Development": 304_420},
}

# Keys are the agency names `parse_book` produces -- i.e. the names printed on the book's
# detail-page footers, which differ from the summary pages' ('Human Resources Department',
# not 'Human Resources'). An agency missing from here is a hard error, not a default, so a
# renamed or new department shows up as a failure instead of a silently dropped budget.
# 'Housing Stability' appears in FY2025 only; every other key is in both books.
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

def NONDEPT_OBJECT_CATEGORY(code, desc):
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

def PW_ORG_CATEGORY(org_name):
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
    raise SystemExit(f"Public Works organization not mapped to a category: {org_name!r}")

def revenue_group(code, desc):
    """Coarse grouping for the general fund's ~170 revenue lines."""
    d = desc.casefold()
    if code == "4083":
        return "Meals & Rooms Tax"
    if "grant" in d or "state aid" in d or code in ("4094", "4109", "4035"):
        return "State Aid & Grants"
    if "reimburse" in d or "chargeback" in d or "charge back" in d or "recover" in d:
        return "Chargebacks & Reimbursements"
    if "in lieu of taxes" in d or "tax lien" in d or "interest on tax" in d:
        return "Other Taxes & PILOTs"
    if any(w in d for w in ("fee", "permit", "license", "rent", "copies", "receipt", "parking")):
        return "Fees, Permits & Charges"
    return "Other Revenue"
