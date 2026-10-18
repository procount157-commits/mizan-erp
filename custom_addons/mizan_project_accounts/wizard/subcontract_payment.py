# -*- coding: utf-8 -*-
"""Paying a subcontractor, retention withheld, in one screen."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MizanSubcontractPayment(models.TransientModel):
    _name = "mizan.subcontract.payment"
    _description = "Pay a subcontractor"

    subcontract_id = fields.Many2one("mizan.subcontract", required=True)
    partner_id = fields.Many2one(related="subcontract_id.partner_id")
    contract_id = fields.Many2one(related="subcontract_id.contract_id")
    company_id = fields.Many2one(related="subcontract_id.company_id")
    currency_id = fields.Many2one(related="subcontract_id.currency_id")
    bill_ids = fields.Many2many(
        "account.move", string="Bills paid",
        domain="[('mizan_subcontract_id', '=', subcontract_id), ('move_type', '=', 'in_invoice'), "
               "('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]")
    bills_due = fields.Monetary(compute="_compute_due", string="Open on the bills")
    retention_amount = fields.Monetary(string="Retention withheld")
    amount = fields.Monetary(string="Amount paid", required=True, default=0.0)
    total = fields.Monetary(compute="_compute_total", string="Debited to the subcontractor")
    date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", string="Paid from", required=True,
                                 domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    reference = fields.Char(string="Reference")

    @api.depends("bill_ids")
    def _compute_due(self):
        for wiz in self:
            wiz.bills_due = sum(wiz.bill_ids.mapped("amount_residual"))

    @api.depends("amount", "retention_amount")
    def _compute_total(self):
        for wiz in self:
            wiz.total = wiz.amount + wiz.retention_amount

    @api.onchange("bill_ids", "subcontract_id")
    def _onchange_bills(self):
        sc = self.subcontract_id
        if not self.bill_ids or not sc:
            return
        retention = 0.0
        for bill in self.bill_ids:
            already = bill.mizan_retention_amount if bill.mizan_retention_move_id else 0.0
            retention += max(bill.amount_untaxed * (sc.retention_percent or 0.0) / 100.0 - already, 0.0)
        retention = min(retention, self.bills_due)
        self.retention_amount = retention
        self.amount = self.bills_due - retention

    def action_pay(self):
        self.ensure_one()
        sc = self.subcontract_id
        partner = sc.partner_id
        if self.amount < 0 or self.retention_amount < 0 or self.total <= 0:
            raise UserError(_("Type the amount paid and the retention withheld."))
        partner.action_create_subcontractor_accounts()
        payable = partner.mizan_sc_payable_account_id
        lines = [(0, 0, {"name": _("Payment to %s", partner.name), "account_id": payable.id,
                         "partner_id": partner.id, "debit": self.total, "credit": 0.0})]
        if self.amount:
            lines.append((0, 0, {"name": _("Payment to %s", partner.name),
                                 "account_id": self.journal_id.default_account_id.id,
                                 "partner_id": partner.id, "debit": 0.0, "credit": self.amount}))
        if self.retention_amount:
            lines.append((0, 0, {"name": _("Retention withheld from %s", partner.name),
                                 "account_id": partner.mizan_sc_retention_account_id.id,
                                 "partner_id": partner.id, "debit": 0.0, "credit": self.retention_amount}))
        move = self.env["account.move"].with_context(mizan_routing=True).create({
            "move_type": "entry", "journal_id": self.journal_id.id, "date": self.date,
            "ref": _("Subcontractor payment %(ref)s — %(sc)s", ref=self.reference or "", sc=sc.code).strip(),
            "mizan_contract_id": sc.contract_id.id, "mizan_subcontract_id": sc.id,
            "mizan_source_kind": "sc_payment", "line_ids": lines})
        move.action_post()
        debit_line = move.line_ids.filtered(lambda l: l.account_id == payable)
        open_lines = self.bill_ids.line_ids.filtered(lambda l: l.account_id == payable and not l.reconciled)
        if open_lines and payable.reconcile:
            (debit_line | open_lines).reconcile()
        sc.invalidate_recordset(["retention_held"])
        sc.contract_id._mizan_invalidate_figures()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Subcontractor paid"), "type": "success",
                       "message": _("%(a)s paid, %(r)s held as retention, on %(sc)s.",
                                    a=self.amount, r=self.retention_amount, sc=sc.code),
                       "next": {"type": "ir.actions.act_window_close"}},
        }


class MizanSubcontractRelease(models.TransientModel):
    _name = "mizan.subcontract.release"
    _description = "Release subcontractor retention"

    subcontract_id = fields.Many2one("mizan.subcontract", required=True)
    partner_id = fields.Many2one(related="subcontract_id.partner_id")
    company_id = fields.Many2one(related="subcontract_id.company_id")
    currency_id = fields.Many2one(related="subcontract_id.currency_id")
    held = fields.Monetary(compute="_compute_held", string="Held")
    amount = fields.Monetary(string="Released", required=True, default=0.0)
    date = fields.Date(required=True, default=fields.Date.context_today)

    @api.depends("subcontract_id")
    def _compute_held(self):
        for wiz in self:
            wiz.held = wiz.subcontract_id.retention_held if wiz.subcontract_id else 0.0

    @api.onchange("subcontract_id")
    def _onchange_subcontract(self):
        if self.subcontract_id and not self.amount:
            self.amount = self.held

    def action_release(self):
        self.ensure_one()
        sc = self.subcontract_id
        partner = sc.partner_id
        if self.amount <= 0 or self.amount > self.held + 0.005:
            raise UserError(_("The release cannot exceed what is held (%s).", self.held))
        general = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", sc.company_id.id)], limit=1)
        move = self.env["account.move"].with_context(mizan_routing=True).create({
            "move_type": "entry", "journal_id": general.id, "date": self.date,
            "ref": _("Retention released — %s", sc.code), "mizan_contract_id": sc.contract_id.id,
            "mizan_subcontract_id": sc.id, "mizan_source_kind": "retention",
            "line_ids": [
                (0, 0, {"name": _("Retention released to %s", partner.name),
                        "account_id": partner.mizan_sc_retention_account_id.id, "partner_id": partner.id,
                        "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": _("Retention released to %s", partner.name),
                        "account_id": partner.mizan_sc_payable_account_id.id, "partner_id": partner.id,
                        "debit": 0.0, "credit": self.amount}),
            ]})
        move.action_post()
        sc.invalidate_recordset(["retention_held"])
        sc.contract_id._mizan_invalidate_figures()
        return {"type": "ir.actions.act_window_close"}
