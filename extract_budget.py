"""Extract Manchester NH budget book PDFs into data.js. No OCR: pypdf text layer only."""
import re, sys

import pypdf

from category_map import (AGENCY_CATEGORY, EXPECTED, NONDEPT_OBJECT_CATEGORY, PW_ORG_CATEGORY,
                          TRANSIT_OBJECT, UNATTRIBUTED, revenue_group)

AMOUNT = r"[\d][\d,\s]*(?:\.\d+)?"
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

def parse_sections(text):
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
        # anything else: footers, page numbers, orphan amounts, wrapped labels -> skip
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

    agencies, detail, printed, warnings = {}, {}, {}, []
    for text, meta in zip(texts, metas):
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
        sections = parse_sections(text)
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
    warnings += _total_warnings(agencies, printed)
    return {"agencies": agencies, "warnings": warnings}

def _total_warnings(agencies, printed):
    """Non-fatal check that each bucket matches the total the book prints for its agency.

    Diagnostic only: the printed totals are never treated as anchors, they just have to
    agree with what was aggregated. This is what would have caught the FY2026 Aviation gap.
    """
    out = []
    for (key, kind), total in sorted(printed.items()):
        bucket = agencies[key]["expenses"] if kind == "expense" else agencies[key]["revenues"]
        if bucket and abs(sum(bucket.values()) - total) > 1:
            out.append(f"{key} {kind} total {sum(bucket.values()):,} != printed {total:,}")
    return out

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

def validate_book(book, fy_label):
    errors, exp = list(book.get("warnings", ())), EXPECTED[fy_label]
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

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--dump":
        print(pypdf.PdfReader(sys.argv[2]).pages[int(sys.argv[3])].extract_text())
        sys.exit(0)
