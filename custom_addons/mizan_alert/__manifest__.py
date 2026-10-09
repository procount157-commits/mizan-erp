# -*- coding: utf-8 -*-
{
    "name": "Miqyas Alerts",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Tell somebody before it costs money, instead of reporting it afterwards",
    "description": """Every warning in this system is already written into the code that owns it:
the guarantee knows it is expiring, the contract knows it is over budget. All
of them wait to be looked at, and nobody opens a screen to find out that
nothing is wrong.

So the conditions stay in Python as named evaluators -- they read computed
figures like cost at completion that no stored filter can see -- while the
threshold, the recipients and the on/off switch are data a finance manager
edits without a developer. Seven rules ship switched on with nobody to tell,
which raises nothing until somebody is named.

An alert becomes an activity on the record rather than an email: an email is
read once and lost, an activity stays in that person's to-do list with a link
back to the contract. A condition that stops being true closes its own alert,
and one already raised is not raised again, because an alert that fires every
night is an alert people learn to dismiss.
""",
    "depends": ["mizan_core", "mizan_hub", "mizan_contracting", "mizan_cheque"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/alert_views.xml",
        "data/alert_data.xml",
    ],
}
