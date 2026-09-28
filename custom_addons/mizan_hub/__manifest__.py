# -*- coding: utf-8 -*-
{
    "name": "ProAccount Hub — Work Inbox, Project Health, Data Quality",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "One screen answering what is waiting for me, why, and what happens next",
    "description": """The finance manager approved the Work Inbox prototype, so this is the real
thing. Three screens that share one idea: the system should say what needs a
person, not wait to be asked.

  * WORK INBOX — everything waiting on you across eight apps, in one list,
    with the next action on each row. Unlike the prototype it can act: the
    button calls the real document's own method, so every validation the
    document carries still runs.

  * PROJECT HEALTH — one row per contract, with the reasons spelled out
    rather than a score. A manager cannot act on "62%". He can act on
    "estimate at completion is over the contract value".

  * DATA QUALITY — the things that are not wrong today and are how a month
    end goes wrong. Each one opens the records it counted.

The inbox is a transient model rebuilt when opened, not a stored one kept in
step by triggers. A stored inbox must be invalidated from every model it
watches, and the first missed trigger shows a manager a task that was done
yesterday, which is worse than no inbox at all.
""",
    "depends": [
        "mizan_core",
        "mizan_contracting",
        "mizan_cheque",
        "hr_expense",
        "purchase",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/hub_groups.xml",
        "security/ir.model.access.csv",
        "views/inbox_views.xml",
        "views/project_health_views.xml",
        "views/data_quality_views.xml",
        "views/menus.xml",
    ],
}
