# -*- coding: utf-8 -*-
"""Tell somebody before it costs money, not in the report afterwards.

Every warning in this system today is written into the code that owns it: the
guarantee knows it is expiring, the contract knows it is over budget, and both
of them wait to be looked at. Nobody looks at a screen to find out that
nothing is wrong, so the screen is only read after the problem is already
expensive.

What a company actually changes is not the arithmetic -- "estimate at
completion above the contract value" means one thing -- but who is told, at
what threshold, and whether it is worth telling them. So the condition stays
in Python as a named evaluator, and the threshold, the recipients and the
on/off switch are data the finance manager edits without a developer.

An alert becomes an activity on the record itself rather than an email. An
email is read once and lost; an activity sits on the contract, in that
person's to-do list, until it is dealt with, and it carries the link back.

The log is what stops the thing becoming noise. A rule that fires every night
on the same guarantee trains people to dismiss it, so a record already raised
and not yet cleared is not raised again.
"""

import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MizanAlertRule(models.Model):
    _name = "mizan.alert.rule"
    _description = "Alert Rule"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    kind = fields.Selection(
        [("budget_overrun", "Project cost above a share of its budget"),
         ("eac_over_contract", "Cost at completion above the contract value"),
         ("bond_expiring", "Guarantee expiring"),
         ("customer_overdue", "Customer invoice overdue"),
         ("cheque_bounced", "Cheque bounced or under claim"),
         ("advance_overdue", "Employee advance not settled"),
         ("claim_uninvoiced", "Claim certified and not invoiced")],
        required=True,
        help="The condition. It is a named test rather than a filter because "
             "the interesting ones read computed figures -- cost at "
             "completion, percent complete -- that no stored filter can see.")
    threshold = fields.Float(
        string="Threshold",
        help="A percentage for the budget rule, a number of days for the "
             "others. Left at zero the evaluator uses its own default.")
    recipient_ids = fields.Many2many(
        "res.users", string="Tell",
        domain=[("share", "=", False)],
        help="Who gets the activity. A rule with nobody to tell is off.")
    note = fields.Text(string="What to do about it", translate=True,
                       help="Shown on the activity, so the person who gets it "
                            "is not left to work out what is being asked.")
    last_run = fields.Datetime(readonly=True)
    raised_count = fields.Integer(
        compute="_compute_raised", string="Open alerts")

    def _compute_raised(self):
        data = self.env["mizan.alert.log"]._read_group(
            [("rule_id", "in", self.ids), ("state", "=", "open")],
            groupby=["rule_id"], aggregates=["__count"])
        counts = {rule.id: count for rule, count in data}
        for rule in self:
            rule.raised_count = counts.get(rule.id, 0)

    def action_open_alerts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "mizan.alert.log",
            "domain": [("rule_id", "=", self.id)],
            "view_mode": "list,form",
        }

    # ------------------------------------------------------------ evaluators
    # Each returns [(record, message)]. They take the threshold and nothing
    # else, so a rule is testable on its own.
    def _eval_budget_overrun(self, threshold):
        share = threshold or 90.0
        found = []
        for contract in self.env["mizan.contract"].search(
                [("state", "=", "running")]):
            budget = contract.budget_cost or 0.0
            if not budget:
                continue
            used = (contract.cost_incurred or 0.0) / budget * 100.0
            if used >= share:
                found.append((contract, _(
                    "%(used).1f%% of the budget is spent (%(cost)s of "
                    "%(budget)s), and the job is %(done).1f%% complete.",
                    used=used, cost=self._money(contract.cost_incurred),
                    budget=self._money(budget),
                    done=contract.completion_percent or 0.0)))
        return found

    def _eval_eac_over_contract(self, threshold):
        found = []
        for contract in self.env["mizan.contract"].search(
                [("state", "=", "running")]):
            eac = contract.cost_at_completion or contract.budget_cost or 0.0
            value = contract.revised_contract_value or contract.contract_value or 0.0
            if eac and value and eac > value:
                found.append((contract, _(
                    "Expected to cost %(eac)s against a contract worth "
                    "%(value)s — a loss of %(loss)s unless something changes.",
                    eac=self._money(eac), value=self._money(value),
                    loss=self._money(eac - value))))
        return found

    def _eval_bond_expiring(self, threshold):
        days = int(threshold or 30)
        found = []
        for bond in self.env["mizan.contract.bond"].search(
                [("state", "=", "active")]):
            if 0 <= (bond.days_to_expiry or 0) <= days:
                found.append((bond, _(
                    "Expires in %(days)s day(s), on %(date)s.",
                    days=bond.days_to_expiry, date=bond.expiry_date)))
        return found

    def _eval_customer_overdue(self, threshold):
        days = int(threshold or 30)
        cutoff = fields.Date.context_today(self) - relativedelta(days=days)
        found = []
        for move in self.env["account.move"].search([
                ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("invoice_date_due", "<", cutoff)]):
            late = (fields.Date.context_today(self) - move.invoice_date_due).days
            found.append((move, _(
                "%(amount)s outstanding, %(days)s days past due.",
                amount=self._money(move.amount_residual), days=late)))
        return found

    def _eval_cheque_bounced(self, threshold):
        found = []
        for cheque in self.env["mizan.cheque"].search(
                [("state", "in", ("bounced", "claimed"))]):
            when = getattr(cheque, "bounce_date", False) or cheque.due_date
            found.append((cheque, _(
                "Bounced on %(date)s. %(amount)s is not coming without a claim.",
                date=when, amount=self._money(cheque.amount))))
        return found

    def _eval_advance_overdue(self, threshold):
        days = int(threshold or 30)
        cutoff = fields.Date.context_today(self) - relativedelta(days=days)
        model = "mizan.employee.advance"
        if model not in self.env:
            return []
        found = []
        for advance in self.env[model].search([("state", "=", "paid")]):
            date = getattr(advance, "date", False)
            if date and date < cutoff:
                found.append((advance, _(
                    "Paid on %(date)s and still not settled.", date=date)))
        return found

    def _eval_claim_uninvoiced(self, threshold):
        return [(claim, _("Certified on %(date)s and still not invoiced. "
                          "The client has accepted the work.",
                          date=claim.certified_date))
                for claim in self.env["mizan.progress.claim"].search(
                    [("state", "=", "certified")])]

    @api.model
    def _money(self, amount):
        return "%s %s" % ("{:,.2f}".format(amount or 0.0),
                          self.env.company.currency_id.name)

    # ------------------------------------------------------------------ run
    def action_run(self):
        """Evaluate now. Used by the cron and by the button."""
        Log = self.env["mizan.alert.log"]
        raised = 0
        for rule in self:
            evaluator = getattr(rule, "_eval_%s" % rule.kind, None)
            if evaluator is None:
                _logger.warning("Alert rule %s has no evaluator %s",
                                rule.name, rule.kind)
                continue
            try:
                found = evaluator(rule.threshold)
            except Exception:
                # One broken rule must not stop the others: the whole point is
                # that this runs unattended every night.
                _logger.exception("Alert rule %s failed", rule.name)
                continue

            still_true = set()
            for record, message in found:
                still_true.add((record._name, record.id))
                existing = Log.search([
                    ("rule_id", "=", rule.id),
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("state", "=", "open")], limit=1)
                if existing:
                    existing.message = message
                    continue
                Log.create({
                    "rule_id": rule.id,
                    "res_model": record._name,
                    "res_id": record.id,
                    "name": record.display_name,
                    "message": message,
                })
                rule._raise_activity(record, message)
                raised += 1

            # Anything that was raised and is no longer true has been dealt
            # with, so it closes itself rather than waiting to be ticked off.
            gone = Log.search([("rule_id", "=", rule.id), ("state", "=", "open")])
            for log in gone:
                if (log.res_model, log.res_id) not in still_true:
                    log.action_resolve()

            rule.last_run = fields.Datetime.now()
        return raised

    def _raise_activity(self, record, message):
        self.ensure_one()
        if not self.recipient_ids:
            return
        model = self.env["ir.model"]._get(record._name)
        if not model:
            return
        body = message
        if self.note:
            body = "%s\n\n%s" % (message, self.note)
        for user in self.recipient_ids:
            self.env["mail.activity"].sudo().create({
                "res_model_id": model.id,
                "res_id": record.id,
                "activity_type_id": self.env.ref(
                    "mail.mail_activity_data_todo").id,
                "summary": self.name,
                "note": body,
                "user_id": user.id,
                "date_deadline": fields.Date.context_today(self),
            })

    @api.model
    def cron_run_alerts(self):
        rules = self.search([])
        raised = rules.action_run()
        _logger.info("Alert rules: %s rule(s) evaluated, %s new alert(s)",
                     len(rules), raised)
        return raised

    def action_run_now(self):
        raised = self.action_run()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Alerts"),
                "message": (_("%s new alert(s).", raised) if raised
                            else _("Nothing new. Everything these rules watch "
                                   "is within its limit.")),
                "type": "success", "sticky": False,
            },
        }


class MizanAlertLog(models.Model):
    _name = "mizan.alert.log"
    _description = "Alert"
    _order = "create_date desc, id desc"
    _inherit = ["mail.thread"]

    rule_id = fields.Many2one("mizan.alert.rule", required=True,
                              ondelete="cascade", index=True)
    name = fields.Char(string="Record", readonly=True)
    res_model = fields.Char(readonly=True, index=True)
    res_id = fields.Integer(readonly=True, index=True)
    message = fields.Text(readonly=True)
    state = fields.Selection(
        [("open", "Open"), ("resolved", "Resolved"), ("ignored", "Ignored")],
        default="open", required=True, tracking=True)
    resolved_on = fields.Datetime(readonly=True)

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            raise UserError(_("The record this alert was about is gone."))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [(False, "form")],
            "target": "current",
        }

    def action_resolve(self):
        return self.write({"state": "resolved",
                           "resolved_on": fields.Datetime.now()})

    def action_ignore(self):
        """Stop telling me about this one. It stays on the record."""
        return self.write({"state": "ignored",
                           "resolved_on": fields.Datetime.now()})
