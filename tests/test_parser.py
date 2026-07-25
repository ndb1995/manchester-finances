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


# FY2026 p15 (revenue, parenthesized negatives)
CITY_CLERK_NEGATIVES = """Object Description Budget
4013 Cable TV Fee 1,300,000      
4209 Certified Record 335,000         
4210 State Share Certified Record (160,000)        
4211 Vending Machine Commissions 20                  
4212 Copying Receipts 2,500             
4216 Bounced Check Fee 30                  
4217 Late Fee on Licenses & Permits 11,500           
4218 UCC Financing Statement Fee 23,000           
4219 Legal Petitions 300                
4223 Noise Permits 400                
4495 Political Filing Fee 2,600             
4697 Animal Population Control Fee (22,000)          
4698 Forfeiture Dog License 20,000           
4699 Food Service Establishments 85,000           
4700 Spayed/Neutered Dog 95,000           
4702 State Share Dog License (6,000)            
4703 Arcade Application Fee 18,000           
4709 Mech Devices - Each Additional 150,000         
4714 Employment Office License Fee 1,800             
4717 Banner Permits 9,000             
4721 Sidewalk Encumbrance 5,500             
4725 Taxi License - Application Fee 1,500             
4734 Second Hand Lic - Secondhand Dealer 26,000           
4736 Peddlers Lic - App Fee for Annl Lic 15,500           
4741 Marriage Ceremonies 235,000         
4743 Marriage License 75,000           
4744 State Share Marriage License (55,000)          
4746 Towing License 640                
4747 Annual Scrap/Junk Dealer Trans. Fee 7,000             
4748 High Impact Retail 15,500           
4999 Miscellaneous Reimbursement 14,000           
City Clerk's Office Total: 2,206,790$    
Fund:  0101  General Fund
Agency:  040  City Clerk's Office
FY 2026 Revenue Budget
10"""

# FY2026 p36 first section (leading zero stripped from some object codes)
PARKS_ADMIN_3DIGIT = """Object Description Budget
0110 Regular Salary 2,723,207      
120 Temporary Salary 460,000         
130 Overtime Salary 336,867         
0271 Staff Development 2,000             
0390 Other Services 10,000           
0445 Contracts 140,500         
0460 Safety 4,000             
0539 Marketing 2,000             
0540 Advertising 500                
0580 Travel, Conferences & Meetings 4,000             
0615 Gas, Oil & Diesel Fuel 92,265           
0651 Natural Gas 138,599         
0740 Equipment 30,000           
0810 Dues, Fees, & Licenses 4,900             
0865 Medical Supplies 1,000             
0890 Miscellaneous 1,000             
0898 Special Projects 4,585             
Parks-Administration Total: 3,955,423      """

# FY2026 p86 (amounts printed with cents)
AVIATION_DECIMALS = """Object Description Budget
0110 Regular Salary 1,647,359        
0130 Overtime Salary 230,000           
0211 Health Insurance 352,121.00      
0212 Dental Insurance 21,127.00        
0213 Life Insurance 2,000.00          
0214 Worker's Compensation 28,170             
0219 Disability Insurance 1,000.00          
0228 City Contributory System 652,863.00      
0230 FICA 143,618.00      
0271 Staff Development 10,000             
0298 Uniform Allowance 10,500             
0390 Other Services 50,900             
0419 Service Agreements 143,600           
0431 Hazardous Waste Removal 3,000               
0436 Towing Services 5,000               
0439 Maintenance & Repairs/Real Property 120,000           
0441 Maintenance & Repair/ Mach/Equip 35,000             
0442 Vehicle Repairs/Parts 200,000           
0445 Contracts 17,500             
0448 Contracted Airport Rescue & Fire 1,784,125        
0451 Rental Machinery & Equipment 21,000             
0460 Safety 15,000             
0532 Postage 100                  
0533 Radio 65,000             
0580 Travel, Conferences & Meetings 4,500               
0610 General Supplies 2,000               
0615 Gas, Oil & Diesel Fuel 110,000           
0616 Tires & Batteries 60,000             
0617 Minor Apparatus & Tools 20,000             
0619 Fire Extinguishers 8,000               
0622 Tool Allowance 11,000             
0651 Natural Gas 85,000             
0652 Electricity 199,013           
0657 Sewer & Water 9,000               
0670 Freight 7,000               
0684 Chemicals & Chlorine 350,000           
0685 Lawn & Tree Supplies 4,000               
0689 Special Treated Airfield Sand 80,000             
0740 Equipment 5,000               
0810 Dues, Fees, & Licenses 3,230               
0865 Medical Supplies 9,500               
0891 Supplies 1,500               
0898 Special Projects 16,500             
0906 Street Lighting 90,000             
Aviation-Runway/Airfield Maintenance Total:          6,634,226 
Fund:  0805 Aviation
Agency:  250  Aviation
FY 2026 Expense Budget by Organization
Organization: 2501 Aviation-Runway/Airfield Maintenance
81"""

# FY2025 p25 tail (page roll-up printed as 'Total <label>:')
INFO_SYSTEMS_ROLLUP = """Object Description Budget
0110 Regular Salary 756,732         
0419 Service Agreements 305,541         
0441 Maintenance & Repair/ Mach/Equip 17,962           
0610 General Supplies 1,000             
Information Systems-Communication Total: 1,081,235      
Total Information Systems: 2,223,386$    
Organization: 1302 Information Systems-Operations
Organization: 1303 Information Systems-Communication
Fund:  0101  General Fund
Agency:  130  Information Systems
FY 2025 Expense Budget by Organization
Organization: 1300 Information Systems-Admin
20"""

# FY2025 p32 (text layer splits '0740 Equipment' mid-word)
PW_WRAPPED_ITEM = """Object Description Budget
0110 Regular Salary 13,399,961    
0120 Temporary Salary 460,000         
0130 Overtime Salary 1,484,305      
0271 Staff Development 10,000           
0298 Uniform Allowance 3,750             
0390 Other Services 46,000           
0419 Service Agreements 339,000         
0434 Laundry Services 1,500             
0441 Maintenance & Repair/Mach/Equip 105,500         
0442 Vehicle Repairs/Parts 3,000             
0445 Contracts 7,681,019      
0451 Rental Machinery & Equipment 46,500           
0452 Leases - All 4,000             
0460 Safety 44,000           
0531 Telephone 45,250           
0532 Postage 2,200             
0539 Marketing 2,000             
0540 Advertising 4,200             
0550 Printing, Publishing, Binding 6,000             
0580 Travel, Conferences & Meetings 12,500           
0591 Contract Manpower 5,516,953      
0608 Irrigation Supplies 20,000           
0610 General Supplies 22,220           
0615 Gas, Oil & Diesel Fuel 691,861         
0616 Tires & Batteries 5,000             
0617 Minor Apparatus & tools 37,000           
0618 Custodial Supplies 17,000           
0619 Fire Extinguishers 2,000             
0640 Periodicals 400                
0651 Natural Gas 209,159         
0652 Electricity 620,982         
0653 Fuel Oil 25,000           
0681 Salt 1,160,467      
0682 Construction Material 1,232,000      
0684 Chemicals & Chlorine 25,000           
0685 Lawn & Tree Supplies 95,000           
0688 Recreational Supplies 24,600           
0740 Equi
pment 136,300         
0750 Furniture & Fixtures 4,000             
0801 Toter Project 5,000             
0810 Dues, Fees, & Licenses 18,500           
0865 Medical Supplies 4,500             
0890 Miscellaneous 3,000             
0897 Public Entertainment 32,000           
0898 Special Project 218,195         
Public Works Department Total: 33,826,822$  
Fund:  0101  General Fund
Agency:  Public Works
FY 2025 Expense Budget
27"""

def test_parse_amount_negatives_and_cents():
    assert eb.parse_amount("(160,000)") == -160000
    assert eb.parse_amount("(30)") == -30
    assert eb.parse_amount("352,121.00") == 352121
    assert eb.parse_amount("2,000.00") == 2000
    assert eb.parse_amount("(1,172,729.00)") == -1172729
    assert eb.parse_amount("352,121.49") == 352121
    assert eb.parse_amount("352,120.51") == 352121

def test_parenthesized_amounts_parse_as_negative_items():
    secs = eb.parse_sections(CITY_CLERK_NEGATIVES)
    items = secs[0]["items"]
    assert ("4210", "State Share Certified Record", -160000) in items
    assert ("4697", "Animal Population Control Fee", -22000) in items
    assert ("4702", "State Share Dog License", -6000) in items
    assert ("4744", "State Share Marriage License", -55000) in items
    # negatives are what makes the printed total reconcile
    assert secs[0]["total"] == 2206790
    assert sum(a for _, _, a in items) == 2206790

def test_three_digit_object_codes_are_zero_padded():
    secs = eb.parse_sections(PARKS_ADMIN_3DIGIT)
    items = secs[0]["items"]
    assert ("0120", "Temporary Salary", 460000) in items
    assert ("0130", "Overtime Salary", 336867) in items
    assert all(len(code) == 4 for code, _, _ in items)
    assert secs[0]["total"] == 3955423
    assert sum(a for _, _, a in items) == 3955423

def test_decimal_amounts_round_to_whole_dollars():
    secs = eb.parse_sections(AVIATION_DECIMALS)
    items = secs[0]["items"]
    assert ("0211", "Health Insurance", 352121) in items
    assert ("0213", "Life Insurance", 2000) in items
    assert ("0228", "City Contributory System", 652863) in items
    assert secs[0]["total"] == 6634226
    assert sum(a for _, _, a in items) == 6634226

def test_total_prefix_form_yields_label():
    secs = eb.parse_sections(INFO_SYSTEMS_ROLLUP)
    assert secs[0]["total_label"] == "Information Systems-Communication"
    assert secs[0]["total"] == 1081235
    # page roll-up "Total Information Systems: 2,223,386$" -> label without items
    assert secs[-1]["total_label"] == "Information Systems"
    assert secs[-1]["total"] == 2223386
    assert secs[-1]["items"] == []

def test_mid_word_wrapped_item_is_rejoined():
    secs = eb.parse_sections(PW_WRAPPED_ITEM)
    items = secs[0]["items"]
    assert ("0740", "Equipment", 136300) in items
    assert not any(desc == "Equi" for _, desc, _ in items)
    assert secs[0]["total"] == 33826822
    assert sum(a for _, _, a in items) == 33826822


# FY2025 p97 tail (dash instead of an amount; must not absorb the total line)
PARKING_DASH_AMOUNT = """Object Description Budget
4216 Bounced Check Fee 150                
4367 Parking Pay Stations-CR CD Collect 683,000         
4368 Parking Meters 13,000           
4370 Pay BY Phone 450,000         
4496 Booting Fine 20,000           
4646 Parking Permits 1,818,779      
4650 Card Lease 390,000         
4651 Daily Revenue 120,000         
4652 Meter Hood 35,000           
4653 Pay & Display 230,020         
4681 Auto Registration Parking 235,000         
4770 Income from Invested Funds 1,500             
4771 Interest on Accounts Receivable 1,000             
4866 Parking Fine Court 2,500             
4896 Expired Meters 1,068,800      
4898 Refund on Parking Ticket -                     
Parking Enterprise Total: 5,068,749$    
Fund:  0809  Parking Enterprise
Agency:  540  Parking
FY 2025 Revenue Budget
94"""

# FY2025 p87 (text layer emits ';0460 Safety 1,080')
AVIATION_STRAY_SEMICOLON = """Object Description Budget
0110 Regular Salary 990,278           
0130 Overtime Salary 100,000           
0211 Health Insurance 172,570           
0212 Dental Insurance 8,354               
0213 Life Insurance 250                  
0219 Disability Insurance 1,000               
0228 City Contributory System 282,986           
0230 FICA 60,456             
0270 Tuition Reimbursement 1,500               
0271 Staff Development 450                  
0298 Uniform Allowance 7,000               
0419 Service Agreements 1,107,800        
0431 Hazardous Waste Removal 2,000               
0433 Custodial Services 1,404,500        
0439 Maintenance & Repairs/Real Property 90,000             
0441 Maintenance & Repair/Mach/Equip 4,500               
0442 Vehicle Repairs/Parts 4,500               
0445 Contracts 85,000             
0451 Rental Machinery & Equipment 3,000               
;0460 Safety 1,080               
0533 Radio 1,500               
0580 Travel, Conferences & Meetings 3,000               
0592 Duplicating Services 1,000               
0610 General Supplies 1,000               
0615 Gas, Oil & Diesel Fuel 5,000               
0617 Minor Apparatus & Tools 2,000               
0618 Custodial Supplies 250,000           
0619 Fire Extinguishers 3,000               
0622 Tool Allowance 5,000               
0651 Natural Gas 420,000           
0652 Electricity 1,323,626        
0657 Sewer & Water 67,000             
0670 Freight 4,000               
0682 Construction Material 10,000             
0750 Furniture & Fixtures 5,000               
0810 Dues, Fees, & Licenses 1,635               
0891 Supplies 48,000             
Aviation-Terminal Building & Land Total: 6,477,985        
Organization: 2502 Aviation-Terminal Building & Land
Fund:  0805 Aviation
Agency:  250  Aviation
FY 2025 Expense Budget by Organization
83"""

def test_dash_amount_line_is_skipped_without_eating_the_total():
    secs = eb.parse_sections(PARKING_DASH_AMOUNT)
    assert secs[0]["total_label"] == "Parking Enterprise"
    assert secs[0]["total"] == 5068749
    assert not any("Total" in desc for _, desc, _ in secs[0]["items"])
    assert sum(a for _, _, a in secs[0]["items"]) == 5068749

def test_stray_leading_punctuation_before_object_code():
    secs = eb.parse_sections(AVIATION_STRAY_SEMICOLON)
    items = secs[0]["items"]
    assert ("0460", "Safety", 1080) in items
    assert secs[0]["total"] == 6477985
    assert sum(a for _, _, a in items) == 6477985

# SYNTHETIC (no real page triggers this): two independently broken item-start lines in a
# row -- the first lost its amount, the second lost its description. Concatenating them
# happens to satisfy ITEM_RE, so the rejoin pass must refuse to weld two item starts
# together and fabricate one item under 0740 that swallows 0741's amount.
SYNTHETIC_ADJACENT_ITEM_STARTS = """Object Description Budget
0740 Equipment
0741 5,000
Synthetic Section Total: 5,000"""

def test_rejoin_does_not_merge_adjacent_item_start_lines():
    secs = eb.parse_sections(SYNTHETIC_ADJACENT_ITEM_STARTS)
    items = secs[0]["items"]
    assert items == []
    assert not any(code == "0740" for code, _, _ in items)
    assert secs[0]["total_label"] == "Synthetic Section"
    assert secs[0]["total"] == 5000
