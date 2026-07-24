# Manchester NH Budget Flow Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract full line-item budget data from the FY2025/FY2026 Manchester NH budget book PDFs with a local Python script, and extend the existing `index.html` with a money-flow Sankey hero and department drill-down.

**Architecture:** A pypdf-based parser (`extract_budget.py`) classifies each PDF page by its footer, parses object-code line items, aggregates by fund/agency/organization, validates against totals printed in the book, and emits `data.js` (`window.BUDGET_DATA`). The static site loads `data.js` and renders a Sankey via the `chartjs-chart-sankey` plugin plus a drill-down modal, keeping all existing sections.

**Tech Stack:** Python 3 + pypdf + pytest (extraction); plain HTML/JS + Chart.js 4 + chartjs-chart-sankey (site). No build step, no server.

## Global Constraints

- No OCR and no model-based PDF reading — pypdf text layer only.
- Static delivery: site must open from disk; only CDN dependencies allowed (jsDelivr, as already used).
- All extraction validation must pass exactly (±$1 rounding tolerance); the script exits nonzero on failure.
- Existing page sections, styling, and CDN pins remain; FY2023/FY2024 figures stay hand-entered.
- Individual employee salaries and a citywide searchable line-item table are out of scope.
- Spec: `docs/superpowers/specs/2026-07-24-manchester-budget-flow-design.md`.

## Ground truth (verified against the PDFs — use these numbers verbatim)

**Page anatomy (pypdf text):** Detail pages carry a footer with `Fund:  0101  General Fund`, `Agency:  020  Board of Assessors` (agency code sometimes absent: `Agency:  Public Works`), and either `FY 2026 Expense Budget` or `FY 2026 Revenue Budget` (or `... by Organization`). Line items look like `0110 Regular Salary 844,355` (expense codes 0xxx/0141-style, revenue codes 4xxx). Totals look like `Board of Assessors Total: 937,285$`. Multi-organization pages repeat `Object Description Budget` headers per section, end sections with `<label> Total:` lines, and list `Organization: 140 Debt Service` lines near the footer (order does NOT match section order — match by name). Known text quirks: amounts may contain stray spaces (`33, 826,822`), an amount may appear alone on the following line (page 72 FY26), and total labels may split across lines (`Non-City Programs Total:` on its own line after the amount).

**Validation anchors:**

| Quantity | FY2025 (from 2025 book) | FY2026 (from 2026 book) |
|---|---|---|
| General Fund expense total (excl. Transit Subsidy, object 0909) | 185,760,157 | 196,511,261 |
| GF department revenues total | 64,074,762 | 66,487,051 |
| MSD (School District) total | 227,982,610 | 237,999,925 |
| Net School District Appropriation (property-tax share) | 120,439,237 | 117,531,711 |
| Property tax to GF (balancing = GF total − GF revenues) | 121,685,395 | 130,024,210 |

**Expected category totals** (must match `index.html`'s existing constants exactly; MSD is a constant, others derived from parsing):

| Category | FY2025 | FY2026 |
|---|---|---|
| Education (MSD) | 227,982,610 | 237,999,925 |
| Public Safety (agencies 300, 330) | 57,760,666 | 61,551,254 |
| Retirement (objects 0224, 0225, 0228 in Non-Departmental org 170) | 27,291,207 | 29,706,516 |
| General Government (agencies 010,020,040,070,100,130,160,180,190,200,220,230,830 + PW facilities/admin orgs) | 25,559,290 | 26,788,383 |
| Highway & Streets (PW street/highway orgs) | 19,968,652 | 21,545,314 |
| Health, Dental & Insurance (objects 0211, 0212, 0213 in org 170) | 17,195,489 | 17,595,489 |
| Debt Service (org 140) | 16,100,000 | 16,100,000 |
| Other (remaining org 170/171/172/700/800 items, excl. Transit 0909) | 10,734,674 | 11,050,579 |
| Culture & Recreation (agency 710 Library + PW parks/rec orgs) | 7,618,111 | 7,764,641 |
| Health & Welfare (agencies 410, 600) | 3,308,180 | 4,104,665 |
| Economic Development (agency 050) | 223,888 | 304,420 |

Derived PW split targets (implied by the rows above; use to debug the PW org mapping): FY26 Highway 21,545,314 / Culture 5,144,949 / GG 8,893,057 (sums to PW 35,583,320). FY25: Highway 19,968,652 / Culture 5,156,896 / GG 8,701,274 (sums to PW 33,826,822).

Enterprise funds (0801 EPD, 0805 Aviation, 0809 Parking Enterprise) are parsed and stored with their fund code and category `"Enterprise Funds"`, appear in the drill-down list, and are excluded from the Sankey, category totals, and existing charts.

## File Structure

- Create `extract_budget.py` — parser, aggregation, validation, `data.js` emitter, CLI (incl. `--dump` page-inspection mode).
- Create `category_map.py` — agency/org/object → category mappings, revenue grouping rules, expected-value constants (all tables above live here).
- Create `tests/test_parser.py`, `tests/test_aggregate.py`, `tests/test_categories.py` — pytest, fixtures are real page text pasted below.
- Create `data.js` — generated artifact (committed so the site works from a fresh clone).
- Modify `index.html` — Sankey hero section, drill-down modal, FY25/FY26 values of existing charts rewired to `BUDGET_DATA`.

---

### Task 1: Parser core — page classification and line-item parsing

**Files:**
- Create: `extract_budget.py`
- Create: `category_map.py` (constants only for now)
- Test: `tests/test_parser.py`

**Interfaces:**
- Produces: `parse_amount(s: str) -> int`; `classify_page(text: str) -> PageMeta | None` where `PageMeta = dict(kind='expense'|'revenue', fund_code, fund_name, agency_code, agency_name, by_org: bool, orgs: list[(code,name)])`; `parse_sections(text: str) -> list[Section]` where `Section = dict(items=[(code,desc,amount)], total_label: str|None, total: int|None)`.

- [ ] **Step 1: Write failing tests using real page text**

```python
# tests/test_parser.py
import extract_budget as eb

ASSESSORS_EXPENSE = """Object Description Budget
0110 Regular Salary 844,355         
0420 Data Processing 61,230           
0810 Dues, Fees, & Licenses 13,200           
Board of Assessors Total: 937,285$       
Fund:  0101  General Fund
Agency:  020  Board of Assessors
FY 2026 Expense Budget
6"""

PW_REVENUE_CONTINUATION = """4877 Building Rent 209,240          
4998 School Chargebacks 8,808,047       
Public Works Department Total: 16,831,830     
FY 2026 Revenue Budget
Fund:  0101  General Fund
Agency:  Public Works
36"""

NONDEPT_BY_ORG = """Object Description Budget
0919 Maturing Debt 9,700,000      
0920 Interest On Maturing Debt 6,400,000      
Debt service Total: 16,100,000    
Object Description Budget
0224 Fire State Retirement 7,542,465      
Non-Departmental Total: 59,521,050    
Fund:  0101  General Fund
Non-Departmental Items
FY 2026 Expense Budget by Organization
Organization: 140 Debt Service
Organization: 170 Non-Departmental
72"""

ORPHAN_AMOUNT = """Object Description Budget
0912 Community Improvement Program 150,000         
150,000         
Non-Departmental Items Total: 76,452,422$  
Non-City Programs Total:
Organization: 800 CIP Adminstrations
Fund:  0101  General Fund
FY 2026 Expense Budget by Organization
68"""

def test_parse_amount_handles_commas_spaces_dollar():
    assert eb.parse_amount("844,355") == 844355
    assert eb.parse_amount("33, 826,822") == 33826822
    assert eb.parse_amount("937,285$") == 937285

def test_classify_expense_page():
    m = eb.classify_page(ASSESSORS_EXPENSE)
    assert m == {"kind": "expense", "fund_code": "0101", "fund_name": "General Fund",
                 "agency_code": "020", "agency_name": "Board of Assessors",
                 "by_org": False, "orgs": []}

def test_classify_revenue_page_without_agency_code():
    m = eb.classify_page(PW_REVENUE_CONTINUATION)
    assert m["kind"] == "revenue"
    assert m["agency_code"] is None
    assert m["agency_name"] == "Public Works"

def test_classify_by_org_page_collects_orgs():
    m = eb.classify_page(NONDEPT_BY_ORG)
    assert m["by_org"] is True
    assert ("140", "Debt Service") in m["orgs"]
    assert ("170", "Non-Departmental") in m["orgs"]

def test_classify_summary_page_returns_none():
    assert eb.classify_page("010 Aldermen 70,000\nGeneral Fund Total: 196,511,261") is None

def test_parse_sections_single():
    secs = eb.parse_sections(ASSESSORS_EXPENSE)
    assert len(secs) == 1
    assert secs[0]["items"][0] == ("0110", "Regular Salary", 844355)
    assert secs[0]["total_label"] == "Board of Assessors"
    assert secs[0]["total"] == 937285

def test_parse_sections_multi_org():
    secs = eb.parse_sections(NONDEPT_BY_ORG)
    assert [s["total_label"] for s in secs] == ["Debt service", "Non-Departmental"]
    assert secs[0]["items"] == [("0919", "Maturing Debt", 9700000),
                                ("0920", "Interest On Maturing Debt", 6400000)]

def test_parse_sections_ignores_orphan_amount_and_split_total():
    secs = eb.parse_sections(ORPHAN_AMOUNT)
    assert secs[0]["items"] == [("0912", "Community Improvement Program", 150000)]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL with `AttributeError`/`ModuleNotFoundError` (module or functions missing).

- [ ] **Step 3: Implement parser core**

```python
# extract_budget.py
"""Extract Manchester NH budget book PDFs into data.js. No OCR: pypdf text layer only."""
import re, sys

AMOUNT = r"[\d][\d,\s]*"
ITEM_RE = re.compile(rf"^(\d{{4}})\s+(.+?)\s+({AMOUNT})\$?\s*$")
TOTAL_RE = re.compile(rf"^(.*?)\s*Totals?:\s*({AMOUNT})\$?\s*$")
FUND_RE = re.compile(r"Fund:\s*(\d{4})\s+(.+?)\s*$", re.M)
AGENCY_RE = re.compile(r"Agency:\s*(?:(\d{3})\s+)?(.+?)\s*$", re.M)
KIND_RE = re.compile(r"FY\s*\d{4}\s+(Expense|Revenue)\s+Budget(\s+by\s+Organization)?", re.I)
ORG_RE = re.compile(r"Organization:\s*(\d+)\s+(.+?)\s*$", re.M)
HEADER = "Object Description Budget"

def parse_amount(s):
    return int(re.sub(r"[^\d]", "", s))

def classify_page(text):
    kind = KIND_RE.search(text)
    fund = FUND_RE.search(text)
    if not kind or not fund:
        return None  # summary/TOC/cover page
    agency = AGENCY_RE.search(text)
    return {
        "kind": kind.group(1).lower(),
        "fund_code": fund.group(1),
        "fund_name": fund.group(2),
        "agency_code": agency.group(1) if agency else None,
        "agency_name": agency.group(2) if agency else None,
        "by_org": bool(kind.group(2)),
        "orgs": ORG_RE.findall(text),
    }

def parse_sections(text):
    sections, cur = [], {"items": [], "total_label": None, "total": None}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == HEADER:
            if cur["items"]:
                sections.append(cur)
            cur = {"items": [], "total_label": None, "total": None}
            continue
        m = ITEM_RE.match(line)
        if m:
            cur["items"].append((m.group(1), m.group(2).strip(), parse_amount(m.group(3))))
            continue
        m = TOTAL_RE.match(line)
        if m and m.group(1):  # split/label-only totals (empty label) are ignored
            cur["total_label"] = m.group(1).strip()
            cur["total"] = parse_amount(m.group(2))
            sections.append(cur)
            cur = {"items": [], "total_label": None, "total": None}
            continue
        # anything else: footers, page numbers, orphan amounts, wrapped labels -> skip
    if cur["items"]:
        sections.append(cur)
    return sections
```

Note: `TOTAL_RE` also matches the page-level `Non-Departmental Items Total:` grand line; that is fine — it closes a section that has no items and is dropped, or acts as an extra section with empty items which aggregation ignores. If `test_parse_sections_ignores_orphan_amount_and_split_total` fails on the grand-total line, filter sections with empty `items` and no matching org name during aggregation (Task 2), not here.

Create `category_map.py` containing only the two anchor constants for now:

```python
# category_map.py
"""Mappings and expected values for Manchester NH budget extraction."""
EXPECTED = {
    "FY2025": {"gf_total": 185_760_157, "gf_revenue": 64_074_762,
               "msd_total": 227_982_610, "msd_property_tax": 120_439_237},
    "FY2026": {"gf_total": 196_511_261, "gf_revenue": 66_487_051,
               "msd_total": 237_999_925, "msd_property_tax": 117_531_711},
}
TRANSIT_OBJECT = "0909"  # excluded from GF totals per the book's own footnote
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_parser.py -v`
Expected: all PASS. If `parse_sections` boundary handling differs from the fixtures, fix the code (not the fixtures — they are verbatim book text).

- [ ] **Step 5: Commit**

```bash
git add extract_budget.py category_map.py tests/test_parser.py
git commit -m "feat: budget PDF page classifier and line-item parser"
```

---

### Task 2: Whole-book parsing, org attribution, and book-internal validation

**Files:**
- Modify: `extract_budget.py`
- Test: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `classify_page`, `parse_sections`, `parse_amount` from Task 1.
- Produces: `parse_book(pdf_path: str) -> Book` where `Book = dict(agencies: dict[key, Agency])`, `key = agency_name` (stable across pages; PW has no code), `Agency = dict(code: str|None, name: str, fund_code: str, expenses: dict[(obj_code, desc) -> int], revenues: dict[(obj_code, desc) -> int], org_expenses: dict[org_name -> dict[(obj_code, desc) -> int]], printed_totals: dict)`. Also `validate_book(book, fy_label) -> list[str]` returning human-readable failures (empty = pass), and CLI `python extract_budget.py --dump <pdf> <page#>` printing raw page text.

- [ ] **Step 1: Write failing tests (run against the real PDFs — they are in the repo root)**

```python
# tests/test_aggregate.py
import extract_budget as eb
from category_map import EXPECTED

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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_aggregate.py -v`
Expected: FAIL (`parse_book` not defined).

- [ ] **Step 3: Implement `parse_book`, `validate_book`, and `--dump`**

```python
# append to extract_budget.py
import pypdf
from category_map import EXPECTED, TRANSIT_OBJECT

def _match_org(label, orgs):
    """Match a section total label like 'Debt service' to ('140','Debt Service')."""
    lab = label.casefold()
    for code, name in orgs:
        n = name.casefold()
        if lab.startswith(n) or n.startswith(lab):
            return name
    return None

def parse_book(pdf_path):
    agencies = {}
    for page in pypdf.PdfReader(pdf_path).pages:
        text = page.extract_text() or ""
        meta = classify_page(text)
        if not meta:
            continue
        key = meta["agency_name"]
        a = agencies.setdefault(key, {"code": meta["agency_code"], "name": key,
                                      "fund_code": meta["fund_code"], "expenses": {},
                                      "revenues": {}, "org_expenses": {}, "printed_totals": {}})
        bucket = a["expenses"] if meta["kind"] == "expense" else a["revenues"]
        for sec in parse_sections(text):
            if not sec["items"]:
                continue  # grand-total-only pseudo sections
            org = _match_org(sec["total_label"], meta["orgs"]) if (meta["by_org"] and sec["total_label"]) else None
            for code, desc, amt in sec["items"]:
                k = (code, desc)
                bucket[k] = bucket.get(k, 0) + amt
                if org and meta["kind"] == "expense":
                    a["org_expenses"].setdefault(org, {})
                    a["org_expenses"][org][k] = a["org_expenses"][org].get(k, 0) + amt
            if sec["total"] is not None and sec["total_label"]:
                a["printed_totals"][sec["total_label"]] = sec["total"]
    return {"agencies": agencies}

def validate_book(book, fy_label):
    errors, exp = [], EXPECTED[fy_label]
    gf_exp = gf_rev = 0
    for a in book["agencies"].values():
        if a["fund_code"] != "0101":
            continue
        gf_exp += sum(v for (code, _), v in a["expenses"].items() if code != TRANSIT_OBJECT)
        gf_rev += sum(a["revenues"].values())
    if abs(gf_exp - exp["gf_total"]) > 1:
        errors.append(f"{fy_label} GF expense total {gf_exp:,} != expected {exp['gf_total']:,}")
    if abs(gf_rev - exp["gf_revenue"]) > 1:
        errors.append(f"{fy_label} GF revenue total {gf_rev:,} != expected {exp['gf_revenue']:,}")
    return errors

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--dump":
        print(pypdf.PdfReader(sys.argv[2]).pages[int(sys.argv[3])].extract_text())
        sys.exit(0)
```

- [ ] **Step 4: Run tests; debug with `--dump` until green**

Run: `python -m pytest tests/test_aggregate.py -v`
Expected: PASS. If a total is off, the debugging loop is: `python extract_budget.py --dump Budget_Book_2026.pdf <page>` for the offending agency's pages, compare printed `... Total:` values against parsed sums per agency (add a temporary print of `printed_totals` vs computed sums), and fix `parse_sections`/`ITEM_RE`. Known likely culprits: multi-org section labels that don't prefix-match org names (extend `_match_org` with a token-overlap fallback), items whose wrapped description spans two lines (join a bare non-amount line with the following item line before matching), and pages where the same agency appears in two funds — key agencies by `(fund_code, agency_name)` if collisions occur (then update Task 3/4 accesses to use the same key; note it in the task report).

- [ ] **Step 5: Commit**

```bash
git add extract_budget.py tests/test_aggregate.py
git commit -m "feat: whole-book parsing with org attribution and GF validation"
```

---

### Task 3: Category mapping, revenue grouping, and exact cross-checks

**Files:**
- Modify: `category_map.py`
- Modify: `extract_budget.py`
- Test: `tests/test_categories.py`

**Interfaces:**
- Consumes: `parse_book` output (Task 2).
- Produces: in `category_map.py`: `AGENCY_CATEGORY: dict[str, str]` (agency name → category), `NONDEPT_OBJECT_CATEGORY(code, desc) -> str`, `PW_ORG_CATEGORY(org_name) -> str`, `revenue_group(code, desc) -> str`, `EXPECTED_CATEGORIES: dict[fy_label, dict[category, int]]`. In `extract_budget.py`: `categorize(book) -> dict[category, int]` (GF only, transit excluded) and `group_revenues(book) -> dict[group, int]`.

- [ ] **Step 1: Write failing tests with the exact expected tables**

```python
# tests/test_categories.py
import extract_budget as eb
from category_map import EXPECTED_CATEGORIES

def _check(pdf, fy):
    got = eb.categorize(eb.parse_book(pdf))
    exp = EXPECTED_CATEGORIES[fy]
    diffs = {c: (got.get(c, 0), exp[c]) for c in exp if abs(got.get(c, 0) - exp[c]) > 1}
    assert not diffs, f"{fy} category mismatches (got, expected): {diffs}"

def test_categories_fy26():
    _check("Budget_Book_2026.pdf", "FY2026")

def test_categories_fy25():
    _check("Budget_Book_2025.pdf", "FY2025")

def test_revenue_groups_partition_fy26():
    book = eb.parse_book("Budget_Book_2026.pdf")
    groups = eb.group_revenues(book)
    assert abs(sum(groups.values()) - 66_487_051) <= 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_categories.py -v`
Expected: FAIL (`EXPECTED_CATEGORIES` missing).

- [ ] **Step 3: Implement mappings**

```python
# append to category_map.py
EXPECTED_CATEGORIES = {
    "FY2025": {"Public Safety": 57_760_666, "Retirement": 27_291_207,
               "General Government": 25_559_290, "Highway & Streets": 19_968_652,
               "Health, Dental & Insurance": 17_195_489, "Debt Service": 16_100_000,
               "Other": 10_734_674, "Culture & Recreation": 7_618_111,
               "Health & Welfare": 3_308_180, "Economic Development": 223_888},
    "FY2026": {"Public Safety": 61_551_254, "Retirement": 29_706_516,
               "General Government": 26_788_383, "Highway & Streets": 21_545_314,
               "Health, Dental & Insurance": 17_595_489, "Debt Service": 16_100_000,
               "Other": 11_050_579, "Culture & Recreation": 7_764_641,
               "Health & Welfare": 4_104_665, "Economic Development": 304_420},
}

AGENCY_CATEGORY = {  # simple whole-agency mappings (GF)
    "Aldermen": "General Government", "Board of Assessors": "General Government",
    "City Clerk's Office": "General Government", "City Solicitor's Office": "General Government",
    "Finance Department": "General Government", "Information Systems": "General Government",
    "Mayor's Office": "General Government", "Office of Youth Services": "General Government",
    "Human Resources": "General Government", "Planning & Community Development": "General Government",
    "Tax Collector's Office": "General Government", "Central Fleet Management": "General Government",
    "Housing Stability": "General Government",
    "Fire Department": "Public Safety", "Police Department": "Public Safety",
    "Health Department - City": "Health & Welfare", "Welfare Department": "Health & Welfare",
    "Library Department": "Culture & Recreation",
    "Manchester Economic Development Office": "Economic Development",
}

def NONDEPT_OBJECT_CATEGORY(code, desc):
    """Non-Departmental Items page: split org 170 by object code; other orgs are 'Other'
    except Debt Service (org 140)."""
    if code in ("0224", "0225", "0228"):
        return "Retirement"
    if code in ("0211", "0212", "0213"):
        return "Health, Dental & Insurance"
    if code in ("0919", "0920"):
        return "Debt Service"
    return "Other"

def PW_ORG_CATEGORY(org_name):
    """Public Works organizations. Iterate against the derived split targets in the plan
    (FY26: Highway 21,545,314 / Culture 5,144,949 / GG 8,893,057) using --dump on PW pages."""
    n = org_name.casefold()
    if any(w in n for w in ("park", "recreation", "pool", "stadium", "cemeter", "aquatic", "arena")):
        return "Culture & Recreation"
    if any(w in n for w in ("facilit", "admin", "building", "engineer")):
        return "General Government"
    return "Highway & Streets"

def revenue_group(code, desc):
    d = desc.casefold()
    if code == "4083":
        return "Meals & Rooms Tax"
    if "grant" in d or "state aid" in d or code in ("4094", "4109", "4035"):
        return "State Aid & Grants"
    if "reimburse" in d or "chargeback" in d or "charge back" in d or "recover" in d:
        return "Chargebacks & Reimbursements"
    if "in lieu of taxes" in d or "tax lien" in d or "interest on tax" in d:
        return "Other Taxes & PILOTs"
    if any(w in d for w in ("fee", "permit", "license", "rent", "copies", "receipt", "parking")):
        return "Fees, Permits & Charges"
    return "Other Revenue"
```

```python
# append to extract_budget.py
from category_map import AGENCY_CATEGORY, NONDEPT_OBJECT_CATEGORY, PW_ORG_CATEGORY, revenue_group

def _agency_category_items(a):
    """Yield (category, amount) for one GF agency's expense items."""
    name = a["name"]
    if name in AGENCY_CATEGORY:
        for (code, _), amt in a["expenses"].items():
            yield AGENCY_CATEGORY[name], amt
    elif "Non-Departmental" in name:
        for (code, desc), amt in a["expenses"].items():
            if code != TRANSIT_OBJECT:
                yield NONDEPT_OBJECT_CATEGORY(code, desc), amt
    elif name == "Public Works":
        for org, items in a["org_expenses"].items():
            for _, amt in items.items():
                yield PW_ORG_CATEGORY(org), amt
    else:
        raise SystemExit(f"Agency not mapped to a category: {name!r}")

def categorize(book):
    out = {}
    for a in book["agencies"].values():
        if a["fund_code"] != "0101":
            continue
        for cat, amt in _agency_category_items(a):
            out[cat] = out.get(cat, 0) + amt
    return out

def group_revenues(book):
    out = {}
    for a in book["agencies"].values():
        if a["fund_code"] != "0101":
            continue
        for (code, desc), amt in a["revenues"].items():
            g = revenue_group(code, desc)
            out[g] = out.get(g, 0) + amt
    return out
```

Adaptation notes (expected, not failures): agency names on detail-page footers may differ slightly from the names above (taken from the book's summary pages) — fix `AGENCY_CATEGORY` keys to whatever `parse_book` actually produces, listing them via a temporary `print(sorted(book['agencies']))`. Non-departmental pages may parse under names like `Non-Departmental Items` — the `"Non-Departmental" in name` test covers it. Debt Service (0919/0920) may arrive inside the Non-Departmental agency (page 71 shows it as org 140 on the same pages) — the object-code rule routes it correctly regardless of org attribution. MPTS/Civic/So.NH/CIP objects (0890, 0935, 0937, 0948, 0912) fall through to "Other", which the expected totals confirm is correct.

- [ ] **Step 4: Run tests; iterate the PW org mapping until exact**

Run: `python -m pytest tests/test_categories.py tests/test_aggregate.py tests/test_parser.py -v`
Expected: PASS. The test failure message prints per-category (got, expected); only the three PW-fed categories should ever be off, and their errors must sum to zero. Use `--dump` on the Public Works pages (find them: `python - <<'EOF'` loop printing page indexes where `Agency:  Public Works` appears) to list actual org names, then adjust the keyword lists in `PW_ORG_CATEGORY` (or convert it to an explicit dict of org name → category) until both years match exactly. Escalate to the orchestrator if any non-PW category cannot be matched — that would mean the model in the spec is wrong, which is an architectural question.

- [ ] **Step 5: Commit**

```bash
git add category_map.py extract_budget.py tests/test_categories.py
git commit -m "feat: category mapping and revenue grouping with exact cross-checks"
```

---

### Task 4: data.js emission, reconciliation report, CLI

**Files:**
- Modify: `extract_budget.py`
- Create: `data.js` (generated)
- Test: `tests/test_aggregate.py` (extend)

**Interfaces:**
- Consumes: everything above.
- Produces: `build_budget_data(books: dict[fy_label, Book]) -> dict` and `main()`; running `python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf` writes `data.js` and prints a reconciliation report, exit 0 only if all validations pass. `data.js` defines `window.BUDGET_DATA` exactly as consumed by Tasks 5–7:

```js
window.BUDGET_DATA = {
  years: ["FY2025", "FY2026"],
  categories: { "Public Safety": {fy25: 57760666, fy26: 61551254}, /* ...all 10 + Education (MSD) */ },
  revenueGroups: { "Meals & Rooms Tax": {fy25: 0, fy26: 0}, /* ... */ },
  propertyTax: { gf: {fy25: 121685395, fy26: 130024210}, msd: {fy25: 120439237, fy26: 117531711} },
  msdOther: {fy25: 107543373, fy26: 120468214},   // msd_total - msd_property_tax
  citywide: {fy25: 413742767, fy26: 434511186},
  departments: [ { name: "Police Department", code: "330", fund: "0101",
    category: "Public Safety",
    expenses: [ {code: "0110", desc: "Regular Salary", fy25: null, fy26: 30603259}, /*...*/ ],
    revenues: [ /* same shape */ ],
    totals: {fy25: 32166107, fy26: 34329533} }, /* ... every agency incl. enterprise funds ... */ ],
};
```

- [ ] **Step 1: Write failing test**

```python
# append to tests/test_aggregate.py
def test_build_budget_data_shapes():
    books = {"FY2025": eb.parse_book("Budget_Book_2025.pdf"),
             "FY2026": eb.parse_book("Budget_Book_2026.pdf")}
    data = eb.build_budget_data(books)
    assert data["citywide"] == {"fy25": 413_742_767, "fy26": 434_511_186}
    assert data["categories"]["Education (MSD)"] == {"fy25": 227_982_610, "fy26": 237_999_925}
    police = next(d for d in data["departments"] if d["name"] == "Police Department")
    sal = next(i for i in police["expenses"] if i["code"] == "0110")
    assert sal["fy26"] == 30_603_259 and sal["fy25"] is not None
    epd = next(d for d in data["departments"] if d["fund"] != "0101")
    assert epd["category"] == "Enterprise Funds"
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest tests/test_aggregate.py -v`
Expected: new test FAILS (`build_budget_data` not defined); earlier tests still pass.

- [ ] **Step 3: Implement builder, emitter, CLI**

```python
# append to extract_budget.py
import json

def _merge_items(items25, items26):
    keys = sorted(set(items25) | set(items26), key=lambda k: (k[0], k[1]))
    return [{"code": c, "desc": d,
             "fy25": items25.get((c, d)), "fy26": items26.get((c, d))}
            for c, d in keys]

def build_budget_data(books):
    b25, b26 = books["FY2025"], books["FY2026"]
    cats25, cats26 = categorize(b25), categorize(b26)
    cats = {c: {"fy25": cats25.get(c, 0), "fy26": cats26.get(c, 0)} for c in EXPECTED_CATEGORIES["FY2026"]}
    cats["Education (MSD)"] = {"fy25": EXPECTED["FY2025"]["msd_total"], "fy26": EXPECTED["FY2026"]["msd_total"]}
    rev25, rev26 = group_revenues(b25), group_revenues(b26)
    revgroups = {g: {"fy25": rev25.get(g, 0), "fy26": rev26.get(g, 0)} for g in sorted(set(rev25) | set(rev26))}
    departments = []
    for name in sorted(set(b25["agencies"]) | set(b26["agencies"])):
        a25 = b25["agencies"].get(name, {"expenses": {}, "revenues": {}, "fund_code": None, "code": None})
        a26 = b26["agencies"].get(name, {"expenses": {}, "revenues": {}, "fund_code": None, "code": None})
        fund = a26["fund_code"] or a25["fund_code"]
        if fund == "0101":
            cat = (AGENCY_CATEGORY.get(name) or
                   ("Other" if "Non-Departmental" in name else
                    "Mixed (see line items)" if name == "Public Works" else None))
        else:
            cat = "Enterprise Funds"
        departments.append({"name": name, "code": a26["code"] or a25["code"], "fund": fund,
            "category": cat,
            "expenses": _merge_items(a25["expenses"], a26["expenses"]),
            "revenues": _merge_items(a25["revenues"], a26["revenues"]),
            "totals": {"fy25": sum(a25["expenses"].values()) or None,
                       "fy26": sum(a26["expenses"].values()) or None}})
    e25, e26 = EXPECTED["FY2025"], EXPECTED["FY2026"]
    return {"years": ["FY2025", "FY2026"], "categories": cats, "revenueGroups": revgroups,
        "propertyTax": {"gf": {"fy25": e25["gf_total"] - e25["gf_revenue"],
                               "fy26": e26["gf_total"] - e26["gf_revenue"]},
                        "msd": {"fy25": e25["msd_property_tax"], "fy26": e26["msd_property_tax"]}},
        "msdOther": {"fy25": e25["msd_total"] - e25["msd_property_tax"],
                     "fy26": e26["msd_total"] - e26["msd_property_tax"]},
        "citywide": {"fy25": e25["gf_total"] + e25["msd_total"],
                     "fy26": e26["gf_total"] + e26["msd_total"]}}

def main(argv):
    if len(argv) >= 3 and argv[0] == "--dump":
        print(pypdf.PdfReader(argv[1]).pages[int(argv[2])].extract_text())
        return 0
    paths = {"FY2025": argv[0], "FY2026": argv[1]}
    books, failures = {}, []
    for fy, path in paths.items():
        books[fy] = parse_book(path)
        failures += validate_book(books[fy], fy)
        got = categorize(books[fy])
        for c, exp in EXPECTED_CATEGORIES[fy].items():
            if abs(got.get(c, 0) - exp) > 1:
                failures.append(f"{fy} category {c}: {got.get(c, 0):,} != {exp:,}")
    data = build_budget_data(books)
    print("=== Reconciliation report ===")
    for fy in books:
        print(f"{fy}: GF/category/revenue checks", "OK" if not any(fy in f for f in failures) else "FAILED")
    for f in failures:
        print("MISMATCH:", f)
    if failures:
        return 1
    with open("data.js", "w", encoding="utf-8") as fh:
        fh.write("// GENERATED by extract_budget.py — do not edit by hand.\n")
        fh.write("window.BUDGET_DATA = " + json.dumps(data, indent=1) + ";\n")
    print("Wrote data.js")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

(Replace the Task 2 `__main__` block with this one — `--dump` moves into `main`.)

- [ ] **Step 4: Run full test suite and the real extraction**

Run: `python -m pytest -v` — Expected: all PASS.
Run: `python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf` — Expected: reconciliation report all OK, exit 0, `data.js` written (roughly 100–400 KB).
Spot-check: open `data.js`, confirm `"Regular Salary"` appears with plausible values and `citywide` matches.

- [ ] **Step 5: Commit**

```bash
git add extract_budget.py tests/test_aggregate.py data.js
git commit -m "feat: emit data.js with reconciliation report; commit generated data"
```

---

### Task 5: Sankey money-flow hero with year toggle

**Files:**
- Modify: `index.html` (add `<script src="data.js">` + Sankey section + JS)

**Interfaces:**
- Consumes: `window.BUDGET_DATA` (shape in Task 4).
- Produces: DOM: `section#flow` containing `canvas#sankeyChart` and `#flowYearToggle`; JS globals `renderSankey(yearKey)` where `yearKey` is `"fy25"|"fy26"`, and `FLOW_COLORS` (category → color map reused by Task 6). Department click hook: `onSankeyDeptClick(deptName)` — defined as a no-op stub here, replaced in Task 6.

- [ ] **Step 1: Add the CDN pin and data include**

In `index.html` `<head>`, after the existing datalabels plugin `<script>`, add:

```html
<script src="https://cdn.jsdelivr.net/npm/chartjs-chart-sankey@0.14.0/dist/chartjs-chart-sankey.min.js"></script>
<script src="data.js"></script>
```

- [ ] **Step 2: Add the hero section markup**

Insert as the first section inside the main content container (immediately after the existing hero/header block), following the page's existing section markup pattern (`.container`, cards, headings — copy the classes used by the first existing chart section):

```html
<section id="flow" class="section">
  <div class="container">
    <h2>Where the Money Comes From &amp; Where It Goes</h2>
    <p class="subtitle">Every dollar of the city budget: revenue sources &rarr; funds &rarr; spending categories &rarr; departments. Hover a band for amounts; click a department for line items.</p>
    <div class="toggle-group" id="flowYearToggle">
      <button data-year="fy25">FY2025</button>
      <button data-year="fy26" class="active">FY2026</button>
    </div>
    <div style="position:relative;height:640px"><canvas id="sankeyChart"></canvas></div>
  </div>
</section>
```

(Reuse the existing `.toggle-group`/button styling used by the trend chart's stacked/line toggle if present; otherwise add matching CSS consistent with existing buttons.)

- [ ] **Step 3: Implement the Sankey build**

Add to the page's script block:

```js
const D = window.BUDGET_DATA;
const FLOW_COLORS = Object.fromEntries(budgetData.map(d => [d.category, d.color]));
FLOW_COLORS['General Fund'] = '#1a2d4a'; FLOW_COLORS['School District'] = '#1e5a99';
FLOW_COLORS['Enterprise Funds'] = '#6c757d';

function sankeyFlows(y) {
  const flows = [];
  // Revenue groups -> General Fund
  for (const [g, v] of Object.entries(D.revenueGroups)) {
    if (v[y] > 0) flows.push({ from: g, to: 'General Fund', flow: v[y] });
  }
  flows.push({ from: 'Property Tax', to: 'General Fund', flow: D.propertyTax.gf[y] });
  flows.push({ from: 'Property Tax', to: 'School District', flow: D.propertyTax.msd[y] });
  flows.push({ from: 'State & Other School Revenue', to: 'School District', flow: D.msdOther[y] });
  // Funds -> categories
  for (const [c, v] of Object.entries(D.categories)) {
    if (c === 'Education (MSD)') flows.push({ from: 'School District', to: c, flow: v[y] });
    else if (v[y] > 0) flows.push({ from: 'General Fund', to: c, flow: v[y] });
  }
  // Categories -> departments (GF only; PW appears once per category via its label)
  for (const d of D.departments) {
    if (d.fund !== '0101' || !d.totals[y]) continue;
    if (d.category && d.category !== 'Mixed (see line items)' && d.category !== 'Other')
      flows.push({ from: d.category, to: d.name, flow: d.totals[y] });
  }
  return flows;
}

let sankeyChart = null;
function renderSankey(y) {
  const ctx = document.getElementById('sankeyChart').getContext('2d');
  if (sankeyChart) sankeyChart.destroy();
  sankeyChart = new Chart(ctx, {
    type: 'sankey',
    data: { datasets: [{
      data: sankeyFlows(y),
      colorFrom: c => FLOW_COLORS[c.dataset.data[c.dataIndex].from] || '#2c7bc0',
      colorTo:   c => FLOW_COLORS[c.dataset.data[c.dataIndex].to]   || '#2c7bc0',
      colorMode: 'gradient', nodeWidth: 14,
    }]},
    options: { animation: false, plugins: { datalabels: { display: false },
      tooltip: { callbacks: { label: c => {
        const f = c.dataset.data[c.dataIndex];
        const total = D.citywide[y];
        return `${f.from} → ${f.to}: $${f.flow.toLocaleString()} (${(100*f.flow/total).toFixed(1)}%)`;
      }}}},
      onClick: (evt, els) => {
        if (!els.length) return;
        const f = sankeyChart.data.datasets[0].data[els[0].index];
        const dept = D.departments.find(d => d.name === f.to);
        if (dept) onSankeyDeptClick(dept.name);
      }},
  });
}
function onSankeyDeptClick(name) {}  // replaced in drill-down task
document.querySelectorAll('#flowYearToggle button').forEach(b =>
  b.addEventListener('click', () => {
    document.querySelectorAll('#flowYearToggle button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    renderSankey(b.dataset.year);
  }));
renderSankey('fy26');
```

Note: `budgetData` here is the page's existing hand-entered category array — reused only for its color assignments. Category→department flows omit non-departmental "Other"/PW-mixed to keep flows consistent (their category bands still show full amounts; dollar-exact node balance at the department stage is not required — the plugin tolerates unbalanced intermediate nodes).

- [ ] **Step 4: Verify in browser**

Open `index.html` in a browser (or serve the folder). Expected: Sankey renders with property tax as the largest left band; tooltip on the Property Tax→School District band reads `$117,531,711 (27.1%)` for FY2026; toggling FY2025 re-renders with `$120,439,237`. No console errors. Fix before committing.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: money-flow Sankey hero with year toggle"
```

---

### Task 6: Department drill-down modal

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `window.BUDGET_DATA`, `FLOW_COLORS`, replaces `onSankeyDeptClick`.
- Produces: DOM `#deptModal` overlay; `openDeptDetail(deptName)`; a department index list `#deptList` under the Sankey (grouped GF then Enterprise Funds) so every department is reachable without the Sankey.

- [ ] **Step 1: Add modal + list markup and styles**

After `section#flow`'s canvas div, add:

```html
<div class="dept-list" id="deptList"></div>
```

Before `</body>`:

```html
<div id="deptModal" class="modal-overlay" hidden>
  <div class="modal-card">
    <button class="modal-close" aria-label="Close">&times;</button>
    <h3 id="deptModalTitle"></h3>
    <p id="deptModalMeta" class="subtitle"></p>
    <div style="position:relative;height:260px"><canvas id="deptTopChart"></canvas></div>
    <h4>Expense line items</h4>
    <table class="dept-table"><thead>
      <tr><th>Code</th><th>Description</th><th>FY2025</th><th>FY2026</th><th>$ Change</th><th>%</th></tr>
    </thead><tbody id="deptExpBody"></tbody></table>
    <h4 id="deptRevHead" hidden>Revenue line items</h4>
    <table class="dept-table" id="deptRevTable" hidden><thead>
      <tr><th>Code</th><th>Description</th><th>FY2025</th><th>FY2026</th><th>$ Change</th><th>%</th></tr>
    </thead><tbody id="deptRevBody"></tbody></table>
  </div>
</div>
```

CSS (in the existing `<style>` block, reusing the palette variables):

```css
.modal-overlay { position: fixed; inset: 0; background: rgba(15,27,45,0.55); display: flex;
  align-items: flex-start; justify-content: center; padding: 40px 16px; overflow-y: auto; z-index: 100; }
.modal-card { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  max-width: 900px; width: 100%; padding: 28px; position: relative; }
.modal-close { position: absolute; top: 14px; right: 18px; font-size: 1.6rem; border: 0;
  background: none; cursor: pointer; color: var(--gray); }
.dept-table { width: 100%; border-collapse: collapse; margin: 8px 0 20px; font-size: 0.92rem; }
.dept-table th, .dept-table td { padding: 6px 10px; text-align: right; border-bottom: 1px solid var(--gray-light); }
.dept-table th:nth-child(2), .dept-table td:nth-child(2) { text-align: left; }
.dept-table .up { color: var(--red); } .dept-table .down { color: var(--green); }
.badge-new, .badge-gone { font-size: 0.72rem; padding: 1px 7px; border-radius: 9px; margin-left: 6px; }
.badge-new { background: var(--teal); color: var(--white); } .badge-gone { background: var(--gray); color: var(--white); }
.dept-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.dept-list button { border: 1px solid var(--gray-light); background: var(--white); padding: 6px 12px;
  border-radius: 20px; cursor: pointer; font-size: 0.85rem; }
.dept-list button:hover { background: var(--gray-light); }
```

- [ ] **Step 2: Implement drill-down JS**

```js
const fmt = n => n == null ? '—' : '$' + n.toLocaleString();
let deptTopChart = null;

function lineRows(items) {
  return items.filter(i => (i.fy25 || 0) + (i.fy26 || 0) > 0)
    .sort((a, b) => (b.fy26 ?? b.fy25 ?? 0) - (a.fy26 ?? a.fy25 ?? 0))
    .map(i => {
      const badge = i.fy25 == null ? ' <span class="badge-new">new FY26</span>'
                  : i.fy26 == null ? ' <span class="badge-gone">ended</span>' : '';
      const chg = (i.fy25 != null && i.fy26 != null) ? i.fy26 - i.fy25 : null;
      const pct = chg != null && i.fy25 ? (100 * chg / i.fy25).toFixed(1) + '%' : '—';
      const cls = chg > 0 ? 'up' : chg < 0 ? 'down' : '';
      return `<tr><td>${i.code}</td><td>${i.desc}${badge}</td><td>${fmt(i.fy25)}</td>` +
             `<td>${fmt(i.fy26)}</td><td class="${cls}">${chg == null ? '—' : fmt(chg)}</td><td class="${cls}">${pct}</td></tr>`;
    }).join('');
}

function openDeptDetail(name) {
  const d = D.departments.find(x => x.name === name);
  if (!d) return;
  document.getElementById('deptModalTitle').textContent = d.name;
  document.getElementById('deptModalMeta').textContent =
    `${d.category || ''} · FY2026 budget ${fmt(d.totals.fy26)} (FY2025 ${fmt(d.totals.fy25)})`;
  document.getElementById('deptExpBody').innerHTML = lineRows(d.expenses);
  const hasRev = d.revenues.some(i => (i.fy25 || 0) + (i.fy26 || 0) > 0);
  document.getElementById('deptRevHead').hidden = !hasRev;
  document.getElementById('deptRevTable').hidden = !hasRev;
  if (hasRev) document.getElementById('deptRevBody').innerHTML = lineRows(d.revenues);
  const top = d.expenses.filter(i => i.fy26).sort((a, b) => b.fy26 - a.fy26).slice(0, 8);
  if (deptTopChart) deptTopChart.destroy();
  deptTopChart = new Chart(document.getElementById('deptTopChart'), {
    type: 'bar', data: { labels: top.map(i => i.desc),
      datasets: [{ data: top.map(i => i.fy26), backgroundColor: FLOW_COLORS[d.category] || '#2c7bc0' }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false }, datalabels: { display: false } },
      scales: { x: { ticks: { callback: v => '$' + (v / 1e6).toFixed(1) + 'M' } } } },
  });
  document.getElementById('deptModal').hidden = false;
}
onSankeyDeptClick = openDeptDetail;  // reassign the Task 5 stub (declare it with `let` there)

document.querySelector('#deptModal .modal-close').addEventListener('click',
  () => document.getElementById('deptModal').hidden = true);
document.getElementById('deptModal').addEventListener('click',
  e => { if (e.target.id === 'deptModal') e.currentTarget.hidden = true; });

const list = document.getElementById('deptList');
for (const d of [...D.departments].sort((a, b) => (a.fund === '0101' ? 0 : 1) - (b.fund === '0101' ? 0 : 1)
    || (b.totals.fy26 || 0) - (a.totals.fy26 || 0))) {
  if (!d.totals.fy26 && !d.totals.fy25) continue;
  const btn = document.createElement('button');
  btn.textContent = d.fund === '0101' ? d.name : `${d.name} (Enterprise)`;
  btn.addEventListener('click', () => openDeptDetail(d.name));
  list.appendChild(btn);
}
```

(Change Task 5's stub to `let onSankeyDeptClick = () => {};` so this reassignment works.)

- [ ] **Step 3: Verify in browser**

Expected: clicking "Police Department" in the list opens the modal; Regular Salary row shows FY2026 $30,603,259; % change column populated; Board of Assessors shows both expense and revenue tables; an EPD/Aviation button opens enterprise-fund detail; close button and backdrop click both dismiss. No console errors.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: department drill-down modal with FY25/26 line-item comparison"
```

---

### Task 7: Rewire existing charts' FY25/FY26 values from BUDGET_DATA

**Files:**
- Modify: `index.html` (the `budgetData`/`totals`/`generalFund`/`msdBudget` constants block, ~lines 479–513)

**Interfaces:**
- Consumes: `window.BUDGET_DATA.categories`, `.citywide`; existing chart code (unchanged consumers of `budgetData`, `totals`, `generalFund`, `msdBudget`).

- [ ] **Step 1: Replace fy25/fy26 fields with derived values plus a guard**

Keep the existing array but source fy25/fy26 from `BUDGET_DATA`, keeping the old numbers as a legacy cross-check. Replace the constants block with:

```js
const LEGACY_FY = {  // previous hand-entered values; retained as a tripwire
  'Education (MSD)': [227982610, 237999925], 'Public Safety': [57760666, 61551254],
  'Retirement': [27291207, 29706516], 'General Government': [25559290, 26788383],
  'Highway & Streets': [19968652, 21545314], 'Health, Dental & Insurance': [17195489, 17595489],
  'Debt Service': [16100000, 16100000], 'Other': [10734674, 11050579],
  'Culture & Recreation': [7618111, 7764641], 'Health & Welfare': [3308180, 4104665],
  'Economic Development': [223888, 304420],
};
const HAVE_DATA = typeof window.BUDGET_DATA === 'object' && window.BUDGET_DATA;
function catFY(name, y, legacyIdx) {
  if (!HAVE_DATA) return LEGACY_FY[name][legacyIdx];
  const v = window.BUDGET_DATA.categories[name][y];
  if (v !== LEGACY_FY[name][legacyIdx])
    console.error(`BUDGET_DATA mismatch for ${name} ${y}: ${v} != ${LEGACY_FY[name][legacyIdx]}`);
  return v;
}
const budgetData = [
  { category: 'Education (MSD)', fy23: 187097818, fy24: 191759220, fy25: catFY('Education (MSD)','fy25',0), fy26: catFY('Education (MSD)','fy26',1), color: '#1e5a99' },
  { category: 'Public Safety', fy23: 51633037, fy24: 55605988, fy25: catFY('Public Safety','fy25',0), fy26: catFY('Public Safety','fy26',1), color: '#dc3545' },
  { category: 'Retirement', fy23: 25134031, fy24: 25555116, fy25: catFY('Retirement','fy25',0), fy26: catFY('Retirement','fy26',1), color: '#6f42c1' },
  { category: 'General Government', fy23: 18742866, fy24: 25011825, fy25: catFY('General Government','fy25',0), fy26: catFY('General Government','fy26',1), color: '#17a2b8' },
  { category: 'Highway & Streets', fy23: 21421714, fy24: 19504209, fy25: catFY('Highway & Streets','fy25',0), fy26: catFY('Highway & Streets','fy26',1), color: '#fd7e14' },
  { category: 'Health, Dental & Insurance', fy23: 13299242, fy24: 15276990, fy25: catFY('Health, Dental & Insurance','fy25',0), fy26: catFY('Health, Dental & Insurance','fy26',1), color: '#0dcaf0' },
  { category: 'Debt Service', fy23: 16100000, fy24: 16100000, fy25: catFY('Debt Service','fy25',0), fy26: catFY('Debt Service','fy26',1), color: '#6c757d' },
  { category: 'Other', fy23: 12799403, fy24: 11238353, fy25: catFY('Other','fy25',0), fy26: catFY('Other','fy26',1), color: '#adb5bd' },
  { category: 'Culture & Recreation', fy23: 6649562, fy24: 7161121, fy25: catFY('Culture & Recreation','fy25',0), fy26: catFY('Culture & Recreation','fy26',1), color: '#20c997' },
  { category: 'Health & Welfare', fy23: 4078143, fy24: 3066657, fy25: catFY('Health & Welfare','fy25',0), fy26: catFY('Health & Welfare','fy26',1), color: '#e83e8c' },
  { category: 'Economic Development', fy23: 10000, fy24: 175907, fy25: catFY('Economic Development','fy25',0), fy26: catFY('Economic Development','fy26',1), color: '#ffc107' },
];
const totals = { fy23: 356965816, fy24: 370455386,
  fy25: HAVE_DATA ? window.BUDGET_DATA.citywide.fy25 : 413742767,
  fy26: HAVE_DATA ? window.BUDGET_DATA.citywide.fy26 : 434511186 };
const generalFund = { fy23: 169867998, fy24: 178696166,
  fy25: HAVE_DATA ? 185760157 : 185760157, fy26: HAVE_DATA ? 196511261 : 196511261 };
const msdBudget = { fy23: 187097818, fy24: 191759220,
  fy25: catFY('Education (MSD)','fy25',0), fy26: catFY('Education (MSD)','fy26',1) };
```

Also wrap the Task 5/6 flow-section initialization in `if (HAVE_DATA) { ... } else { document.getElementById('flow').innerHTML = '<div class="container"><p>Run <code>python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf</code> to generate data.js.</p></div>'; }` — this is the spec's missing-data fallback. (`generalFund` fy25/fy26 stay literal because `BUDGET_DATA` stores GF only implicitly via propertyTax + revenue sums; deriving them adds no information and the tripwire already covers category sums.)

- [ ] **Step 2: Verify in browser**

Expected: every pre-existing chart and the table render numbers identical to before (compare the totals row: FY2026 $434,511,186); **zero** `BUDGET_DATA mismatch` errors in the console. Temporarily rename `data.js` → confirm the page still renders legacy charts and the flow section shows the fallback notice; rename back.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat: drive existing charts' FY25/FY26 from extracted data with legacy tripwire"
```

---

### Task 8: Browser verification and final review

**Files:** none (verification only)

- [ ] **Step 1: Full test suite + extraction**

Run: `python -m pytest -v` and `python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf`
Expected: all tests pass; reconciliation all OK; `git status` shows no unexpected `data.js` diff.

- [ ] **Step 2: Delegate interactive verification to browser-tester** (per CLAUDE.md)

Acceptance criteria to hand to the browser-tester agent:
1. Page loads from disk with zero console errors.
2. Sankey renders; Property Tax → School District tooltip = $117,531,711 (FY2026); year toggle switches to $120,439,237 (FY2025).
3. Clicking Police Department (Sankey node or list chip) opens the modal; Regular Salary FY2026 = $30,603,259; change columns populated; badges appear for at least one new/ended item somewhere (e.g., Housing Stability, FY25-only).
4. Board of Assessors modal shows a revenue table totaling $1,111,041 across FY2026 rows.
5. An Enterprise-fund department (EPD or Aviation) opens with line items.
6. Existing charts unchanged: allocation doughnut total $434,511,186; trend chart still shows FY2023–FY2026.
7. No `BUDGET_DATA mismatch` console errors.
8. Page is usable at 375px width (Sankey scrolls or shrinks; modal scrollable).

- [ ] **Step 3: Fix anything the tester finds, re-verify, final commit**

```bash
git add -A
git commit -m "chore: verification fixes from browser test pass"
```

---

## Self-review notes

- Spec coverage: extraction+validation (Tasks 1–4), Sankey (5), drill-down (6), existing-charts rewiring + fallback (7), browser verification (8). Re-runnability: CLI takes paths (Task 4). Category mapping failure mode: named `SystemExit` (Task 3).
- The FY26 book's summary page prints *different* FY25 numbers (DRA-adjusted) than the FY25 book. All FY2025 values come from the FY2025 book only; the constants in `EXPECTED` follow that rule and match `index.html`.
- Type consistency: `yearKey` is `"fy25"/"fy26"` everywhere in JS; Python fiscal labels are `"FY2025"/"FY2026"`; the boundary is `build_budget_data`.
