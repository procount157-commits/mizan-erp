# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    invoice_edi_format = fields.Selection(
        selection_add=[("pint_ae", "UAE (Peppol PINT AE)")])

    def _get_edi_builder(self, invoice_edi_format):
        if invoice_edi_format == "pint_ae":
            return self.env["account.edi.xml.pint_ae"]
        return super()._get_edi_builder(invoice_edi_format)

    def _get_ubl_cii_formats_info(self):
        formats_info = super()._get_ubl_cii_formats_info()
        # on_peppol is False deliberately: Odoo's own access point does not
        # carry the UAE, and claiming it does would send invoices nowhere.
        formats_info["pint_ae"] = {
            "countries": ["AE"], "on_peppol": False, "sequence": 90}
        return formats_info
