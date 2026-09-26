# tests/test_book.py -- parse_book on the real budget books: aggregation and its self-checks
from budget import parse
from budget.categorize import gf_totals
from budget.checks import check_book
from budget.model import TRANSIT_OBJECT, Agency, Book


def test_book_reproduces_every_anchor(books, year, fy):
    # warnings, the General Fund totals and every category total, as `python -m budget` checks
    assert check_book(books[fy], year[fy]) == []


def test_book_parses_without_structural_warnings(books, fy):
    # covers the self-consistency check too: every agency bucket the book prints a total for
    # must match that total, so a clean book yields no warnings at all
    assert books[fy].warnings == []


def test_general_fund_totals_hit_the_anchors_exactly(books, year, fy):
    assert gf_totals(books[fy]) == (year[fy].gf_total, year[fy].gf_revenue)


def test_every_agency_bucket_is_cross_checked_against_a_printed_total(books, fy):
    # the printed-total check is only worth what it covers: a bucket the book states no
    # subtotal for is constrained by the general fund anchors at best, and for an enterprise
    # fund by nothing at all
    checked, unchecked = parse.anchor_coverage(books[fy])
    assert unchecked == [], unchecked
    assert len(checked) >= 40


def test_unparsed_money_lines_are_reported_not_dropped_silently(books, fy):
    # Unparseable lines are collected and printed in the reconciliation report, never dropped
    # silently. Every line these books drop is a section total in a form the parser
    # deliberately does not accept as an item (a colon-only organization total like
    # 'Aviation-Marketing: 1,805,580', or an orphan amount the text layer left behind), so
    # none is item-shaped and no money is lost.
    dropped = books[fy].dropped_lines
    assert all(parse.MONEY_LINE_RE.search(ln) for _, ln in dropped)
    assert [ln for _, ln in dropped if parse.ITEM_START_RE.match(ln)] == []
    assert all(isinstance(p, int) and p > 0 for p, _ in dropped)  # page numbers, for audit


def test_unparsed_money_line_counts_are_pinned(books):
    # pinned per book so a future parser change cannot start dropping real line items quietly
    for fy, expected in (("FY2025", 14), ("FY2026", 13)):
        dropped = books[fy].dropped_lines
        assert len(dropped) == expected, [ln for _, ln in dropped]


def test_fy26_agency_totals(books):
    a = books["FY2026"].agencies["Board of Assessors"]
    assert sum(a.expenses.values()) == 937_285
    assert sum(a.revenues.values()) == 1_111_041


def test_agency_bucket_is_supplemented_from_organization_detail(books):
    # FY2026 Aviation: objects 0740 (13,200) and 0745 (357,248) are itemized only on the
    # 'by Organization' pages -- they are absent from the agency pages' text layer entirely --
    # so the agency bucket falls 370,448 short of the 42,884,197 the book prints for it.
    av = books["FY2026"].agencies["Aviation"]
    assert sum(av.expenses.values()) == 42_884_197
    assert {"0740", "0745"} <= {code for code, _ in av.expenses}


def test_total_warnings_flag_a_bucket_that_misses_its_printed_total():
    agencies = {"Made Up": Agency("Made Up", "0101", expenses={("0110", "Regular Salary"): 100})}
    assert parse._total_warnings(agencies, {("Made Up", "expense"): 100}) == []
    assert parse._total_warnings(agencies, {("Made Up", "revenue"): 0}) == []
    warnings = parse._total_warnings(agencies, {("Made Up", "expense"): 150})
    assert len(warnings) == 1
    assert "Made Up" in warnings[0] and "150" in warnings[0] and "100" in warnings[0]


def test_an_empty_bucket_against_a_nonzero_printed_total_warns():
    # a whole side of a department's ledger going missing is the loudest failure the check can
    # see, so it must not be the one case the check waves through
    agencies = {"Made Up": Agency("Made Up", "0101", expenses={("0110", "Regular Salary"): 100})}
    warnings = parse._total_warnings(agencies, {("Made Up", "revenue"): 50})
    assert len(warnings) == 1
    assert "Made Up revenue" in warnings[0] and "0" in warnings[0] and "50" in warnings[0]


def test_alias_map_anchors_the_totals_the_name_match_cannot_reach(books):
    # three agencies the book foots under a label that is not the name the aggregation keys on.
    # 'Various' (airport revenue) is fund 0805, so before this it was checked by nothing --
    # not even indirectly by the general fund anchors.
    cases = {"FY2026": {("Planning & Community Development", "expense"): 2_682_014,
                        ("Planning & Community Development", "revenue"): 5_531_176,
                        ("Various", "revenue"): 43_951_550,
                        ("Non-Departmental Items", "expense"): 76_452_422},
             "FY2025": {("Planning & Community Development", "expense"): 2_548_264,
                        ("Planning & Community Development", "revenue"): 3_481_400,
                        ("Various", "revenue"): 42_267_600,
                        ("Non-Departmental Items", "expense"): 72_978_914}}
    for fy, want in cases.items():
        printed = books[fy].printed
        for k, v in want.items():
            assert printed.get(k) == v, (fy, k, printed.get(k))


def test_detail_only_department_falls_back_to_its_organization_detail(books):
    # Non-Departmental Items has no agency-level page: it is printed only 'by Organization',
    # and its name comes from the page's department line, not an 'Agency:' line.
    nd = books["FY2026"].agencies["Non-Departmental Items"]
    assert sum(nd.expenses.values()) == 76_452_422  # the book's printed grand total
    assert "Debt Service" in nd.org_expenses


def test_sub_agency_pages_roll_into_their_parent_department(books):
    # 'Senior Services' is printed as its own agency but stamped 'Health Department - City',
    # and its 296,719 is inside the Health Department page total: it must not be a second
    # top-level agency or the general fund would double count it.
    agencies = books["FY2026"].agencies
    health = agencies["Health Department - City"]
    assert sum(health.expenses.values()) == 2_594_841
    assert sum(health.org_expenses["Senior Services"].values()) == 296_719
    for name in ("Senior Services", "Facilities Division", "Highway Division",
                 "Parks, Recreation & Cemeteries"):
        assert name not in agencies


def test_public_works_organization_detail_reconciles_with_its_total(books, fy):
    pw = books[fy].agencies["Public Works"]
    assert sum(sum(d.values()) for d in pw.org_expenses.values()) == sum(pw.expenses.values())
    assert {"Facilities-Custodial", "Highway-Administration", "Parks-Administration"} <= set(
        pw.org_expenses)


def test_fy26_public_works_total(books):
    assert sum(books["FY2026"].agencies["Public Works"].expenses.values()) == 35_583_320


def test_agency_name_variants_share_one_entry(books, fy):
    # the book calls agency 500 both 'Highway Division' and 'Highway Department', and 410
    # both 'Health Department - City' (expense pages) and 'Health Department' (revenue page).
    # Without the merge, 410's revenue page and its 'by Organization' restatement land in
    # two entries and the restatement is counted a second time as detail-only.
    agencies = books[fy].agencies
    assert "Highway Department" not in agencies
    assert "Health Department" not in agencies
    assert sum(agencies["Health Department - City"].revenues.values()) == 227_500


def test_printed_totals_keep_expense_and_revenue_apart(books):
    pt = books["FY2026"].agencies["Board of Assessors"].printed_totals
    assert pt[("expense", "Board of Assessors")] == 937_285
    assert pt[("revenue", "Board of Assessors")] == 1_111_041


def test_negative_revenue_items_survive_aggregation(books):
    clerk = books["FY2026"].agencies["City Clerk's Office"]
    assert clerk.revenues[("4210", "State Share Certified Record")] == -160_000
    assert sum(clerk.revenues.values()) == 2_206_790


def test_transit_subsidy_is_budgeted_but_outside_the_general_fund_total(books, fy):
    book = books[fy]
    transit = sum(v for a in book.general_fund() for (code, _), v in a.expenses.items()
                  if code == TRANSIT_OBJECT)
    assert transit > 0  # the book really does budget it
    assert gf_totals(book)[0] == sum(sum(a.expenses.values()) for a in book.general_fund()) - transit


def test_check_book_turns_parser_warnings_into_labelled_failures(year):
    # a parser warning must fail the run, not just print: the label lets the report attribute it
    fails = check_book(Book(warnings=["a page lost its agency name"]), year["FY2026"])
    assert fails[0] == "FY2026 a page lost its agency name"
    assert any("GF expense total" in f for f in fails)
