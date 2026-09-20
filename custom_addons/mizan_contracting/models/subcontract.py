# -*- coding: utf-8 -*-
"""Subcontracts as agreements, not as a pile of supplier bills.

A UAE contractor puts 30-70% of the work out to subcontractors. Treated as
ordinary vendors — which is all the system could do — none of the questions
that decide whether the money is safe have an answer: what did we agree, how
much of it has been certified, what has been varied, what have we back-charged
for his mess, when does his retention come out, and has his insurance lapsed.

So a subcontract is its own document. Its certified value flows to the job's
cost code as committed cost until the bill arrives, and its retention and
back-charges reduce what he is paid without losing what he is owed.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanSubcontract(models.Model):
    _name = "mizan.subcontract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Subcontract"
    _order = "code"
    _rec_name = "code"

    code = fields.Char(string="Subcontract No.", required=True, copy=False,
                       tracking=True)
    name = fields.Char(string="Scope", required=True, tracking=True)
    contract_id = fields.Many2one(
        "mizan.contract", string="Main Contract", required=True,
        ondelete="restrict", index=True, tracking=True)
    partner_id = fields.Many2one(
        "res.partner", string="Subcontractor", required=True,
        domain="[('is_company', '=', True)]", tracking=True)
    cost_code_id = fields.Many2one(
        "mizan.cost.code", string="Cost Code", required=True,
        help="The trade this agreement covers. Its value lands here as "
             "committed cost until the subcontractor bills.")
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")

    date_start = fields.Date(tracking=True)
    date_end = fields.Date(tracking=True)
    order_value = fields.Monetary(required=True, tracking=True)
    variation_total = fields.Monetary(
        compute="_compute_totals", store=True, string="Variations")
    revised_value = fields.Monetary(compute="_compute_totals", store=True)

    retention_percent = fields.Float(
        string="Retention %", default=5.0,
        help="Held back from every certificate until the defects period ends.")
    backcharge_total = fields.Monetary(
        compute="_compute_totals", store=True, string="Back-charges",
        help="What we spent putting his work right, recovered from him.")

    certified_total = fields.Monetary(compute="_compute_certified")
    invoiced_total = fields.Monetary(compute="_compute_certified")
    retention_held = fields.Monetary(compute="_compute_certified")
    paid_total = fields.Monetary(compute="_compute_certified")
    outstanding = fields.Monetary(compute="_compute_certified")
    committed_remaining = fields.Monetary(
        compute="_compute_certified",
        help="Agreed and not yet certified: the exposure still to come.")
    percent_certified = fields.Float(compute="_compute_certified")

    insurance_expiry = fields.Date(
        help="Lapsed insurance on site is the contractor's problem, not his.")
    insurance_expiring = fields.Boolean(compute="_compute_insurance")

    variation_ids = fields.One2many("mizan.subcontract.variation", "subcontract_id")
    backcharge_ids = fields.One2many("mizan.subcontract.backcharge", "subcontract_id")
    bill_ids = fields.One2many("account.move", "mizan_subcontract_id")
    bill_count = fields.Integer(compute="_compute_certified")

    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"),
         ("closed", "Closed"), ("cancel", "Cancelled")],
        default="draft", required=True, tracking=True)
    note = fields.Text()

    _sql_constraints = [
        ("code_uniq", "unique(code, company_id)",
         "That subcontract number already exists."),
    ]

    @api.depends("order_value", "variation_ids.amount", "variation_ids.state",
                 "backcharge_ids.amount", "backcharge_ids.state")
    def _compute_totals(self):
        for record in self:
            approved = record.variation_ids.filtered(
                lambda v: v.state == "approved")
            record.variation_total = sum(approved.mapped("amount"))
            record.revised_value = record.order_value + record.variation_total
            charged = record.backcharge_ids.filtered(
                lambda b: b.state in ("applied", "recovered"))
            record.backcharge_total = sum(charged.mapped("amount"))

    def _compute_certified(self):
        for record in self:
            bills = record.bill_ids.filtered(lambda m: m.state == "posted")
            record.bill_count = len(bills)
            invoiced = sum(bills.mapped("amount_untaxed"))
            record.invoiced_total = invoiced
            record.certified_total = invoiced
            record.retention_held = sum(bills.mapped("mizan_retention_amount"))
            record.paid_total = invoiced - sum(bills.mapped("amount_residual"))
            record.outstanding = sum(bills.mapped("amount_residual"))
            record.committed_remaining = max(
                record.revised_value - invoiced, 0.0)
            record.percent_certified = (
                (invoiced / record.revised_value * 100)
                if record.revised_value else 0.0)

    @api.depends("insurance_expiry")
    def _compute_insurance(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.insurance_expiring = bool(
                record.insurance_expiry
                and (record.insurance_expiry - today).days <= 30)

    def action_activate(self):
        self.write({"state": "active"})

    def action_close(self):
        for record in self:
            if record.retention_held > 0:
                raise UserError(_(
                    "%s still holds %s of retention. Release it before closing.",
                    record.code, record.retention_held))
        self.write({"state": "closed"})

    def action_view_bills(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bills for %s", self.code),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("mizan_subcontract_id", "=", self.id)],
            "context": {"default_mizan_subcontract_id": self.id,
                        "default_move_type": "in_invoice"},
        }


class MizanSubcontractVariation(models.Model):
    _name = "mizan.subcontract.variation"
    _description = "Subcontract Variation"
    _order = "date desc, id desc"

    name = fields.Char(string="Description", required=True)
    reference = fields.Char(string="VO No.", required=True)
    subcontract_id = fields.Many2one(
        "mizan.subcontract", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="subcontract_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft", required=True)

    def action_approve(self):
        self.write({"state": "approved"})

    def action_reject(self):
        self.write({"state": "rejected"})


class MizanSubcontractBackcharge(models.Model):
    """What we spent fixing his work, recovered from what he is owed."""

    _name = "mizan.subcontract.backcharge"
    _description = "Back-charge"
    _order = "date desc, id desc"

    name = fields.Char(string="Reason", required=True)
    subcontract_id = fields.Many2one(
        "mizan.subcontract", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="subcontract_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("applied", "Applied"),
         ("recovered", "Recovered"), ("waived", "Waived")],
        default="draft", required=True)
    note = fields.Text()

    def action_apply(self):
        self.write({"state": "applied"})

    def action_waive(self):
        self.write({"state": "waived"})


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_subcontract_id = fields.Many2one(
        "mizan.subcontract", string="Subcontract", copy=False, index=True,
        help="Ties this bill to the agreement it is drawn against.")

    @api.onchange("mizan_subcontract_id")
    def _onchange_subcontract(self):
        """Carry the agreement's terms onto the bill."""
        if self.mizan_subcontract_id:
            self.partner_id = self.mizan_subcontract_id.partner_id
            self.mizan_contract_id = self.mizan_subcontract_id.contract_id
            self.mizan_retention_percent = (
                self.mizan_subcontract_id.retention_percent)
