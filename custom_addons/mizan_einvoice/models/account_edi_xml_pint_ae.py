# -*- coding: utf-8 -*-
"""The UAE profile of Peppol PINT.

Odoo 18 ships PINT builders for Singapore, Malaysia, Japan and Australia/New
Zealand. There is no UAE one, so this is it, built on the same base class they
all use — account.edi.xml.ubl_bis3 — with the three things that make a document
Emirati rather than generic: the tax scheme is VAT rather than GST, the party
identifier is the TRN under Peppol scheme 0235, and the amounts are AED.

One string cannot be pinned down from here: the customization identifier that
names the exact published version of the UAE profile. It is a company setting
with a sensible default rather than a constant in the code, because the
accredited service provider will state the value they accept, and a wrong
constant compiled into a module means reinstalling to change one line of XML.
"""

from odoo import models, _

# The tax categories a UAE invoice can carry, in the UNCL5305 codes the profile
# uses. S = standard 5%, Z = zero-rated, E = exempt, O = outside scope,
# G = export of goods, K = intra-GCC supply, AE = reverse charge.
AE_TAX_CATEGORIES = {"S", "Z", "E", "O", "G", "K", "AE"}

# Peppol's electronic address scheme for a UAE Tax Registration Number. This
# one IS a constant: Odoo already ships it in the partner's EAS list.
AE_EAS_TRN = "0235"


class AccountEdiXmlUBL21(models.AbstractModel):
    _inherit = "account.edi.xml.ubl_21"

    def _get_customization_ids(self):
        vals = super()._get_customization_ids()
        vals["pint_ae"] = (
            self.env.company.mizan_einvoice_customization_id
            or "urn:peppol:pint:billing-1@ae-1")
        return vals


class AccountEdiXmlUBLPINTAE(models.AbstractModel):
    _inherit = "account.edi.xml.ubl_bis3"
    _name = "account.edi.xml.pint_ae"
    _description = "UAE implementation of Peppol International (PINT) for Billing"

    def _export_invoice_filename(self, invoice):
        return "%s_pint_ae.xml" % invoice.name.replace("/", "_")

    # ------------------------------------------------------------ new helpers
    def _add_invoice_header_nodes(self, document_node, vals):
        super()._add_invoice_header_nodes(document_node, vals)
        invoice = vals["invoice"]
        document_node["cbc:CustomizationID"] = {
            "_text": self._get_customization_ids()["pint_ae"]}
        document_node["cbc:ProfileID"] = {"_text": "urn:peppol:bis:billing"}
        document_node["cbc:UUID"] = {"_text": invoice._mizan_einvoice_uuid()}

    def _add_invoice_tax_total_nodes(self, document_node, vals):
        super()._add_invoice_tax_total_nodes(document_node, vals)
        for tax_total_node in document_node.get("cac:TaxTotal") or []:
            for subtotal in tax_total_node.get("cac:TaxSubtotal") or []:
                for category in subtotal.get("cac:TaxCategory") or []:
                    category["cac:TaxScheme"] = {"cbc:ID": {"_text": "VAT"}}

    def _export_invoice_constraints_new(self, invoice, vals):
        constraints = super()._export_invoice_constraints_new(invoice, vals)
        constraints = self._mizan_drop_eu_only(constraints)
        constraints.update(self._mizan_ae_constraints(invoice, vals))
        for tax_total_node in vals["document_node"].get("cac:TaxTotal") or []:
            for subtotal in tax_total_node.get("cac:TaxSubtotal") or []:
                for category in subtotal.get("cac:TaxCategory") or []:
                    code = (category.get("cbc:ID") or {}).get("_text")
                    if code not in AE_TAX_CATEGORIES:
                        constraints["ae_tax_category"] = _(
                            "Every tax on the invoice needs a UAE tax category "
                            "(S, Z, E, O, G, K or AE). %s is not one of them.",
                            code or _("nothing"))
        return constraints

    # ------------------------------------------------------------ old helpers
    def _get_partner_party_vals(self, partner, role):
        vals = super()._get_partner_party_vals(partner, role)
        vals.setdefault("party_tax_scheme_vals", [])
        for scheme in vals["party_tax_scheme_vals"]:
            scheme["tax_scheme_vals"] = {"id": "VAT"}
        return vals

    def _get_tax_category_list(self, customer, supplier, taxes):
        vals_list = super()._get_tax_category_list(customer, supplier, taxes)
        for vals in vals_list:
            vals["tax_scheme_vals"] = {"id": "VAT"}
        return vals_list

    def _export_invoice_vals(self, invoice):
        vals = super()._export_invoice_vals(invoice)
        vals["vals"].update({
            "customization_id": self._get_customization_ids()["pint_ae"],
            "profile_id": "urn:peppol:bis:billing",
            "uuid": invoice._mizan_einvoice_uuid(),
        })
        return vals

    def _export_invoice_constraints(self, invoice, vals):
        constraints = super()._export_invoice_constraints(invoice, vals)
        constraints = self._mizan_drop_eu_only(constraints)
        constraints.update(self._mizan_ae_constraints(invoice, vals))
        return constraints

    # Rules the base class inherits from EN 16931 that do not hold here.
    #
    # BR-CO-09 requires the VAT identifier to start with an ISO 3166-1 country
    # code, because in the EU it does: DE123456789. A UAE TRN is fifteen digits
    # and nothing else, and the party is identified as Emirati by the Peppol
    # scheme 0235 on the endpoint, not by letters inside the number. Leaving
    # the rule on would block every UAE invoice ever issued, and satisfying it
    # would mean writing a TRN the FTA would not recognise.
    EU_ONLY_CONSTRAINTS = (
        "cen_en16931_supplier_vat_country_code",
        "cen_en16931_customer_vat_country_code",
    )

    def _mizan_drop_eu_only(self, constraints):
        for key in self.EU_ONLY_CONSTRAINTS:
            constraints.pop(key, None)
        return constraints

    # ------------------------------------------------------------ the checks
    def _mizan_ae_constraints(self, invoice, vals):
        """What the UAE profile needs that an ordinary invoice may not carry.

        Returned as a dict of failures rather than raised one at a time, so a
        user fixing an invoice sees everything wrong with it at once instead of
        discovering the next missing field after correcting the last.
        """
        company = invoice.company_id
        supplier = vals.get("supplier") or company.partner_id
        customer = vals.get("customer") or invoice.commercial_partner_id
        failures = {}

        if not company.vat:
            failures["ae_supplier_trn"] = _(
                "The company has no TRN. Every UAE tax invoice must carry the "
                "supplier's Tax Registration Number.")
        if not customer.vat and not invoice._mizan_is_b2c():
            failures["ae_customer_trn"] = _(
                "%s has no TRN. A tax invoice to a registered business must "
                "carry the buyer's TRN.", customer.display_name)

        for party, key, label in (
                (supplier, "supplier", _("company")),
                (customer, "customer", _("customer"))):
            missing = [name for name, field in (
                (_("street"), party.street),
                (_("city"), party.city),
                (_("country"), party.country_id),
            ) if not field]
            if missing:
                failures["ae_%s_address" % key] = _(
                    "The %(who)s address is incomplete: %(missing)s missing.",
                    who=label, missing=", ".join(missing))

        if invoice.currency_id.name != "AED":
            failures["ae_currency"] = _(
                "A UAE tax invoice is issued in AED. %s is in %s; the AED "
                "equivalent has to be shown as well.",
                invoice.name, invoice.currency_id.name)

        if supplier.peppol_eas and supplier.peppol_eas != AE_EAS_TRN:
            failures["ae_supplier_eas"] = _(
                "The company's Peppol scheme is %s. A UAE party is identified "
                "by its TRN under scheme %s.", supplier.peppol_eas, AE_EAS_TRN)

        if not company.mizan_einvoice_customization_id:
            failures["ae_customization"] = _(
                "No PINT AE profile identifier is set on the company. Your "
                "accredited service provider states the value they accept.")

        return failures
