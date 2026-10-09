# -*- coding: utf-8 -*-
"""Everybody holding company cash, on one list.

Rebuilt each time it is opened, like the other screens in this product: a
stored copy of a balance is a balance that has already gone stale. Each viewer
sees whom their access lets them see — an accountant everybody, a site
manager his own team, an engineer himself."""

from odoo import api, fields, models, _


class MizanPettyCashBalance(models.TransientModel):
    _name = "mizan.petty.cash.balance"
    _description = "Petty Cash Balance"
    _order = "available, id"

    employee_id = fields.Many2one("hr.employee", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    held = fields.Monetary(readonly=True, string="Holding")
    waiting = fields.Monetary(readonly=True, string="Receipts Waiting")
    waiting_count = fields.Integer(readonly=True, string="Receipts")
    available = fields.Monetary(readonly=True, string="Available")
    last_paid = fields.Date(readonly=True, string="Last Top-up")
    tone = fields.Selection([("good", "Good"), ("watch", "Watch"), ("bad", "Bad")],
                            readonly=True)

    @api.model
    def _rows(self):
        Advance = self.env["mizan.employee.advance"]
        holders = Advance.search([("state", "=", "paid")]).employee_id
        rows = []
        for employee in holders:
            cash = Advance._petty_cash(employee)
            float_size = sum(cash["advances"].mapped("amount")) or 1.0
            tone = ("bad" if cash["available"] < 0 else
                    "watch" if cash["available"] < 0.2 * float_size else "good")
            rows.append({
                "employee_id": employee.id,
                "currency_id": cash["currency"].id,
                "held": cash["held"], "waiting": cash["waiting"],
                "waiting_count": cash["waiting_count"],
                "available": cash["available"],
                "last_paid": max(cash["advances"].mapped("date")),
                "tone": tone,
            })
        return rows

    @api.model
    def action_refresh(self):
        self.search([("create_uid", "=", self.env.uid)]).unlink()
        self.create(self._rows())
        return {
            "type": "ir.actions.act_window",
            "name": _("Petty Cash Balances"),
            "res_model": self._name,
            "view_mode": "list",
            "target": "current",
            "domain": [("create_uid", "=", self.env.uid)],
        }

    def action_open_receipts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.employee_id.name,
            "res_model": "hr.expense.sheet",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.employee_id.id),
                       ("mizan_advance_id", "!=", False)],
        }
