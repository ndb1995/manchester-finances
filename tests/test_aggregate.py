# tests/test_aggregate.py
import functools

import extract_budget as eb
from category_map import EXPECTED

parsed = functools.lru_cache(maxsize=None)(eb.parse_book)  # parse each book once
FY26, FY25 = "Budget_Book_2026.pdf", "Budget_Book_2025.pdf"

def test_parse_book_fy26_agency_totals():
    book = eb.parse_book("Budget_Book_2026.pdf")
    a = book["agencies"]["Board of Assessors"]
    assert sum(a["expenses"].values()) == 937_285
    assert sum(a["revenues"].values()) == 1_111_041

def test_parse_book_fy26_public_works_by_org():
    book = eb.parse_book("Budget_Book_2026.pdf")
    pw = book["agencies"]["Public Works"]
    assert sum(pw["expenses"].values()) == 35_583_320
    assert len(pw["org_expenses"]) >= 2  # PW detail is by organization

def test_validate_book_fy26_passes():
    book = eb.parse_book("Budget_Book_2026.pdf")
    assert eb.validate_book(book, "FY2026") == []

def test_validate_book_fy25_passes():
    book = eb.parse_book("Budget_Book_2025.pdf")
    assert eb.validate_book(book, "FY2025") == []


def test_both_books_parse_without_structural_warnings():
    assert parsed(FY26)["warnings"] == []
    assert parsed(FY25)["warnings"] == []

def test_general_fund_totals_hit_the_anchors_exactly():
    for pdf, fy in [(FY26, "FY2026"), (FY25, "FY2025")]:
        gf = [a for a in parsed(pdf)["agencies"].values() if a["fund_code"] == "0101"]
        expense = sum(v for a in gf for (code, _), v in a["expenses"].items()
                      if code != eb.TRANSIT_OBJECT)
        assert expense == EXPECTED[fy]["gf_total"]
        assert sum(v for a in gf for v in a["revenues"].values()) == EXPECTED[fy]["gf_revenue"]

def test_detail_only_department_falls_back_to_its_organization_detail():
    # Non-Departmental Items has no agency-level page: it is printed only 'by Organization',
    # and its name comes from the page's department line, not an 'Agency:' line.
    nd = parsed(FY26)["agencies"]["Non-Departmental Items"]
    assert sum(nd["expenses"].values()) == 76_452_422  # the book's printed grand total
    assert "Debt Service" in nd["org_expenses"]

def test_sub_agency_pages_roll_into_their_parent_department():
    # 'Senior Services' is printed as its own agency but stamped 'Health Department - City',
    # and its 296,719 is inside the Health Department page total: it must not be a second
    # top-level agency or the general fund would double count it.
    agencies = parsed(FY26)["agencies"]
    health = agencies["Health Department - City"]
    assert sum(health["expenses"].values()) == 2_594_841
    assert sum(health["org_expenses"]["Senior Services"].values()) == 296_719
    for name in ("Senior Services", "Facilities Division", "Highway Division",
                 "Parks, Recreation & Cemeteries"):
        assert name not in agencies

def test_public_works_organization_detail_reconciles_with_its_total():
    pw = parsed(FY26)["agencies"]["Public Works"]
    orgs = pw["org_expenses"]
    assert sum(sum(d.values()) for d in orgs.values()) == sum(pw["expenses"].values())
    assert {"Facilities-Custodial", "Highway-Administration", "Parks-Administration"} <= set(orgs)

def test_agency_name_variants_share_one_entry():
    # the book calls agency 500 both 'Highway Division' and 'Highway Department', and 410
    # both 'Health Department - City' (expense pages) and 'Health Department' (revenue page).
    # Without the merge, 410's revenue page and its 'by Organization' restatement land in
    # two entries and the restatement is counted a second time as detail-only.
    for pdf in (FY26, FY25):
        assert "Highway Department" not in parsed(pdf)["agencies"]
        assert "Health Department" not in parsed(pdf)["agencies"]
        health = parsed(pdf)["agencies"]["Health Department - City"]
        assert sum(health["revenues"].values()) == 227_500

def test_printed_totals_keep_expense_and_revenue_apart():
    pt = parsed(FY26)["agencies"]["Board of Assessors"]["printed_totals"]
    assert pt[("expense", "Board of Assessors")] == 937_285
    assert pt[("revenue", "Board of Assessors")] == 1_111_041

def test_negative_revenue_items_survive_aggregation():
    clerk = parsed(FY26)["agencies"]["City Clerk's Office"]
    assert clerk["revenues"][("4210", "State Share Certified Record")] == -160_000
    assert sum(clerk["revenues"].values()) == 2_206_790
