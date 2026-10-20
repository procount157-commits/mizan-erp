# -*- coding: utf-8 -*-
{
    "name": "Miqyas Mobile API",
    "version": "1.3",
    "category": "Productivity",
    "summary": "The data the Miqyas phone app shows, by role: the manager's figures and approvals, the engineer's cash and crew",
    "description": """The native phone app does not open the system's pages; it asks for
compact data and draws it itself, which is what makes it fast. This module
answers it:

* sign in with the company's address, email and password (an ordinary Odoo
  session, so every right and rule applies as on the computer);
* who the person is and which screens are theirs (manager, approver,
  engineer, accountant);
* the manager's summary, projects, reports and alerts;
* the four approvals: petty cash receipts, top-up requests, large supplier
  bills, payments to subcontractors — the last two now wait for the
  manager before money moves;
* the engineer's petty cash, receipts with photos, top-up requests, and the
  day's crew on each project (labour cards).
""",
    "author": "ProAccount",
    "depends": ["mizan_owner", "mizan_pettycash", "mizan_project_accounts", "mizan_mobile", "mizan_ai", "purchase_request"],
    "data": [
        "security/ir.model.access.csv",
        "views/approval_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
