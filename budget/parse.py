"""Parse a Manchester NH budget book PDF into agencies. No OCR: pypdf text layer only."""
import re

import pypdf

from .model import EXPENSE, KINDS, UNATTRIBUTED, Agency, Book, ItemKey, agrees

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

# Agencies whose grand total the book prints under a label that is not the agency's own name,
# so the strict name match never pairs the two and the bucket goes unchecked. Listed one by
# one on purpose: loosening `_same_entity` to reach them would also pair labels that merely
# resemble each other, which is how a wrong total gets accepted as a right one.
PRINTED_TOTAL_ALIAS = {
    "Planning & Community Development": "Planning Department",  # 'Planning Department Total:'
    # airport revenue: the books file it under the agency name 'Various' but foot the page
    # 'Aviation Total:'
    "Various": "Aviation",
    # the roll-up 'Non-Departmental Items Total:' names the agency exactly, but it sits in a
    # section that carries items on a 'by Organization' page, so the guard skips it
    "Non-Departmental Items": "Non-Departmental Items",
}


# ---- lines and pages --------------------------------------------------------------------

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


def _new_section():
    return {"items": [], "total_label": None, "total": None}


def parse_sections(text, dropped=None):
    """Sections on one page. `dropped`, when given, collects every skipped line carrying money.

    Nothing is dropped silently: the caller passes a list and the reconciliation report prints
    what landed in it. Today every such line is a section total in a form the parser
    deliberately does not accept (a colon-only 'Aviation-Marketing: 1,805,580', or an orphan
    amount left behind by the text layer), so no line item is lost -- but that is a fact about
    these two books, not a guarantee about the next one.
    """
    sections, cur = [], _new_section()
    lines = [JUNK_PREFIX_RE.sub("", ln) for ln in (raw.strip() for raw in text.splitlines()) if ln]
    for line in _rejoin_wrapped(lines):
        if line == HEADER:
            if cur["items"]:
                sections.append(cur)
            cur = _new_section()
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
            cur = _new_section()
            continue
        # anything else: footers, page numbers, orphan amounts, wrapped labels -> skip,
        # but report it when it carries an amount
        if dropped is not None and MONEY_LINE_RE.search(line):
            dropped.append(line)
    if cur["items"]:
        sections.append(cur)
    return sections


# ---- names ------------------------------------------------------------------------------

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


def _agency_names(metas):
    """(fund, normalized any-name) -> canonical agency name.

    The same agency is named inconsistently across pages ('Highway Division' /
    'Highway Department', 'Health Department - City' / 'Health Department'); its code is
    stable, so the first name seen for a (fund, code) becomes canonical.
    """
    canon = {}
    for m in metas:
        if m and m["agency_code"] and m["agency_name"]:
            canon.setdefault((m["fund_code"], m["agency_code"]), m["agency_name"])
    known = {}
    for m in metas:
        if m and m["agency_name"]:
            name = canon.get((m["fund_code"], m["agency_code"]), m["agency_name"])
            known[(m["fund_code"], _norm(m["agency_name"]))] = name
            known[(m["fund_code"], _norm(name))] = name
    return known


def _resolve_agency(meta, depts, known):
    """(name, parent) for one page: the agency it names and, for a sub-agency page stamped
    with its parent department's name, that parent. `name` is None when the page names none."""
    fund = meta["fund_code"]
    name = known.get((fund, _norm(meta["agency_name"]))) if meta["agency_name"] else None
    if not name:  # no 'Agency:' line at all (Non-Departmental Items)
        name = next((known.get((fund, _norm(d)), d) for d in depts), None)
        if not name:
            return None, None
    parent = next((known[(fund, _norm(d))] for d in depts
                   if (fund, _norm(d)) in known and known[(fund, _norm(d))] != name), None)
    return name, parent


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


# ---- the book ---------------------------------------------------------------------------

def read_pages(pdf_path):
    """The text layer of every page, in order."""
    return [(page.extract_text() or "") for page in pypdf.PdfReader(pdf_path).pages]


def parse_book(pdf_path):
    return parse_pages(read_pages(pdf_path))


def parse_pages(texts):
    """Aggregate one budget book's pages into agencies, counting every dollar exactly once.

    The book prints each department three ways: an agency-level page, 'by Organization'
    detail pages, and -- for departments with sub-agencies -- sub-agency pages stamped with
    the parent department's name. The detail restates the agency page, so only the
    agency-level page feeds `expenses`/`revenues`; everything else feeds `org_expenses`.
    Departments printed only as detail (Non-Departmental Items) fall back to that detail.
    """
    metas = [classify_page(t) for t in texts]
    known = _agency_names(metas)
    book, detail = Book(), {}
    for page_no, (text, meta) in enumerate(zip(texts, metas), 1):
        if meta:  # otherwise a summary/TOC/cover page
            _add_page(book, detail, known, page_no, text, meta)
    _fill_from_detail(book.agencies, detail)
    book.printed.update(_alias_anchors(book.agencies, book.printed))
    book.warnings += _total_warnings(book.agencies, book.printed)
    return book


def _add_page(book, detail, known, page_no, text, meta):
    """Fold one classified page into the book: its items, organizations and printed totals."""
    fund, kind = meta["fund_code"], meta["kind"]
    name, parent = _resolve_agency(meta, _dept_lines(text), known)
    if not name:
        book.warnings.append(f"page with fund {fund} has no agency or department name")
        return
    key = parent or name
    agency = book.agencies.setdefault(key, Agency(name=key, fund_code=fund))
    if agency.fund_code != fund:
        book.warnings.append(f"agency {key!r} appears in funds {agency.fund_code} and {fund}")
    if parent is None and meta["agency_code"] and not agency.code:
        agency.code = meta["agency_code"]

    page_dropped = []
    sections = parse_sections(text, page_dropped)
    book.dropped_lines += [(page_no, ln) for ln in page_dropped]
    # A page restating the agency total (its own 'by Organization' detail, or any page
    # belonging to a parent department) must not be added to the agency bucket again.
    is_detail = bool(parent) or meta["by_org"]
    _record_printed_totals(book, agency, kind, sections, is_detail)

    sections = [s for s in sections if s["items"]]  # drop grand-total-only pseudo sections
    bucket = detail.setdefault((key, kind), {}) if is_detail else agency.bucket(kind)
    orgs = _page_orgs(sections, meta, name if parent else None)
    for sec, org in zip(sections, orgs):
        for code, desc, amt in sec["items"]:
            k = ItemKey(code, desc)
            bucket[k] = bucket.get(k, 0) + amt
            if org and kind == EXPENSE:
                items = agency.org_expenses.setdefault(org, {})
                items[k] = items.get(k, 0) + amt


def _record_printed_totals(book, agency, kind, sections, is_detail):
    """Keep every printed total for diagnostics, and the agency's own as its anchor."""
    for sec in sections:  # roll-ups included
        if sec["total"] is None or not sec["total_label"]:
            continue
        # keyed by kind too: an agency's expense and revenue totals share one label
        agency.printed_totals[(kind, sec["total_label"])] = sec["total"]
        # the department's own total: printed on its agency-level pages, and repeated as
        # an item-less roll-up at the end of its detail. Organization totals sit on
        # detail pages and carry items, so they cannot be mistaken for it.
        if (not is_detail or not sec["items"]) and _same_entity(sec["total_label"], agency.name):
            pk = (agency.name, kind)
            book.printed[pk] = max(book.printed.get(pk, 0), sec["total"])


def _fill_from_detail(agencies, detail):
    """Use organization detail where the agency-level pages leave a bucket short.

    A department printed only as detail takes that detail wholesale. Otherwise, FY2026
    Aviation itemizes objects 0740 'Equipment' and 0745 'Computer Software Services' on its
    organization pages only -- they are absent from the agency pages' text layer -- leaving
    the bucket 370,448 short of the total the book prints. An item whose object code AND
    description are both new to the bucket cannot be a restatement, so take it from the
    detail. The description half of that test matters: the book files the same line under
    different codes in its two views (Aviation 'Special Salary' is 0142 by agency but 0140 by
    organization, EPD FY2025 'Severance Pay' is 0142 by agency but 0141 by organization), and
    those must not be added twice.
    """
    for (key, kind), items in detail.items():
        bucket = agencies[key].bucket(kind)
        if not bucket:
            bucket.update(items)
            continue
        codes = {code for code, _ in bucket}
        descs = {desc for _, desc in bucket}
        for (code, desc), amt in items.items():
            if code not in codes and desc not in descs:
                bucket[ItemKey(code, desc)] = amt


def _alias_anchors(agencies, printed):
    """Printed grand totals the name match cannot reach, keyed the way `printed` is.

    Only fills gaps: an agency the name match already anchored keeps that anchor.
    """
    out = {}
    for key, label in PRINTED_TOTAL_ALIAS.items():
        agency = agencies.get(key)
        if not agency:
            continue
        for kind in KINDS:
            if (key, kind) not in printed and (kind, label) in agency.printed_totals:
                out[(key, kind)] = agency.printed_totals[(kind, label)]
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
        got = sum(agencies[key].bucket(kind).values())
        if not agrees(got, total):
            out.append(f"{key} {kind} total {got:,} != printed {total:,}")
    return out


def anchor_coverage(book):
    """(checked, unchecked) bucket names, so the report can say what the check really covers.

    A bucket with no printed total is not wrong, it is just unwitnessed: nothing in the book
    states its subtotal, so only the general fund anchors constrain it -- and for an
    enterprise fund, nothing does.
    """
    checked, unchecked = [], []
    for key, agency in sorted(book.agencies.items()):
        for kind in KINDS:
            if not agency.bucket(kind):
                continue  # a side of the ledger the department does not have
            (checked if (key, kind) in book.printed else unchecked).append(f"{key} {kind}")
    return checked, unchecked
