# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

WAITING = ("submit", "approve")


class MizanEmployeeAdvance(models.Model):
    _inherit = "mizan.employee.advance"

    mizan_topup = fields.Boolean(
        string="Petty Cash Top-up", readonly=True, copy=False,
        help="Replenishes cash the employee already holds. Unlike a new "
             "advance, a top-up is expected while the last one is still "
             "being spent; the ceiling still applies to the total held.")

    def _check_allowed(self):
        """A top-up is meant to arrive before the last float is used up, so
        "settle the first one before a second" would refuse every top-up. The
        ceiling then applies to everything the employee would be holding."""
        self.ensure_one()
        if not self.mizan_topup:
            return super()._check_allowed()
        held = sum(self._outstanding_advances().filtered(
            lambda other: other.amount_outstanding > 0).mapped("amount_outstanding"))
        limit = self.company_id.mizan_advance_limit
        if limit and held + self.amount > limit:
            if not self.env.user.has_group("mizan_advance.group_advance_override"):
                raise UserError(_(
                    "%(name)s already holds %(held)s. A top-up of %(amount)s "
                    "would take it above the limit of %(limit)s.",
                    name=self.employee_id.name, held="{:,.2f}".format(held),
                    amount="{:,.2f}".format(self.amount),
                    limit="{:,.2f}".format(limit)))
            self.override_by_id = self.env.user
            self.override_reason = _("Top-up above the petty cash limit")

    def action_submit(self):
        res = super().action_submit()
        # Somebody has to know it was asked for: the employee's manager, or
        # whoever approves his expenses.
        for advance in self:
            approver = (advance.employee_id.parent_id.user_id
                        or advance.employee_id.expense_manager_id)
            if approver and approver != self.env.user:
                advance.activity_schedule(
                    "mail.mail_activity_data_todo", user_id=approver.id,
                    summary=_("Approve %(kind)s of %(amount)s for %(name)s",
                              kind=_("a petty cash top-up") if advance.mizan_topup
                              else _("an advance"),
                              amount="{:,.2f}".format(advance.amount),
                              name=advance.employee_id.name))
        return res

    # ------------------------------------------------------------ figures
    @api.model
    def _petty_cash(self, employee):
        """What one employee holds, has waiting, and can still spend.

        Held is the advance balance the ledger agrees with: paid, less claims
        posted against it, less cash returned. Waiting is what he has claimed
        and nobody has posted yet — still in his hand on paper, already spent
        in fact, so "available" takes it off."""
        advances = self.search([("employee_id", "=", employee.id),
                                ("state", "=", "paid")], order="date, id")
        held = sum(advances.mapped("amount_outstanding"))
        waiting_sheets = advances.expense_sheet_ids.filtered(
            lambda sheet: sheet.state in WAITING)
        waiting = sum(waiting_sheets.mapped("total_amount"))
        return {
            "advances": advances,
            "held": held,
            "waiting": waiting,
            "waiting_count": len(waiting_sheets),
            "available": held - waiting,
            "currency": employee.company_id.currency_id or self.env.company.currency_id,
        }

    @api.model
    def action_request_topup(self):
        employee = self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid)], limit=1)
        if not employee:
            raise UserError(_("Your login is not linked to an employee record."))
        cash = self._petty_cash(employee)
        # What he has spent from the float is what brings it back to where it
        # started — the usual imprest top-up.
        spent = sum(cash["advances"].mapped("amount_spent")) + cash["waiting"]
        return {
            "type": "ir.actions.act_window",
            "name": _("Ask for a Top-up"),
            "res_model": "mizan.employee.advance",
            "view_mode": "form",
            "views": [(self.env.ref("mizan_pettycash.view_topup_form").id, "form")],
            "target": "new",
            "context": {
                "default_employee_id": employee.id,
                "default_mizan_topup": True,
                "default_amount": spent or False,
                "default_purpose": _("Petty cash top-up"),
                "default_project_id": self.env["mizan.site.capture"]._default_project().id,
            },
        }

    def action_send_topup(self):
        self.ensure_one()
        if not self.mizan_topup:
            self.mizan_topup = True
        self.action_submit()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Sent"), "type": "success",
                       "message": _("Your top-up request went to your manager."),
                       "next": {"type": "ir.actions.act_window_close"}},
        }
