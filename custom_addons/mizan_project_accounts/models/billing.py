# -*- coding: utf-8 -*-
"""Claim invoices on the project's own accounts.

Dr the project's client account (gross) / Cr the project's billing account
(net) / Cr VAT. In progress-claim mode, posting the invoice also posts the
recognition for the claim's cumulative percent, so revenue and cost follow
the work in the same breath as the bill."""
from odoo import _, models
from odoo.exceptions import UserError


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    def action_invoice_instalment(self):
        """An invoice to the client that is not a measured claim: an agreed
        instalment, or an invoice against an advance. It credits the billing
        account; progress is recorded in its own window."""
        self.ensure_one()
        journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.company_id.id)], limit=1)
        return {
            "type": "ir.actions.act_window", "name": _("Instalment invoice — %s", self.name),
            "res_model": "account.move", "views": [[False, "form"]], "target": "current",
            "context": {"default_move_type": "out_invoice", "default_partner_id": self.partner_id.id,
                        "default_mizan_contract_id": self.id, "default_journal_id": journal.id,
                        "default_ref": _("%s — instalment", self.code)},
        }


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

    def _mizan_route_customer_invoice(self):
        """Any invoice to the client that names the project — a claim, an
        instalment, an invoice against an advance — credits the project's
        billing account (the sieve), never revenue, and debits the project's
        client account. Revenue comes only from the recognition."""
        for move in self:
            contract = move.mizan_contract_id
            if move.state != "draft" or move.move_type not in ("out_invoice", "out_refund") \
                    or not contract or not contract.billing_account_id:
                continue
            income = move.line_ids.filtered(
                lambda l: l.display_type == "product"
                and l.account_id.account_type in ("income", "income_other")
                and l.account_id != contract.billing_account_id)
            if income:
                income.with_context(mizan_routing=True).write({"account_id": contract.billing_account_id.id})
            term = move.line_ids.filtered(
                lambda l: l.display_type == "payment_term" and l.account_id != contract.receivable_account_id)
            if term:
                term.with_context(mizan_routing=True).write({"account_id": contract.receivable_account_id.id})

    def _post(self, soft=True):
        self._mizan_route_customer_invoice()
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
