{
    "name": "Mizan Core",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Mizan ERP core — accounting foundation and shared extensions",
    "depends": ["base", "account"],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/views.xml",
        "views/templates.xml",
        "report/mizan_invoice_template.xml",
    ],
}
