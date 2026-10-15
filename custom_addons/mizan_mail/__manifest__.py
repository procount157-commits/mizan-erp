# -*- coding: utf-8 -*-
{
    "name": "Miqyas Email",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Send invoices and payment reminders by email, set up in one screen",
    "description": """Nothing could be emailed: no outgoing server was configured, and the
invoice message was Odoo's English one. This module:

* sets up the outgoing email in one screen — choose the provider, type the
  address and its password, test, save;
* replaces the invoice email with a bilingual Arabic/English one carrying the
  amount, the due date, the link to view and pay, and the PDF;
* sends a payment reminder on an overdue invoice in one tap, and optionally
  every few days by itself;
* optionally emails an invoice the moment it is confirmed;
* shows which customers have no email address, so the send does not fail.
""",
    "author": "ProAccount",
    "depends": ["account", "mail", "mizan_core"],
    "data": [
        "security/ir.model.access.csv",
        "data/mail_templates.xml",
        "data/cron.xml",
        "wizard/mail_setup_views.xml",
        "views/account_move_views.xml",
        "views/settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
