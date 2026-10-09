# -*- coding: utf-8 -*-
{
    "name": "Miqyas Month-End Close",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "A guided month-end close: every check, the records behind it, and the lock",
    "description": """Closing a month is a checklist somebody keeps in their head, and the month it
is done from memory is the month something is missed. This turns it into a
record: press Run the checks, get a numbered list of what stands in the way,
open each one, fix it, run them again, and close.

The checks are split by what a failure MEANS, which is the part a generic
checklist gets wrong:

  * BLOCKING — the ledger does not balance, an entry does not balance on its
    own, a posted invoice line carries no tax decision, a claim the client
    certified was never invoiced. These are wrong, and closing over them
    closes over an error.

  * WARNING — a cost with no cost centre, a cheque past its date, a guarantee
    about to lapse. None of these are wrong. All of them are how the next
    month goes wrong, and a manager is entitled to close anyway with his eyes
    open.

Closing sets the global lock date, which is the soft lock: an accountant with
the right to move it can still correct the period. It deliberately does not
use the hard lock, which cannot be undone by anybody — a month end is not the
place to make an irreversible decision on a manager's behalf.
""",
    "depends": ["mizan_core", "mizan_contracting", "mizan_cheque", "mizan_hub"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/close_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_closing/static/src/js/commands.js",
        ],
    },
}
