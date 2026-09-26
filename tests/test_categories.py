# tests/test_categories.py -- spending categories and revenue groups
import pytest

from budget.categories import (SPLIT_RULES, nondepartmental_object_category,
                               public_works_org_category, revenue_group)
from budget.categorize import (category_items, categorize, department_category,
                               group_revenues)
from budget.errors import BudgetError
from budget.model import (ENTERPRISE_CATEGORY, MIXED_CATEGORY, TRANSIT_OBJECT, UNATTRIBUTED,
                          Agency, Book)

REVENUE_GROUPS = {"Meals & Rooms Tax", "Motor Vehicle Fees", "Investment & Dividend Income",
                  "State Aid & Grants", "Chargebacks & Reimbursements", "Other Taxes & PILOTs",
                  "Fees, Permits & Charges", "Other Revenue"}


def test_categories_match_the_published_totals(books, year, fy):
    got, exp = categorize(books[fy]), year[fy].categories
    diffs = {c: (got.get(c, 0), exp[c]) for c in exp if abs(got.get(c, 0) - exp[c]) > 1}
    assert not diffs, f"{fy} category mismatches (got, expected): {diffs}"
    assert set(got) == set(exp), f"{fy} unexpected categories: {set(got) ^ set(exp)}"


def test_categories_partition_the_general_fund(books, year, fy):
    # every GF dollar (transit excluded) lands in exactly one category: the categories are a
    # partition, so their sum has to be the same anchor the book check uses.
    assert sum(categorize(books[fy]).values()) == year[fy].gf_total


def test_categorize_excludes_enterprise_funds(books, fy):
    # Aviation/EPD/Parking are their own funds; only fund 0101 is the general fund.
    gf_names = {a.name for a in books[fy].general_fund()}
    assert "Aviation" not in gf_names and "Parking" not in gf_names


def test_categorize_rejects_an_unmapped_agency():
    book = Book(agencies={"Ministry of Silly Walks": Agency(
        "Ministry of Silly Walks", "0101", expenses={("0110", "Regular Salary"): 1})})
    with pytest.raises(BudgetError, match="Ministry of Silly Walks"):
        categorize(book)


def test_department_category_uses_the_same_split_table():
    # the per-department label and the categorization consult one table, so a split
    # department cannot be split in one place and single-category in the other
    for name in SPLIT_RULES:
        assert department_category(name, "0101") == MIXED_CATEGORY
    assert department_category("Police Department", "0101") == "Public Safety"


def test_unmapped_department_stops_the_build():
    # the site cannot draw a null category, so a new or renamed department is a build failure
    with pytest.raises(BudgetError, match="Ministry of Silly Walks"):
        department_category("Ministry of Silly Walks", "0101")
    assert department_category("Ministry of Silly Walks", "0805") == ENTERPRISE_CATEGORY


def test_public_works_splits_three_ways_exactly(books):
    # PW feeds more than one category, so its split is where a category error can hide; the
    # three shares must add back to the department total.
    targets = {"FY2026": {"Highway & Streets": 21_545_314, "Culture & Recreation": 5_144_949,
                          "General Government": 8_893_057},
               "FY2025": {"Highway & Streets": 19_968_652, "Culture & Recreation": 5_156_896,
                          "General Government": 8_701_274}}
    for fy, want in targets.items():
        pw = books[fy].agencies["Public Works"]
        got = {}
        for cat, amt in category_items(pw):
            got[cat] = got.get(cat, 0) + amt
        assert got == want
        assert sum(got.values()) == sum(pw.expenses.values())


def test_pw_org_category_rejects_an_unrecognized_organization():
    # the PW split is prefix-driven, so a new or renamed organization must fail loudly rather
    # than fall into whichever branch happens to be last. Mirrors the agency-level guard.
    with pytest.raises(BudgetError, match="Zoning-Enforcement"):
        public_works_org_category("Zoning-Enforcement")


def test_unrecognized_public_works_organization_stops_categorize():
    # the guard has to be reachable through the real code path, not just callable directly
    book = Book(agencies={"Public Works": Agency(
        "Public Works", "0101",
        org_expenses={"Zoning-Enforcement": {("0110", "Regular Salary"): 1}})})
    with pytest.raises(BudgetError, match="Zoning-Enforcement"):
        categorize(book)


def test_unattributed_public_works_section_is_culture_and_recreation(books, fy):
    # the West Side Arena and Derryfield sections lost their org labels to split totals
    assert public_works_org_category(UNATTRIBUTED) == "Culture & Recreation"
    orgs = books[fy].agencies["Public Works"].org_expenses
    assert sum(orgs[UNATTRIBUTED].values()) == 357_130


def test_nondepartmental_object_rules():
    f = nondepartmental_object_category
    assert f("0228", "City Contributory System") == "Retirement"
    assert f("0211", "Health Insurance") == "Health, Dental & Insurance"
    assert f("0919", "Maturing Debt") == "Debt Service"
    assert f("0230", "FICA") == "Other"


def test_transit_subsidy_is_excluded_from_every_category(books, fy):
    nd = books[fy].agencies["Non-Departmental Items"]
    transit = sum(v for (code, _), v in nd.expenses.items() if code == TRANSIT_OBJECT)
    assert transit > 0  # the book really does budget it
    categorized = sum(amt for _, amt in category_items(nd))
    assert categorized == sum(nd.expenses.values()) - transit


def test_revenue_groups_partition_the_general_fund_revenue(books, year, fy):
    assert abs(sum(group_revenues(books[fy]).values()) - year[fy].gf_revenue) <= 1


def test_every_revenue_group_is_nonempty(books, fy):
    groups = group_revenues(books[fy])
    assert set(groups) == REVENUE_GROUPS, f"{fy}: {set(groups) ^ REVENUE_GROUPS}"
    assert all(v > 0 for v in groups.values()), groups


def test_other_revenue_is_not_a_mega_bucket(books, year, fy):
    # guard against regressing to the state where the residual was 56% of revenue and would
    # dominate the flow diagram; every large source should have a named group instead.
    share = group_revenues(books[fy])["Other Revenue"] / year[fy].gf_revenue
    assert share < 0.20, f"{fy} Other Revenue is {share:.1%}"


def test_meals_and_rooms_tax_is_its_own_group(books):
    assert revenue_group("4083", "Rooms & Meals Tax Distribution") == "Meals & Rooms Tax"
    assert group_revenues(books["FY2026"])["Meals & Rooms Tax"] > 0


def test_motor_vehicle_group_takes_registrations_before_the_fee_keywords():
    # 'Auto Registration' (22.8M) is the book's largest single general fund revenue and
    # 'Motor Vehicle Title Fee' would otherwise be swallowed by the 'fee' keyword.
    g = revenue_group
    assert g("4680", "Auto Registration") == "Motor Vehicle Fees"
    assert g("4681", "Auto Registration Parking") == "Motor Vehicle Fees"
    assert g("4478", "Motor Vehicle Title Fee") == "Motor Vehicle Fees"


def test_investment_group_takes_dividends_before_the_fee_keywords():
    # 'Dividend (Parking Division)' (2.7M) would otherwise match the 'parking' keyword.
    g = revenue_group
    assert g("4820", "Dividend (Parking Division)") == "Investment & Dividend Income"
    assert g("4770", "Income from Invested Funds") == "Investment & Dividend Income"


def test_fee_keywords_catch_permit_applications_and_recreation_charges():
    for desc in ("Building - Application", "Heating - Application", "Derryfield Country Club",
                 "Ice Arenas", "Drop-Off Center Revenue", "Aquatics"):
        assert revenue_group("4999", desc) == "Fees, Permits & Charges", desc


def _gf_lines(book, code):
    return [(d, v) for a in book.general_fund() for (c, d), v in a.revenues.items() if c == code]


def test_object_code_4820_is_investment_income_in_both_years(books):
    # the book renames this line between books -- FY2025 'Transfer', FY2026 'Dividend', same
    # code, same agency, same 550,100 -- so routing it by description moved it between groups
    # and showed a spurious year-over-year shift. The object code is the stable fact.
    g = revenue_group
    assert g("4820", "Transfer") == "Investment & Dividend Income"
    assert g("4820", "Dividend") == "Investment & Dividend Income"
    for fy, book in books.items():
        lines = _gf_lines(book, "4820")
        assert lines, f"{fy} has no 4820 revenue"
        for desc, _ in lines:
            assert g("4820", desc) == "Investment & Dividend Income", (fy, desc)
    assert ("Transfer", 550_100) in _gf_lines(books["FY2025"], "4820")
    assert ("Dividend", 550_100) in _gf_lines(books["FY2026"], "4820")


def test_ice_keyword_is_word_boundary_matched():
    g = revenue_group
    assert g("4426", "Ice Rates") == "Fees, Permits & Charges"
    assert g("4431", "Ice Logos") == "Fees, Permits & Charges"
    # these two are genuine license fees, so they must stay fees -- but on an honest keyword,
    # not on the letters inside 'Serv-ice' and 'Dev-ice-s'
    assert g("4699", "Food Service Establishments") == "Fees, Permits & Charges"
    assert g("4709", "Mech Devices - Each Additional") == "Fees, Permits & Charges"
    # a description that merely contains the letters is not a fee
    assert g("4999", "Notice of Service") == "Other Revenue"
