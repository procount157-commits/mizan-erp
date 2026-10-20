# -*- coding: utf-8 -*-
"""Budget against actual, per cost code, for jobs with their own accounts.

The cost-code breakdown reads actual cost from expense accounts. A job with
project accounts keeps its cost on its work-in-progress account (an asset)
until it is recognised, and recognition moves it to the job's cost account
without a code — so the breakdown read nearly nothing for exactly the jobs
that are run most carefully. Here the coded cost on the job's WIP account
counts as actual, and the recognition entries (cost moved, not spent) are
left out of the untagged and unbudgeted figures."""
from odoo import models


class MizanContractBudgetLine(models.Model):
    _inherit = "mizan.contract.budget.line"

    def _compute_amounts(self):
        super()._compute_amounts()
        Line = self.env["account.move.line"].sudo()
        for line in self:
            contract = line.contract_id
            if not (contract.wip_account_id and line.cost_code_id):
                continue
            wip = sum(Line.search([
                ("parent_state", "=", "posted"), ("account_id", "=", contract.wip_account_id.id),
                ("mizan_cost_code_id", "=", line.cost_code_id.id)]).mapped("balance"))
            if not wip:
                continue
            line.actual_amount += wip
            line.total_exposure += wip
            line.variance = line.budget_amount - line.total_exposure
            line.variance_percent = (line.variance / line.budget_amount * 100) if line.budget_amount else 0.0
            line.is_over = line.variance < 0


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    def _compute_budget_rollup(self):
        super()._compute_budget_rollup()
        Line = self.env["account.move.line"].sudo()
        for contract in self.filtered("wip_account_id"):
            budgeted = set(contract.budget_line_ids.mapped("cost_code_id").ids)
            recognised = contract.recognition_ids.mapped("move_id")
            analytic = contract.analytic_account_id
            unbudgeted = untagged = 0.0
            spent = Line.search([("parent_state", "=", "posted"), ("account_id", "=", contract.wip_account_id.id),
                                 ("move_id", "not in", recognised.ids)])
            if analytic:
                spent |= Line.search([
                    ("parent_state", "=", "posted"), ("move_id", "not in", recognised.ids),
                    ("account_id", "!=", contract.cost_account_id.id),
                    ("account_id.account_type", "in", ("expense_direct_cost", "expense", "expense_depreciation")),
                ]).filtered(lambda l: (l.analytic_distribution or {}).get(str(analytic.id)))
            for move_line in spent:
                share = 100.0 if move_line.account_id == contract.wip_account_id else \
                    (move_line.analytic_distribution or {}).get(str(analytic.id), 0.0)
                amount = move_line.balance * share / 100.0
                if not move_line.mizan_cost_code_id:
                    untagged += amount
                elif move_line.mizan_cost_code_id.id not in budgeted:
                    unbudgeted += amount
            contract.unbudgeted_cost = unbudgeted
            contract.untagged_cost = untagged
