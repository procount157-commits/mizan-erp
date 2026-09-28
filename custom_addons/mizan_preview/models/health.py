# -*- coding: utf-8 -*-
"""Project health, and a confidence score for bank matching.

Both were proposals. Both are computed from figures the system already holds,
so they can be shown for real rather than described.

Project health deliberately carries NO single score. A number between 0 and 100
in front of a manager is a verdict he cannot argue with and cannot act on. The
screen states the conditions instead: over budget, claim uninvoiced, collection
behind. Each one says what to do.
"""

from odoo import api, fields, models, _


class MizanPreviewProject(models.TransientModel):
    _name = "mizan.preview.project"
    _description = "Project Health"
    _order = "overrun desc"

    contract_id = fields.Many2one("mizan.contract", readonly=True)
    name = fields.Char(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)

    contract_value = fields.Monetary(string="Contract", readonly=True)
    budget = fields.Monetary(string="Budget", readonly=True)
    actual = fields.Monetary(string="Actual", readonly=True)
    committed = fields.Monetary(string="Committed", readonly=True)
    eac = fields.Monetary(string="Cost at Completion", readonly=True)
    overrun = fields.Monetary(string="Over Budget By", readonly=True)
    margin = fields.Monetary(string="Forecast Margin", readonly=True)

    pct_cost = fields.Float(string="% by Cost", readonly=True)
    pct_measured = fields.Float(string="% Measured", readonly=True)
    certified = fields.Monetary(string="Certified", readonly=True)
    collected = fields.Monetary(string="Collected", readonly=True)
    outstanding = fields.Monetary(string="Outstanding", readonly=True)

    flags = fields.Char(string="What needs attention", readonly=True)

    def action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mizan.contract",
            "res_id": self.contract_id.id,
            "views": [[False, "form"]],
        }

    @api.model
    def action_refresh(self):
        self.search([]).unlink()
        Move = self.env["account.move"]
        rows = []
        for c in self.env["mizan.contract"].search([("state", "!=", "cancel")]):
            value = c.revised_contract_value or c.contract_value
            budget = c.budget_cost
            eac = c.cost_at_completion or budget
            overrun = max(eac - budget, 0.0)

            invoices = Move.search([
                ("state", "=", "posted"),
                ("move_type", "=", "out_invoice"),
                ("mizan_contract_id", "=", c.id)])
            billed = sum(invoices.mapped("amount_untaxed"))
            outstanding = sum(invoices.mapped("amount_residual"))

            flags = []
            if overrun > 0:
                flags.append(_("over budget by %.1f%%", overrun / budget * 100
                               if budget else 0))
            if c.is_loss_making:
                flags.append(_("forecast loss"))
            if c.claim_ids.filtered(lambda x: x.state == "certified"):
                flags.append(_("claim certified, not invoiced"))
            if c.measured_completion_percent - c.completion_percent > 10:
                flags.append(_("measured ahead of cost"))
            if c.advance_outstanding > 0:
                flags.append(_("advance outstanding"))
            if c.bond_expiring:
                flags.append(_("guarantee expiring"))
            if c.budget_line_mismatch:
                flags.append(_("cost breakdown does not add up"))
            if c.unbudgeted_cost:
                flags.append(_("cost on an unbudgeted code"))

            rows.append({
                "contract_id": c.id,
                "name": "%s — %s" % (c.code, c.name),
                "currency_id": c.currency_id.id,
                "contract_value": value, "budget": budget,
                "actual": c.cost_incurred, "committed": c.committed_total,
                "eac": eac, "overrun": overrun,
                "margin": c.forecast_margin,
                "pct_cost": c.completion_percent,
                "pct_measured": c.measured_completion_percent,
                "certified": c.certified_to_date,
                "collected": billed - outstanding,
                "outstanding": outstanding,
                "flags": " · ".join(flags) or _("nothing outstanding"),
            })
        self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Project Health"),
            "res_model": "mizan.preview.project",
            "view_mode": "list",
            "target": "current",
        }


class MizanPreviewMatch(models.TransientModel):
    _name = "mizan.preview.match"
    _description = "Bank Match Confidence"
    _order = "confidence desc"

    line_id = fields.Many2one("account.bank.statement.line", readonly=True)
    name = fields.Char(string="Bank narrative", readonly=True)
    date = fields.Date(readonly=True)
    amount = fields.Monetary(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    confidence = fields.Integer(string="Confidence %", readonly=True)
    basis = fields.Char(string="Why", readonly=True)
    candidate = fields.Char(string="Would match", readonly=True)
    verdict = fields.Selection(
        [("auto", "Settle automatically"),
         ("review", "Send to the inbox"),
         ("none", "Nothing found")],
        readonly=True)

    @api.model
    def action_refresh(self):
        """Score every unmatched line the way the proposal describes.

        The threshold is the point of the exercise: today matching is yes or
        no, so a weak match and a certain one are treated alike. Scoring lets
        the certain ones settle themselves and sends the rest to a person.
        """
        self.search([]).unlink()
        Move = self.env["account.move"]
        rows = []
        for line in self.env["account.bank.statement.line"].search(
                [("is_reconciled", "=", False)]):
            docs = line._mizan_candidate_documents()
            exact = docs.filtered(
                lambda m: line.currency_id.compare_amounts(
                    abs(m.amount_residual), abs(line.amount)) == 0)
            if exact:
                score, basis = 98, _("invoice number in the bank reference, "
                                     "amount matches to the fils")
                candidate = exact[0].name
            else:
                partner_hit = line._mizan_exact_partner_match()
                if partner_hit:
                    score, basis = 92, _("the party's only open document of "
                                         "exactly this amount")
                    candidate = partner_hit[0].name
                elif docs:
                    score, basis = 63, _("document named, amount differs")
                    candidate = docs[0].name
                else:
                    line.clean_reconcile()
                    if line.can_reconcile:
                        score, basis = 88, _("a reconciliation rule claims it")
                        candidate = _("rule")
                    else:
                        score, basis, candidate = 12, _("nothing recognised"), ""
            rows.append({
                "line_id": line.id, "name": line.payment_ref,
                "date": line.date, "amount": line.amount,
                "currency_id": line.currency_id.id,
                "confidence": score, "basis": basis, "candidate": candidate,
                "verdict": "auto" if score >= 95 else (
                    "review" if score >= 30 else "none"),
            })
        self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Bank Match Confidence"),
            "res_model": "mizan.preview.match",
            "view_mode": "list",
            "target": "current",
        }
