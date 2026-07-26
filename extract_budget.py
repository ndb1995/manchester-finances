"""Extract Manchester NH budget book PDFs into data.js. No OCR: pypdf text layer only."""
import json, re, sys

import pypdf

from category_map import (AGENCY_CATEGORY, EXPECTED, EXPECTED_CATEGORIES, NONDEPT_OBJECT_CATEGORY,
                          PW_ORG_CATEGORY, TRANSIT_OBJECT, UNATTRIBUTED, revenue_group)

# Whitespace inside a number is tolerated only directly after a comma: the text layer
# sometimes emits '33, 826,822'. Allowing it anywhere let ITEM_RE's lazy description group
# stop at the first opportunity, so '0898 Special Project 2 218,195' parsed as the
# description 'Special Project' with the amount 2,218,195 -- off by an order of magnitude.
AMOUNT = r"\d+(?:,\s?\d+)*(?:\.\d+)?"
ANY_AMOUNT = rf"(?:\({AMOUNT}\)|{AMOUNT})"  # the book prints negatives in parentheses
# Object codes are 4 digits, but the text layer sometimes drops the leading zero.
ITEM_RE = re.compile(rf"^(\d{{3,4}})\s+(.+?)\s+({ANY_AMOUNT})\$?\s*$")
ITEM_START_RE = re.compile(r"^\d{3,4}\s+\S")
TOTAL_RE = re.compile(rf"^(.*?)\s*Totals?:\s*({ANY_AMOUNT})\$?\s*$")
TOTAL_PREFIX_RE = re.compile(rf"^Totals?\s+(.+?):\s*({ANY_AMOUNT})\$?\s*$")
FUND_RE = re.compile(r"Fund:\s*(\d{4})\s+(.+?)\s*$", re.M)
AGENCY_RE = re.compile(r"Agency:\s*(?:(\d{3})\s+)?(.+?)\s*$", re.M)
KIND_RE = re.compile(r"FY\s*\d{4}\s+(Expense|Revenue)\s+Budget(\s+by\s+Organization)?", re.I)
ORG_RE = re.compile(r"Organization:\s*(\d+)\s+(.+?)\s*$", re.M)
STRUCT_RE = re.compile(r"^(Fund:|Agency:|Organization:|FY\s*\d{4}\b)")
JUNK_PREFIX_RE = re.compile(r"^[;:]+(?=\d{3,4}\s)")  # text-layer artifact: ';0460 Safety 1,080'
HEADER = "Object Description Budget"
DEPT_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z&,.'/-]*(?: [A-Za-z&,.'/-]+)*$")  # 'Public Works'
# A line the parser could not turn into an item or a total is only worth reporting when it
# carries money -- a comma-grouped figure or a parenthesized negative. Page numbers, headers
# and prose are noise; a dropped amount is the one thing that could cost a dollar.
MONEY_LINE_RE = re.compile(rf"\d(?:,\s?\d{{3}})+|\({AMOUNT}\)")

def parse_amount(s):
    """'844,355' -> 844355; '(160,000)' -> -160000; '352,121.00' -> 352121 (nearest dollar)."""
    s = s.strip()
    neg = s.startswith("(") and s.endswith(")")
    digits = re.sub(r"[^\d.]", "", s)
    val = round(float(digits)) if "." in digits else int(digits)
    return -val if neg else val

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

def _is_fragment(line):
    """True when a line carries no structure of its own, so it may be a wrapped tail.

    A line that opens its own item (even a malformed one, e.g. '0741 5,000') is never a
    fragment: welding two item starts together would fabricate one item that swallows the
    second object code's amount.
    """
    return not (line == HEADER or STRUCT_RE.match(line) or ITEM_START_RE.match(line)
                or ITEM_RE.match(line) or TOTAL_RE.match(line) or TOTAL_PREFIX_RE.match(line))

def _rejoin_wrapped(lines):
    """Repair items the text layer split mid-word: '0740 Equi' + 'pment 136,300'."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if (nxt and ITEM_START_RE.match(line) and not ITEM_RE.match(line)
                and _is_fragment(nxt) and ITEM_RE.match(line + nxt)):
            out.append(line + nxt)
            i += 2
            continue
        out.append(line)
        i += 1
    return out

def parse_sections(text, dropped=None):
    """Sections on one page. `dropped`, when given, collects every skipped line carrying money.

    Nothing is dropped silently: the caller passes a list and the reconciliation report prints
    what landed in it. Today every such line is a section total in a form the parser
    deliberately does not accept (a colon-only 'Aviation-Marketing: 1,805,580', or an orphan
    amount left behind by the text layer), so no line item is lost -- but that is a fact about
    these two books, not a guarantee about the next one.
    """
    sections, cur = [], {"items": [], "total_label": None, "total": None}
    lines = [JUNK_PREFIX_RE.sub("", ln) for ln in (raw.strip() for raw in text.splitlines()) if ln]
    for line in _rejoin_wrapped(lines):
        if line == HEADER:
            if cur["items"]:
                sections.append(cur)
            cur = {"items": [], "total_label": None, "total": None}
            continue
        m = ITEM_RE.match(line)
        if m:
            code = m.group(1).zfill(4)  # normalize '120' -> '0120' for cross-year matching
            cur["items"].append((code, m.group(2).strip(), parse_amount(m.group(3))))
            continue
        m = TOTAL_RE.match(line) or TOTAL_PREFIX_RE.match(line)
        if m and m.group(1):  # split/label-only totals (empty label) are ignored
            cur["total_label"] = m.group(1).strip()
            cur["total"] = parse_amount(m.group(2))
            sections.append(cur)
            cur = {"items": [], "total_label": None, "total": None}
            continue
        # anything else: footers, page numbers, orphan amounts, wrapped labels -> skip,
        # but report it when it carries an amount
        if dropped is not None and MONEY_LINE_RE.search(line):
            dropped.append(line)
    if cur["items"]:
        sections.append(cur)
    return sections

def _norm(s):
    """Fold case and punctuation so 'City Clerk-General' == 'City Clerk General'."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").casefold()).strip()

def _match_org(label, orgs):
    """Match a section total label like 'Debt service' to ('140','Debt Service')."""
    lab = _norm(label)
    if not lab:
        return None
    for code, name in orgs:
        n = _norm(name)
        if lab.startswith(n) or n.startswith(lab):
            return name
    lab_words = set(lab.split())  # 'Police-Uniformed Officers' vs 'Police-Uniformed Police Officers'
    for code, name in orgs:
        words = set(_norm(name).split())
        if words and (lab_words <= words or words <= lab_words):
            return name
    return None

def _same_entity(label, name):
    """True when a printed total's label names the agency, e.g. 'Public Works Department'."""
    x, y = _norm(label), _norm(name)
    return bool(x and y and (x.startswith(y) or y.startswith(x)))

def _dept_lines(text):
    """Grouping lines the book stamps on a sub-unit's page, e.g. 'Public Works' on the
    Facilities Division pages or 'Health Department - City' on the Senior Services page.

    They are the page's only leftover prose: no digits (which rules out wrapped item
    fragments like 'pment 136,300') and no trailing colon (which rules out split totals).
    """
    out = []
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln or ln == HEADER or STRUCT_RE.match(ln) or ln.endswith(":"):
            continue
        if DEPT_LINE_RE.match(ln):
            out.append(ln)
    return out

def parse_book(pdf_path):
    """Aggregate one budget book into agencies, counting every dollar exactly once.

    The book prints each department three ways: an agency-level page, 'by Organization'
    detail pages, and -- for departments with sub-agencies -- sub-agency pages stamped with
    the parent department's name. The detail restates the agency page, so only the
    agency-level page feeds `expenses`/`revenues`; everything else feeds `org_expenses`.
    Departments printed only as detail (Non-Departmental Items) fall back to that detail.
    """
    texts = [(page.extract_text() or "") for page in pypdf.PdfReader(pdf_path).pages]
    metas = [classify_page(t) for t in texts]

    # The same agency is named inconsistently across pages ('Highway Division' /
    # 'Highway Department', 'Health Department - City' / 'Health Department'); its code is
    # stable, so the first name seen for a (fund, code) becomes canonical.
    canon = {}
    for m in metas:
        if m and m["agency_code"] and m["agency_name"]:
            canon.setdefault((m["fund_code"], m["agency_code"]), m["agency_name"])
    known = {}  # (fund, normalized any-name) -> canonical name
    for m in metas:
        if m and m["agency_name"]:
            name = canon.get((m["fund_code"], m["agency_code"]), m["agency_name"])
            known[(m["fund_code"], _norm(m["agency_name"]))] = name
            known[(m["fund_code"], _norm(name))] = name

    agencies, detail, printed, warnings, dropped = {}, {}, {}, [], []
    for page_no, (text, meta) in enumerate(zip(texts, metas), 1):
        if not meta:
            continue  # summary/TOC/cover page
        fund, depts = meta["fund_code"], _dept_lines(text)
        name = known.get((fund, _norm(meta["agency_name"]))) if meta["agency_name"] else None
        if not name:  # no 'Agency:' line at all (Non-Departmental Items)
            name = next((known.get((fund, _norm(d)), d) for d in depts), None)
            if not name:
                warnings.append(f"page with fund {fund} has no agency or department name")
                continue
        parent = next((known[(fund, _norm(d))] for d in depts
                       if (fund, _norm(d)) in known and known[(fund, _norm(d))] != name), None)
        key = parent or name
        a = agencies.setdefault(key, {"code": None, "name": key, "fund_code": fund,
                                      "expenses": {}, "revenues": {}, "org_expenses": {},
                                      "printed_totals": {}})
        if a["fund_code"] != fund:
            warnings.append(f"agency {key!r} appears in funds {a['fund_code']} and {fund}")
        if parent is None and meta["agency_code"] and not a["code"]:
            a["code"] = meta["agency_code"]
        page_dropped = []
        sections = parse_sections(text, page_dropped)
        dropped += [(page_no, ln) for ln in page_dropped]
        # A page restating the agency total (its own 'by Organization' detail, or any page
        # belonging to a parent department) must not be added to the agency bucket again.
        is_detail = bool(parent) or meta["by_org"]
        for sec in sections:  # printed totals are diagnostics, roll-ups included
            if sec["total"] is None or not sec["total_label"]:
                continue
            # keyed by kind too: an agency's expense and revenue totals share one label
            a["printed_totals"][(meta["kind"], sec["total_label"])] = sec["total"]
            # the department's own total: printed on its agency-level pages, and repeated as
            # an item-less roll-up at the end of its detail. Organization totals sit on
            # detail pages and carry items, so they cannot be mistaken for it.
            if (not is_detail or not sec["items"]) and _same_entity(sec["total_label"], key):
                pk = (key, meta["kind"])
                printed[pk] = max(printed.get(pk, 0), sec["total"])
        sections = [s for s in sections if s["items"]]  # drop grand-total-only pseudo sections
        bucket = detail.setdefault((key, meta["kind"]), {}) if is_detail else (
            a["expenses"] if meta["kind"] == "expense" else a["revenues"])
        orgs = _page_orgs(sections, meta, name if parent else None)
        for sec, org in zip(sections, orgs):
            for code, desc, amt in sec["items"]:
                k = (code, desc)
                bucket[k] = bucket.get(k, 0) + amt
                if org and meta["kind"] == "expense":
                    a["org_expenses"].setdefault(org, {})
                    a["org_expenses"][org][k] = a["org_expenses"][org].get(k, 0) + amt

    for (key, kind), items in detail.items():
        bucket = agencies[key]["expenses"] if kind == "expense" else agencies[key]["revenues"]
        if not bucket:  # department printed only as detail
            bucket.update(items)
            continue
        # FY2026 Aviation itemizes objects 0740 'Equipment' and 0745 'Computer Software
        # Services' on its organization pages only -- they are absent from the agency pages'
        # text layer -- leaving the bucket 370,448 short of the total the book prints. An item
        # whose object code AND description are both new to the bucket cannot be a
        # restatement, so take it from the detail. The description half of that test matters:
        # the book files the same line under different codes in its two views (Aviation
        # 'Special Salary' is 0142 by agency but 0140 by organization, EPD FY2025 'Severance
        # Pay' is 0142 by agency but 0141 by organization), and those must not be added twice.
        codes = {code for code, _ in bucket}
        descs = {desc for _, desc in bucket}
        for (code, desc), amt in items.items():
            if code not in codes and desc not in descs:
                bucket[(code, desc)] = amt
    printed.update(_alias_anchors(agencies, printed))
    warnings += _total_warnings(agencies, printed)
    return {"agencies": agencies, "warnings": warnings, "printed": printed,
            "dropped_lines": dropped}

# Agencies whose grand total the book prints under a label that is not the agency's own name,
# so the strict name match above never pairs the two and the bucket goes unchecked. Listed
# one by one on purpose: loosening `_same_entity` to reach them would also pair labels that
# merely resemble each other, which is how a wrong total gets accepted as a right one.
PRINTED_TOTAL_ALIAS = {
    "Planning & Community Development": "Planning Department",  # 'Planning Department Total:'
    # airport revenue: the books file it under the agency name 'Various' but foot the page
    # 'Aviation Total:'
    "Various": "Aviation",
    # the roll-up 'Non-Departmental Items Total:' names the agency exactly, but it sits in a
    # section that carries items on a 'by Organization' page, so the guard above skips it
    "Non-Departmental Items": "Non-Departmental Items",
}

def _alias_anchors(agencies, printed):
    """Printed grand totals the name match cannot reach, keyed the way `printed` is.

    Only fills gaps: an agency the name match already anchored keeps that anchor.
    """
    out = {}
    for key, label in PRINTED_TOTAL_ALIAS.items():
        a = agencies.get(key)
        if not a:
            continue
        for kind in ("expense", "revenue"):
            if (key, kind) not in printed and (kind, label) in a["printed_totals"]:
                out[(key, kind)] = a["printed_totals"][(kind, label)]
    return out

def _total_warnings(agencies, printed):
    """Non-fatal check that each bucket matches the total the book prints for its agency.

    Diagnostic only: the printed totals are never treated as anchors, they just have to
    agree with what was aggregated. This is what would have caught the FY2026 Aviation gap.

    An empty bucket against a nonzero printed total warns like any other disagreement: it is
    the loudest possible failure -- a whole department's money missing -- so exempting it
    would blind the check to exactly the case it exists for.
    """
    out = []
    for (key, kind), total in sorted(printed.items()):
        bucket = agencies[key]["expenses"] if kind == "expense" else agencies[key]["revenues"]
        if abs(sum(bucket.values()) - total) > 1:
            out.append(f"{key} {kind} total {sum(bucket.values()):,} != printed {total:,}")
    return out

def anchor_coverage(book):
    """(checked, unchecked) bucket names, so the report can say what the check really covers.

    A bucket with no printed total is not wrong, it is just unwitnessed: nothing in the book
    states its subtotal, so only the general fund anchors constrain it -- and for an
    enterprise fund, nothing does.
    """
    checked, unchecked = [], []
    for key, a in sorted(book["agencies"].items()):
        for kind, bucket in (("expense", a["expenses"]), ("revenue", a["revenues"])):
            if not bucket:
                continue  # a side of the ledger the department does not have
            (checked if (key, kind) in book["printed"] else unchecked).append(f"{key} {kind}")
    return checked, unchecked

def _page_orgs(sections, meta, sub_agency):
    """One organization name per section, or None when the section carries no detail.

    On a sub-agency page without an organization breakdown the sub-agency itself is the
    organization. Otherwise the section's own printed label is authoritative; a section
    whose total was split across lines has no label, so it takes the page's one remaining
    unclaimed organization when that is unambiguous.
    """
    if not meta["by_org"]:
        return [sub_agency] * len(sections)
    named = [_match_org(s["total_label"], meta["orgs"]) or s["total_label"] for s in sections]
    unclaimed = [n for _, n in meta["orgs"] if n not in named]
    blanks = [i for i, n in enumerate(named) if not n]
    if len(blanks) == 1 and len(unclaimed) == 1:
        named[blanks[0]] = unclaimed[0]
    return [n or UNATTRIBUTED for n in named]

def gf_totals(book):
    """(expense, revenue) for the general fund, transit subsidy excluded as the book directs."""
    gf_exp = gf_rev = 0
    for a in book["agencies"].values():
        if a["fund_code"] != "0101":
            continue
        gf_exp += sum(v for (code, _), v in a["expenses"].items() if code != TRANSIT_OBJECT)
        gf_rev += sum(a["revenues"].values())
    return gf_exp, gf_rev

def validate_book(book, fy_label):
    errors, exp = list(book.get("warnings", ())), EXPECTED[fy_label]
    gf_exp, gf_rev = gf_totals(book)
    if abs(gf_exp - exp["gf_total"]) > 1:
        errors.append(f"{fy_label} GF expense total {gf_exp:,} != expected {exp['gf_total']:,}")
    if abs(gf_rev - exp["gf_revenue"]) > 1:
        errors.append(f"{fy_label} GF revenue total {gf_rev:,} != expected {exp['gf_revenue']:,}")
    return errors

def _agency_category_items(a):
    """Yield (category, amount) for one agency's expense items.

    Most departments belong to a single category. Two do not: Public Works splits across
    three, so its `org_expenses` breakdown is used instead of its flat bucket (the two are
    equal by construction -- the aggregation checks it), and Non-Departmental Items splits by
    object code. The transit subsidy is dropped here, matching `validate_book`, so the
    categories still add up to the general fund total the book prints.
    """
    name = a["name"]
    if name in AGENCY_CATEGORY:
        for _, amt in a["expenses"].items():
            yield AGENCY_CATEGORY[name], amt
    elif "Non-Departmental" in name:
        for (code, desc), amt in a["expenses"].items():
            if code != TRANSIT_OBJECT:
                yield NONDEPT_OBJECT_CATEGORY(code, desc), amt
    elif name == "Public Works":
        for org, items in a["org_expenses"].items():
            cat = PW_ORG_CATEGORY(org)
            for _, amt in items.items():
                yield cat, amt
    else:
        raise SystemExit(f"Agency not mapped to a category: {name!r}")

def categorize(book):
    """General fund expenses by spending category. Enterprise funds are excluded by fund
    code, not by name: they are separately funded and never part of the tax-supported total."""
    out = {}
    for a in book["agencies"].values():
        if a["fund_code"] != "0101":
            continue
        for cat, amt in _agency_category_items(a):
            out[cat] = out.get(cat, 0) + amt
    return out

def group_revenues(book):
    """General fund revenues by source group. Every line lands in exactly one group, so the
    groups sum to the general fund revenue total."""
    out = {}
    for a in book["agencies"].values():
        if a["fund_code"] != "0101":
            continue
        for (code, desc), amt in a["revenues"].items():
            g = revenue_group(code, desc)
            out[g] = out.get(g, 0) + amt
    return out

MSD_CATEGORY = "Education (MSD)"  # a constant, not parsed: the school district prints its own book
# The books file airport revenue under the literal agency name 'Various' in the aviation fund
# instead of under 'Aviation'. Merging the two would break the totals the book prints for each,
# so the entry stays separate and only its display name is fixed up here.
DISPLAY_NAME = {"Various": "Aviation - Revenues (Various)"}
EMPTY_AGENCY = {"code": None, "fund_code": None, "expenses": {}, "revenues": {}, "org_expenses": {}}

def _merge_items(items25, items26):
    """Pair two years' line items by (object code, description).

    A missing year is `None`, never 0: 'not budgeted' and 'budgeted at zero' are different
    facts, and the site labels them differently.
    """
    keys = sorted(set(items25) | set(items26), key=lambda k: (k[0], k[1]))
    return [{"code": c, "desc": d,
             "fy25": items25.get((c, d)), "fy26": items26.get((c, d))}
            for c, d in keys]

def _year_total(agency, bucket):
    """Sum one bucket, or None when the department is absent from that year's book."""
    return None if agency is None else sum(agency[bucket].values())

def _org_totals(a25, a26):
    """{organization: {fy25, fy26}} where the book breaks a department into organizations.

    Totals only -- the item-level organization detail restates the department's own line items,
    which the payload already carries. `UNATTRIBUTED` passes through as its literal
    '(unattributed)' so the site can label those sections honestly.
    """
    orgs25 = a25["org_expenses"] if a25 else {}
    orgs26 = a26["org_expenses"] if a26 else {}
    return {org: {"fy25": sum(orgs25[org].values()) if org in orgs25 else None,
                  "fy26": sum(orgs26[org].values()) if org in orgs26 else None}
            for org in sorted(set(orgs25) | set(orgs26))}

def _department_category(name, fund):
    """The site's spending category for one department, or a hard error for a new one.

    Enterprise funds are their own band: they are separately funded and outside the tax-supported
    total. Within the general fund, Non-Departmental Items and Public Works are the two
    departments `categorize` splits internally, so they get labels the site can show instead of a
    single category. Anything else unmapped is a failure, not a default -- a renamed department
    would otherwise reach the flow diagram with a null category and silently disappear.
    """
    if fund != "0101":
        return "Enterprise Funds"
    if name in AGENCY_CATEGORY:
        return AGENCY_CATEGORY[name]
    if "Non-Departmental" in name:
        return "Other"
    if name == "Public Works":
        return "Mixed (see line items)"
    raise SystemExit(f"Department not mapped to a category: {name!r}")

def build_budget_data(books):
    """Merge both books into the single payload the site consumes as `window.BUDGET_DATA`."""
    b25, b26 = books["FY2025"], books["FY2026"]
    cats25, cats26 = categorize(b25), categorize(b26)
    cats = {c: {"fy25": cats25.get(c, 0), "fy26": cats26.get(c, 0)}
            for c in EXPECTED_CATEGORIES["FY2026"]}
    cats[MSD_CATEGORY] = {"fy25": EXPECTED["FY2025"]["msd_total"],
                          "fy26": EXPECTED["FY2026"]["msd_total"]}
    rev25, rev26 = group_revenues(b25), group_revenues(b26)
    revgroups = {g: {"fy25": rev25.get(g, 0), "fy26": rev26.get(g, 0)}
                 for g in sorted(set(rev25) | set(rev26))}
    departments = []
    for name in sorted(set(b25["agencies"]) | set(b26["agencies"])):
        a25, a26 = b25["agencies"].get(name), b26["agencies"].get(name)
        e25, e26 = (a25 or EMPTY_AGENCY), (a26 or EMPTY_AGENCY)
        fund = e26["fund_code"] or e25["fund_code"]
        dept = {"name": DISPLAY_NAME.get(name, name), "bookName": name,
                "code": e26["code"] or e25["code"], "fund": fund,
                "category": _department_category(name, fund),
                "expenses": _merge_items(e25["expenses"], e26["expenses"]),
                "revenues": _merge_items(e25["revenues"], e26["revenues"]),
                "totals": {"fy25": _year_total(a25, "expenses"),
                           "fy26": _year_total(a26, "expenses")},
                "revenueTotals": {"fy25": _year_total(a25, "revenues"),
                                  "fy26": _year_total(a26, "revenues")}}
        orgs = _org_totals(a25, a26)
        if orgs:
            dept["orgs"] = orgs
        departments.append(dept)
    departments.sort(key=lambda d: d["name"])  # display order, so 'Various' sits with Aviation
    x25, x26 = EXPECTED["FY2025"], EXPECTED["FY2026"]
    return {"years": ["FY2025", "FY2026"], "categories": cats, "revenueGroups": revgroups,
        "propertyTax": {"gf": {"fy25": x25["gf_total"] - x25["gf_revenue"],
                               "fy26": x26["gf_total"] - x26["gf_revenue"]},
                        "msd": {"fy25": x25["msd_property_tax"], "fy26": x26["msd_property_tax"]}},
        "msdOther": {"fy25": x25["msd_total"] - x25["msd_property_tax"],
                     "fy26": x26["msd_total"] - x26["msd_property_tax"]},
        "citywide": {"fy25": x25["gf_total"] + x25["msd_total"],
                     "fy26": x26["gf_total"] + x26["msd_total"]},
        "departments": departments}

def render_data_js(data):
    """The committed build artifact: a plain assignment, so the site loads from disk with no
    server and no build step."""
    return ("// GENERATED by extract_budget.py -- do not edit by hand.\n"
            "// Regenerate: python extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf\n"
            "window.BUDGET_DATA = " + json.dumps(data, indent=1) + ";\n")

def _check_book(book, fy):
    """Every anchor for one book, as fy-labelled failure strings (empty when it all agrees)."""
    failures = [f if f.startswith(fy) else f"{fy} {f}" for f in validate_book(book, fy)]
    got = categorize(book)
    for c, exp in EXPECTED_CATEGORIES[fy].items():
        if abs(got.get(c, 0) - exp) > 1:
            failures.append(f"{fy} category {c}: {got.get(c, 0):,} != {exp:,}")
    for c in set(got) - set(EXPECTED_CATEGORIES[fy]):
        failures.append(f"{fy} unexpected category {c}: {got[c]:,}")
    return failures

def _report(books, data, failures):
    print("=== Reconciliation report ===")
    for fy, book in books.items():
        exp, (gf_exp, gf_rev) = EXPECTED[fy], gf_totals(book)
        cats = categorize(book)
        groups = group_revenues(book)
        matched = sum(1 for c, v in EXPECTED_CATEGORIES[fy].items()
                      if abs(cats.get(c, 0) - v) <= 1)
        print(f"{fy}: GF/category/revenue checks",
              "OK" if not any(f.startswith(fy) for f in failures) else "FAILED")
        print(f"  agencies parsed        {len(book['agencies']):>15,}"
              f"   parser warnings {len(book['warnings'])}")
        print(f"  GF expenses (net)      {gf_exp:>15,}   expected {exp['gf_total']:>15,}")
        print(f"  GF revenues            {gf_rev:>15,}   expected {exp['gf_revenue']:>15,}")
        print(f"  property tax to GF     {gf_exp - gf_rev:>15,}"
              f"   expected {exp['gf_total'] - exp['gf_revenue']:>15,}")
        print(f"  categories matched     {matched:>15,} / {len(EXPECTED_CATEGORIES[fy])}"
              f"   summing {sum(cats.values()):,}")
        print(f"  revenue groups         {len(groups):>15,}   summing {sum(groups.values()):,}")
        print(f"  MSD total (constant)   {exp['msd_total']:>15,}"
              f"   of which property tax {exp['msd_property_tax']:,}")
        checked, unchecked = anchor_coverage(book)
        print(f"  printed-total checks   {len(checked):>15,} / {len(checked) + len(unchecked)}"
              f"   agency buckets cross-checked against the book's own subtotal")
        if unchecked:  # not an error: the book simply never states these subtotals
            print(f"    no printed total, so unwitnessed: {', '.join(unchecked)}")
        # Spec: unparseable lines are reported, never dropped silently. Informational -- every
        # one of them today is a section total in a form the parser does not accept as an item,
        # so the money is already counted. An item-shaped one would be a genuine loss.
        dropped = book["dropped_lines"]
        item_shaped = [f"p{p} {ln}" for p, ln in dropped if ITEM_START_RE.match(ln)]
        print(f"  unparsed money lines   {len(dropped):>15,}"
              f"   informational; {len(item_shaped)} item-shaped (a nonzero count loses money)")
        if item_shaped:  # a line that opens with an object code is a line item, not a subtotal
            print(f"    ITEM-SHAPED, so money may be missing: {'; '.join(item_shaped)}")
        for page_no, line in dropped:
            print(f"    p{page_no:<4} {line}")
    gf_depts = [d for d in data["departments"] if d["fund"] == "0101"]
    print(f"departments emitted      {len(data['departments']):>15,}"
          f"   ({len(gf_depts)} general fund, {len(data['departments']) - len(gf_depts)} enterprise)")
    print(f"  expense line items     {sum(len(d['expenses']) for d in data['departments']):>15,}"
          f"   revenue line items {sum(len(d['revenues']) for d in data['departments']):,}")
    for fy, key in (("FY2025", "fy25"), ("FY2026", "fy26")):
        print(f"citywide {fy}          {data['citywide'][key]:>15,}"
              f"   = GF {EXPECTED[fy]['gf_total']:,} + MSD {EXPECTED[fy]['msd_total']:,}")
    for f in failures:
        print("MISMATCH:", f)

def main(argv):
    if len(argv) >= 3 and argv[0] == "--dump":
        print(pypdf.PdfReader(argv[1]).pages[int(argv[2])].extract_text())
        return 0
    if len(argv) < 2:
        print("usage: extract_budget.py Budget_Book_2025.pdf Budget_Book_2026.pdf", file=sys.stderr)
        return 2
    books, failures = {}, []
    for fy, path in (("FY2025", argv[0]), ("FY2026", argv[1])):
        books[fy] = parse_book(path)
        failures += _check_book(books[fy], fy)
    data = build_budget_data(books)
    _report(books, data, failures)
    if failures:
        print(f"FAILED: {len(failures)} check(s) did not reconcile; data.js not written")
        return 1
    with open("data.js", "w", encoding="utf-8", newline="\n") as fh:  # LF, as the rest of the repo
        fh.write(render_data_js(data))
    print("Wrote data.js")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
