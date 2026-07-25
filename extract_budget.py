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
