# -*- coding: utf-8 -*-
{
    "name": "Miqyas Petty Cash",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "The engineer's cash in one place: photograph, approve, settle",
    "description": """Petty cash was three modules and five screens: an advance in one place, a
receipt in another, an expense report to build, an approval, a posting, a
settlement. Each step was right, and nobody did all of them, so cash sat on
site with nobody knowing how much.

Here it is one flow and one app:

* The engineer photographs a receipt and says "from my petty cash". It is
  claimed against his advance and submitted in the same tap, and he sees what
  he has left.
* His manager approves a day's receipts together, with the photographs.
* Posting a claim settles the advance by itself and marks the claim paid.
* Everybody who holds company cash is on one list: held, waiting, available.
* Running low, the engineer asks for a top-up from the same screen.
""",
    "author": "ProAccount",
    "depends": ["mizan_advance", "mizan_site", "mizan_hub", "hr_expense"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/pettycash_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
