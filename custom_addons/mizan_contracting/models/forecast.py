# -*- coding: utf-8 -*-
"""Percentage of completion measured the way the standard requires.

The original code measured progress as cost incurred over the ORIGINAL budget,
capped at 100%. Both halves of that are wrong on a real job.

IFRS 15 (and IAS 11 before it) measure progress against the cost expected to be
incurred in total — cost to date divided by the estimate at completion, not by
the budget agreed before anyone broke ground. A job running 20% over budget is
not 120% complete; it is perhaps 85% complete on a larger number. Dividing by
the original budget overstates progress exactly when a job is going wrong, so
revenue is recognised fastest on the contracts least able to support it, and the
cap at 100% then hides the overrun altogether.

The second half matters more. When the estimate at completion exceeds what the
client will pay, the contract is loss-making, and the whole of that loss is
recognised immediately — not spread over the remaining months. That is the
provision this adds, and the account for it (204005) already existed in the
chart, unused, because nothing ever wrote to it.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    # ------------------------------------------------------------ variations
    variation_ids = fields.One2many(
        "mizan.contract.variation", "contract_id", string="Variation Orders")
    variation_approved = fields.Monetary(
        string="Approved Variations", compute="_compute_variations", store=True)
    variation_pending = fields.Monetary(
        string="Pending Variations", compute="_compute_variations", store=True)
    revised_contract_value = fields.Monetary(
        string="Revised Contract Value", compute="_compute_variations", store=True,
        help="Original value plus approved variations. Pending variations are "
             "excluded: they are not yet money the client has agreed to pay.")

    @api.depends("contract_value", "variation_ids.amount", "variation_ids.state",
                 "variation_ids.cost_impact")
    def _compute_variations(self):
        for contract in self:
            approved = contract.variation_ids.filtered(
                lambda v: v.state == "approved")
            pending = contract.variation_ids.filtered(
                lambda v: v.state == "submitted")
            contract.variation_approved = sum(approved.mapped("amount"))
            contract.variation_pending = sum(pending.mapped("amount"))
            contract.revised_contract_value = (
                contract.contract_value + contract.variation_approved)

    # ------------------------------------------------- estimate at completion
    cost_to_complete = fields.Monetary(
        string="Cost to Complete",
        help="What the site team expects the rest of the job to cost. Leave "
             "empty and the original budget is assumed, which is only true "
             "while nothing has gone wrong.")
    cost_at_completion = fields.Monetary(
        string="Estimate at Completion",
        compute="_compute_forecast", store=True,
        help="Cost to date plus cost to complete: the total this job is now "
             "expected to cost.")
    revised_budget_cost = fields.Monetary(
        string="Revised Budget", compute="_compute_variations", store=True)
    forecast_margin = fields.Monetary(
        string="Forecast Margin", compute="_compute_forecast", store=True)
    forecast_margin_percent = fields.Float(
        string="Forecast Margin %", compute="_compute_forecast", store=True)
    is_loss_making = fields.Boolean(compute="_compute_forecast", store=True)
    loss_provision_required = fields.Monetary(
        string="Loss Provision Required", compute="_compute_forecast", store=True,
        help="The whole expected loss. A foreseeable loss is recognised as soon "
             "as it is foreseen, not spread over the remaining work.")
    loss_provision_booked = fields.Monetary(
        string="Loss Provision Booked", readonly=True, copy=False)
    loss_provision_move_id = fields.Many2one(
        "account.move", string="Provision Entry", readonly=True, copy=False)

    @api.depends("cost_incurred", "cost_to_complete", "budget_cost",
                 "revised_contract_value", "variation_ids.cost_impact",
                 "variation_ids.state")
    def _compute_forecast(self):
        for contract in self:
            approved = contract.variation_ids.filtered(
                lambda v: v.state == "approved")
            revised_budget = contract.budget_cost + sum(
                approved.mapped("cost_impact"))
            # With no estimate from the site, the budget is the only figure we
            # have. It is a starting assumption, not a forecast.
            if contract.cost_to_complete:
                eac = contract.cost_incurred + contract.cost_to_complete
            else:
                eac = max(revised_budget, contract.cost_incurred)
            contract.cost_at_completion = eac
            value = contract.revised_contract_value or contract.contract_value
            contract.forecast_margin = value - eac
            contract.forecast_margin_percent = (
                (contract.forecast_margin / value * 100) if value else 0.0)
            contract.is_loss_making = contract.forecast_margin < 0
            contract.loss_provision_required = (
                -contract.forecast_margin if contract.forecast_margin < 0 else 0.0)

    def action_book_loss_provision(self):
        """Recognise the whole foreseeable loss now."""
        for contract in self:
            outstanding = (contract.loss_provision_required
                           - contract.loss_provision_booked)
            if outstanding <= 0.005:
                raise UserError(_(
                    "%s has no unprovided loss.", contract.code))
            Account = self.env["account.account"]
            expense = Account.search([("code", "=", "401011")], limit=1)
            provision = Account.search([("code", "=", "204005")], limit=1)
            if not expense or not provision:
                raise UserError(_(
                    "Accounts 401011 and 204005 are needed. Run "
                    "scripts/complete_coa.py against this database."))
            journal = self.env["account.journal"].search(
                [("type", "=", "general"),
                 ("company_id", "=", contract.company_id.id)], limit=1)
            label = _("Foreseeable loss on %s", contract.code)
            entry = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": fields.Date.context_today(self),
                "ref": label,
                "line_ids": [
                    (0, 0, {"account_id": expense.id, "name": label,
                            "debit": outstanding, "credit": 0.0,
                            "analytic_distribution": {
                                str(contract.analytic_account_id.id): 100}
                            if contract.analytic_account_id else False}),
                    (0, 0, {"account_id": provision.id, "name": label,
                            "debit": 0.0, "credit": outstanding}),
                ],
            })
            entry.action_post()
            contract.write({
                "loss_provision_booked": contract.loss_provision_required,
                "loss_provision_move_id": entry.id,
            })
        return True


class MizanContractVariation(models.Model):
    """A change to the scope, priced and tracked separately.

    Contract value as a single figure cannot answer the question every dispute
    turns on: what was originally agreed, what was varied, by whom, and when.
    Pending variations are deliberately excluded from the revised value —
    recognising revenue on work the client has not yet agreed to pay for is how
    contractors end up writing it off.
    """

    _name = "mizan.contract.variation"
    _description = "Variation Order"
    _order = "date desc, id desc"

    name = fields.Char(string="Description", required=True)
    reference = fields.Char(string="VO No.", required=True, copy=False)
    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(
        string="Value Change", required=True,
        help="What the client will pay for this change. Negative for omissions.")
    cost_impact = fields.Monetary(
        string="Cost Impact", help="What it is expected to cost to build.")
    margin = fields.Monetary(compute="_compute_margin", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"),
         ("approved", "Approved"), ("rejected", "Rejected")],
        default="draft", required=True)
    approved_by = fields.Char(string="Approved By (Client)")
    note = fields.Text()

    _sql_constraints = [
        ("reference_uniq", "unique(contract_id, reference)",
         "That variation number already exists on this contract."),
    ]

    @api.depends("amount", "cost_impact")
    def _compute_margin(self):
        for variation in self:
            variation.margin = variation.amount - variation.cost_impact

    def action_submit(self):
        self.write({"state": "submitted"})

    def action_approve(self):
        self.write({"state": "approved"})

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_draft(self):
        self.write({"state": "draft"})


class MizanContractWipFigures(models.Model):
    """Work in progress, as columns on the contract itself.

    First attempt made this a SQL view, which cannot work: cost to date,
    completion and revenue earned are computed from analytic lines and are not
    stored, so there are no columns for a view to select. Reading them in
    Python is also the only way the figures stay correct the moment a cost is
    posted, rather than whenever someone remembers to refresh.
    """

    _inherit = "mizan.contract"

    billed_to_date = fields.Monetary(
        string="Billed to Date", compute="_compute_wip",
        help="Claims raised against this contract, net of tax.")
    over_billing = fields.Monetary(
        string="Billings in Excess of Work", compute="_compute_wip",
        help="Billed beyond what the work has earned — owed back to the client "
             "in work, not profit.")
    under_billing = fields.Monetary(
        string="Work in Excess of Billings", compute="_compute_wip",
        help="Earned beyond what has been billed — work done that nobody has "
             "been invoiced for.")
    retention_held = fields.Monetary(
        string="Retention Held by Client", compute="_compute_wip")

    def _compute_wip(self):
        Line = self.env["account.move.line"]
        for contract in self:
            billed = retention = 0.0
            analytic = contract.analytic_account_id
            if analytic:
                # Claims credit the progress-billing account, never revenue, so
                # this counts what the client was asked for rather than what
                # the work earned. The two differ by design.
                claims = Line.search([
                    ("parent_state", "=", "posted"),
                    ("move_id.move_type", "in", ("out_invoice", "out_refund")),
                    ("account_id.code", "=like", "204%"),
                ])
                for line in claims:
                    share = (line.analytic_distribution or {}).get(str(analytic.id))
                    if share:
                        billed += -line.balance * share / 100.0
            if contract.partner_id:
                held = Line.search([
                    ("parent_state", "=", "posted"),
                    ("partner_id", "=", contract.partner_id.id),
                    ("account_id.code", "=", "107003"),
                ])
                retention = sum(held.mapped("balance"))
            contract.billed_to_date = billed
            contract.retention_held = retention
            earned = contract.revenue_earned
            contract.over_billing = max(billed - earned, 0.0)
            contract.under_billing = max(earned - billed, 0.0)
