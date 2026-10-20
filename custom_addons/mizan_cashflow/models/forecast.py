# -*- coding: utf-8 -*-
"""Thirteen weeks of cash, from what the books already know.

Every line is a document that will move money on a date: an invoice by its
due date, a post-dated cheque by its own date, the payroll at a month end,
the VAT return on the 28th after a quarter. Nothing is guessed from history,
so every figure can be opened and argued with; the two estimates (payroll from
contracts, retention release) say so on the line.

Rebuilt whole, every night and on demand: a forecast edited by hand is a
forecast nobody can trust."""
import calendar
from datetime import date, timedelta

from odoo import _, api, fields, models

WEEKS = 13
SOURCES = [
    ("opening", "Cash in the banks"),
    ("customer", "Customer invoices"),
    ("supplier", "Supplier bills"),
    ("cheque_in", "Cheques received"),
    ("cheque_out", "Cheques issued"),
    ("payroll", "Payroll"),
    ("vat", "VAT return"),
    ("subcontract", "Subcontractor payments"),
    ("retention", "Retention release"),
]


def users_lang(env):
    """The language most people in the office use: what a night job writes
    in, since it runs as nobody in particular."""
    langs = env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)]).mapped("lang")
    return max(set(langs), key=langs.count) if langs else env.user.lang


def _monday(day):
    return day - timedelta(days=day.weekday())


class MizanCashflowWeek(models.Model):
    _name = "mizan.cashflow.week"
    _description = "Cash flow forecast week"
    _order = "week_start"

    company_id = fields.Many2one("res.company", required=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    week_start = fields.Date(required=True)
    name = fields.Char(string="Week", required=True)
    opening = fields.Monetary(string="Opening cash")
    inflow = fields.Monetary(string="Coming in")
    outflow = fields.Monetary(string="Going out")
    closing = fields.Monetary(string="Closing cash")
    short = fields.Boolean(string="Runs short", help="The closing cash is below zero.")
    line_ids = fields.One2many("mizan.cashflow.line", "week_id")

    # ------------------------------------------------------------ building
    @api.model
    def _cron_rebuild(self):
        lang = users_lang(self.env)
        for company in self.env["res.company"].search([]):
            self.with_company(company).with_context(lang=lang)._rebuild()

    def action_rebuild(self):
        self.sudo().with_company(self.env.company)._rebuild()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    @api.model
    def _rebuild(self):
        """The forecast for the current company, replacing the last one."""
        company = self.env.company
        Week, Line = self.sudo(), self.env["mizan.cashflow.line"].sudo()
        Week.search([("company_id", "=", company.id)]).unlink()
        today = fields.Date.context_today(self)
        first = _monday(today)
        end = first + timedelta(weeks=WEEKS)
        rows = [r for r in self._collect(company, today, end) if r["amount"]]
        weeks = {}
        opening = sum(r["amount"] for r in rows if r["source"] == "opening")
        balance = opening
        for i in range(WEEKS):
            start = first + timedelta(weeks=i)
            week_rows = [r for r in rows if r["source"] != "opening" and _monday(max(r["date"], today)) == start]
            inflow = sum(r["amount"] for r in week_rows if r["amount"] > 0)
            outflow = -sum(r["amount"] for r in week_rows if r["amount"] < 0)
            week = Week.create({
                "company_id": company.id, "week_start": start,
                "name": "%s – %s" % (start.strftime("%d/%m"), (start + timedelta(days=6)).strftime("%d/%m")),
                "opening": balance, "inflow": inflow, "outflow": outflow,
                "closing": balance + inflow - outflow, "short": balance + inflow - outflow < 0,
            })
            balance = week.closing
            weeks[start] = week
            if i == 0:
                week_rows = week_rows + [r for r in rows if r["source"] == "opening"]
            Line.create([{
                "week_id": week.id, "company_id": company.id, "date": max(r["date"], today) if r["source"] != "opening" else today,
                "source": r["source"], "partner_id": r.get("partner_id") or False, "ref": r.get("ref") or "",
                "amount": r["amount"], "late": r.get("late", False), "estimate": r.get("estimate", False),
                "res_model": r.get("res_model") or False, "res_id": r.get("res_id") or 0,
            } for r in week_rows])
        return weeks

    @api.model
    def _collect(self, company, today, end):
        """Every expected movement before ``end``, signed: + in, - out."""
        rows = []
        Move = self.env["account.move"].sudo()
        cash = sum(self.env["account.move.line"].sudo().search([
            ("company_id", "=", company.id), ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "asset_cash")]).mapped("balance"))
        rows.append({"source": "opening", "date": today, "amount": cash, "ref": _("Cash and banks today")})

        # Cheques first: the invoices they settle are left out below.
        Cheque = self.env["mizan.cheque"].sudo()
        cheques = Cheque.search([("company_id", "=", company.id), ("state", "in", ("registered", "deposited")),
                                 ("due_date", "<", end)])
        covered = cheques.mapped("invoice_ids")
        for c in cheques:
            sign = 1 if c.cheque_type == "received" else -1
            rows.append({"source": "cheque_in" if sign > 0 else "cheque_out", "date": c.due_date or today,
                         "amount": sign * c.amount, "partner_id": c.partner_id.id, "ref": c.name,
                         "late": bool(c.due_date and c.due_date < today), "res_model": "mizan.cheque", "res_id": c.id})

        open_moves = Move.search([
            ("company_id", "=", company.id), ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund", "in_invoice", "in_refund")),
            ("payment_state", "in", ("not_paid", "partial")), ("id", "not in", covered.ids)])
        for m in open_moves:
            due = m.invoice_date_due or m.invoice_date or today
            if due >= end:
                continue
            customer = m.move_type in ("out_invoice", "out_refund")
            # amount_residual_signed: + what a customer owes us, - what we owe a supplier.
            rows.append({"source": "customer" if customer else "supplier", "date": due,
                         "amount": m.amount_residual_signed, "partner_id": m.partner_id.id, "ref": m.name,
                         "late": due < today, "res_model": "account.move", "res_id": m.id})

        rows += self._payroll(company, today, end)
        rows += self._vat(company, today, end)

        if "mizan.payment.request" in self.env:
            for req in self.env["mizan.payment.request"].sudo().search(
                    [("company_id", "=", company.id), ("state", "=", "to_approve")]):
                rows.append({"source": "subcontract", "date": req.date or today, "amount": -req.amount,
                             "partner_id": req.partner_id.id, "ref": req.name,
                             "res_model": "mizan.payment.request", "res_id": req.id})

        rows += self._retention(company, today, end)
        return rows

    @api.model
    def _payroll(self, company, today, end):
        """The month's wages at each month end, from the running contracts."""
        contracts = self.env["hr.contract"].sudo().search([("company_id", "=", company.id), ("state", "=", "open")])
        monthly = sum(contracts.mapped("wage"))
        if not monthly:
            return []
        rows, day = [], today
        while True:
            last = date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])
            if last >= end:
                break
            if last >= today:
                rows.append({"source": "payroll", "date": last, "amount": -monthly, "estimate": True,
                             "ref": _("Salaries for %s (%s contracts)", last.strftime("%m/%Y"), len(contracts))})
            day = last + timedelta(days=1)
        return rows

    @api.model
    def _vat(self, company, today, end):
        """What the VAT accounts hold, by quarter: a quarter's net VAT is due
        on the 28th of the month after it ends. The last quarter's, if its
        28th has passed unpaid, is counted now as late."""
        taxes = self.env["account.tax"].sudo().search([("company_id", "=", company.id), ("amount_type", "=", "percent"),
                                                       ("amount", ">", 0)])
        accounts = taxes.mapped("invoice_repartition_line_ids.account_id") | \
            taxes.mapped("refund_repartition_line_ids.account_id")
        if not accounts:
            return []
        Line = self.env["account.move.line"].sudo()
        base = [("company_id", "=", company.id), ("parent_state", "=", "posted"), ("account_id", "in", accounts.ids)]
        q_start = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
        prev_end = q_start - timedelta(days=1)
        rows = []
        for owed, quarter_end in (
                (-sum(Line.search(base + [("date", "<=", prev_end)]).mapped("balance")), prev_end),
                (-sum(Line.search(base + [("date", ">", prev_end)]).mapped("balance")),
                 date(today.year, q_start.month + 2, calendar.monthrange(today.year, q_start.month + 2)[1]))):
            if owed <= 0.5:
                continue
            due_month, due_year = quarter_end.month + 1, quarter_end.year
            if due_month > 12:
                due_month, due_year = 1, due_year + 1
            due = date(due_year, due_month, 28)
            if due >= end:
                continue
            rows.append({"source": "vat", "date": due, "amount": -owed, "late": due < today,
                         "ref": _("VAT return for the quarter to %s", quarter_end.strftime("%m/%Y"))})
        return rows

    @api.model
    def _retention(self, company, today, end):
        """Retention the clients hold: half at completion, half a year later
        (the defects period). Only for contracts with a completion date."""
        rows = []
        Contract = self.env["mizan.contract"].sudo()
        for c in Contract.search([("company_id", "=", company.id), ("state", "in", ("running", "done")),
                                  ("date_end", "!=", False)]):
            held = c.retention_balance if "retention_balance" in c._fields else 0.0
            if held <= 0:
                continue
            for when, share, label in ((c.date_end, 0.5, _("at completion")),
                                       (c.date_end + timedelta(days=365), 0.5, _("after the defects year"))):
                if today <= when < end:
                    rows.append({"source": "retention", "date": when, "amount": held * share, "estimate": True,
                                 "partner_id": c.partner_id.id, "ref": "%s — %s" % (c.name, label),
                                 "res_model": "mizan.contract", "res_id": c.id})
        return rows

    # ------------------------------------------------------------ reading
    @api.model
    def get_forecast(self):
        """The weeks for the phone and the owner's page; built if missing."""
        weeks = self.sudo().search([("company_id", "=", self.env.company.id)])
        stale = not weeks or weeks[0].week_start != _monday(fields.Date.context_today(self)) or \
            (fields.Datetime.now() - weeks[0].create_date).total_seconds() > 3 * 3600
        if stale:
            self.sudo()._rebuild()
            weeks = self.sudo().search([("company_id", "=", self.env.company.id)])
        return weeks

    def action_open_lines(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Week %s", self.name), "res_model": "mizan.cashflow.line",
                "view_mode": "list", "domain": [("week_id", "=", self.id)],
                "context": {"group_by": "source"}}


class MizanCashflowLine(models.Model):
    _name = "mizan.cashflow.line"
    _description = "Cash flow forecast line"
    _order = "date, id"

    week_id = fields.Many2one("mizan.cashflow.week", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    week_start = fields.Date(related="week_id.week_start", store=True, string="Week of")
    date = fields.Date(required=True)
    source = fields.Selection(SOURCES, required=True)
    partner_id = fields.Many2one("res.partner", string="Partner")
    ref = fields.Char(string="Document")
    amount = fields.Monetary()
    late = fields.Boolean(help="Its date has passed; counted in the first week.")
    estimate = fields.Boolean(help="Worked out rather than read from a document.")
    res_model = fields.Char()
    res_id = fields.Integer()

    def action_open_document(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return {"type": "ir.actions.act_window", "res_model": self.res_model, "res_id": self.res_id,
                "view_mode": "form", "target": "current"}
