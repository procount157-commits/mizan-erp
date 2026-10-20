# -*- coding: utf-8 -*-
"""The accountant's tab: what needs the accountant today.

Receipts the manager approved and nobody posted yet, customer invoices past
due, supplier bills due this week, bank lines not matched, and what is still
waiting for the manager. Each list is short and actionable."""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class MizanMobile(models.AbstractModel):
    _inherit = "mizan.mobile"

    @api.model
    def accountant_summary(self):
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("This tab is for accounts."))
        today = fields.Date.context_today(self)
        Move = self.env["account.move"]
        company = self.env.company

        receipts = self.env["hr.expense.sheet"].search(
            [("state", "=", "approve"), ("mizan_advance_id", "!=", False)], order="id desc", limit=30)
        overdue = Move.search([
            ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")), ("invoice_date_due", "<", today),
            ("company_id", "=", company.id)], order="invoice_date_due", limit=15)
        due = Move.search([
            ("move_type", "=", "in_invoice"), ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")), ("invoice_date_due", "<=", today + timedelta(days=7)),
            ("company_id", "=", company.id)], order="invoice_date_due", limit=15)
        bank = self.env["account.bank.statement.line"].search(
            [("is_reconciled", "=", False), ("company_id", "=", company.id)])
        waiting_bills = Move.search_count([("mizan_approval_state", "=", "to_approve")])
        waiting_payments = self.env["mizan.payment.request"].search_count([("state", "=", "to_approve")])

        def late(d):
            return (today - d).days if d else 0

        return {
            "receipts": [{"id": s.id, "title": s.name, "who": s.employee_id.name, "amount": self._money(s.total_amount),
                          "date": s.mizan_date and s.mizan_date.strftime("%d/%m/%Y") or "",
                          "photo": "/web/image/hr.expense.sheet/%d/mizan_photo" % s.id if s.mizan_photo else ""}
                         for s in receipts],
            "overdue": [{"id": m.id, "name": m.name, "who": m.partner_id.name or "", "amount": self._money(m.amount_residual),
                         "late": _("%s days late", late(m.invoice_date_due))} for m in overdue],
            "overdue_total": self._money(sum(overdue.mapped("amount_residual"))),
            "due": [{"id": m.id, "name": m.name, "who": m.partner_id.name or "", "amount": self._money(m.amount_residual),
                     "when": m.invoice_date_due and m.invoice_date_due.strftime("%d/%m") or "",
                     "waiting": m.mizan_approval_state == "to_approve"} for m in due],
            "due_total": self._money(sum(due.mapped("amount_residual"))),
            "bank_count": len(bank), "bank_in": self._money(sum(l.amount for l in bank if l.amount > 0)),
            "bank_out": self._money(-sum(l.amount for l in bank if l.amount < 0)),
            "waiting_manager": waiting_bills + waiting_payments,
        }

    @api.model
    def post_receipts(self, ids):
        sheets = self.env["hr.expense.sheet"].browse([int(i) for i in ids or []]).exists()
        sheets.action_mizan_post()
        self._forget_insights("accountant")
        return self.accountant_summary()
