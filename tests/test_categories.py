# tests/test_categories.py
import functools

import extract_budget as eb
from category_map import EXPECTED, EXPECTED_CATEGORIES

parsed = functools.lru_cache(maxsize=None)(eb.parse_book)  # parse each book once
FY26, FY25 = "Budget_Book_2026.pdf", "Budget_Book_2025.pdf"

def _check(pdf, fy):
    got = eb.categorize(parsed(pdf))
    exp = EXPECTED_CATEGORIES[fy]
    diffs = {c: (got.get(c, 0), exp[c]) for c in exp if abs(got.get(c, 0) - exp[c]) > 1}
    assert not diffs, f"{fy} category mismatches (got, expected): {diffs}"
    assert set(got) == set(exp), f"{fy} unexpected categories: {set(got) ^ set(exp)}"

def test_categories_fy26():
    _check(FY26, "FY2026")

def test_categories_fy25():
    _check(FY25, "FY2025")

def test_categories_partition_the_general_fund():
    # every GF dollar (transit excluded) lands in exactly one category: the categories are a
    # partition, so their sum has to be the same anchor validate_book checks.
    for pdf, fy in [(FY26, "FY2026"), (FY25, "FY2025")]:
        assert sum(eb.categorize(parsed(pdf)).values()) == EXPECTED[fy]["gf_total"]

def test_categorize_excludes_enterprise_funds():
    # Aviation/EPD/Parking are their own funds; only fund 0101 is the general fund.
    for pdf in (FY26, FY25):
        gf_names = {a["name"] for a in parsed(pdf)["agencies"].values() if a["fund_code"] == "0101"}
        assert "Aviation" not in gf_names and "Parking" not in gf_names

def test_categorize_rejects_an_unmapped_agency():
    book = {"agencies": {"Ministry of Silly Walks": {
        "name": "Ministry of Silly Walks", "fund_code": "0101",
        "expenses": {("0110", "Regular Salary"): 1}, "revenues": {}, "org_expenses": {}}}}
    try:
        eb.categorize(book)
    except SystemExit as exc:
        assert "Ministry of Silly Walks" in str(exc)
    else:
        raise AssertionError("expected SystemExit for an unmapped general fund agency")

def test_public_works_splits_three_ways_exactly():
    # PW is the only agency feeding more than one category, so its split is the only place a
    # category error can hide; the three shares must add back to the department total.
    targets = {FY26: {"Highway & Streets": 21_545_314, "Culture & Recreation": 5_144_949,
                      "General Government": 8_893_057},
               FY25: {"Highway & Streets": 19_968_652, "Culture & Recreation": 5_156_896,
                      "General Government": 8_701_274}}
    for pdf, want in targets.items():
        pw = parsed(pdf)["agencies"]["Public Works"]
        got = {}
        for cat, amt in eb._agency_category_items(pw):
            got[cat] = got.get(cat, 0) + amt
        assert got == want
        assert sum(got.values()) == sum(pw["expenses"].values())

def test_unattributed_public_works_section_is_culture_and_recreation():
    # the West Side Arena and Derryfield sections lost their org labels to split totals
    from category_map import PW_ORG_CATEGORY
    assert PW_ORG_CATEGORY(eb.UNATTRIBUTED) == "Culture & Recreation"
    for pdf in (FY26, FY25):
        orgs = parsed(pdf)["agencies"]["Public Works"]["org_expenses"]
        assert sum(orgs[eb.UNATTRIBUTED].values()) == 357_130

def test_nondepartmental_object_rules():
    from category_map import NONDEPT_OBJECT_CATEGORY as f
    assert f("0228", "City Contributory System") == "Retirement"
    assert f("0211", "Health Insurance") == "Health, Dental & Insurance"
    assert f("0919", "Maturing Debt") == "Debt Service"
    assert f("0230", "FICA") == "Other"

def test_transit_subsidy_is_excluded_from_every_category():
    for pdf in (FY26, FY25):
        nd = parsed(pdf)["agencies"]["Non-Departmental Items"]
        transit = sum(v for (code, _), v in nd["expenses"].items() if code == eb.TRANSIT_OBJECT)
        assert transit > 0  # the book really does budget it
        categorized = sum(amt for _, amt in eb._agency_category_items(nd))
        assert categorized == sum(nd["expenses"].values()) - transit

def test_revenue_groups_partition_fy26():
    groups = eb.group_revenues(parsed(FY26))
    assert abs(sum(groups.values()) - 66_487_051) <= 1

def test_revenue_groups_partition_fy25():
    groups = eb.group_revenues(parsed(FY25))
    assert abs(sum(groups.values()) - 64_074_762) <= 1

def test_meals_and_rooms_tax_is_its_own_group():
    from category_map import revenue_group
    assert revenue_group("4083", "Rooms & Meals Tax Distribution") == "Meals & Rooms Tax"
    assert eb.group_revenues(parsed(FY26))["Meals & Rooms Tax"] > 0

def test_motor_vehicle_group_takes_registrations_before_the_fee_keywords():
    # 'Auto Registration' (22.8M) is the book's largest single general fund revenue and
    # 'Motor Vehicle Title Fee' would otherwise be swallowed by the 'fee' keyword.
    from category_map import revenue_group as g
    assert g("4680", "Auto Registration") == "Motor Vehicle Fees"
    assert g("4681", "Auto Registration Parking") == "Motor Vehicle Fees"
    assert g("4478", "Motor Vehicle Title Fee") == "Motor Vehicle Fees"

def test_investment_group_takes_dividends_before_the_fee_keywords():
    # 'Dividend (Parking Division)' (2.7M) would otherwise match the 'parking' keyword.
    from category_map import revenue_group as g
    assert g("4820", "Dividend (Parking Division)") == "Investment & Dividend Income"
    assert g("4770", "Income from Invested Funds") == "Investment & Dividend Income"

def test_fee_keywords_catch_permit_applications_and_recreation_charges():
    from category_map import revenue_group as g
    for desc in ("Building - Application", "Heating - Application", "Derryfield Country Club",
                 "Ice Arenas", "Drop-Off Center Revenue", "Aquatics"):
        assert g("4999", desc) == "Fees, Permits & Charges", desc

def _gf_lines(pdf, code):
    return [(d, v) for a in parsed(pdf)["agencies"].values() if a["fund_code"] == "0101"
            for (c, d), v in a["revenues"].items() if c == code]

def test_object_code_4820_is_investment_income_in_both_years():
    # the book renames this line between books -- FY2025 'Transfer', FY2026 'Dividend', same
    # code, same agency, same 550,100 -- so routing it by description moved it between groups
    # and showed a spurious year-over-year shift. The object code is the stable fact.
    from category_map import revenue_group as g
    assert g("4820", "Transfer") == "Investment & Dividend Income"
    assert g("4820", "Dividend") == "Investment & Dividend Income"
    for pdf in (FY26, FY25):
        lines = _gf_lines(pdf, "4820")
        assert lines, f"{pdf} has no 4820 revenue"
        for desc, _ in lines:
            assert g("4820", desc) == "Investment & Dividend Income", (pdf, desc)
    assert ("Transfer", 550_100) in _gf_lines(FY25, "4820")
    assert ("Dividend", 550_100) in _gf_lines(FY26, "4820")

def test_ice_keyword_is_word_boundary_matched():
    from category_map import revenue_group as g
    assert g("4426", "Ice Rates") == "Fees, Permits & Charges"
    assert g("4431", "Ice Logos") == "Fees, Permits & Charges"
    # these two are genuine license fees, so they must stay fees -- but on an honest keyword,
    # not on the letters inside 'Serv-ice' and 'Dev-ice-s'
    assert g("4699", "Food Service Establishments") == "Fees, Permits & Charges"
    assert g("4709", "Mech Devices - Each Additional") == "Fees, Permits & Charges"
    # a description that merely contains the letters is not a fee
    assert g("4999", "Notice of Service") == "Other Revenue"

def test_every_revenue_group_is_nonempty_in_both_years():
    want = {"Meals & Rooms Tax", "Motor Vehicle Fees", "Investment & Dividend Income",
            "State Aid & Grants", "Chargebacks & Reimbursements", "Other Taxes & PILOTs",
            "Fees, Permits & Charges", "Other Revenue"}
    for pdf in (FY26, FY25):
        groups = eb.group_revenues(parsed(pdf))
        assert set(groups) == want, f"{pdf}: {set(groups) ^ want}"
        assert all(v > 0 for v in groups.values()), groups

def test_other_revenue_is_not_a_mega_bucket():
    # guard against regressing to the state where the residual was 56% of revenue and would
    # dominate the flow diagram; every large source should have a named group instead.
    for pdf, fy in [(FY26, "FY2026"), (FY25, "FY2025")]:
        groups = eb.group_revenues(parsed(pdf))
        total = EXPECTED[fy]["gf_revenue"]
        share = groups["Other Revenue"] / total
        assert share < 0.20, f"{fy} Other Revenue is {share:.1%} of {total:,}"
