# -*- coding: utf-8 -*-
"""Two approvals the manager asked for that did not exist yet.

* A supplier bill at or above the company's limit waits for approval once
  posted: it cannot be paid until the manager approves it.
* A payment to a subcontractor becomes a request; the manager's approval
  posts it (bank, retention, reconciliation) exactly as the payment screen
  did, so nothing changes for the books — only who says yes."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_bill_approval_amount = fields.Monetary(
        string="Supplier bills need the manager's approval from", currency_field="currency_id", default=10000.0,
        help="A posted supplier bill at or above this amount cannot be paid until a manager approves it. 0 turns it off.")
    mizan_sc_payment_approval = fields.Boolean(
        string="Subcontractor payments need the manager's approval", default=True)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_bill_approval_amount = fields.Monetary(related="company_id.mizan_bill_approval_amount",
                                                 readonly=False, currency_field="currency_id")
    mizan_sc_payment_approval = fields.Boolean(related="company_id.mizan_sc_payment_approval", readonly=False)


def _is_manager(env):
    user = env.user
    return (user.has_group("mizan_owner.group_owner") or user.has_group("mizan_hub.group_general_manager")
            or user.has_group("account.group_account_manager"))


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_approval_state = fields.Selection([
        ("to_approve", "Waiting for the manager"), ("approved", "Approved"), ("refused", "Refused"),
    ], string="Manager's approval", copy=False, tracking=True, readonly=True)
    mizan_approved_by_id = fields.Many2one("res.users", string="Approved by", copy=False, readonly=True)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted:
            limit = move.company_id.mizan_bill_approval_amount
            if (move.move_type == "in_invoice" and limit and move.amount_total >= limit
                    and not move.mizan_approval_state):
                move.mizan_approval_state = "to_approve"
        return posted

    def action_mizan_approve_bill(self):
        if not _is_manager(self.env):
            raise UserError(_("Only a manager can approve supplier bills."))
        self.filtered(lambda m: m.mizan_approval_state == "to_approve").write(
            {"mizan_approval_state": "approved", "mizan_approved_by_id": self.env.user.id})
        return True

    def action_mizan_refuse_bill(self):
        if not _is_manager(self.env):
            raise UserError(_("Only a manager can refuse supplier bills."))
        self.filtered(lambda m: m.mizan_approval_state == "to_approve").write({"mizan_approval_state": "refused"})
        return True

    def action_register_payment(self):
        waiting = self.filtered(lambda m: m.mizan_approval_state in ("to_approve", "refused"))
        if waiting:
            raise UserError(_("%s is waiting for the manager's approval and cannot be paid yet.",
                              ", ".join(waiting.mapped("display_name"))))
        return super().action_register_payment()


class MizanPaymentRequest(models.Model):
    _name = "mizan.payment.request"
    _description = "Subcontractor payment waiting for approval"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    subcontract_id = fields.Many2one("mizan.subcontract", required=True, readonly=True)
    partner_id = fields.Many2one(related="subcontract_id.partner_id", store=True)
    contract_id = fields.Many2one(related="subcontract_id.contract_id", store=True)
    company_id = fields.Many2one(related="subcontract_id.company_id", store=True)
    currency_id = fields.Many2one(related="subcontract_id.currency_id")
    bill_ids = fields.Many2many("account.move", string="Bills", readonly=True)
    amount = fields.Monetary(string="To pay", readonly=True)
    retention_amount = fields.Monetary(string="Retention withheld", readonly=True)
    journal_id = fields.Many2one("account.journal", string="Paid from", readonly=True)
    date = fields.Date(readonly=True)
    reference = fields.Char(readonly=True)
    requested_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)
    state = fields.Selection([("to_approve", "Waiting for the manager"), ("paid", "Approved and paid"),
                              ("refused", "Refused")], default="to_approve", readonly=True, tracking=True)
    move_id = fields.Many2one("account.move", string="Payment entry", readonly=True)

    @api.depends("subcontract_id", "amount")
    def _compute_name(self):
        for req in self:
            req.name = "%s — %s" % (req.subcontract_id.code or "", req.partner_id.name or "")

    def action_approve(self):
        if not _is_manager(self.env):
            raise UserError(_("Only a manager can approve payments to subcontractors."))
        for req in self.filtered(lambda r: r.state == "to_approve"):
            wizard = self.env["mizan.subcontract.payment"].sudo().create({
                "subcontract_id": req.subcontract_id.id, "bill_ids": [(6, 0, req.bill_ids.ids)],
                "amount": req.amount, "retention_amount": req.retention_amount,
                "journal_id": req.journal_id.id, "date": req.date or fields.Date.context_today(self),
                "reference": req.reference,
            })
            wizard.with_context(mizan_approved_payment=True)._mizan_post_payment()
            move = self.env["account.move"].sudo().search(
                [("mizan_subcontract_id", "=", req.subcontract_id.id), ("mizan_source_kind", "=", "sc_payment")],
                order="id desc", limit=1)
            req.write({"state": "paid", "move_id": move.id})
            req.message_post(body=_("Approved by %s and paid.", self.env.user.name))
        return True

    def action_refuse(self):
        if not _is_manager(self.env):
            raise UserError(_("Only a manager can refuse payments to subcontractors."))
        self.filtered(lambda r: r.state == "to_approve").write({"state": "refused"})
        return True


class MizanSubcontractPayment(models.TransientModel):
    _inherit = "mizan.subcontract.payment"

    def _mizan_post_payment(self):
        return super().action_pay()

    def action_pay(self):
        """With approvals on, the payment waits for the manager; a manager
        paying approves it in the same breath."""
        self.ensure_one()
        company = self.subcontract_id.company_id
        if (not company.mizan_sc_payment_approval or self.env.context.get("mizan_approved_payment")
                or _is_manager(self.env)):
            return self._mizan_post_payment()
        if self.amount < 0 or self.retention_amount < 0 or self.total <= 0:
            raise UserError(_("Type the amount paid and the retention withheld."))
        req = self.env["mizan.payment.request"].create({
            "subcontract_id": self.subcontract_id.id, "bill_ids": [(6, 0, self.bill_ids.ids)],
            "amount": self.amount, "retention_amount": self.retention_amount,
            "journal_id": self.journal_id.id, "date": self.date, "reference": self.reference,
        })
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Sent for approval"), "type": "info",
                       "message": _("The payment of %(a)s to %(p)s waits for the manager's approval (%(r)s).",
                                    a=self.amount, p=self.subcontract_id.partner_id.name, r=req.name),
                       "next": {"type": "ir.actions.act_window_close"}},
        }
