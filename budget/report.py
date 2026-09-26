"""The reconciliation report printed on every run."""
from .categorize import categorize, gf_totals, group_revenues
from .model import agrees
from .parse import ITEM_START_RE, anchor_coverage


def _book_section(book, year, failures):
    gf_exp, gf_rev = gf_totals(book)
    cats, groups = categorize(book), group_revenues(book)
    matched = sum(1 for c, v in year.categories.items() if agrees(cats.get(c, 0), v))
    ok = not any(f.startswith(year.label) for f in failures)
    print(f"{year.label}: GF/category/revenue checks", "OK" if ok else "FAILED")
    print(f"  agencies parsed        {len(book.agencies):>15,}"
          f"   parser warnings {len(book.warnings)}")
    print(f"  GF expenses (net)      {gf_exp:>15,}   expected {year.gf_total:>15,}")
    print(f"  GF revenues            {gf_rev:>15,}   expected {year.gf_revenue:>15,}")
    print(f"  property tax to GF     {gf_exp - gf_rev:>15,}"
          f"   expected {year.gf_total - year.gf_revenue:>15,}")
    print(f"  categories matched     {matched:>15,} / {len(year.categories)}"
          f"   summing {sum(cats.values()):,}")
    print(f"  revenue groups         {len(groups):>15,}   summing {sum(groups.values()):,}")
    print(f"  MSD total (constant)   {year.msd_total:>15,}"
          f"   of which property tax {year.msd_property_tax:,}")
    checked, unchecked = anchor_coverage(book)
    print(f"  printed-total checks   {len(checked):>15,} / {len(checked) + len(unchecked)}"
          f"   agency buckets cross-checked against the book's own subtotal")
    if unchecked:  # not an error: the book simply never states these subtotals
        print(f"    no printed total, so unwitnessed: {', '.join(unchecked)}")
    # Unparseable lines are reported, never dropped silently. Informational -- every one of
    # them today is a section total in a form the parser does not accept as an item, so the
    # money is already counted. An item-shaped one would be a genuine loss.
    dropped = book.dropped_lines
    item_shaped = [f"p{p} {ln}" for p, ln in dropped if ITEM_START_RE.match(ln)]
    print(f"  unparsed money lines   {len(dropped):>15,}"
          f"   informational; {len(item_shaped)} item-shaped (a nonzero count loses money)")
    if item_shaped:  # a line that opens with an object code is a line item, not a subtotal
        print(f"    ITEM-SHAPED, so money may be missing: {'; '.join(item_shaped)}")
    for page_no, line in dropped:
        print(f"    p{page_no:<4} {line}")


def print_report(years, books, data, failures):
    print("=== Reconciliation report ===")
    for year in years:
        if year.extracted:
            _book_section(books[year.label], year, failures)
        else:
            print(f"{year.label}: hand-entered, {len(year.categories)} categories"
                  f" summing {sum(year.categories.values()):,}")
    depts = data["departments"]
    gf_depts = [d for d in depts if d["generalFund"]]
    print(f"departments emitted      {len(depts):>15,}"
          f"   ({len(gf_depts)} general fund, {len(depts) - len(gf_depts)} enterprise)")
    print(f"  expense line items     {sum(len(d['expenses']) for d in depts):>15,}"
          f"   revenue line items {sum(len(d['revenues']) for d in depts):,}")
    for year in years:
        print(f"citywide {year.label}          {year.citywide:>15,}"
              f"   = GF {year.gf_total:,} + MSD {year.msd_total:,}")
    for f in failures:
        print("MISMATCH:", f)
