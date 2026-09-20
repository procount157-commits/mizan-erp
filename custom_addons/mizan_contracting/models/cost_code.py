# -*- coding: utf-8 -*-
"""Cost codes: the breakdown a contract is actually managed by.

One analytic account per project answers "is this job over budget". It cannot
answer "where", and where is the only part a site manager can act on. A villa
200,000 over is a fact; 200,000 over on concrete because the rate was quoted
before the design changed is a decision.

So a contract carries a budget per cost code, and every cost carries the code
it belongs to. Budget, actual and committed then line up per trade, which is
what the three specialist systems do and what makes their variance reports
worth reading.

Deliberately NOT built on Odoo's second analytic plan. A plan adds a column per
plan to analytic lines and spreads the distribution across dictionaries that
every report then has to unpick; a plain many2one on the journal item says the
same thing and can be grouped, filtered and summed without ceremony.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanCostCode(models.Model):
    _name = "mizan.cost.code"
    _description = "Cost Code"
    _order = "code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    category = fields.Selection(
        [("labour", "Labour"),
         ("material", "Materials"),
         ("subcontract", "Subcontract"),
         ("plant", "Plant & Equipment"),
         ("site", "Site Overheads"),
         ("other", "Other")],
        required=True, default="material",
        help="Groups the variance report the way a contractor reads it: "
             "labour and plant move with time, materials with quantity, "
             "subcontract with the agreement.")
    account_id = fields.Many2one(
        "account.account", string="Default Cost Account",
        domain="[('account_type', 'in', ('expense_direct_cost', 'expense'))]",
        help="Where costs on this code post unless the document says otherwise.")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True)
    active = fields.Boolean(default=True)
    note = fields.Text()

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)",
         "That cost code already exists."),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = "%s %s" % (record.code, record.name or "")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    mizan_cost_code_id = fields.Many2one(
        "mizan.cost.code", string="Cost Code", index=True,
        help="Which part of the job this cost belongs to.")


class HrExpense(models.Model):
    _inherit = "hr.expense"

    mizan_cost_code_id = fields.Many2one(
        "mizan.cost.code", string="Cost Code",
        help="A site claim belongs to a trade as much as a supplier bill does.")

    def _prepare_move_lines_vals(self):
        values = super()._prepare_move_lines_vals()
        if self.mizan_cost_code_id:
            values["mizan_cost_code_id"] = self.mizan_cost_code_id.id
        return values


class MizanContractBudgetLine(models.Model):
    """One line of the contract's budget, per cost code."""

    _name = "mizan.contract.budget.line"
    _description = "Contract Budget Line"
    _order = "contract_id, sequence, id"

    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    cost_code_id = fields.Many2one("mizan.cost.code", required=True)
    category = fields.Selection(related="cost_code_id.category", store=True)
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")

    budget_amount = fields.Monetary(string="Budget", required=True)
    actual_amount = fields.Monetary(string="Actual", compute="_compute_amounts")
    committed_amount = fields.Monetary(
        string="Committed", compute="_compute_amounts",
        help="Ordered and not yet invoiced: signed purchase orders whose "
             "supplier has not billed. Money already spent in every sense that "
             "matters except the ledger's.")
    total_exposure = fields.Monetary(
        string="Actual + Committed", compute="_compute_amounts")
    variance = fields.Monetary(compute="_compute_amounts")
    variance_percent = fields.Float(
        string="Variance %", compute="_compute_amounts")
    is_over = fields.Boolean(compute="_compute_amounts")
    note = fields.Char()

    _sql_constraints = [
        ("code_contract_uniq", "unique(contract_id, cost_code_id)",
         "That cost code is already budgeted on this contract."),
    ]

    def _compute_amounts(self):
        Line = self.env["account.move.line"]
        PoLine = self.env["purchase.order.line"]
        for line in self:
            analytic = line.contract_id.analytic_account_id
            actual = committed = 0.0
            if analytic and line.cost_code_id:
                moves = Line.search([
                    ("parent_state", "=", "posted"),
                    ("mizan_cost_code_id", "=", line.cost_code_id.id),
                    ("account_id.account_type", "in",
                     ("expense_direct_cost", "expense", "expense_depreciation")),
                ])
                for move_line in moves:
                    share = (move_line.analytic_distribution or {}).get(
                        str(analytic.id))
                    if share:
                        actual += move_line.balance * share / 100.0
                # Committed is what is ordered but not yet billed. Once the
                # supplier invoices, it stops being committed and becomes
                # actual — counting both would double the exposure.
                orders = PoLine.search([
                    ("order_id.state", "in", ("purchase", "done")),
                    ("mizan_cost_code_id", "=", line.cost_code_id.id),
                ])
                for order_line in orders:
                    share = (order_line.analytic_distribution or {}).get(
                        str(analytic.id))
                    if not share:
                        continue
                    outstanding = max(
                        order_line.product_qty - order_line.qty_invoiced, 0.0)
                    if outstanding and order_line.product_qty:
                        committed += (order_line.price_subtotal
                                      * outstanding / order_line.product_qty
                                      * share / 100.0)
            line.actual_amount = actual
            line.committed_amount = committed
            line.total_exposure = actual + committed
            line.variance = line.budget_amount - (actual + committed)
            line.variance_percent = (
                (line.variance / line.budget_amount * 100)
                if line.budget_amount else 0.0)
            line.is_over = line.variance < 0


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    mizan_cost_code_id = fields.Many2one(
        "mizan.cost.code", string="Cost Code",
        help="Carries the commitment to the right trade before any invoice "
             "arrives.")

    def _prepare_account_move_line(self, move=False):
        values = super()._prepare_account_move_line(move)
        if self.mizan_cost_code_id:
            values["mizan_cost_code_id"] = self.mizan_cost_code_id.id
        return values


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    budget_line_ids = fields.One2many(
        "mizan.contract.budget.line", "contract_id", string="Cost Breakdown")
    budget_line_total = fields.Monetary(
        string="Budget by Cost Code", compute="_compute_budget_rollup")
    committed_total = fields.Monetary(
        string="Committed", compute="_compute_budget_rollup")
    exposure_total = fields.Monetary(
        string="Actual + Committed", compute="_compute_budget_rollup")
    budget_line_mismatch = fields.Boolean(
        compute="_compute_budget_rollup",
        help="The cost codes do not add up to the contract budget.")

    unbudgeted_cost = fields.Monetary(
        string="Cost Outside the Breakdown", compute="_compute_budget_rollup",
        help="Cost on this job sitting on a code nobody budgeted, or on no "
             "code at all. It is real money and it is invisible in the "
             "variance report until it is given a line.")
    untagged_cost = fields.Monetary(
        string="Cost With No Code", compute="_compute_budget_rollup")

    def _compute_budget_rollup(self):
        Line = self.env["account.move.line"]
        for contract in self:
            lines = contract.budget_line_ids
            contract.budget_line_total = sum(lines.mapped("budget_amount"))
            contract.committed_total = sum(lines.mapped("committed_amount"))
            contract.exposure_total = sum(lines.mapped("total_exposure"))
            contract.budget_line_mismatch = bool(lines) and (
                abs(contract.budget_line_total - contract.budget_cost) > 0.01)

            # A cost on an unbudgeted code disappears from the breakdown
            # entirely: the totals look tidy while the job quietly spends.
            budgeted = set(lines.mapped("cost_code_id").ids)
            analytic = contract.analytic_account_id
            unbudgeted = untagged = 0.0
            if analytic:
                costs = Line.search([
                    ("parent_state", "=", "posted"),
                    ("account_id.account_type", "in",
                     ("expense_direct_cost", "expense", "expense_depreciation")),
                ])
                for move_line in costs:
                    share = (move_line.analytic_distribution or {}).get(
                        str(analytic.id))
                    if not share:
                        continue
                    amount = move_line.balance * share / 100.0
                    if not move_line.mizan_cost_code_id:
                        untagged += amount
                    elif move_line.mizan_cost_code_id.id not in budgeted:
                        unbudgeted += amount
            contract.unbudgeted_cost = unbudgeted
            contract.untagged_cost = untagged

    def action_estimate_from_commitments(self):
        """Set cost to complete from what is already ordered.

        A floor rather than a forecast: it counts only what has been committed
        on paper, so it cannot see work nobody has ordered yet. It is still a
        better starting point than the original budget, which stopped being a
        forecast the day the job started.
        """
        for contract in self:
            if not contract.budget_line_ids:
                raise UserError(_(
                    "%s has no cost breakdown to estimate from.", contract.code))
            remaining_budget = sum(
                max(line.budget_amount - line.total_exposure, 0.0)
                for line in contract.budget_line_ids)
            contract.cost_to_complete = (
                contract.committed_total + remaining_budget)
        return True
