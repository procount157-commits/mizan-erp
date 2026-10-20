# -*- coding: utf-8 -*-
{
    "name": "Miqyas Project Accounts",
    "version": "1.3",
    "category": "Accounting/Accounting",
    "summary": "Every project readable from the chart of accounts: its own client, billing, cost, retention and WIP accounts, fed by the entry screens",
    "description": """The CFO's way of keeping contract books (docs/superpowers/specs/
2026-10-18-project-accounts-design.md):

* Starting a contract creates its accounts — client (receivable), billing,
  work in progress, client retention, contract cost — plus its cost centre,
  project and site stock location.
* One rule routes every cost that names the project (supplier bill,
  subcontractor bill, petty cash, expense, direct entry, payroll) to the
  project's work-in-progress account, keeping the cost code.
* Two billing modes: progress claims that state cumulative work, or a
  payment schedule with the percent complete typed in its own window.
  Either way the claim invoice credits the project's billing account and
  debits the project's client account; recognition then moves revenue
  (billing → contract revenue) and cost (WIP → contract cost) for the
  percent reached. IFRS 15.
* Project cards with the figures that matter, a ledger that says where
  each dirham came from, and the printed progress statement.
""",
    "author": "ProAccount",
    "depends": ["mizan_contracting", "mizan_core", "mizan_site", "stock_account", "hr_contract"],
    "data": [
        "security/ir.model.access.csv",
        "views/contract_views.xml",
        "views/ledger_views.xml",
        "views/recognition_views.xml",
        "report/progress_statement.xml",
        "report/project_reports.xml",
        "wizard/wizard_views.xml",
        "views/subcontract_views.xml",
        "views/labour_views.xml",
        "views/stock_issue_views.xml",
        "views/project_grid_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_project_accounts/static/src/projects.scss",
            "mizan_project_accounts/static/src/projects.xml",
            "mizan_project_accounts/static/src/projects.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
