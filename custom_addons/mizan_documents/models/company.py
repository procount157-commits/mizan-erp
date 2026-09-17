# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # A Gulf client expects a stamped, signed document. Without these the PDF
    # reads as a draft to them, however correct the numbers are.
    mizan_stamp = fields.Image(
        string="Company Stamp", max_width=512, max_height=512,
        help="Round company stamp printed on quotations, invoices and vouchers.")
    mizan_signature = fields.Image(
        string="Authorised Signature", max_width=512, max_height=256,
        help="Scanned signature of the person authorised to sign documents.")
    mizan_signatory_name = fields.Char(
        string="Signatory Name",
        help="Printed under the signature, e.g. the general manager.")
    mizan_signatory_title = fields.Char(string="Signatory Title")

    mizan_show_bank_on_quote = fields.Boolean(
        string="Show Bank Details on Quotations", default=True,
        help="Clients transfer against the quotation as often as the invoice, "
             "so the account details belong on both.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_stamp = fields.Image(related="company_id.mizan_stamp", readonly=False)
    mizan_signature = fields.Image(related="company_id.mizan_signature", readonly=False)
    mizan_signatory_name = fields.Char(
        related="company_id.mizan_signatory_name", readonly=False)
    mizan_signatory_title = fields.Char(
        related="company_id.mizan_signatory_title", readonly=False)
    mizan_show_bank_on_quote = fields.Boolean(
        related="company_id.mizan_show_bank_on_quote", readonly=False)
