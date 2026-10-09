# -*- coding: utf-8 -*-
{
    "name": "Miqyas Site",
    "version": "1.0",
    "category": "Project",
    "summary": "The engineer's screen: his jobs, the daily report, and the four things he raises",
    "description": """An engineer given a login today gets the whole back office on a phone
screen. He does not need an ERP; he needs five things, and he needs them in
one hand while standing on a slab.

So this is a curated app rather than new machinery. Where Odoo already has the
right model it is reached through a narrow, mobile-first menu — expenses,
timesheets, purchase requests, site issues as project tasks — and only the one
thing genuinely missing is built: the daily site report.

THE DAILY REPORT is what a contractor's day actually produces, and until now it
lived in a WhatsApp group. Manpower by trade, plant on site, what was built,
what stopped, and photographs, against a project and a date. It is what a delay
claim is later argued from, which is why it records the weather and the reason
work stopped: a claim for an extension that cannot say which days were lost and
why is not a claim.

Nothing here posts to the ledger. An engineer raises; somebody else approves.
That separation is the reason a site engineer can be given a login at all.
""",
    "depends": [
        "project", "hr", "hr_timesheet", "hr_expense", "purchase_request", "account",
        "mizan_contracting", "mizan_hub", "mail",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "security/site_groups.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/reminder.xml",
        "data/trades.xml",
        "views/site_report_views.xml",
        "views/site_capture_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_site/static/src/scss/site.scss",
            "mizan_site/static/src/js/camera_field.js",
            "mizan_site/static/src/xml/camera_field.xml",
        ],
    },
}
