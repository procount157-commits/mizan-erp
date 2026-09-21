# -*- coding: utf-8 -*-
"""What an invoice needs to know about being an e-invoice.

The useful part of this, today, is the check rather than the file. An accredited
service provider can be appointed in a week; getting every customer's TRN and
address right across a live ledger cannot, and that is what stops a contractor
on the day the mandate starts. So the invoice carries its own readiness, the
reason it is not ready is written in words the accountant can act on, and the
list can be read across the whole ledger at once.
"""

import uuid

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_einvoice_state = fields.Selection(
        [("na", "Not Applicable"),
         ("blocked", "Missing Data"),
         ("ready", "Ready"),
         ("generated", "Document Built"),
         ("sent", "Sent")],
        string="e-Invoice", default="na", copy=False, readonly=True,
        compute="_compute_mizan_einvoice_state", store=True)
    # Deliberately NOT stored. The text is sentences, and a stored compute
    # freezes them in whichever language happened to run it — an Arabic user
    # was reading English here because the first compute ran under en_US.
    # Computed on read, so every reader gets their own language.
    mizan_einvoice_issues = fields.Text(
        string="What Is Missing", compute="_compute_mizan_einvoice_issues")
    mizan_einvoice_attachment_id = fields.Many2one(
        "ir.attachment", string="e-Invoice File", copy=False, readonly=True)
    mizan_einvoice_sent_on = fields.Datetime(readonly=True, copy=False)

    def _mizan_einvoice_uuid(self):
        """A stable identifier for this document.

        Derived from the database uuid and the move id rather than stored, so
        it is the same every time the document is rebuilt and cannot drift
        between a copy sent to the buyer and one sent to the authority.
        """
        self.ensure_one()
        dbuuid = self.env["ir.config_parameter"].sudo().get_param("database.uuid")
        return str(uuid.uuid5(uuid.UUID(dbuuid), str(self.id)))

    def _mizan_is_b2c(self):
        """A sale to someone who is not a registered business.

        A private buyer has no TRN and requiring one would block every
        legitimate consumer invoice, so the test is whether the partner is a
        company — not whether the field happens to be filled.
        """
        self.ensure_one()
        return not self.commercial_partner_id.is_company

    def _mizan_einvoice_applies(self):
        self.ensure_one()
        return (self.move_type in ("out_invoice", "out_refund")
                and self.company_id.country_id.code == "AE")

    @api.depends("state", "move_type", "partner_id", "currency_id",
                 "company_id.vat", "company_id.mizan_einvoice_customization_id",
                 "mizan_einvoice_attachment_id", "mizan_einvoice_sent_on")
    def _compute_mizan_einvoice_state(self):
        for move in self:
            if not move._mizan_einvoice_applies():
                move.mizan_einvoice_state = "na"
                continue
            if move._mizan_einvoice_check():
                move.mizan_einvoice_state = "blocked"
                continue
            if move.mizan_einvoice_sent_on:
                move.mizan_einvoice_state = "sent"
            elif move.mizan_einvoice_attachment_id:
                move.mizan_einvoice_state = "generated"
            else:
                move.mizan_einvoice_state = "ready"

    @api.depends("mizan_einvoice_state", "partner_id", "currency_id",
                 "company_id.vat")
    def _compute_mizan_einvoice_issues(self):
        for move in self:
            if not move._mizan_einvoice_applies():
                move.mizan_einvoice_issues = False
                continue
            issues = move._mizan_einvoice_check()
            move.mizan_einvoice_issues = "\n".join(
                "• %s" % issue for issue in issues) if issues else False

    def _mizan_einvoice_check(self):
        """The profile's own constraints, run without building the file."""
        self.ensure_one()
        builder = self.env["account.edi.xml.pint_ae"]
        failures = builder._mizan_ae_constraints(self, {
            "supplier": self.company_id.partner_id,
            "customer": self.commercial_partner_id,
        })
        return [message for message in failures.values() if message]

    def action_mizan_check_einvoice(self):
        """Re-run the checks and say what is wrong, in one message."""
        self.ensure_one()
        self._compute_mizan_einvoice_state()
        if self.mizan_einvoice_state == "na":
            raise UserError(_(
                "e-invoicing applies to customer invoices issued by a UAE "
                "company. %s is neither.", self.name))
        if self.mizan_einvoice_issues:
            raise UserError(_(
                "%(name)s cannot be issued as an e-invoice yet:\n\n%(issues)s",
                name=self.name, issues=self.mizan_einvoice_issues))
        raise UserError(_(
            "%s carries everything the UAE profile requires.", self.name))

    def action_mizan_generate_einvoice(self):
        """Build the UBL document and keep it on the invoice."""
        for move in self:
            if move.state != "posted":
                raise UserError(_("Post %s before building its e-invoice.",
                                  move.name))
            if not move._mizan_einvoice_applies():
                raise UserError(_(
                    "e-invoicing applies to customer invoices issued by a UAE "
                    "company. %s is neither.", move.name))
            issues = move._mizan_einvoice_check()
            if issues:
                raise UserError(_(
                    "%(name)s cannot be issued as an e-invoice yet:\n\n%(issues)s",
                    name=move.name,
                    issues="\n".join("• %s" % issue for issue in issues)))
            builder = self.env["account.edi.xml.pint_ae"]
            xml_content, build_errors = builder._export_invoice(move)
            if build_errors:
                raise UserError(_(
                    "The UAE profile rejected %(name)s:\n\n%(errors)s",
                    name=move.name,
                    errors="\n".join("• %s" % e for e in build_errors)))
            attachment = self.env["ir.attachment"].create({
                "name": builder._export_invoice_filename(move),
                "raw": xml_content,
                "mimetype": "application/xml",
                "res_model": "account.move",
                "res_id": move.id,
            })
            move.mizan_einvoice_attachment_id = attachment.id
            move.message_post(
                body=_("e-invoice document built to the UAE Peppol profile."),
                attachment_ids=[attachment.id])
        return True

    def action_mizan_send_einvoice(self):
        """Deliberately not implemented, and saying so precisely.

        The UAE runs a five-corner model: the invoice goes from the supplier to
        the supplier's accredited service provider, on to the buyer's, to the
        buyer, and to the Federal Tax Authority. There is no endpoint to post
        to without a provider, and writing one against a guessed API would give
        the comforting appearance of compliance while nothing arrived.
        """
        self.ensure_one()
        provider = self.company_id.mizan_einvoice_asp_name
        raise UserError(_(
            "Transmission needs an accredited service provider.\n\n"
            "The UAE sends e-invoices through an ASP: supplier → your ASP → "
            "the buyer's ASP → the buyer, with a copy to the FTA. There is no "
            "address to send to directly.\n\n"
            "%(status)s\n\n"
            "The document itself is built and attached, so it can be handed to "
            "a provider for testing today. What takes the time is the data, "
            "and the readiness list shows exactly where it stands.",
            status=(_("Recorded provider: %s. Install their connector to "
                      "enable sending.") % provider) if provider
            else _("No provider is recorded on the company yet.")))

    def action_mizan_view_einvoice_file(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true"
                   % self.mizan_einvoice_attachment_id.id,
            "target": "self",
        }
