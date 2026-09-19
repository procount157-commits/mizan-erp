# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanContract(models.Model):
    _name = "mizan.contract"
    _description = "Construction Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Contract No.", required=True, copy=False, tracking=True)
    partner_id = fields.Many2one(
        "res.partner", string="Client", required=True, tracking=True)
    project_id = fields.Many2one("project.project", string="Project")
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Cost Center", required=True,
        help="Costs posted to this cost center are what drive the progress "
             "calculation, so every job cost must carry it.")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    date_start = fields.Date(string="Start Date", tracking=True)
    date_end = fields.Date(string="Completion Date", tracking=True)

    state = fields.Selection(
        [("draft", "Draft"), ("running", "In Progress"),
         ("done", "Completed"), ("cancel", "Cancelled")],
        default="draft", required=True, tracking=True)

    contract_value = fields.Monetary(
        string="Contract Value", required=True, tracking=True,
        help="Total revenue expected over the life of the contract.")
    budget_cost = fields.Monetary(
        string="Budgeted Cost", required=True, tracking=True,
        help="Total cost expected to complete. Progress is measured against it, "
             "so revising it revises revenue for every later period.")
    retention_percent = fields.Float(
        string="Retention %", default=5.0,
        help="Share of each progress claim the client withholds until handover.")

    # --- progress ---------------------------------------------------------
    cost_incurred = fields.Monetary(
        string="Cost to Date", compute="_compute_cost_incurred", store=False,
        help="Sum of analytic costs booked against the cost center.")
    completion_percent = fields.Float(
        string="% Complete", compute="_compute_completion", store=False)
    revenue_earned = fields.Monetary(
        string="Revenue Earned", compute="_compute_completion", store=False,
        help="Contract value × % complete — the revenue IFRS 15 says belongs "
             "to work done so far.")
    revenue_recognised = fields.Monetary(
        string="Already Recognised", compute="_compute_recognised", store=False)
    revenue_to_recognise = fields.Monetary(
        string="To Recognise", compute="_compute_recognised", store=False)

    recognition_ids = fields.One2many(
        "mizan.contract.recognition", "contract_id", string="Recognitions")
    recognition_count = fields.Integer(compute="_compute_recognition_count")

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)",
         "Another contract already uses this number."),
    ]

    @api.depends("analytic_account_id")
    def _compute_cost_incurred(self):
        Line = self.env["account.analytic.line"]
        for contract in self:
            if not contract.analytic_account_id:
                contract.cost_incurred = 0.0
                continue
            lines = Line.search([
                ("account_id", "=", contract.analytic_account_id.id),
                ("amount", "<", 0),
            ])
            # Analytic costs are stored negative; report them as a positive cost.
            contract.cost_incurred = -sum(lines.mapped("amount"))

    @api.depends("cost_incurred", "budget_cost", "contract_value")
    def _compute_completion(self):
        for contract in self:
            if contract.budget_cost <= 0:
                contract.completion_percent = 0.0
            else:
                # Cost overruns must not claim more than the contract is worth.
                ratio = contract.cost_incurred / contract.budget_cost
                contract.completion_percent = min(ratio, 1.0) * 100
            contract.revenue_earned = (
                contract.contract_value * contract.completion_percent / 100)

    @api.depends("recognition_ids.amount", "recognition_ids.state", "revenue_earned")
    def _compute_recognised(self):
        for contract in self:
            posted = contract.recognition_ids.filtered(
                lambda r: r.state == "posted")
            contract.revenue_recognised = sum(posted.mapped("amount"))
            contract.revenue_to_recognise = (
                contract.revenue_earned - contract.revenue_recognised)

    @api.depends("recognition_ids")
    def _compute_recognition_count(self):
        for contract in self:
            contract.recognition_count = len(contract.recognition_ids)

    def action_start(self):
        self.write({"state": "running"})

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_draft(self):
        self.write({"state": "draft"})

    def action_create_recognition(self):
        """Create a draft recognition entry for the revenue earned but not yet booked."""
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Only a contract in progress can recognise revenue."))
        amount = self.revenue_to_recognise
        if self.currency_id.is_zero(amount):
            raise UserError(_(
                "There is no new revenue to recognise: work done so far is "
                "already fully booked."))
        recognition = self.env["mizan.contract.recognition"].create({
            "contract_id": self.id,
            "date": fields.Date.context_today(self),
            "amount": amount,
            "completion_percent": self.completion_percent,
            "cost_incurred": self.cost_incurred,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "mizan.contract.recognition",
            "res_id": recognition.id,
            "views": [[False, "form"]],
            "target": "current",
        }

    def action_view_recognitions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Revenue Recognitions"),
            "res_model": "mizan.contract.recognition",
            "domain": [("contract_id", "=", self.id)],
            "views": [[False, "list"], [False, "form"]],
            "context": {"default_contract_id": self.id},
        }


class MizanContractRecognition(models.Model):
    _name = "mizan.contract.recognition"
    _description = "Contract Revenue Recognition"
    _order = "date desc, id desc"

    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")

    date = fields.Date(required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string="Revenue Recognised", required=True)
    completion_percent = fields.Float(string="% Complete at Date", readonly=True)
    cost_incurred = fields.Monetary(string="Cost to Date", readonly=True)

    retention_amount = fields.Monetary(
        string="Retention Withheld", compute="_compute_retention", store=True)
    net_amount = fields.Monetary(
        string="Net Claim", compute="_compute_retention", store=True)

    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True)
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted")],
        default="draft", required=True)

    journal_id = fields.Many2one(
        "account.journal", string="Journal", domain="[('type', '=', 'general')]",
        default=lambda self: self.env["account.journal"].search(
            [("type", "=", "general")], limit=1))
    def _default_revenue_account(self):
        """The contract revenue account from the chart we ship.

        Defaulted rather than left blank because an accountant who has to pick
        the account on every recognition will eventually pick a different one,
        and then revenue for the same contract lands in two places.
        """
        return self.env["account.account"].search(
            [("code", "=", "501001")], limit=1)

    def _default_wip_account(self):
        return self.env["account.account"].search(
            [("code", "=", "107002")], limit=1)

    revenue_account_id = fields.Many2one(
        "account.account", string="Revenue Account",
        domain="[('account_type', '=', 'income')]",
        default=lambda self: self._default_revenue_account())
    wip_account_id = fields.Many2one(
        "account.account", string="Accrued Revenue Account",
        domain="[('account_type', 'in', ('asset_current', 'asset_receivable'))]",
        default=lambda self: self._default_wip_account(),
        help="Work in progress: revenue earned that has not been invoiced yet.")

    @api.depends("amount", "contract_id.retention_percent")
    def _compute_retention(self):
        for rec in self:
            rec.retention_amount = (
                rec.amount * rec.contract_id.retention_percent / 100)
            rec.net_amount = rec.amount - rec.retention_amount

    def action_post(self):
        for rec in self:
            if rec.state == "posted":
                continue
            if not (rec.journal_id and rec.revenue_account_id and rec.wip_account_id):
                raise UserError(_(
                    "Set the journal, revenue account and accrued revenue account "
                    "before posting."))
            analytic = rec.contract_id.analytic_account_id
            distribution = {str(analytic.id): 100} if analytic else False
            move = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": rec.journal_id.id,
                "date": rec.date,
                "ref": _("Revenue recognition %(pct).1f%% — %(contract)s",
                         pct=rec.completion_percent, contract=rec.contract_id.name),
                "line_ids": [
                    (0, 0, {
                        "name": _("Accrued revenue"),
                        "account_id": rec.wip_account_id.id,
                        "debit": rec.amount,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "name": _("Contract revenue"),
                        "account_id": rec.revenue_account_id.id,
                        "debit": 0.0,
                        "credit": rec.amount,
                        "analytic_distribution": distribution,
                    }),
                ],
            })
            move.action_post()
            rec.write({"move_id": move.id, "state": "posted"})

    def action_view_move(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "views": [[False, "form"]],
        }
