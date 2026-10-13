# -*- coding: utf-8 -*-
{
    "name": "Miqyas Home",
    "version": "1.0",
    "category": "Productivity",
    "summary": "The front door: every department, its key figures and its screens, on one page",
    "description": """Twenty-nine apps on the home screen is not access, it is a search problem.
This is the one page a person opens instead: what is waiting for them, a
search box that finds any document, and a card per department — accounting,
VAT, cheques and banks, projects and claims, petty cash, people, operations,
sales, reports — each with the two or three figures that matter today and the
screens behind them, one tap away. Cards and figures follow the person's
role: a site engineer sees their site, cash and tasks, not the ledger.
""",
    "author": "ProAccount",
    "depends": ["web", "mizan_core", "mizan_hub"],
    "data": [
        "views/home_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mizan_home/static/src/scss/home.scss",
            "mizan_home/static/src/xml/home.xml",
            "mizan_home/static/src/js/home.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
