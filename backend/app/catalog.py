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
        "view_summary", "transfer_budget", "plan_year", "manage_years", "manage_limits", "import", "export", "view_log")},
    {"name": "Department editor", "locked": False, "perms": _perms(
        "view_expense", "edit_expense", "edit_lines", "view_summary", "transfer_budget")},
    {"name": "Viewer", "locked": False, "perms": _perms("view_expense", "view_income", "view_summary", "export")},
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
