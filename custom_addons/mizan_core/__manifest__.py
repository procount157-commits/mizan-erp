{
    "name": "Mizan Core",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Mizan ERP core — branded invoicing and quick access to daily accounting",
    "depends": [
        "base", "account", "account_financial_report",
        "sale", "purchase", "hr_expense",
        "purchase_request", "account_asset_management", "account_reconcile_oca",
        "web_responsive", "project", "hr_timesheet", "maintenance",
        "account_budget_oca", "analytic", "mizan_contracting", "mizan_cheque", "payroll", "payroll_account", "hr_contract", "mizan_documents",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "views/views.xml",
        "report/mizan_invoice_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_core/static/src/scss/mizan.scss",
            "mizan_core/static/src/js/quick_create.js",
            "mizan_core/static/src/xml/quick_create.xml",
        ],
    },
}
