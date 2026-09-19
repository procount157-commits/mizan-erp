{
    "name": "ProAccount Documents",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Stamp, signature and bank details on quotations, invoices and vouchers",
    "description": """
A Gulf client expects a stamped and signed document, and pays by transfer against
whichever document is in front of them. This adds a company stamp and authorised
signature to the printed quotation, invoice and voucher, and prints the IBAN on
quotations as well as invoices.
""",
    # l10n_gcc_invoice supplies the bilingual Arabic/English invoice that
    # replaces the standard one for a GCC company, and this module extends it.
    # Without the dependency the extension loads before its target exists,
    # which only ever worked here because the development database happened to
    # have it installed already.
    "depends": ["account", "sale", "portal", "l10n_ae", "l10n_gcc_invoice"],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
    "data": [
        "data/mail_template.xml",
        "views/report_templates.xml",
        "views/watermark_templates.xml",
        "views/settings_views.xml",
        "views/document_layout_views.xml",
        "views/whatsapp_views.xml",
    ],
}
