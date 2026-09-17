# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayslip(models.Model):
    """Charge a payslip to the job it was worked on.

    Site labour is one of the two biggest costs on a contract, and percentage of
    completion is measured from costs booked to the analytic account. A payslip
    that posts without one leaves the wage out of the progress calculation, so
    the contract looks less complete than it is and under-recognises revenue.
    """

    _inherit = "hr.payslip"

    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Cost Center",
        help="Charges this payslip to a contract. Leave empty for office staff "
             "whose wages are overhead rather than job cost.")

    @api.onchange("employee_id")
    def _onchange_employee_analytic(self):
        """Default to the cost center on the employee's contract, if any."""
        for slip in self:
            contract = slip.contract_id
            if contract and "analytic_account_id" in contract._fields:
                slip.analytic_account_id = contract.analytic_account_id


class HrPayslipLine(models.Model):
    _inherit = "hr.payslip.line"

    analytic_distribution = fields.Json(
        compute="_compute_analytic_distribution", store=True, readonly=False)

    @api.depends("slip_id.analytic_account_id")
    def _compute_analytic_distribution(self):
        for line in self:
            account = line.slip_id.analytic_account_id
            line.analytic_distribution = {str(account.id): 100} if account else False
