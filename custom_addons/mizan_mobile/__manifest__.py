# -*- coding: utf-8 -*-
{
    "name": "Miqyas Mobile",
    "version": "1.0",
    "category": "Productivity",
    "summary": "The phone apps: native iPhone notifications, and the day's work on the first screen",
    "description": """The Android and iPhone apps show the system itself, so every screen, right
and approval reaches the phone the day it is built, with no new app release.
Two things a web page cannot do on its own are done here:

* iPhone notifications. Inside an iPhone app, web push does not exist; the
  app registers with Apple, gives the server its token, and the server sends
  through Apple's push service. A tap opens the record the message is about.
* The first screen. Tasks due, opportunities to follow, alongside petty cash
  and the jobs — so nobody hunts through apps to find their day.
""",
    "author": "ProAccount",
    "depends": ["mail", "mizan_hub", "crm", "project"],
    "external_dependencies": {"python": []},
    "data": [
        "security/ir.model.access.csv",
        "views/push_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
