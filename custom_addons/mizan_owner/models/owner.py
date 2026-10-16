# -*- coding: utf-8 -*-
"""The owner page's figures, and the sentences that explain them.

Everything is read from the posted ledger, so the owner and the accountant see
the same numbers. Each figure carries the action that opens its detail, for
the day the owner does want to look."""
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError

INCOME = ("income", "income_other")
EXPENSE = ("expense", "expense_depreciation", "expense_direct_cost")


class MizanOwner(models.AbstractModel):
    _name = "mizan.owner"
    _description = "Owner page"

    # ------------------------------------------------------------- helpers
    @api.model
    def _money(self, amount, short=False):
        currency = self.env.company.currency_id
        lang = self.env.context.get("lang") or self.env.user.lang or ""
        unit = "د.إ" if (lang.startswith("ar") and currency.name == "AED") else currency.name
        value = amount or 0.0
        if short and abs(value) >= 1_000_000:
            text = "%s %s" % ("{:,.2f}".format(value / 1_000_000).rstrip("0").rstrip("."),
                              _("million"))
        elif short and abs(value) >= 10_000:
            text = "%s %s" % ("{:,.0f}".format(value / 1000), _("thousand"))
        else:
            text = "{:,.0f}".format(value)
        return "%s %s" % (text, unit)

    @api.model
    def _balance(self, domain):
        Line = self.env["account.move.line"]
        try:
            groups = Line._read_group(domain + [("parent_state", "=", "posted"),
                                                ("company_id", "=", self.env.company.id)],
                                      [], ["balance:sum"])
            return groups[0][0] or 0.0
        except AccessError:
            return 0.0

    @api.model
    def _profit(self, start, end):
        dates = [("date", ">=", start), ("date", "<=", end)]
        income = -self._balance(dates + [("account_id.account_type", "in", INCOME)])
        expense = self._balance(dates + [("account_id.account_type", "in", EXPENSE)])
        return income, expense, income - expense

    @api.model
    def _act(self, name, model, domain, views="list,form"):
        return {"type": "ir.actions.act_window", "name": name, "res_model": model,
                "domain": domain, "views": [[False, v] for v in views.split(",")], "target": "current"}

    # ------------------------------------------------------------- the page
    @api.model
    def get_summary(self):
        env = self.env
        company = env.company
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        last_start = month_start - relativedelta(months=1)
        last_end = month_start - timedelta(days=1)
        Move = env["account.move"]

        cash = self._balance([("account_id.account_type", "=", "asset_cash")])
        today_in = self._balance([("account_id.account_type", "=", "asset_cash"), ("date", "=", today),
                                  ("debit", ">", 0)])
        today_out = -self._balance([("account_id.account_type", "=", "asset_cash"), ("date", "=", today),
                                    ("credit", ">", 0)])

        inc, exp, profit = self._profit(month_start, today)
        _li, _le, last_profit = self._profit(last_start, last_end)
        ytd_inc, ytd_exp, ytd = self._profit(today.replace(month=1, day=1), today)

        open_sales = [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                      ("payment_state", "in", ("not_paid", "partial")), ("company_id", "=", company.id)]
        receivables = Move.search(open_sales)
        owed = sum(receivables.mapped("amount_residual"))
        late_cut = today - timedelta(days=30)
        late = receivables.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < late_cut)
        late_amount = sum(late.mapped("amount_residual"))
        by_customer = {}
        for move in receivables:
            by_customer[move.partner_id] = by_customer.get(move.partner_id, 0.0) + move.amount_residual
        top = sorted(by_customer.items(), key=lambda kv: -kv[1])[:3]

        week = today + timedelta(days=7)
        open_bills = [("move_type", "=", "in_invoice"), ("state", "=", "posted"),
                      ("payment_state", "in", ("not_paid", "partial")), ("company_id", "=", company.id)]
        payables = Move.search(open_bills)
        we_owe = sum(payables.mapped("amount_residual"))
        due_week = payables.filtered(lambda m: m.invoice_date_due and m.invoice_date_due <= week)
        due_week_amount = sum(due_week.mapped("amount_residual"))
        cheques_amount = 0.0
        if "mizan.cheque" in env:
            try:
                cheques_amount = sum(env["mizan.cheque"].search([
                    ("cheque_type", "=", "issued"), ("state", "in", ("registered", "deposited")),
                    ("due_date", "<=", week)]).mapped("amount"))
            except AccessError:
                cheques_amount = 0.0

        # How long the cash lasts at the last three months' pace of spending.
        three = month_start - relativedelta(months=3)
        _i3, spent3, _p3 = self._profit(three, last_end)
        monthly_spend = spent3 / 3.0 if spent3 > 0 else 0.0
        runway = (cash / monthly_spend) if monthly_spend else None

        projects = []
        if "mizan.contract" in env:
            try:
                for contract in env["mizan.contract"].search([("state", "=", "running")], limit=8):
                    margin = contract.forecast_margin_percent
                    over = contract.cost_at_completion > contract.revised_contract_value
                    tone = "bad" if over else ("watch" if margin < 5 else "good")
                    projects.append({
                        "name": contract.name, "tone": tone,
                        "progress": round(contract.completion_percent or 0.0),
                        "line": (_("Losing money: costs will pass the contract value") if over else
                                 _("Thin margin: %s%%", round(margin, 1)) if margin < 5 else
                                 _("On track: %s%% margin", round(margin, 1))),
                        "action": self._act(contract.name, "mizan.contract", [("id", "=", contract.id)], "form"),
                    })
            except AccessError:
                pass

        # The headline: one sentence, the worst thing first.
        if runway is not None and runway < 2:
            headline, mood = _("Cash is short: it covers about %s weeks of spending.", max(1, round(runway * 4.3))), "bad"
        elif owed and late_amount / owed > 0.4:
            headline, mood = _("Most of what customers owe is more than a month late."), "watch"
        elif profit < 0:
            headline, mood = _("This month is at a loss so far."), "watch"
        else:
            headline, mood = _("The company is in good shape."), "good"

        if not inc and not exp:
            compare = _("No sales or costs recorded yet this month")
        elif last_profit:
            change = (profit - last_profit) / abs(last_profit) * 100
            compare = _("%(pct)s%% %(dir)s than last month", pct=abs(round(change)),
                        dir=_("more") if change >= 0 else _("less"))
        else:
            compare = _("last month: %s", self._money(last_profit, short=True))

        cash_lines = [_("Came in today: %s", self._money(today_in, short=True)),
                      _("Went out today: %s", self._money(today_out, short=True))]
        if runway is not None:
            cash_lines.append(_("Covers about %s months of spending", round(runway, 1)))

        events = []
        recent = Move.search([("move_type", "in", ("out_invoice",)), ("state", "=", "posted"),
                              ("company_id", "=", company.id)], order="invoice_date desc, id desc", limit=3)
        for move in recent:
            events.append({"icon": "fa-file-text-o", "text": _("Invoice %(n)s to %(p)s — %(a)s", n=move.name,
                           p=move.partner_id.name, a=self._money(move.amount_total)),
                           "date": move.invoice_date and move.invoice_date.strftime("%d/%m") or ""})
        payments = env["account.payment"].search([("payment_type", "=", "inbound"), ("state", "in", ("paid", "in_process")),
                                                  ("company_id", "=", company.id)], order="date desc, id desc", limit=3)
        for pay in payments:
            events.append({"icon": "fa-arrow-down", "text": _("Payment from %(p)s — %(a)s", p=pay.partner_id.name or "-",
                           a=self._money(pay.amount)), "date": pay.date.strftime("%d/%m")})
        events.sort(key=lambda e: e["date"][3:] + e["date"][:2], reverse=True)

        user = env.user
        return {
            "name": user.name.split(" ")[0],
            "company": company.name,
            "date": today.strftime("%d/%m/%Y"),
            "headline": headline, "mood": mood,
            "cards": [
                {"key": "cash", "title": _("Cash in the banks"), "value": self._money(cash), "tone": "hero",
                 "lines": cash_lines,
                 "action": self._act(_("Cash and banks"), "account.move.line",
                                     [("account_id.account_type", "=", "asset_cash"), ("parent_state", "=", "posted")])},
                {"key": "profit", "title": _("Profit this month"), "value": self._money(profit),
                 "tone": "good" if profit >= 0 else "bad",
                 "lines": [compare, _("Sales %(i)s · costs %(e)s", i=self._money(inc, short=True), e=self._money(exp, short=True)),
                           _("Since January: %s", self._money(ytd, short=True))],
                 "action": env["ir.actions.actions"]._for_xml_id("mizan_core.action_profit_loss")
                 if env.ref("mizan_core.action_profit_loss", raise_if_not_found=False) else False},
                {"key": "owed", "title": _("Customers owe you"), "value": self._money(owed),
                 "tone": "watch" if late_amount else "plain",
                 "lines": ([_("%s of it is over a month late", self._money(late_amount, short=True))] if late_amount else
                           [_("Nothing over a month late")]) +
                          [_("%(p)s: %(a)s", p=partner.name, a=self._money(amount, short=True)) for partner, amount in top],
                 "action": self._act(_("What customers owe"), "account.move", open_sales)},
                {"key": "due", "title": _("Due from you this week"), "value": self._money(due_week_amount + cheques_amount),
                 "tone": "watch" if (due_week_amount + cheques_amount) > cash else "plain",
                 "lines": [_("Supplier bills: %s", self._money(due_week_amount, short=True)),
                           _("Our cheques: %s", self._money(cheques_amount, short=True)),
                           _("Everything you owe: %s", self._money(we_owe, short=True))],
                 "action": self._act(_("What you owe"), "account.move", open_bills)},
            ],
            "projects": projects,
            "events": events[:5],
        }

    @api.model
    def open(self, action):
        """Actions are built on the server; this only hands them back so the
        page never needs model rights of its own to build one."""
        return action
