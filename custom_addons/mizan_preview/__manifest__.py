{
    "name": "ProAccount Preview — Work Inbox",
    "version": "0.1",
    "category": "Accounting/Accounting",
    "summary": "A working prototype of the proposed Work Inbox, for review before it is built for real",
    "description": """
A PROTOTYPE, deliberately marked as one.

The proposal was a single screen answering "what is waiting for me?", instead
of opening eight apps to find out. Arguing about that on paper wastes everyone's
time: this builds it against the live ledger so the finance manager can open it
and say yes or no to the thing itself.

It is read-only by design. Every row links to the real document and the real
buttons; nothing is approved or posted from here. That keeps a prototype from
quietly becoming a second way to post entries.

Uninstalling it removes the menu and the model and touches nothing else.
""",
    "depends": [
        "mizan_core", "mizan_contracting", "mizan_cheque", "hr_expense",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/inbox_views.xml",
    ],
}
