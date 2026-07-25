"""Extract Manchester NH budget book PDFs into data.js. No OCR: pypdf text layer only."""
import re, sys

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
