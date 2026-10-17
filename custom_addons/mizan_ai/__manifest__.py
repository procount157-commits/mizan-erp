# -*- coding: utf-8 -*-
{
    "name": "Miqyas AI",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Read a supplier invoice into a draft bill; the figures are checked, a person approves",
    "description": """A supplier's PDF or photo is read by a language model through any
OpenAI-compatible service (OpenRouter, Groq, or another), chosen in Settings.
The model only reads: supplier, TRN, number, dates and lines go into a DRAFT
bill. The system then checks the arithmetic itself — lines against subtotal,
VAT against the rate, subtotal plus VAT against the total, the TRN's format,
a repeated supplier invoice number — and writes what it found on the bill.
Nothing is posted by the model; an accountant reviews and confirms.

The API key is typed into Settings by the administrator, kept server-side,
and never shown again.
""",
    "author": "ProAccount",
    "depends": ["account", "mail", "mizan_core"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "views/settings_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
