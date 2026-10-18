# -*- coding: utf-8 -*-
"""Claim invoices on the project's own accounts.

Dr the project's client account (gross) / Cr the project's billing account
(net) / Cr VAT. In progress-claim mode, posting the invoice also posts the
recognition for the claim's cumulative percent, so revenue and cost follow
the work in the same breath as the bill."""
from odoo import _, models
from odoo.exceptions import UserError


class MizanProgressClaim(models.Model):
    _inherit = "mizan.progress.claim"

    def _claim_revenue_account(self):
        if self.contract_id.billing_account_id:
            return self.contract_id.billing_account_id
        return super()._claim_revenue_account()

    def action_create_invoice(self):
        result = super().action_create_invoice()
        contract = self.contract_id
        invoice = self.invoice_id
        if invoice and contract.receivable_account_id and invoice.state == "draft":
            invoice.line_ids.filtered(lambda l: l.display_type == "payment_term").write(
                {"account_id": contract.receivable_account_id.id})
        return result

    def action_post_invoice_and_deduct(self):
        """On project accounts the retention is withheld when the client pays
        (the payment screen) and the advance sits as a credit on the client's
        account; the old entries against the shared receivable are skipped."""
        self.ensure_one()
        if not self.contract_id.has_project_accounts:
            return super().action_post_invoice_and_deduct()
        invoice = self.invoice_id
        if not invoice:
            raise UserError(_("Raise the invoice for %s first.", self.name))
        if invoice.state == "draft":
            invoice.action_post()
        return True


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        Claim = self.env["mizan.progress.claim"]
        for move in posted:
            contract = move.mizan_contract_id
            if move.move_type != "out_invoice" or not contract or not contract.billing_account_id:
                continue
            if contract.billing_mode != "progress":
                continue
            claim = Claim.search([("invoice_id", "=", move.id)], limit=1)
            if not claim:
                continue
            recognition = self.env["mizan.contract.recognition"].create({
                "contract_id": contract.id, "date": move.date, "source": "claim",
                "claim_id": claim.id, "measured_percent": claim.percent_complete,
                "amount": 0.0,
            })
            recognition.action_post()
        return posted
