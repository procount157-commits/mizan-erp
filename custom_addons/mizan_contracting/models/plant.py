# -*- coding: utf-8 -*-
"""Charging owned plant to the jobs that used it.

An excavator the company owns and runs on a job for two months costs that job
money — the depreciation, the fuel, the servicing, the operator. Left where it
lands, all of that sits on the company as a whole, so the job looks cheaper
than it was and the next tender is priced from a margin that never existed.
Al Amana carried 63,750 of plant depreciation outside any job for exactly this
reason.

Every specialist system solves it the same way: an internal hire rate per hour
or per day, charged to the job and credited to a plant recovery account. What
the plant actually costs then sits against what it recovered, and the balance
says whether owning it beats hiring it.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanPlant(models.Model):
    _name = "mizan.plant"
    _description = "Plant & Equipment"
    _order = "code"
    _rec_name = "code"

    code = fields.Char(required=True, copy=False)
    name = fields.Char(required=True, translate=True)
    equipment_id = fields.Many2one(
        "maintenance.equipment", string="Maintenance Record",
        help="Links to the servicing history already kept for this machine.")
    asset_account_id = fields.Many2one(
        "account.account", string="Asset Account",
        domain="[('account_type', '=', 'asset_fixed')]")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")

    rate_basis = fields.Selection(
        [("hour", "Per Hour"), ("day", "Per Day"), ("month", "Per Month")],
        default="day", required=True)
    internal_rate = fields.Monetary(
        string="Internal Hire Rate", required=True,
        help="What a job is charged for using this machine. Set it from what "
             "the machine costs to own and run, not from the market hire rate "
             "— the point is to recover cost, not to make a margin on yourself.")
    active = fields.Boolean(default=True)

    charge_ids = fields.One2many("mizan.plant.charge", "plant_id")
    recovered_total = fields.Monetary(compute="_compute_recovery")
    cost_total = fields.Monetary(compute="_compute_recovery")
    recovery_balance = fields.Monetary(
        compute="_compute_recovery",
        help="Recovered from jobs less what the machine actually cost. "
             "Persistently negative means it is cheaper to hire one.")

    _sql_constraints = [
        ("code_uniq", "unique(code, company_id)",
         "That plant number already exists."),
    ]

    def _compute_recovery(self):
        Line = self.env["account.move.line"]
        for plant in self:
            posted = plant.charge_ids.filtered(lambda c: c.state == "posted")
            plant.recovered_total = sum(posted.mapped("amount"))
            costs = 0.0
            if plant.asset_account_id:
                # What this machine actually cost: anything posted against it.
                entries = Line.search([
                    ("parent_state", "=", "posted"),
                    ("mizan_plant_id", "=", plant.id),
                    ("account_id.account_type", "in",
                     ("expense_direct_cost", "expense", "expense_depreciation")),
                ])
                costs = sum(entries.mapped("balance"))
            plant.cost_total = costs
            plant.recovery_balance = plant.recovered_total - costs


class MizanPlantCharge(models.Model):
    """One machine on one job for a measured time."""

    _name = "mizan.plant.charge"
    _description = "Plant Charge"
    _order = "date desc, id desc"

    plant_id = fields.Many2one(
        "mizan.plant", required=True, ondelete="restrict", index=True)
    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="restrict", index=True)
    cost_code_id = fields.Many2one(
        "mizan.cost.code", string="Cost Code",
        help="Defaults to the owned-plant code so the charge lands with the "
             "rest of the plant cost.")
    company_id = fields.Many2one(related="plant_id.company_id", store=True)
    currency_id = fields.Many2one(related="plant_id.currency_id")

    date = fields.Date(required=True, default=fields.Date.context_today)
    quantity = fields.Float(required=True, default=1.0)
    rate = fields.Monetary(required=True)
    amount = fields.Monetary(compute="_compute_amount", store=True)
    note = fields.Char()
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Charged")],
        default="draft", required=True)

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for charge in self:
            charge.amount = charge.quantity * charge.rate

    @api.onchange("plant_id")
    def _onchange_plant(self):
        if self.plant_id:
            self.rate = self.plant_id.internal_rate
            if not self.cost_code_id:
                self.cost_code_id = self.env["mizan.cost.code"].search(
                    [("code", "=", "30-200")], limit=1)

    def action_post(self):
        """Charge the job and credit plant recovery."""
        for charge in self:
            if charge.move_id:
                raise UserError(_("Already charged."))
            Account = self.env["account.account"]
            expense = (charge.cost_code_id.account_id
                       or Account.search([("code", "=", "401013")], limit=1))
            recovery = Account.search([("code", "=", "401014")], limit=1)
            if not recovery:
                raise UserError(_(
                    "Account 401014 (plant recovery) is missing. Run "
                    "scripts/complete_coa.py against this database."))
            journal = self.env["account.journal"].search(
                [("type", "=", "general"),
                 ("company_id", "=", charge.company_id.id)], limit=1)
            analytic = charge.contract_id.analytic_account_id
            label = _("Plant %(plant)s on %(contract)s",
                      plant=charge.plant_id.code,
                      contract=charge.contract_id.code)
            entry = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": charge.date,
                "ref": label,
                "line_ids": [
                    (0, 0, {"account_id": expense.id, "name": label,
                            "debit": charge.amount, "credit": 0.0,
                            "mizan_cost_code_id": charge.cost_code_id.id,
                            "mizan_plant_id": charge.plant_id.id,
                            "analytic_distribution": (
                                {str(analytic.id): 100} if analytic else False)}),
                    (0, 0, {"account_id": recovery.id, "name": label,
                            "debit": 0.0, "credit": charge.amount,
                            "mizan_plant_id": charge.plant_id.id}),
                ],
            })
            entry.action_post()
            charge.write({"move_id": entry.id, "state": "posted"})
        return True


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    mizan_plant_id = fields.Many2one(
        "mizan.plant", string="Plant", index=True,
        help="Which machine this cost or recovery belongs to.")
