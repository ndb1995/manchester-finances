# Manchester, NH city budget visualizer

A single-page site (`index.html`) that shows where Manchester's money comes from and where
it goes, for fiscal years 2023–2026. Every FY2025 and FY2026 figure it draws is extracted
from the city's own budget books rather than typed in by hand, so any number on the page can
be traced back to a printed page in a PDF in this repository.

## Source data

The two budget books are tracked here so the site is reproducible from a fresh clone:

- `Budget_Book_2025.pdf`
- `Budget_Book_2026.pdf`

These are the only inputs. FY2023 and FY2024 figures are literals in `index.html`, carried
over from the version of the page that predates the extraction, and are not derived from any
PDF here.

## Regenerating the data

```
python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf
```

That prints the reconciliation report and, only if every check passes, writes `data.js`.
A failing check exits 1 and leaves the existing `data.js` untouched — the site never
publishes numbers that did not reconcile.

**`data.js` is a generated artifact that is nevertheless committed.** It is committed so the
site opens from disk with no server and no build step; it is generated so it must be
regenerated and committed again after *any* change to `extract_budget.py` or
`category_map.py`. A test enforces this: it re-renders the payload and fails if the committed
file does not match, with instructions to re-run the command above.

## Requirements

- Python 3.10 or newer (developed and verified on 3.10.9)
- `pypdf` for the PDF text layer — no OCR, no other runtime dependency

```
pip install -r requirements.txt
```

The site itself needs no build tooling. It loads Chart.js and the Sankey plugin from a CDN,
so the charts need an internet connection; everything else, including `data.js`, is local.

## Tests

```
python -m pytest -q
```

`pytest -q` works too (a root `conftest.py` puts the repository root on `sys.path`). The
tests parse both PDFs for real — nothing is mocked or fixtured from a cached parse — so a
full run takes roughly 20 seconds.

## Verifying the numbers against the books

You do not have to trust the parser. The reconciliation report prints the anchors it checks,
and every one of them is a figure the budget books themselves print:

- **General Fund expense and revenue totals** for each year, against the book's own totals.
  The books exclude the transit subsidy from the General Fund total under their own `**`
  footnote, and so does the extraction — which is why the General Fund departments add up to
  about $2M more than the General Fund total. The site says so on the page.
- **Every spending category total** (Public Safety, Retirement, Debt Service, …), against the
  figures the city publishes.
- **Every department's own printed subtotal**, cross-checked against the line items summed
  for it. The report says how many buckets this covers (41/41 and 40/40 today) and names any
  the book prints no subtotal for.
- **Revenue groups**, which must add back to the General Fund revenue total exactly.

The report also lists every line the parser could not turn into a line item or a subtotal but
that carried an amount. Those are informational: in both books they are all subtotals printed
in a form the parser deliberately does not accept as an item, so the money is already counted
elsewhere. The count is printed anyway so a future book cannot start dropping real line items
quietly. To read the raw text of any page yourself:

```
python extract_budget.py --dump Budget_Book_2026.pdf 72
```

(The reconciliation report prints page numbers as 1-based; if the report says `p73`, pass `72` to `--dump` since `--dump` takes 0-based indexes.)

## Layout

| Path | What it is |
| --- | --- |
| `index.html` | the whole site: markup, styles and charts |
| `data.js` | generated payload, `window.BUDGET_DATA` |
| `extract_budget.py` | PDF parsing, aggregation, reconciliation, rendering |
| `category_map.py` | department → category mapping, revenue grouping, and the expected totals used as anchors |
| `tests/` | pytest suite covering the parser, the aggregation and the mappings |
| `docs/superpowers/` | the design spec and implementation plan |
