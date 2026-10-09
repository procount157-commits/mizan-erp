{
    "name": "Miqyas UAE e-Invoicing (Peppol PINT AE)",
    "version": "1.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Generate and check UAE Peppol PINT invoices ahead of the mandate",
    "description": """
The UAE is moving to mandatory e-invoicing over Peppol, and Odoo ships PINT
profiles for Singapore, Malaysia, Japan and Australia/New Zealand but not for
the UAE. This module adds the missing profile: it builds the UBL document from
an invoice, checks it against what the UAE profile requires, and says exactly
which field is missing on which invoice.

Transmission is deliberately not implemented. Under the five-corner model an
invoice reaches the buyer and the FTA through an ACCREDITED SERVICE PROVIDER,
and that is a contract, not a library. What this module does is make sure that
when the provider is appointed, the data is already there and correct — which
is the part that takes months, not the connection.
""",
    "depends": ["account", "account_edi_ubl_cii", "l10n_ae", "mizan_core"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "views/einvoice_views.xml",
    ],
}
