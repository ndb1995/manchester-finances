"""`python -m budget`: parse every configured book, reconcile, and write data.js."""
import argparse
import sys

from .categorize import categorize, gf_totals, group_revenues
from .checks import check_book, check_payload
from .config import DATA_JS, load_years
from .errors import BudgetError
from .parse import parse_books, read_page
from .payload import build_budget_data, render_data_js
from .report import print_report


def _safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc))


def _dump(pdf, page):
    """Print one page's raw text layer. `page` is 1-based, as the report prints it."""
    _safe_print(read_page(pdf, page))


def _parse_page_arg(raw):
    try:
        return int(raw)
    except ValueError as exc:
        raise BudgetError(f"page number must be an integer, got {raw!r}") from exc


def build(out=DATA_JS):
    """Parse, reconcile and, only if every check passes, write `out`. Returns an exit code."""
    years = load_years()
    extracted = [y for y in years if y.extracted]
    books = parse_books(years)
    totals = {y.label: gf_totals(books[y.label]) for y in extracted}
    parsed = {y.label: categorize(books[y.label]) for y in extracted}
    revenue = {y.label: group_revenues(books[y.label]) for y in extracted}
    failures = [f for y in extracted
                for f in check_book(books[y.label], y,
                                    categories=parsed[y.label], totals=totals[y.label])]
    data = build_budget_data(years, books, parsed=parsed, revenue=revenue)
    failures += check_payload(data)
    print_report(years, books, data, failures, totals=totals)
    if failures:
        print(f"FAILED: {len(failures)} check(s) did not reconcile; {out.name} not written")
        return 1
    with open(out, "w", encoding="utf-8", newline="\n") as fh:  # LF, as .gitattributes pins
        fh.write(render_data_js(data))
    print(f"Wrote {out.name}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m budget",
        description="Extract every book listed in years/*.json and write data.js. "
                    "A failing check exits 1 and leaves the existing data.js untouched.")
    parser.add_argument("--dump", nargs=2, metavar=("PDF", "PAGE"),
                        help="print the raw text of one page (1-based, as the report prints it)")
    args = parser.parse_args(argv)
    try:
        if args.dump:
            _dump(args.dump[0], _parse_page_arg(args.dump[1]))
            return 0
        return build()
    except BudgetError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
