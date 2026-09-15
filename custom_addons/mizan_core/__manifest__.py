{
    "name": "Mizan Core",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Mizan ERP core — branded invoicing and quick access to daily accounting",
    "depends": ["base", "account", "account_financial_report"],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "views/views.xml",
        "report/mizan_invoice_template.xml",
    ],
}
