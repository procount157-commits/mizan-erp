# -*- coding: utf-8 -*-
"""One row per job, and the reasons spelled out instead of a score.

A single Health Score would be easy to build and useless to act on. "62%"
tells a manager that something is wrong and not what, so he opens the six
screens the score was supposed to save him. What a manager can act on is a
sentence: the estimate at completion is now above the contract value.

So each job gets four separate verdicts — financial, contractual, cash and
operational — each with its own reasons listed. They are kept apart because
they fail for different causes and different people fix them. A job can be
profitable and still not be collecting; that is a cash problem, not a costing
one, and averaging the two into a number hides exactly the distinction the
manager needs.

Everything here is read from figures the contracting module already computes.
Nothing is recalculated a second way: a health screen that disagrees with the
contract it reports on is worse than no health screen.
"""

from odoo import api, fields, models, _


class MizanProjectHealth(models.TransientModel):
    _name = "mizan.project.health"
    _description = "Project Health"
    _order = "severity desc, contract_value desc"

    contract_id = fields.Many2one("mizan.contract", readonly=True)
    name = fields.Char(readonly=True)
    partner_name = fields.Char(string="Client", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)

    contract_value = fields.Monetary(string="Contract Value", readonly=True)
    cost_at_completion = fields.Monetary(string="Expected Cost", readonly=True)
    cost_incurred = fields.Monetary(string="Cost to Date", readonly=True)
    committed = fields.Monetary(string="Committed", readonly=True)
    forecast_margin = fields.Monetary(string="Forecast Margin", readonly=True)
    forecast_margin_percent = fields.Float(string="Margin %", readonly=True)
    completion_percent = fields.Float(string="% Complete", readonly=True)
    billed_to_date = fields.Monetary(string="Billed", readonly=True)
    collected = fields.Monetary(string="Collected", readonly=True)
    outstanding = fields.Monetary(string="Outstanding", readonly=True)
    retention_held = fields.Monetary(string="Retention", readonly=True)

    financial = fields.Selection(
        [("ok", "Healthy"), ("watch", "Watch"), ("bad", "At risk")],
        string="Financial", readonly=True)
    contractual = fields.Selection(
        [("ok", "Healthy"), ("watch", "Watch"), ("bad", "At risk")],
        string="Contractual", readonly=True)
    cash = fields.Selection(
        [("ok", "Healthy"), ("watch", "Watch"), ("bad", "At risk")],
        string="Cash", readonly=True)
    operational = fields.Selection(
        [("ok", "Healthy"), ("watch", "Watch"), ("bad", "At risk")],
        string="Operational", readonly=True)

    reasons = fields.Text(string="Why", readonly=True)
    severity = fields.Integer(readonly=True)

    def action_open_contract(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mizan.contract",
            "res_id": self.contract_id.id,
            "views": [[False, "form"]],
            "target": "current",
        }

    # ------------------------------------------------------------ building
    @api.model
    def _assess(self, contract):
        """Four verdicts and the reasons behind each, for one job."""
        reasons = []
        verdicts = {"financial": "ok", "contractual": "ok",
                    "cash": "ok", "operational": "ok"}

        def flag(area, level, text):
            # Only ever worsens a verdict: a job with one healthy signal and
            # one bad one is not healthy on average.
            order = {"ok": 0, "watch": 1, "bad": 2}
            if order[level] > order[verdicts[area]]:
                verdicts[area] = level
            reasons.append(text)

        value = contract.revised_contract_value or contract.contract_value
        eac = contract.cost_at_completion or contract.budget_cost

        # --- financial: is the job going to make money
        if contract.is_loss_making:
            flag("financial", "bad",
                 _("Forecast loss of %(amount)s — the whole loss belongs in "
                   "this period, not the remaining ones",
                   amount="{:,.0f}".format(abs(contract.forecast_margin))))
            if not contract.loss_provision_booked:
                flag("financial", "bad", _("The loss provision is not booked"))
        elif contract.forecast_margin_percent < 5 and value:
            flag("financial", "watch",
                 _("Forecast margin down to %(pct).1f%%",
                   pct=contract.forecast_margin_percent))
        if contract.budget_cost and eac > contract.budget_cost * 1.05:
            flag("financial", "watch",
                 _("Expected cost is %(pct).1f%% over the original budget",
                   pct=(eac / contract.budget_cost - 1) * 100))
        if contract.unbudgeted_cost:
            flag("financial", "watch",
                 _("%(amount)s spent on cost codes that carry no budget",
                   amount="{:,.0f}".format(contract.unbudgeted_cost)))

        # --- contractual: is the paperwork keeping up with the work
        if contract.variation_pending:
            flag("contractual", "watch",
                 _("%(amount)s of variations submitted and not approved — "
                   "work priced but not yet part of the contract",
                   amount="{:,.0f}".format(contract.variation_pending)))
        expiring = contract.bond_ids.filtered(
            lambda bond: bond.state == "active" and 0 <= bond.days_to_expiry <= 30)
        for bond in expiring:
            flag("contractual", "bad",
                 _("Guarantee %(ref)s expires in %(days)s days",
                   ref=bond.name, days=bond.days_to_expiry))
        uncertified = contract.claim_ids.filtered(
            lambda claim: claim.state == "submitted")
        if uncertified:
            flag("contractual", "watch",
                 _("%(count)s claim(s) with the consultant and not certified",
                   count=len(uncertified)))

        # --- cash: is the money actually arriving
        # This job's own invoices, reached through the claims that raised
        # them. Every posted invoice for the CLIENT would be wrong the moment
        # a client holds two contracts: one job would report the other's debt.
        invoices = contract.claim_ids.mapped("invoice_id").filtered(
            lambda move: move.state == "posted")
        outstanding = sum(invoices.mapped("amount_residual"))
        overdue = invoices.filtered(
            lambda move: move.invoice_date_due
            and move.invoice_date_due < fields.Date.context_today(self)
            and move.payment_state in ("not_paid", "partial"))
        if overdue:
            flag("cash", "bad",
                 _("%(count)s invoice(s) overdue, %(amount)s outstanding",
                   count=len(overdue),
                   amount="{:,.0f}".format(sum(overdue.mapped("amount_residual")))))
        if contract.under_billing > 0:
            flag("cash", "watch",
                 _("%(amount)s of work done and not yet billed",
                   amount="{:,.0f}".format(contract.under_billing)))
        if contract.advance_outstanding > 0:
            flag("cash", "watch",
                 _("%(amount)s of advance still to recover",
                   amount="{:,.0f}".format(contract.advance_outstanding)))

        # --- operational: is the data fit to report on
        if contract.untagged_cost:
            flag("operational", "watch",
                 _("%(amount)s of cost carries no cost code, so it is outside "
                   "every budget line",
                   amount="{:,.0f}".format(contract.untagged_cost)))
        if not contract.budget_line_ids:
            flag("operational", "watch",
                 _("No cost breakdown — progress is measured against one "
                   "number for the whole job"))
        if contract.date_end and contract.date_end < fields.Date.context_today(self) \
                and contract.state == "running":
            flag("operational", "bad",
                 _("Completion date passed on %(date)s and the job is still "
                   "running", date=contract.date_end))

        if not reasons:
            reasons = [_("Nothing needs attention on this job.")]
        severity = sum({"ok": 0, "watch": 1, "bad": 4}[v]
                       for v in verdicts.values())
        return verdicts, reasons, severity, outstanding

    @api.model
    def action_refresh(self):
        self.search([("create_uid", "=", self.env.uid)]).unlink()
        rows = []
        contracts = self.env["mizan.contract"].search(
            [("state", "in", ("draft", "running"))])
        for contract in contracts:
            verdicts, reasons, severity, outstanding = self._assess(contract)
            rows.append({
                "contract_id": contract.id,
                "name": contract.name,
                "partner_name": contract.partner_id.display_name,
                "currency_id": contract.currency_id.id,
                "contract_value": (contract.revised_contract_value
                                   or contract.contract_value),
                "cost_at_completion": (contract.cost_at_completion
                                       or contract.budget_cost),
                "cost_incurred": contract.cost_incurred,
                "committed": contract.committed_total,
                "forecast_margin": contract.forecast_margin,
                "forecast_margin_percent": contract.forecast_margin_percent,
                "completion_percent": contract.completion_percent,
                "billed_to_date": contract.billed_to_date,
                "outstanding": outstanding,
                "collected": contract.billed_to_date - outstanding,
                "retention_held": contract.retention_held,
                "reasons": "\n".join("• %s" % reason for reason in reasons),
                "severity": severity,
                **verdicts,
            })
        if rows:
            self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Project Health"),
            "res_model": "mizan.project.health",
            "view_mode": "list,form",
            "target": "current",
        }
