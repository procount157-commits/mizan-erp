# -*- coding: utf-8 -*-
"""Labour cards: a worker's day costed to the project the same day.

One card per worker with a daily wage (from the HR contract when there is
one). The engineer records who worked where, and for how much of the day;
posting writes Dr project WIP / Cr accrued site wages for each day and
contract, so the job carries its labour without a manual card and payroll
settles the accrual when the month is paid."""
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MizanLabourCard(models.Model):
    _name = "mizan.labour.card"
    _description = "Labour card"
    _rec_name = "employee_id"
    _order = "employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    daily_wage = fields.Monetary(string="Daily wage", compute="_compute_daily_wage", store=True, readonly=False,
                                 help="From the HR contract (monthly wage ÷ 30) when there is one; type it otherwise.")
    trade = fields.Char(string="Trade", help="Mason, steel fixer, carpenter, labourer…")
    active = fields.Boolean(default=True)
    day_ids = fields.One2many("mizan.labour.day", "card_id", string="Days")
    days_month = fields.Float(compute="_compute_month", string="Days this month")
    cost_month = fields.Monetary(compute="_compute_month", string="Cost this month")

    _sql_constraints = [("employee_uniq", "unique(employee_id)", "This worker already has a labour card.")]

    @api.depends("employee_id", "employee_id.contract_id.wage")
    def _compute_daily_wage(self):
        for card in self:
            contract = card.employee_id.contract_id if "contract_id" in card.employee_id._fields else False
            if contract and contract.wage and not card.daily_wage:
                card.daily_wage = contract.wage / 30.0
            elif not card.daily_wage:
                card.daily_wage = 0.0

    def _compute_month(self):
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        for card in self:
            days = card.day_ids.filtered(lambda d: start <= d.date <= today)
            card.days_month = sum(float(d.fraction or 0) for d in days)
            card.cost_month = sum(days.mapped("cost"))

    def action_open_days(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": self.employee_id.name,
            "res_model": "mizan.labour.day", "view_mode": "list",
            "views": [[self.env.ref("mizan_project_accounts.view_labour_day_list").id, "list"]],
            "domain": [("card_id", "=", self.id)], "context": {"default_card_id": self.id},
        }


class MizanLabourDay(models.Model):
    _name = "mizan.labour.day"
    _description = "Labour day"
    _order = "date desc, id desc"

    card_id = fields.Many2one("mizan.labour.card", string="Worker", required=True, ondelete="cascade")
    employee_id = fields.Many2one(related="card_id.employee_id", store=True)
    company_id = fields.Many2one(related="card_id.company_id", store=True)
    currency_id = fields.Many2one(related="card_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    contract_id = fields.Many2one("mizan.contract", string="Project", required=True,
                                  domain="[('state', '=', 'running'), ('wip_account_id', '!=', False)]")
    fraction = fields.Selection([("1", "Full day"), ("0.5", "Half day"), ("1.5", "Day and a half (overtime)"),
                                 ("2", "Two shifts")], string="Worked", default="1", required=True)
    daily_wage = fields.Monetary(related="card_id.daily_wage")
    cost = fields.Monetary(compute="_compute_cost", store=True)
    state = fields.Selection([("draft", "To post"), ("posted", "Posted")], default="draft", readonly=True)
    move_id = fields.Many2one("account.move", string="Entry", readonly=True)
    note = fields.Char()

    _sql_constraints = [("day_uniq", "unique(card_id, date, contract_id)",
                         "This worker is already recorded on that project for that day.")]

    @api.depends("fraction", "card_id.daily_wage")
    def _compute_cost(self):
        for day in self:
            day.cost = float(day.fraction or 0) * (day.card_id.daily_wage or 0.0)

    def write(self, vals):
        if any(d.state == "posted" for d in self) and set(vals) - {"note"}:
            raise UserError(_("A posted labour day cannot be changed; reverse its entry instead."))
        return super().write(vals)

    def unlink(self):
        if any(d.state == "posted" for d in self):
            raise UserError(_("A posted labour day cannot be deleted."))
        return super().unlink()

    def action_post(self):
        """One entry per day and project: Dr WIP / Cr accrued site wages."""
        groups = defaultdict(lambda: self.env["mizan.labour.day"])
        for day in self.filtered(lambda d: d.state == "draft" and d.cost > 0):
            groups[(day.date, day.contract_id, day.company_id)] |= day
        # The engineer records the facts; the entry is the system's, written
        # with its rights, not his.
        Move = self.env["account.move"].sudo().with_context(mizan_routing=True)
        for (date, contract, company), days in groups.items():
            wages = company.mizan_site_wages_account_id
            if not wages:
                company._mizan_ensure_project_company_accounts()
                wages = company.mizan_site_wages_account_id
            journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", company.id)], limit=1)
            analytic = contract.analytic_account_id
            distribution = {str(analytic.id): 100} if analytic else False
            lines = [(0, 0, {"name": "%s — %s" % (d.employee_id.name, dict(d._fields["fraction"].selection).get(d.fraction)),
                             "account_id": contract.wip_account_id.id, "debit": d.cost, "credit": 0.0,
                             "analytic_distribution": distribution}) for d in days]
            total = sum(days.mapped("cost"))
            lines.append((0, 0, {"name": _("Site labour %(d)s — %(c)s", d=date, c=contract.code),
                                 "account_id": wages.id, "debit": 0.0, "credit": total}))
            move = Move.create({"move_type": "entry", "journal_id": journal.id, "date": date,
                                "ref": _("Labour %(d)s — %(c)s", d=date, c=contract.code),
                                "mizan_contract_id": contract.id, "mizan_source_kind": "labour",
                                "line_ids": lines})
            move.action_post()
            days.sudo().write({"state": "posted", "move_id": move.id})
            contract._mizan_invalidate_figures()
        return True

    @api.model
    def _cron_post_yesterday(self):
        self.search([("state", "=", "draft"), ("date", "<", fields.Date.context_today(self))]).action_post()
