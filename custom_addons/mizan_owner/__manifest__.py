# -*- coding: utf-8 -*-
{
    "name": "Miqyas Owner",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "The owner's phone: how the company is doing today, in plain words, and a ping when money moves",
    "description": """An owner does not read journals. He wants to know whether the company is
making money, how much cash there is, who owes him and what is due — and to be
told when a large amount comes in or goes out.

* One page, made for the phone, in plain sentences: cash now, this month's
  profit against last month, what customers owe and how much of it is late,
  what is due this week, how long the cash lasts, and each project in a colour.
  Every figure opens the detail for whoever wants it.
* Notifications on the Miqyas app: a new sales invoice, a payment received, a
  deposit or a withdrawal above a set amount, a large supplier bill, a bounced
  cheque. A summary every evening and every Sunday.
* An owner account in one step, read-only on the books.
""",
    "author": "ProAccount",
    "depends": ["account", "mail", "mizan_core", "mizan_hub", "mizan_cheque", "mizan_contracting"],
    "data": [
        "security/owner_security.xml",
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/owner_views.xml",
        "wizard/create_owner_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_owner/static/src/scss/owner.scss",
            "mizan_owner/static/src/xml/owner.xml",
            "mizan_owner/static/src/js/owner.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
