"""`python -m budget`: parse every configured book, reconcile, and write data.js."""
import argparse
import sys

from .checks import check_book, check_payload
from .config import DATA_JS, load_years
from .errors import BudgetError
from .parse import parse_book, read_pages
from .payload import build_budget_data, render_data_js
from .report import print_report


def _dump(pdf, page):
    """Print one page's raw text layer. `page` is 1-based, as the report prints it."""
    pages = read_pages(pdf)
    if not 1 <= page <= len(pages):
        raise BudgetError(f"{pdf} has pages 1-{len(pages)}, not {page}")
    print(pages[page - 1])


def build(out=DATA_JS):
    """Parse, reconcile and, only if every check passes, write `out`. Returns an exit code."""
    years = load_years()
    books = {y.label: parse_book(y.source_path) for y in years if y.extracted}
    failures = [f for y in years if y.extracted for f in check_book(books[y.label], y)]
    data = build_budget_data(years, books)
    failures += check_payload(data)
    print_report(years, books, data, failures)
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
            _dump(args.dump[0], int(args.dump[1]))
            return 0
        return build()
    except BudgetError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
