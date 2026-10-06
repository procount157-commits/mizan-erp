# -*- coding: utf-8 -*-
"""Retention withheld on a contract invoice.

A client keeps back a percentage of every progress claim until the defects
period ends, and the contractor keeps the same back from subcontractors. That
money is not an ordinary receivable: it is not due yet, so leaving it in trade
debtors makes the ageing report demand money nobody owes, and the invoice can
never reach paid because the last 5% will never arrive against it.

Withholding here does two things, and the second is the one that is easy to
forget: it moves the amount to a retention account, and it reconciles that
movement against the invoice. Without the reconciliation the ledger and the
invoice disagree by exactly the retention — the ledger is right and every
customer statement is wrong.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_contract_id = fields.Many2one(
        "mizan.contract", string="Contract", copy=False,
        help="The contract this claim is drawn against.")
    mizan_retention_percent = fields.Float(
        string="Retention %", copy=False,
        compute="_compute_retention_percent", store=True, readonly=False)
    mizan_retention_amount = fields.Monetary(
        string="Retention Withheld", copy=False, readonly=True)
    mizan_retention_move_id = fields.Many2one(
        "account.move", string="Retention Entry", copy=False, readonly=True)

    @api.depends("mizan_contract_id")
    def _compute_retention_percent(self):
        for move in self:
            if move.mizan_contract_id:
                move.mizan_retention_percent = move.mizan_contract_id.retention_percent
            else:
                move.mizan_retention_percent = move.mizan_retention_percent or 0.0

    def _retention_accounts(self):
        """(retention account, the control account it comes out of)."""
        self.ensure_one()
        Account = self.env["account.account"]
        if self.move_type in ("out_invoice", "out_refund"):
            code, control = "107003", "asset_receivable"
        else:
            code, control = "204001", "liability_payable"
        retention = Account.search([("code", "=", code)], limit=1)
        if not retention:
            raise UserError(_(
                "Account %s is missing. Run scripts/complete_coa.py against "
                "this database.", code))
        return retention, control

    def _mizan_retention_to_withhold(self):
        """How much to hold back, and why the claim gets the last word.

        Retention is five per cent of the value certified *to date*, not five
        per cent of each invoice taken on its own. The two agree until
        rounding bites: 5% of a cumulative figure, minus 5% of the previous
        cumulative figure, is not always 5% of the difference. Recomputing it
        from the invoice therefore drifts a fils at a time, and the drift only
        ever grows, until the retention account no longer equals what the
        claims say is held -- which is the number the contractor and the
        client argue over at handover.

        So when the invoice came from a progress claim, the claim's figure is
        the one posted. Only a retention invoice with no claim behind it falls
        back to a percentage of itself, because then there is nothing
        cumulative to be consistent with.
        """
        self.ensure_one()
        claim = self.env["mizan.progress.claim"].search(
            [("invoice_id", "=", self.id)], limit=1)
        if claim and claim.retention_amount:
            return self.currency_id.round(claim.retention_amount)
        return self.currency_id.round(
            self.amount_untaxed * self.mizan_retention_percent / 100.0)

    def action_withhold_retention(self):
        for move in self:
            if move.state != "posted":
                raise UserError(_("Post the document before withholding retention."))
            if move.mizan_retention_move_id:
                raise UserError(_(
                    "Retention was already withheld on %s.", move.name))
            if not move.mizan_retention_percent:
                raise UserError(_("Set the retention percentage first."))

            retention_account, control_type = move._retention_accounts()
            amount = move._mizan_retention_to_withhold()
            if amount <= 0:
                raise UserError(_("Nothing to withhold on %s.", move.name))

            control_line = move.line_ids.filtered(
                lambda l: l.account_id.account_type == control_type)[:1]
            if not control_line:
                raise UserError(_("No receivable or payable line on %s.", move.name))

            customer = control_type == "asset_receivable"
            journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", move.company_id.id)],
                limit=1)
            label = _("Retention on %s", move.name)
            entry = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": move.invoice_date or move.date,
                "ref": label,
                "line_ids": [
                    (0, 0, {
                        "account_id": retention_account.id,
                        "partner_id": move.partner_id.id,
                        "name": label,
                        "debit": amount if customer else 0.0,
                        "credit": 0.0 if customer else amount,
                    }),
                    (0, 0, {
                        "account_id": control_line.account_id.id,
                        "partner_id": move.partner_id.id,
                        "name": label,
                        "debit": 0.0 if customer else amount,
                        "credit": amount if customer else 0.0,
                    }),
                ],
            })
            entry.action_post()

            # The step that keeps the invoice and the ledger telling the same
            # story: without it the invoice still asks for the retention.
            offset = entry.line_ids.filtered(
                lambda l: l.account_id == control_line.account_id)
            (control_line | offset).reconcile()

            move.write({
                "mizan_retention_amount": amount,
                "mizan_retention_move_id": entry.id,
            })
        return True

    def action_view_retention_entry(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.mizan_retention_move_id.id,
            "view_mode": "form",
        }
