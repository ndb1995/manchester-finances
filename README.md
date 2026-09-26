# Manchester, NH city budget visualizer

A static site (`index.html`) that shows where Manchester's money comes from and where it
goes. Every figure for a year with a budget book in `sources/` is extracted from the city's
own book rather than typed in by hand, so any number on the page can be traced back to a
printed page in a PDF in this repository.

## Source data

Each fiscal year is one file in `years/`:

- **Extracted years** (`FY2025.json`, `FY2026.json`) name their budget book in `source` and
  list the figures the city publishes — General Fund totals, school district totals and every
  spending category. The extraction has to reproduce each of those to the dollar.
- **Hand-entered years** (`FY2023.json`, `FY2024.json`) have no `source`. Their category totals
  are literals carried over from the page's original version and are not derived from any PDF
  here. The loader still checks that they add up to the General Fund total.

The budget books themselves are in `sources/`, so the site can be reproduced from a fresh clone.

## Regenerating the data

```
python -m budget
```

That parses every extracted year's book, prints the reconciliation report and, only if every
check passes, writes `data.js`. A failing check exits 1 and leaves the existing `data.js`
untouched, so the site never publishes numbers that did not reconcile.

**`data.js` is a generated file that is nevertheless committed.** It is committed so the site
opens from disk with no server and no build step. Because it is generated, it must be
regenerated and committed again after *any* change under `budget/` or `years/`. A test enforces
this: it re-renders the payload and fails if the committed file does not match.

### Adding a year

1. Put the book in `sources/`.
2. Add `years/FY20XX.json`, copying an existing extracted year and filling in the book's published
   totals.
3. Run `python -m budget`. A department or organization the category rules do not know stops the
   run with its name. Add it to `budget/categories.py`, then run again.
4. Run the tests and commit `data.js`.

The page picks up the new year by itself. Its headline figures, year labels, tables and
comparisons all come from `data.js`.

## Requirements

- Python 3.10 or newer (developed and verified on 3.10.9)
- `pypdf` for the PDF text layer. There is no OCR and no other runtime dependency.
  `requirements.txt` pins it exactly: the parser is tuned to that version's text output. To
  upgrade it, bump the pin, re-run `python -m budget` and review the report.
- Node 18+ only to run the JavaScript tests

```
pip install -r requirements.txt
```

The site needs no build tooling. It loads Chart.js and the Sankey plugin from a CDN, so the
charts need an internet connection. Everything else, including `data.js`, is local.

## Tests

```
python -m pytest -q
node --test "tests/js/*.test.js"
```

The Python tests parse both PDFs for real. Nothing is mocked or fixtured from a cached parse,
but each book is parsed once per session, so a run takes a few seconds. Any test that takes an
`fy` argument runs for every extracted year in `years/`. The Node tests exercise the page's
pure logic (`js/format.js`, `js/model.js`) against the committed `data.js`. CI runs both.

## Verifying the numbers against the books

You do not have to trust the parser. Every check in the reconciliation report is against a
figure the budget books themselves print:

- **General Fund expense and revenue totals** for each year, against the book's own totals.
  The books exclude the transit subsidy from the General Fund total under their own `**`
  footnote, and so does the extraction. That is why the General Fund departments add up to
  about $2M more than the General Fund total. The site says so on the page.
- **Every spending category total** (Public Safety, Retirement, Debt Service, …), against the
  figures the city publishes.
- **Every department's own printed subtotal**, cross-checked against the line items summed
  for it. The report says how many departments this covers (41/41 and 40/40 today) and names
  any that the book prints no subtotal for.
- **Revenue groups**, which must add up to the General Fund revenue total exactly.
- **The payload itself.** On what the site will load, the report checks that the categories,
  revenue plus property tax, and departments less transit each land on the General Fund total.

The report also lists every line the parser could not turn into a line item or a subtotal but
that carried an amount. These are informational: in both books they are all subtotals printed
in a form the parser deliberately does not accept as an item, so the money is already counted
elsewhere. The count is printed anyway so that a future book cannot start dropping real line
items quietly. To read the raw text of any page yourself (page numbers as the report prints them):

```
python -m budget --dump sources/Budget_Book_2026.pdf 73
```

## Layout

| Path | What it is |
| --- | --- |
| `index.html` | the page's markup |
| `css/styles.css` | styles; also the single source of every chart color |
| `js/` | `format.js` and `model.js` (pure, tested in Node), `charts.js` (Chart.js helpers), `sections.js` and `drilldown.js` (rendering), `app.js` (boot) |
| `data.js` | generated payload, `window.BUDGET_DATA` |
| `years/` | one JSON file per fiscal year: its book and the published figures it must reproduce |
| `sources/` | the budget book PDFs |
| `budget/` | the extraction package: `config` → `parse` → `categorize` → `checks` → `payload` → `report`; `categories.py` holds the department and revenue mapping rules |
| `tests/` | pytest suite (parser, books, categories, payload, config) and `tests/js/` Node tests |
