# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_einvoice_customization_id = fields.Char(
        string="PINT AE Profile ID",
        default="urn:peppol:pint:billing-1@ae-1",
        help="The identifier naming the exact published version of the UAE "
             "Peppol profile. It goes in the CustomizationID of every document "
             "and your accredited service provider states the value they "
             "accept. Kept as a setting rather than a constant in the code "
             "because the profile is versioned and you should not need a new "
             "release to follow it.")
    mizan_einvoice_asp_name = fields.Char(
        string="Accredited Service Provider",
        help="Who transmits your invoices to the buyer and to the FTA. Under "
             "the five-corner model nothing reaches either without one.")
    mizan_einvoice_asp_reference = fields.Char(
        string="ASP Account Reference",
        help="The identifier the provider issues you, for the record. "
             "Credentials belong in the provider's own connector, not here.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_einvoice_customization_id = fields.Char(
        related="company_id.mizan_einvoice_customization_id", readonly=False)
    mizan_einvoice_asp_name = fields.Char(
        related="company_id.mizan_einvoice_asp_name", readonly=False)
    mizan_einvoice_asp_reference = fields.Char(
        related="company_id.mizan_einvoice_asp_reference", readonly=False)
