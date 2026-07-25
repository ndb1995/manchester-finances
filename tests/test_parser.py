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
