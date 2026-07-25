# tests/test_aggregate.py
import functools
import json
import os

import pytest

import extract_budget as eb
from category_map import EXPECTED

parsed = functools.lru_cache(maxsize=None)(eb.parse_book)  # parse each book once
FY26, FY25 = "Budget_Book_2026.pdf", "Budget_Book_2025.pdf"

@functools.lru_cache(maxsize=None)
def built():  # build the merged payload once for every test that inspects it
    return eb.build_budget_data({"FY2025": parsed(FY25), "FY2026": parsed(FY26)})

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
    # covers the self-consistency check too: every agency bucket the book prints a total for
    # must match that total, so a clean book yields no warnings at all
    assert parsed(FY26)["warnings"] == []
    assert parsed(FY25)["warnings"] == []

def test_agency_bucket_is_supplemented_from_organization_detail():
    # FY2026 Aviation: objects 0740 (13,200) and 0745 (357,248) are itemized only on the
    # 'by Organization' pages -- they are absent from the agency pages' text layer entirely --
    # so the agency bucket falls 370,448 short of the 42,884,197 the book prints for it.
    av = parsed(FY26)["agencies"]["Aviation"]
    assert sum(av["expenses"].values()) == 42_884_197
    codes = {code for code, _ in av["expenses"]}
    assert {"0740", "0745"} <= codes

def test_total_warnings_flag_a_bucket_that_misses_its_printed_total():
    agencies = {"Made Up": {"expenses": {("0110", "Regular Salary"): 100}, "revenues": {}}}
    assert eb._total_warnings(agencies, {("Made Up", "expense"): 100}) == []
    assert eb._total_warnings(agencies, {("Made Up", "revenue"): 50}) == []  # empty bucket
    warnings = eb._total_warnings(agencies, {("Made Up", "expense"): 150})
    assert len(warnings) == 1
    assert "Made Up" in warnings[0] and "150" in warnings[0] and "100" in warnings[0]

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


def test_build_budget_data_shapes():
    data = built()
    assert data["citywide"] == {"fy25": 413_742_767, "fy26": 434_511_186}
    assert data["categories"]["Education (MSD)"] == {"fy25": 227_982_610, "fy26": 237_999_925}
    police = next(d for d in data["departments"] if d["name"] == "Police Department")
    sal = next(i for i in police["expenses"] if i["code"] == "0110")
    assert sal["fy26"] == 30_603_259 and sal["fy25"] is not None
    epd = next(d for d in data["departments"] if d["fund"] != "0101")
    assert epd["category"] == "Enterprise Funds"

def test_build_budget_data_top_level_scalars_match_the_anchors():
    data = built()
    assert data["years"] == ["FY2025", "FY2026"]
    assert data["propertyTax"] == {"gf": {"fy25": 121_685_395, "fy26": 130_024_210},
                                   "msd": {"fy25": 120_439_237, "fy26": 117_531_711}}
    assert data["msdOther"] == {"fy25": 107_543_373, "fy26": 120_468_214}
    # the eleven bands the site draws: the ten parsed general fund categories plus the school
    # district, and each parsed category still equals the general fund total when summed
    assert len(data["categories"]) == 11
    for fy, key in [("FY2025", "fy25"), ("FY2026", "fy26")]:
        gf = sum(v[key] for c, v in data["categories"].items() if c != "Education (MSD)")
        assert gf == EXPECTED[fy]["gf_total"]
        assert sum(v[key] for v in data["revenueGroups"].values()) == EXPECTED[fy]["gf_revenue"]

def test_every_general_fund_department_has_a_category():
    # an unmapped department must not reach the site as a null category: it would vanish from
    # the flow diagram silently. `categorize` fails loudly on the same condition.
    for d in built()["departments"]:
        assert d["category"], d["name"]
        if d["fund"] != "0101":
            assert d["category"] == "Enterprise Funds", d["name"]

def test_department_present_in_only_one_year_is_kept_with_a_null_total():
    # 'Housing Stability' is budgeted in FY2025 (2,200) and gone in FY2026. It must survive the
    # merge with a null -- not a zero -- for the missing year, so the site can say 'ended'
    # rather than 'cut to zero', and its line items must carry the same null.
    hs = next(d for d in built()["departments"] if d["name"] == "Housing Stability")
    assert hs["totals"] == {"fy25": 2_200, "fy26": None}
    assert hs["category"] == "General Government"
    assert hs["expenses"] and all(i["fy26"] is None and i["fy25"] is not None
                                  for i in hs["expenses"])

def test_merge_items_pairs_line_items_by_code_and_description():
    merged = eb._merge_items({("0110", "Regular Salary"): 10, ("0740", "Equipment"): 5},
                             {("0110", "Regular Salary"): 12, ("0745", "Software"): 7})
    assert merged == [{"code": "0110", "desc": "Regular Salary", "fy25": 10, "fy26": 12},
                      {"code": "0740", "desc": "Equipment", "fy25": 5, "fy26": None},
                      {"code": "0745", "desc": "Software", "fy25": None, "fy26": 7}]

def test_negative_line_items_reach_the_payload_unchanged():
    clerk = next(d for d in built()["departments"] if d["name"] == "City Clerk's Office")
    state_share = next(i for i in clerk["revenues"] if i["code"] == "4210")
    assert state_share["fy25"] < 0 and state_share["fy26"] == -160_000

def test_department_organization_totals_are_emitted_when_the_book_breaks_them_out():
    pw = next(d for d in built()["departments"] if d["name"] == "Public Works")
    assert sum(o["fy26"] for o in pw["orgs"].values() if o["fy26"]) == pw["totals"]["fy26"]
    assert pw["orgs"]["Highway-Administration"]["fy25"] > 0
    assert pw["orgs"][eb.UNATTRIBUTED]["fy26"] == 357_130  # emitted as '(unattributed)'
    assert "orgs" not in next(d for d in built()["departments"] if d["name"] == "Aldermen")

def test_aviation_revenue_is_carried_by_its_own_book_entry():
    # the 2025/2026 books file airport revenue under the literal agency name 'Various' in fund
    # 0805, not under 'Aviation'. It stays its own entry (merging it would break the printed
    # totals) but gets a name the site can label.
    various = next(d for d in built()["departments"] if d["bookName"] == "Various")
    assert various["name"] == "Aviation - Revenues (Various)"
    assert various["fund"] == "0805" and various["category"] == "Enterprise Funds"
    assert various["totals"] == {"fy25": 0, "fy26": 0}
    assert various["revenueTotals"] == {"fy25": 42_267_600, "fy26": 43_951_550}

def test_unmapped_department_stops_the_build():
    # the site cannot draw a null category, so a new or renamed department is a build failure
    with pytest.raises(SystemExit, match="Ministry of Silly Walks"):
        eb._department_category("Ministry of Silly Walks", "0101")
    assert eb._department_category("Ministry of Silly Walks", "0805") == "Enterprise Funds"

def test_check_book_turns_parser_warnings_into_labelled_failures():
    # a parser warning must fail the run, not just print: the label lets the report attribute it
    fails = eb._check_book({"agencies": {}, "warnings": ["a page lost its agency name"]}, "FY2026")
    assert fails[0] == "FY2026 a page lost its agency name"
    assert any("GF expense total" in f for f in fails)

def test_render_data_js_wraps_the_payload_as_an_assignment():
    text = eb.render_data_js({"years": ["FY2025"]})
    assert text.startswith("//") and text.rstrip().endswith(";")
    assert "window.BUDGET_DATA = " in text

def test_committed_data_js_round_trips_through_json():
    # data.js is a checked-in build artifact: the site must work from a fresh clone, so the
    # committed file has to exist and parse. Regenerate it with
    # `python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf` when the parser moves.
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.js")
    assert os.path.exists(path), "data.js is missing -- regenerate it"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    payload = text.split("window.BUDGET_DATA = ", 1)[1].rstrip().rstrip(";")
    data = json.loads(payload)
    assert data["years"] == ["FY2025", "FY2026"]
    assert data["citywide"] == {"fy25": 413_742_767, "fy26": 434_511_186}
    assert data["categories"]["Public Safety"] == {"fy25": 57_760_666, "fy26": 61_551_254}
    police = next(d for d in data["departments"] if d["name"] == "Police Department")
    assert {"name", "bookName", "code", "fund", "category", "expenses", "revenues",
            "totals", "revenueTotals"} <= set(police)
    assert next(i for i in police["expenses"] if i["desc"] == "Regular Salary")["fy26"] == 30_603_259
