{
    "name": "ProAccount Cheques",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Post-dated cheque register with clearing, bouncing and bank entries",
    "description": """
Gulf trade settles on post-dated cheques, which are neither cash nor an ordinary
receivable until they clear. This module tracks each cheque from receipt through
deposit to clearing or bouncing, and posts the journal entries for each step.
""",
    "depends": ["account"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/cheque_views.xml",
        "views/cheque_workflow_views.xml",
    ],
}
