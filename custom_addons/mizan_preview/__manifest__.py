{
    "name": "Preview — proposals awaiting a decision (superseded)",
    "version": "0.1",
    "category": "Accounting/Accounting",
    "summary": "The proposed roadmap as one app: what exists, what does not, and a decision recorded against each item",
    "description": """
Thirty proposals, five recommended exclusions, and five working prototypes.

The roadmap arrived as a document. A document cannot be argued with usefully:
it does not say which items already exist, and it cannot be tried. This app
puts the whole list on one screen with an honest status against each row --
already built, partly built, not built -- and where a proposal could be shown
rather than described, it is built here and runs against the live ledger.

Six of the thirty already exist in some form, and one of them ships with Odoo
itself. Those are marked as such. Asking someone to approve building what is
already built is how a roadmap loses its credibility.

Decisions: approved, later or rejected, with a note and the name of whoever
recorded it. The decision survives an upgrade; the descriptions do not, so a
wording can be corrected without touching what was decided.

The prototypes are read-only. Every row links to the real document and the
real buttons; nothing is approved or posted from here. That is what keeps a
prototype from quietly becoming a second way to post entries.

Uninstalling removes the menu, the models and the decisions, and touches
nothing else.
""",
    "depends": [
        "mizan_core", "mizan_contracting", "mizan_cheque", "hr_expense", "mail",
    ],
    # Superseded by mizan_hub and uninstalled from every database on
    # 2026-09-29. Kept in the tree because data/proposals.xml is the roadmap
    # itself — the honest status of all thirty proposals, which is worth
    # reading before planning anything — but marked uninstallable so nobody
    # brings it back and ends up with two Work Inboxes fighting over the same
    # model name, which is exactly how it went the first time.
    "installable": False,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/inbox_views.xml",
        "views/preview_views.xml",
        "data/proposals.xml",
    ],
}
