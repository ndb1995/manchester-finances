# tests/test_payload.py -- the merged payload and the committed data.js
import json

import pytest

from budget.checks import check_payload
from budget.config import DATA_JS
from budget.errors import BudgetError
from budget.model import ENTERPRISE_CATEGORY, SCHOOL_CATEGORY, UNATTRIBUTED
from budget.payload import _merge_items, build_budget_data, render_data_js

REGEN = "python -m budget"


def _dept(payload, name):
    return next(d for d in payload["departments"] if d["name"] == name)


def test_payload_passes_its_own_identities(payload):
    # categories, revenue + property tax, and departments less transit all land on the
    # General Fund total; citywide is GF + schools -- for every year, hand-entered ones included
    assert check_payload(payload) == []


def test_every_configured_year_is_in_the_payload(payload, years):
    assert payload["years"] == [y.label for y in years]
    for y in years:
        assert payload["yearInfo"][y.label]["extracted"] == y.extracted
        assert payload["citywide"][y.label] == y.gf_total + y.msd_total
        assert payload["generalFund"][y.label] == y.gf_total
        assert payload["categories"][SCHOOL_CATEGORY][y.label] == y.msd_total


def test_hand_entered_years_carry_their_literals(payload, year):
    for label in ("FY2023", "FY2024"):
        for category, value in year[label].categories.items():
            assert payload["categories"][category][label] == value


def test_top_level_scalars_match_the_anchors(payload):
    assert payload["citywide"]["FY2025"] == 413_742_767
    assert payload["citywide"]["FY2026"] == 434_511_186
    assert payload["propertyTax"] == {"gf": {"FY2025": 121_685_395, "FY2026": 130_024_210},
                                      "msd": {"FY2025": 120_439_237, "FY2026": 117_531_711}}
    assert payload["msdOther"] == {"FY2025": 107_543_373, "FY2026": 120_468_214}
    assert payload["transitSubsidy"] == {"FY2025": 1_657_544, "FY2026": 1_999_838}
    # the eleven bands the site draws: the ten parsed general fund categories plus the schools
    assert len(payload["categories"]) == 11


def test_line_items_are_keyed_by_year(payload):
    police = _dept(payload, "Police Department")
    sal = next(i for i in police["expenses"] if i["code"] == "0110")
    assert sal["amounts"]["FY2026"] == 30_603_259 and sal["amounts"]["FY2025"] is not None


def test_every_department_has_a_category(payload):
    # an unmapped department must not reach the site as a null category: it would vanish from
    # the flow diagram silently. `categorize` fails loudly on the same condition.
    for d in payload["departments"]:
        assert d["category"], d["name"]
        assert d["generalFund"] == (d["fund"] == "0101")
        if not d["generalFund"]:
            assert d["category"] == ENTERPRISE_CATEGORY and not d["inFlow"], d["name"]


def test_split_departments_are_kept_out_of_the_flow_bands(payload):
    for name in ("Public Works", "Non-Departmental Items"):
        assert not _dept(payload, name)["inFlow"]
    assert _dept(payload, "Police Department")["inFlow"]


def test_department_present_in_only_one_year_is_kept_with_a_null_total(payload):
    # 'Housing Stability' is budgeted in FY2025 (2,200) and gone in FY2026. It must survive the
    # merge with a null -- not a zero -- for the missing year, so the site can say 'ended'
    # rather than 'cut to zero', and its line items must carry the same null.
    hs = _dept(payload, "Housing Stability")
    assert hs["totals"] == {"FY2025": 2_200, "FY2026": None}
    assert hs["category"] == "General Government"
    assert hs["expenses"] and all(i["amounts"]["FY2026"] is None
                                  and i["amounts"]["FY2025"] is not None for i in hs["expenses"])


def test_merge_items_pairs_line_items_by_code_and_description():
    merged = _merge_items({"FY2025": {("0110", "Regular Salary"): 10, ("0740", "Equipment"): 5},
                           "FY2026": {("0110", "Regular Salary"): 12, ("0745", "Software"): 7}})
    assert merged == [
        {"code": "0110", "desc": "Regular Salary", "amounts": {"FY2025": 10, "FY2026": 12}},
        {"code": "0740", "desc": "Equipment", "amounts": {"FY2025": 5, "FY2026": None}},
        {"code": "0745", "desc": "Software", "amounts": {"FY2025": None, "FY2026": 7}}]


def test_merge_items_takes_any_number_of_years():
    merged = _merge_items({"FY2025": {("0110", "Salary"): 1}, "FY2026": {},
                           "FY2027": {("0110", "Salary"): 3}})
    assert merged == [{"code": "0110", "desc": "Salary",
                       "amounts": {"FY2025": 1, "FY2026": None, "FY2027": 3}}]


def test_negative_line_items_reach_the_payload_unchanged(payload):
    clerk = _dept(payload, "City Clerk's Office")
    state_share = next(i for i in clerk["revenues"] if i["code"] == "4210")
    assert state_share["amounts"]["FY2025"] < 0 and state_share["amounts"]["FY2026"] == -160_000


def test_department_organization_totals_are_emitted_when_the_book_breaks_them_out(payload):
    pw = _dept(payload, "Public Works")
    assert sum(o["FY2026"] for o in pw["orgs"].values() if o["FY2026"]) == pw["totals"]["FY2026"]
    assert pw["orgs"]["Highway-Administration"]["FY2025"] > 0
    assert pw["orgs"][UNATTRIBUTED]["FY2026"] == 357_130  # emitted as '(unattributed)'
    assert "orgs" not in _dept(payload, "Aldermen")


def test_aviation_revenue_is_carried_by_its_own_book_entry(payload):
    # the books file airport revenue under the literal agency name 'Various' in fund 0805, not
    # under 'Aviation'. It stays its own entry (merging it would break the printed totals) but
    # gets a name the site can label.
    various = next(d for d in payload["departments"] if d["bookName"] == "Various")
    assert various["name"] == "Aviation - Revenues (Various)"
    assert various["fund"] == "0805" and various["category"] == ENTERPRISE_CATEGORY
    assert various["totals"] == {"FY2025": 0, "FY2026": 0}
    assert various["revenueTotals"] == {"FY2025": 42_267_600, "FY2026": 43_951_550}


def test_an_extracted_year_without_a_parsed_book_is_an_error(years, books):
    with pytest.raises(BudgetError, match="FY2025"):
        build_budget_data(years, {"FY2026": books["FY2026"]})


def test_render_data_js_wraps_the_payload_as_an_assignment():
    text = render_data_js({"years": ["FY2025"]})
    assert text.startswith("//") and text.rstrip().endswith(";")
    assert "window.BUDGET_DATA = " in text


def _committed():
    assert DATA_JS.exists(), "data.js is missing -- regenerate it: " + REGEN
    # Read with newline translation, not in binary: a CRLF checkout is a checkout convention,
    # not a stale payload.
    return DATA_JS.read_text(encoding="utf-8")


def test_committed_data_js_is_a_fresh_render_of_the_books(payload):
    # Every other test parses the PDFs live, so the parser and the mappings can change while
    # all of them still pass and the data.js the site actually serves goes stale -- publishing
    # last week's numbers under this week's code. This is the only test that reads the
    # committed artifact and compares it with what the current code produces.
    assert _committed() == render_data_js(payload), (
        "data.js does not match a fresh render of the budget books -- regenerate it: " + REGEN)


def test_committed_data_js_round_trips_through_json():
    # the site must work from a fresh clone, so the committed file has to parse
    text = _committed()
    data = json.loads(text.split("window.BUDGET_DATA = ", 1)[1].rstrip().rstrip(";"))
    assert data["categories"]["Public Safety"]["FY2026"] == 61_551_254
    police = next(d for d in data["departments"] if d["name"] == "Police Department")
    assert {"name", "bookName", "code", "fund", "generalFund", "category", "inFlow", "expenses",
            "revenues", "totals", "revenueTotals"} <= set(police)
