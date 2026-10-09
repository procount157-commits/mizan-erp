{
    "name": "Miqyas Contracting",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Percentage-of-completion revenue recognition and retention for contractors",
    "description": """
Long-term construction contracts cannot recognise revenue when the invoice is
raised: IFRS 15 requires it to follow progress. This module measures progress by
cost incurred against budget, posts the resulting revenue and WIP entries, and
tracks the retention withheld on each progress claim.
""",
    "depends": ["account", "project", "analytic", "sale", "payroll"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/contract_views.xml",
        "views/retention_views.xml",
        "views/forecast_views.xml",
        "views/variation_views.xml",
        "views/overhead_views.xml",
        "data/overhead_cron.xml",
        "views/cost_code_views.xml",
        "views/advance_bond_views.xml",
        "views/subcontract_views.xml",
        "views/plant_views.xml",
        "views/boq_claim_views.xml",
        "views/complete_all_views.xml",
    ],
}
