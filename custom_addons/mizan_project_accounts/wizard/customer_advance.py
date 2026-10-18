# -*- coding: utf-8 -*-
"""Receiving a client's advance, the CFO's way.

Two entries, both naming the contract: (1) Dr the advance clearing account /
Cr the project's client account; (2) Dr the bank / Cr the clearing account.
The clearing account therefore always reads zero, the client's account
carries the credit that later offsets the claims, and the advance register
reads the first entry to say who financed which project and by how much."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MizanCustomerAdvance(models.TransientModel):
    _name = "mizan.customer.advance"
    _description = "Receive a customer advance"

    contract_id = fields.Many2one("mizan.contract", required=True,
                                  domain="[('state', '=', 'running'), ('receivable_account_id', '!=', False)]")
    partner_id = fields.Many2one(related="contract_id.partner_id")
    company_id = fields.Many2one(related="contract_id.company_id")
    currency_id = fields.Many2one(related="contract_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", string="Received in", required=True,
                                 domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]")
    amount = fields.Monetary(required=True)
    suggested_amount = fields.Monetary(compute="_compute_suggested")
    reference = fields.Char(string="Reference", help="Cheque or transfer number")

    @api.depends("contract_id")
    def _compute_suggested(self):
        for wiz in self:
            c = wiz.contract_id
            wiz.suggested_amount = (c.contract_value * (c.advance_percent or 0.0) / 100.0) if c else 0.0

    @api.onchange("contract_id")
    def _onchange_contract(self):
        if self.contract_id and not self.amount:
            self.amount = self.suggested_amount

    def action_receive(self):
        self.ensure_one()
        c = self.contract_id
        if self.amount <= 0:
            raise UserError(_("Type the amount received."))
        clearing = c.company_id.mizan_advance_clearing_account_id
        if not clearing:
            c.company_id._mizan_ensure_project_company_accounts()
            clearing = c.company_id.mizan_advance_clearing_account_id
        general = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", c.company_id.id)], limit=1)
        Move = self.env["account.move"].with_context(mizan_routing=True)
        ref = _("Advance from %(client)s — %(contract)s %(ref)s",
                client=c.partner_id.name, contract=c.code, ref=self.reference or "").strip()
        advance = Move.create({
            "move_type": "entry", "journal_id": general.id, "date": self.date, "ref": ref,
            "mizan_contract_id": c.id, "mizan_source_kind": "advance",
            "line_ids": [
                (0, 0, {"name": _("Advance received"), "account_id": clearing.id,
                        "partner_id": c.partner_id.id, "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": _("Advance received"), "account_id": c.receivable_account_id.id,
                        "partner_id": c.partner_id.id, "debit": 0.0, "credit": self.amount}),
            ]})
        bank = Move.create({
            "move_type": "entry", "journal_id": self.journal_id.id, "date": self.date, "ref": ref,
            "mizan_contract_id": c.id, "mizan_source_kind": "advance",
            "line_ids": [
                (0, 0, {"name": _("Advance banked"), "account_id": self.journal_id.default_account_id.id,
                        "partner_id": c.partner_id.id, "debit": self.amount, "credit": 0.0}),
                (0, 0, {"name": _("Advance banked"), "account_id": clearing.id,
                        "partner_id": c.partner_id.id, "debit": 0.0, "credit": self.amount}),
            ]})
        (advance | bank).action_post()
        c._mizan_invalidate_figures()
        c.message_post(body=_("Advance of %(a)s received on %(d)s (%(j)s).",
                              a=self.amount, d=self.date, j=self.journal_id.name))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Advance received"), "type": "success",
                       "message": _("%(a)s credited to %(client)s on %(contract)s.",
                                    a=self.amount, client=c.partner_id.name, contract=c.name),
                       "next": {"type": "ir.actions.act_window_close"}},
        }
