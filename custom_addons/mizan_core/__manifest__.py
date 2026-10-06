{
    "name": "Mizan Core",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Mizan ERP core — branded invoicing and quick access to daily accounting",
    "depends": [
        "base", "account", "account_financial_report",
        # Balance sheet and profit & loss; Community ships neither.
        "mis_builder",
        # sale_management, not just sale: the Sales app menu ships inactive in
        # `sale`, so a client built from `sale` alone has quotations in the
        # database and no way to reach them.
        "sale", "sale_management", "purchase", "hr_expense",
        "purchase_request", "account_asset_management", "account_reconcile_oca",
        "account_statement_import_file_reconcile_oca",
        "web_responsive", "project", "hr_timesheet", "maintenance",
        "account_budget_oca", "analytic", "mizan_contracting", "mizan_cheque", "payroll", "payroll_account", "hr_contract", "mizan_documents", "mizan_wps", "contract",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "views/banking.xml",
        "views/reporting.xml",
        "views/views.xml",
        "report/mizan_invoice_template.xml",
        # Last: it refers to the Platform menu that views.xml creates.
        "data/repair_icons.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_core/static/src/scss/mizan.scss",
            "mizan_core/static/src/js/quick_create.js",
            "mizan_core/static/src/xml/quick_create.xml",
        ],
    },
}
