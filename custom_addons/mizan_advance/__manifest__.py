# -*- coding: utf-8 -*-
{
    "name": "Miqyas Employee Advances",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Advance to an employee, tracked from request to settlement",
    "description": """An advance to a site engineer is money the company is still owed, and until
now it was an ordinary journal entry with nothing tracking what was left of
it. The consequence is familiar on every site: a second advance is paid while
the first has never been accounted for, and the balance is discovered at the
year end.

This is the whole cycle — request, approval, payment, spending, settlement and
the return of what is left — with the outstanding amount computed from the
expense claims actually posted against it rather than from anyone's note.

It refuses a new advance to an employee who has one outstanding, unless the
person asking holds the override right. That refusal is the point of the
module; the accounting around it is the easy part.
""",
    "depends": ["account", "hr", "hr_expense", "mizan_core", "mizan_hub"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/advance_groups.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/advance_views.xml",
        "views/menus.xml",
    ],
}
