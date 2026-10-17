# -*- coding: utf-8 -*-
{
    "name": "Miqyas Test Data Reset",
    "version": "1.0",
    "category": "Hidden",
    "summary": "A screen for the administrator to clear demonstration data, after a backup",
    "description": """
Settings → Technical → Clean test data, for the administrator only. The
administrator types the company's name to confirm; a full backup (database
and files) is written first and nothing is deleted if it fails. Then the
documents and test records go and the set-up stays: chart of accounts, taxes,
journals, cost codes, workflow templates, alert rules, payroll rules,
departments, financial reports.
""",
    "author": "ProAccount",
    "depends": ["mizan_core", "mizan_contracting", "mizan_hub", "mizan_ops", "mizan_owner"],
    "data": [
        "security/ir.model.access.csv",
        "views/reset_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
