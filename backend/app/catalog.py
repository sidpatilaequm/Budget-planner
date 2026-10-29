"""Permission list, default roles and the standard heads from Budget_26-27.xlsx."""

PERMISSION_GROUPS = [
    ("Budget data", [
        ("view_expense", "View expenses"),
        ("edit_expense", "Enter expense amounts"),
        ("view_income", "View income"),
        ("edit_income", "Enter income amounts"),
        ("edit_lines", "Add, rename and delete lines"),
        ("manage_heads", "Add, rename and delete heads"),
        ("view_summary", "View summary"),
        ("transfer_budget", "Transfer budgets between lines"),
    ]),
    ("Planning", [
        ("plan_year", "Plan next year"),
        ("manage_years", "Add and delete years"),
        ("manage_limits", "Set budget limits"),
        ("simulate", "Run budget simulations"),
    ]),
    ("Actuals and Tally", [
        ("view_actuals", "View actuals and budget against actual"),
        ("enter_actuals", "Enter and import actuals"),
        ("manage_integration", "Set up Tally and ledger mapping"),
    ]),
    ("TDS", [
        ("view_tds", "View the TDS report and alerts"),
        ("manage_tds", "Edit TDS rates and parties, record deposits and returns"),
    ]),
    ("Files", [
        ("import", "Import Excel"),
        ("export", "Download Excel"),
    ]),
    ("Administration", [
        ("view_log", "View activity log"),
        ("manage_users", "Manage users and roles"),
    ]),
]
ALL_PERMS = [key for _, items in PERMISSION_GROUPS for key, _ in items]
PERM_LABELS = {key: label for _, items in PERMISSION_GROUPS for key, label in items}


def _perms(*on):
    return {k: k in on for k in ALL_PERMS}


DEFAULT_ROLES = [
    {"name": "Administrator", "locked": True, "perms": _perms(*ALL_PERMS)},
    {"name": "Finance manager", "locked": False, "perms": _perms(
        "view_expense", "edit_expense", "view_income", "edit_income", "edit_lines", "manage_heads",
        "view_summary", "transfer_budget", "plan_year", "manage_years", "manage_limits", "import", "export", "view_log",
        "simulate", "view_actuals", "enter_actuals", "manage_integration", "view_tds", "manage_tds")},
    {"name": "Department editor", "locked": False, "perms": _perms(
        "view_expense", "edit_expense", "edit_lines", "view_summary", "transfer_budget", "view_actuals")},
    {"name": "Viewer", "locked": False, "perms": _perms("view_expense", "view_income", "view_summary", "export", "view_actuals", "view_tds")},
]

EXPENSE_TEMPLATE = [
    ("Consultant Charges", ["Adv. Ashwini Gole", "Parag Erande", "Satish Ghanekar", "Uma Dalvi", "Sutar Sir PF",
                            "Mahesh Mehetre", "Internal Audit", "ASKY & Co (CA Taware)", "Adv. Manoj Wad (J S Wad & Co)"]),
    ("Advertisement and Marketing", ["Social Media (Webbex)", "Star News", "Pinnacle", "Pudhari"]),
    ("Printing & Stationery", ["Canvas Creations", "Books & Periodicals", "School Stationery"]),
    ("Government Taxes", ["PCMC Tax", "NA Tax", "Water Charges (PCMC)"]),
    ("Transport Expenses", ["Maintenance", "Bus GPS Tracker and CCTV Cost", "Diesel Expenses", "Road Tax",
                            "Bus Insurance", "Fitness Passing", "PUC", "Bus Rent"]),
    ("Office Expenses", ["Electricity", "Rent (Old)", "Office Expenses", "CBSE/SSC Expenses",
                         "Telephone and Mobile", "Internet Bill"]),
    ("Repairs & Maintenance", ["Computer Maintenance", "Coffee Machine", "Repairs & Maintenance - Others", "Lift"]),
    ("New Purchase", ["Sports Equipments", "Furniture & Fixture", "Solar Panels (NPPS)", "Solar Panels (Vita)",
                      "NPPS Shed", "Air Conditioner", "Fire System", "Solar Panels (Pune)", "Buses"]),
    ("Building and Landscape Maintenance", ["Lawn Maint. Charges", "Building Maintenance", "Construction (Vita SAS)",
                                           "Basket Ball Court", "Wall Paint", "Building Paint"]),
    ("Bank Loan", ["Mahindra Finance New Buses (Principal)", "Mahindra Finance New Buses (Interest)",
                   "HDB Finance New Buses (Principal)", "HDB Finance New Buses (Interest)",
                   "HDB Finance Old Buses (Principal)", "HDB Finance Old Buses (Interest)",
                   "HDFC Retail Assets Vita 11Cr (Principal)", "HDFC Retail Assets Vita 11Cr (Interest)",
                   "Citron Federal (Principal)", "Citron Federal (Interest)",
                   "HDFC Retail Assets Vita 6Cr (Principal)", "HDFC Retail Assets Vita 6Cr (Interest)",
                   "Estimated Loan", "RD Account"]),
    ("Software Expenses", ["ERP NPPS", "ERP Jr. College", "ERP Vita", "Tata Class Edge (Vita and Pune)",
                           "Simply Admission (School Ascent)", "Servetel Infocomm Pvt Ltd (IVR)"]),
    ("Security and Housekeeping", ["Grow India"]),
    ("Salary", ["NPPS", "Society", "DDYPPS - Salary"]),
    ("Miscellaneous", ["Student Welfare", "Refreshment Exps.", "Staff Uniform", "Laboratory",
                       "Festival Expenses", "Group Insurance"]),
    ("Undri School Expenses", ["Undri School (Rent)", "Undri School (Stamp Duty)",
                               "Security Deposit (Undri School)", "Salary"]),
]
INCOME_TEMPLATE = [
    ("NPPS – Tuition Fees", ["Pre-Primary", "Grade I to X Regular", "Grade I to VIII RTE", "XI and XII"]),
    ("NPPS – Admission Fees", ["Registration Fees", "Admission Fees", "Administrative Fees"]),
    ("NPPS – Transport", ["Transport"]),
    ("DYPPS – Tuition Fees", ["Nursery", "L.K.G", "U.K.G", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th",
                              "8th", "9th", "10th"]),
    ("DYPPS – Admission Fees", ["Pre-Primary", "Grade I to X Regular"]),
    ("DYPPS – Transport", ["Transport"]),
]

# Permissions added in version 2. Existing roles get these defaults once, by name, only for keys they do not have yet.
NEW_PERM_DEFAULTS = {
    "Finance manager": ["simulate", "view_actuals", "enter_actuals", "manage_integration", "view_tds", "manage_tds"],
    "Department editor": ["view_actuals"],
    "Viewer": ["view_actuals", "view_tds"],
}
V2_PERMS = ["simulate", "view_actuals", "enter_actuals", "manage_integration", "view_tds", "manage_tds"]

# TDS categories under the Income-tax Act, 2025 (section 393, in force from 1 April 2026), with the
# matching 1961 Act section. Rates and thresholds as published for tax year 2026-27; check them with
# your CA and edit them in the app when the law changes.
TDS_DEFAULTS = [
    # code, label, new ref, old ref, rate ind %, rate other %, single limit, annual limit, monthly limit
    ("CONTRACT", "Payments to contractors (work, including supply of labour)", "393(1) Table Sl. 6(i)", "194C", 1, 2, 30000, 100000, None),
    ("PROF", "Fees for professional services", "393(1) Table Sl. 6(iii)", "194J", 10, 10, None, 50000, None),
    ("TECH", "Fees for technical services", "393(1) Table Sl. 6(iii)", "194J", 2, 2, None, 50000, None),
    ("RENT_LB", "Rent of land, building or furniture", "393(1) Table Sl. 2(ii)", "194I(b)", 10, 10, None, None, 50000),
    ("RENT_PM", "Rent of plant, machinery or equipment", "393(1) Table Sl. 2(ii)", "194I(a)", 2, 2, None, None, 50000),
    ("COMM", "Commission or brokerage", "393(1) Table Sl. 1(ii)", "194H", 2, 2, None, 20000, None),
    ("INT", "Interest other than on securities (e.g. to an NBFC)", "393(1) Table Sl. 5(iii)", "194A", 10, 10, None, 10000, None),
    ("GOODS", "Purchase of goods (buyer with turnover above ₹10 crore)", "393(1) Table Sl. 8(ii)", "194Q", 0.1, 0.1, None, 5000000, None),
]
NO_PAN_RATE = 20  # higher rate when the payee has not given a PAN
