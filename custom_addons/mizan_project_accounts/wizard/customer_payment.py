# -*- coding: utf-8 -*-
"""A client's payment that is short by the retention, in one screen.

The client pays 100 against a 120 invoice and keeps 20 as retention. One
entry: Dr bank 100 / Dr the project's retention account 20 / Cr the
project's client account 120, reconciled with the invoices chosen. When
the client releases the retention, the release screen posts Dr client /
Cr retention and the money is then received as an ordinary payment."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MizanCustomerPayment(models.TransientModel):
    _name = "mizan.customer.payment"
    _description = "Record a customer payment with retention"

    contract_id = fields.Many2one("mizan.contract", required=True,
                                  domain="[('state', 'in', ('running', 'done')), ('receivable_account_id', '!=', False)]")
    partner_id = fields.Many2one(related="contract_id.partner_id")
    company_id = fields.Many2one(related="contract_id.company_id")
    currency_id = fields.Many2one(related="contract_id.currency_id")
    invoice_ids = fields.Many2many(
        "account.move", string="Invoices paid",
        domain="[('mizan_contract_id', '=', contract_id), ('move_type', '=', 'out_invoice'), "
               "('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]")
    date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", string="Received in", required=True,
                                 domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    invoices_due = fields.Monetary(compute="_compute_defaults", string="Open on the invoices")
    retention_amount = fields.Monetary(string="Retention withheld by the client")
    amount = fields.Monetary(string="Amount received", required=True, default=0.0)
    total = fields.Monetary(compute="_compute_total", string="Credited to the client")
    reference = fields.Char(string="Reference")

    @api.depends("invoice_ids")
    def _compute_defaults(self):
        for wiz in self:
            wiz.invoices_due = sum(wiz.invoice_ids.mapped("amount_residual"))

    @api.depends("amount", "retention_amount")
    def _compute_total(self):
        for wiz in self:
            wiz.total = wiz.amount + wiz.retention_amount

    @api.onchange("invoice_ids", "contract_id")
    def _onchange_invoices(self):
        """Default the retention to the contract's percent of the invoices'
        net value, less what was already withheld on them; the rest is cash."""
        c = self.contract_id
        if not self.invoice_ids or not c:
            return
        retention = 0.0
        for inv in self.invoice_ids:
            already = inv.mizan_retention_amount if inv.mizan_retention_move_id else 0.0
            retention += max(inv.amount_untaxed * (c.retention_percent or 0.0) / 100.0 - already, 0.0)
        retention = min(retention, self.invoices_due)
        self.retention_amount = retention
        self.amount = self.invoices_due - retention

    def action_record(self):
        self.ensure_one()
        c = self.contract_id
        if self.amount < 0 or self.retention_amount < 0 or self.total <= 0:
            raise UserError(_("Type the amount received and the retention withheld."))
        if self.retention_amount and not c.retention_account_id:
            raise UserError(_("%s has no retention account; create the project accounts first.", c.name))
        lines = []
        if self.amount:
            lines.append((0, 0, {"name": _("Payment from %s", c.partner_id.name),
                                 "account_id": self.journal_id.default_account_id.id,
                                 "partner_id": c.partner_id.id, "debit": self.amount, "credit": 0.0}))
        if self.retention_amount:
            lines.append((0, 0, {"name": _("Retention withheld by %s", c.partner_id.name),
                                 "account_id": c.retention_account_id.id,
                                 "partner_id": c.partner_id.id, "debit": self.retention_amount, "credit": 0.0}))
        lines.append((0, 0, {"name": _("Settlement — %s", ", ".join(self.invoice_ids.mapped("name")) or c.code),
                             "account_id": c.receivable_account_id.id,
                             "partner_id": c.partner_id.id, "debit": 0.0, "credit": self.total}))
        move = self.env["account.move"].with_context(mizan_routing=True).create({
            "move_type": "entry", "journal_id": self.journal_id.id, "date": self.date,
            "ref": _("Payment %(ref)s — %(contract)s", ref=self.reference or "", contract=c.code).strip(),
            "mizan_contract_id": c.id, "mizan_source_kind": "payment", "line_ids": lines})
        move.action_post()
        credit_line = move.line_ids.filtered(lambda l: l.account_id == c.receivable_account_id)
        open_lines = self.invoice_ids.line_ids.filtered(
            lambda l: l.account_id == c.receivable_account_id and not l.reconciled)
        if open_lines and c.receivable_account_id.reconcile:
            (credit_line | open_lines).reconcile()
        c._mizan_invalidate_figures()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Payment recorded"), "type": "success",
                       "message": _("%(a)s received, %(r)s held as retention, on %(contract)s.",
                                    a=self.amount, r=self.retention_amount, contract=c.name),
                       "next": {"type": "ir.actions.act_window_close"}},
        }


class MizanRetentionRelease(models.TransientModel):
    _name = "mizan.retention.release"
    _description = "Release of client retention"

    contract_id = fields.Many2one("mizan.contract", required=True,
                                  domain="[('retention_account_id', '!=', False)]")
    partner_id = fields.Many2one(related="contract_id.partner_id")
    company_id = fields.Many2one(related="contract_id.company_id")
    currency_id = fields.Many2one(related="contract_id.currency_id")
    held = fields.Monetary(compute="_compute_held", string="Held by the client")
    amount = fields.Monetary(string="Released", required=True, default=0.0)
    date = fields.Date(required=True, default=fields.Date.context_today)

    @api.depends("contract_id")
    def _compute_held(self):
        for wiz in self:
            wiz.held = wiz.contract_id.retention_balance if wiz.contract_id else 0.0

    @api.onchange("contract_id")
    def _onchange_contract(self):
        if self.contract_id and not self.amount:
            self.amount = self.held

    def action_release(self):
        self.ensure_one()
        c = self.contract_id
        if self.amount <= 0 or self.amount > self.held + 0.005:
            raise UserError(_("The release cannot exceed what the client holds (%s).", self.held))
        general = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", c.company_id.id)], limit=1)
        move = self.env["account.move"].with_context(mizan_routing=True).create({
            "move_type": "entry", "journal_id": general.id, "date": self.date,
            "ref": _("Retention released — %s", c.code), "mizan_contract_id": c.id,
            "mizan_source_kind": "retention",
            "line_ids": [
                (0, 0, {"name": _("Retention released by %s", c.partner_id.name),
                        "account_id": c.receivable_account_id.id, "partner_id": c.partner_id.id,
                        "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": _("Retention released by %s", c.partner_id.name),
                        "account_id": c.retention_account_id.id, "partner_id": c.partner_id.id,
                        "debit": 0.0, "credit": self.amount}),
            ]})
        move.action_post()
        c._mizan_invalidate_figures()
        return {"type": "ir.actions.act_window_close"}
