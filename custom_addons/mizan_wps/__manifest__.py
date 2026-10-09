{
    "name": "Miqyas WPS",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "summary": "UAE Wage Protection System salary file (SIF) from posted payslips",
    "description": """
Paying wages through the Wage Protection System is mandatory for UAE employers:
a fixed-format SIF file goes to the bank, which pays each employee and reports
the transfer to the Ministry of Human Resources. Building it from confirmed
payslips keeps the file and the ledger in agreement, which is the usual reason
a hand-typed file gets rejected.
""",
    "depends": ["payroll", "hr"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/wps_views.xml",
    ],
}
