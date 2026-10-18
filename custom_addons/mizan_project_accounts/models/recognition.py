# -*- coding: utf-8 -*-
"""Recognition on the project's accounts.

For the percent reached — from the claim, typed in the progress window, or
cost-to-cost — one entry moves revenue (Dr billing / Cr contract revenue,
for what is earned and not yet booked) and cost (Dr contract cost / Cr WIP,
for everything sitting in WIP). Under IFRS 15 the cost of an output-measured
contract is expensed as incurred; that is what the cost side does."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MizanContractRecognition(models.Model):
    _inherit = "mizan.contract.recognition"

    source = fields.Selection([
        ("cost", "By cost incurred (cost-to-cost)"),
        ("claim", "By progress claim"),
        ("measured", "Measured progress (typed)"),
    ], default="cost", required=True)
    measured_percent = fields.Float(string="% complete to date", digits=(5, 2))
    claim_id = fields.Many2one("mizan.progress.claim", string="Progress claim", readonly=True)
    cost_amount = fields.Monetary(string="Cost recognised", readonly=True)
    revenue_reversed = fields.Boolean(string="Revenue reduced", readonly=True,
                                      help="The percent fell below the last one; the entry reverses the difference.")

    @api.onchange("contract_id", "source")
    def _onchange_measured_default(self):
        if self.contract_id and self.source == "measured" and not self.measured_percent:
            last = self.contract_id.recognition_ids.filtered(
                lambda r: r.state == "posted" and r.source in ("claim", "measured"))
            self.measured_percent = max(last.mapped("measured_percent") or [0.0])

    def _mizan_percent(self):
        self.ensure_one()
        if self.source in ("claim", "measured"):
            return self.measured_percent
        return self.contract_id.completion_percent

    def action_post(self):
        on_accounts = self.filtered(lambda r: r.state != "posted" and r.contract_id.billing_account_id)
        for rec in on_accounts:
            contract = rec.contract_id
            if not rec.journal_id:
                raise UserError(_("Set the journal before posting."))
            percent = rec._mizan_percent()
            if percent < 0 or percent > 100:
                raise UserError(_("The percent complete must be between 0 and 100."))
            value = contract.revised_contract_value or contract.contract_value
            earned = value * percent / 100.0
            already = sum(contract.recognition_ids.filtered(
                lambda r: r.state == "posted" and r.id != rec.id).mapped("amount"))
            revenue = earned - already
            cost = contract._mizan_balance(contract.wip_account_id)
            currency = contract.currency_id
            if currency.is_zero(revenue) and currency.is_zero(cost):
                raise UserError(_("Nothing to recognise: revenue for %(p).1f%% is already booked and WIP is empty.",
                                  p=percent))
            analytic = contract.analytic_account_id
            distribution = {str(analytic.id): 100} if analytic else False
            lines = []
            if not currency.is_zero(revenue):
                debit, credit = (revenue, 0.0) if revenue > 0 else (0.0, -revenue)
                lines += [
                    (0, 0, {"name": _("Revenue earned to %(p).1f%%", p=percent),
                            "account_id": contract.billing_account_id.id, "debit": debit, "credit": credit}),
                    (0, 0, {"name": _("Contract revenue — %s", contract.name),
                            "account_id": rec.revenue_account_id.id, "debit": credit, "credit": debit,
                            "analytic_distribution": distribution}),
                ]
            if cost > 0:
                lines += [
                    (0, 0, {"name": _("Cost of work — %s", contract.name),
                            "account_id": contract.cost_account_id.id, "debit": cost, "credit": 0.0,
                            "analytic_distribution": distribution}),
                    (0, 0, {"name": _("Transferred from work in progress"),
                            "account_id": contract.wip_account_id.id, "debit": 0.0, "credit": cost}),
                ]
            move = self.env["account.move"].with_context(mizan_routing=True).create({
                "move_type": "entry", "journal_id": rec.journal_id.id, "date": rec.date,
                "ref": _("Recognition %(pct).1f%% — %(contract)s", pct=percent, contract=contract.name),
                "mizan_contract_id": contract.id, "line_ids": lines,
            })
            move.action_post()
            rec.write({"move_id": move.id, "state": "posted", "amount": revenue, "cost_amount": cost,
                       "completion_percent": percent, "measured_percent": percent,
                       "cost_incurred": contract.cost_incurred, "revenue_reversed": revenue < 0})
            contract._mizan_invalidate_figures()
        return super(MizanContractRecognition, self - on_accounts).action_post()


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    @api.depends("cost_incurred", "budget_cost", "contract_value", "cost_at_completion",
                 "revised_contract_value", "recognition_ids.state", "recognition_ids.measured_percent",
                 "billing_mode")
    def _compute_completion(self):
        """On project accounts, progress is what was measured (claim or
        typed), not cost-to-cost, unless nothing was measured yet."""
        measured = self.env["mizan.contract"]
        for contract in self.filtered("billing_account_id"):
            posted = contract.recognition_ids.filtered(
                lambda r: r.state == "posted" and r.source in ("claim", "measured"))
            if posted:
                latest = posted.sorted(lambda r: (r.date, r.id))[-1]
                contract.completion_percent = latest.measured_percent
                value = contract.revised_contract_value or contract.contract_value
                contract.revenue_earned = value * latest.measured_percent / 100.0
                measured |= contract
        super(MizanContract, self - measured)._compute_completion()

    def action_progress_window(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Progress to date"),
            "res_model": "mizan.contract.recognition", "view_mode": "form",
            "views": [[self.env.ref("mizan_project_accounts.view_recognition_progress_form").id, "form"]],
            "target": "new",
            "context": {"default_contract_id": self.id, "default_source": "measured",
                        "default_measured_percent": self.completion_percent, "default_amount": 0.0},
        }
