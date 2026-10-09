# -*- coding: utf-8 -*-
{
    "name": "Miqyas Quick Access",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Every destination that matters, with the one figure that says "
               "whether it needs you today",
    "description": """A launcher, and deliberately more than a shortcut bar.

Shortcuts save two clicks and tell the user nothing. What makes this worth
opening is the figure on the tile: "Bank reconciliation" is a menu item, and
"Bank reconciliation - 8 lines unexplained" is a reason to click. The absence
of a figure is a reason not to, which saves more time than the shortcut does.

Sections: the statements and the chart of accounts; bank and cash; cheques;
projects and sites; the things worth starting in one click; and the month.
Where no honest figure exists - a chart of accounts has no state of readiness
- the tile carries a description instead of an invented metric.

Every tile resolves its destination by external id when the screen is built
and quietly drops itself when that module is not installed, so this app
depends on mizan_core alone. A client without cheques has no cheque tiles,
and gets them the day the module is installed.

Nothing is posted or approved from here. Each tile opens the real screen with
its own views and access rules; only the filter travels with it.
""",
    "depends": ["mizan_core"],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/quick_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_quick/static/src/scss/quick.scss",
        ],
    },
}
