# Manchester NH Budget Flow Visualizer — Design

Date: 2026-07-24
Status: Approved by user (conversation), pending spec review

## Goal

Extend the existing single-page Manchester NH budget visualizer (`index.html`) with
full line-item detail extracted from the city's FY2025 and FY2026 budget books, centered
on a money-flow (Sankey) view of where revenue comes from and where spending goes.

## Constraints

- **No OCR / no model-based extraction.** Both PDFs (`Budget_Book_2025.pdf`,
  `Budget_Book_2026.pdf`) have embedded text layers. All extraction is done by a local
  Python script using `pypdf` (verified working on this machine). Zero API token cost
  for reading pages.
- **Static delivery.** No server, no build step. The site remains plain HTML/JS
  openable from disk or hostable on GitHub Pages/Netlify.
- **One page, one charting stack.** New visuals go into the existing `index.html`
  using Chart.js plus the `chartjs-chart-sankey` CDN plugin. Existing sections are
  preserved.
- Individual employee salaries are **out of scope** — the budget books only contain
  department-level salary totals.
- A searchable citywide line-item table is **out of scope** (not selected by user).

## Component 1: Extraction pipeline — `extract_budget.py`

**Purpose:** parse both budget book PDFs into one generated data file consumed by the site.

**Input:** the two PDF files in the project root.

**Behavior:**

1. Extract text per page with `pypdf`.
2. Classify each page: citywide summary, department expense detail, department revenue
   detail, or continuation page (continuation pages lack the `Object Description Budget`
   header and attach to the preceding department).
3. Parse line items with a tolerant regex: 4-digit object code, description (may wrap),
   right-aligned amount with comma separators. Expense object codes are 0xxx; revenue
   codes are 4xxx.
4. Capture department identity from page headings (3-digit department code + name) and
   `... Total:` lines.
4b. Department → spending-category mapping (e.g., Police → Public Safety) is a
   hand-maintained dictionary in the script, since the detail pages carry no category
   labels. Categories mirror the 11 already used in `index.html`; education (MSD)
   appears as a single line, however it is represented in the books. Any department
   missing from the mapping fails the run with a named error.
5. Match line items across the two books by (department code, object code) to support
   FY25→FY26 change display. Items present in only one year are flagged
   `newIn26` / `discontinued`.

**Output:** `data.js` defining a single global `BUDGET_DATA`:

```js
window.BUDGET_DATA = {
  years: ["FY2025", "FY2026"],
  departments: [
    {
      code: "110", name: "Police", category: "Public Safety",
      expenses: [ { code: "0110", desc: "Regular Salary", fy25: 29500000, fy26: 30603259 }, ... ],
      revenues: [ ... ],
      totals: { fy25: ..., fy26: ... }
    }, ...
  ],
  categories: [ ... ],          // spending groups used by the Sankey and existing charts
  revenueGroups: [ ... ],       // property tax (balancing), meals & rooms, state aid, fees, grants, reimbursements, other
  citywide: { fy25: ..., fy26: ... }
};
```

**Validation (built into the script, runs every time):**

- Sum of parsed line items per department must equal the department/division `Total:`
  printed in the book.
- Sum of department totals must reconcile with the book's citywide summary pages.
- The script prints a reconciliation report and exits nonzero on any mismatch above a
  $1 rounding tolerance. No silent bad data.
- The category totals already hand-entered in `index.html` (FY25/FY26 columns) serve as
  an independent cross-check of the parse.

**Re-runnability:** the script takes PDF paths as arguments so the FY2027 book can be
added later with one command.

## Component 2: Money-flow hero (Sankey)

A new hero section at the top of `index.html`:

- Left nodes: revenue groups. Department-attributed revenues (4xxx codes) are grouped
  into meals & rooms tax, state aid, fees & permits, grants, reimbursements, other;
  **property tax is shown as the balancing amount** (citywide spending minus all
  department revenues), which matches how the budget book presents it.
- Middle/right: revenue flows into spending categories, then out to individual
  departments.
- Hovering a flow shows dollar amount and percent of budget.
- Rendered with `chartjs-chart-sankey` from the same jsDelivr CDN already used.
- A year toggle (FY2025 / FY2026) re-renders the diagram.

## Component 3: Department drill-down

- Clicking a department node in the Sankey (or an entry in a department list beneath
  it) opens a detail panel.
- Panel contents: all expense line items sorted by FY26 amount, columns for FY25,
  FY26, $ change, % change; new/discontinued items flagged with a badge instead of a
  broken comparison; the department's own revenue lines if any; a small horizontal bar
  chart of its top 8 line items.
- Implemented as a modal-style overlay in the existing page's styling (CSS variables
  already defined).

## Component 4: Existing sections

- All current charts/tables remain below the new sections.
- FY2023/FY2024 figures are **not present in these PDFs** and stay hand-entered as
  historical constants. FY2025/FY2026 values in the existing charts are derived from
  `BUDGET_DATA`; the previously hand-entered FY25/FY26 numbers serve as the cross-check
  and any difference indicates a parse error that blocks completion.
- `index.html` gains one `<script src="data.js">` tag; the site still works offline
  except for the CDN chart libraries (unchanged from today).

## Error handling

- Parser: unparseable lines are collected and printed in the reconciliation report,
  never dropped silently.
- Site: if `BUDGET_DATA` is missing, existing sections still render from a guarded
  fallback; the Sankey section shows a "data not generated" notice.
- Cross-year matching: missing counterpart year renders as "—" with a badge, not NaN.

## Testing & verification

1. `extract_budget.py` reconciliation report passes for both PDFs (exit 0).
2. Existing chart numbers match their previous hand-entered values.
3. Browser test pass (delegated to browser-tester): page loads without console errors;
   Sankey renders with plausible flows; year toggle works; drill-down opens for at
   least Police, MSD-adjacent categories, and one small department; FY25→FY26 deltas
   spot-checked against the PDFs for two departments.

## Implementation notes

- Follow the CLAUDE.md multi-model workflow: scoped implementation delegated to
  opus-implementor; interactive verification delegated to browser-tester.
- Repo is not under git yet; initialize git and commit spec + pipeline + site changes
  in reviewable steps.
