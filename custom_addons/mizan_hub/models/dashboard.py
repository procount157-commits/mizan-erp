# -*- coding: utf-8 -*-
"""A screen per role, because one dashboard for everyone is a dashboard for
nobody.

The general manager, the finance manager and the project manager are not
looking at the same business. The first wants to know whether the company is
winning, the second whether the month will close and the cash will arrive, the
third whether his job is going to make its margin. Handing all three the same
twenty figures means each of them reads past sixteen of them, every day, until
they stop reading any.

So the tiles are chosen by role, and each tile is a figure a person can act on
with somewhere to go. A tile with no action behind it is a poster.

Built as tiles on a transient model rather than as a custom web client. It
costs a kanban view instead of a JavaScript bundle, it inherits search,
grouping and mobile layout for free, and every tile opens a real list with a
real domain — so a figure can always be taken apart into the records that make
it. A dashboard whose numbers cannot be opened is a dashboard nobody trusts
twice.
"""

from ast import literal_eval

from odoo import api, fields, models, _


class MizanDashboardTile(models.TransientModel):
    _name = "mizan.dashboard.tile"
    _description = "Dashboard"
    _order = "sequence, id"

    sequence = fields.Integer()
    section = fields.Char(readonly=True)
    name = fields.Char(string="Figure", readonly=True)
    value = fields.Char(readonly=True)
    sublabel = fields.Char(readonly=True)
    tone = fields.Selection(
        [("plain", "Plain"), ("good", "Good"), ("watch", "Watch"),
         ("bad", "Bad")], default="plain", readonly=True)
    res_model = fields.Char(readonly=True)
    domain = fields.Char(readonly=True)
    action_xmlid = fields.Char(readonly=True)

    def action_open(self):
        """Take the figure apart into the records behind it."""
        self.ensure_one()
        if self.action_xmlid:
            return self.env["ir.actions.actions"]._for_xml_id(self.action_xmlid)
        if not self.res_model:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.res_model,
            "domain": literal_eval(self.domain or "[]"),
            "view_mode": "list,form",
            "target": "current",
        }

    # ------------------------------------------------------------- building
    @api.model
    def _money(self, amount):
        currency = self.env.company.currency_id
        return "%s %s" % ("{:,.0f}".format(amount or 0.0), currency.name)

    @api.model
    def _tiles_for(self, role):
        company = self.env.company
        today = fields.Date.context_today(self)
        Move = self.env["account.move"]
        Contract = self.env["mizan.contract"]
        rows = []

        def tile(section, name, value, sublabel="", tone="plain",
                 model=False, domain=None, xmlid=False):
            rows.append({
                "sequence": len(rows) * 10, "section": section, "name": name,
                "value": value, "sublabel": sublabel, "tone": tone,
                "res_model": model, "domain": repr(domain or []),
                "action_xmlid": xmlid or "",
            })

        running = Contract.search([("state", "=", "running")])
        receivable = Move.search([
            ("company_id", "=", company.id), ("state", "=", "posted"),
            ("move_type", "=", "out_invoice"),
            ("payment_state", "in", ("not_paid", "partial"))])
        overdue = receivable.filtered(
            lambda move: move.invoice_date_due and move.invoice_date_due < today)
        payable = Move.search([
            ("company_id", "=", company.id), ("state", "=", "posted"),
            ("move_type", "=", "in_invoice"),
            ("payment_state", "in", ("not_paid", "partial"))])

        # ---------------------------------------------------- the business
        if role in ("gm", "cfo"):
            tile(_("The business"), _("Contracts running"), str(len(running)),
                 _("%s of contract value",
                   self._money(sum(running.mapped("revised_contract_value")))),
                 model="mizan.contract", domain=[("state", "=", "running")])

            earned = sum(running.mapped("revenue_earned"))
            recognised = sum(running.mapped("revenue_recognised"))
            tile(_("The business"), _("Revenue earned"), self._money(earned),
                 _("%s recognised so far", self._money(recognised)),
                 tone="watch" if earned - recognised > 1 else "good",
                 model="mizan.contract", domain=[("state", "=", "running")])

            margin = sum(running.mapped("forecast_margin"))
            losing = running.filtered("is_loss_making")
            tile(_("The business"), _("Forecast margin"), self._money(margin),
                 (_("%s contract(s) forecast to lose money", len(losing))
                  if losing else _("Every job forecast in profit")),
                 tone="bad" if losing else "good",
                 model="mizan.contract",
                 domain=[("state", "=", "running")] + (
                     [("is_loss_making", "=", True)] if losing else []))

        # ------------------------------------------------------- the money
        if role in ("gm", "cfo"):
            banks = self.env["account.journal"].search(
                [("type", "in", ("bank", "cash")),
                 ("company_id", "=", company.id)])
            cash = 0.0
            for journal in banks:
                account = journal.default_account_id
                if account:
                    cash += sum(self.env["account.move.line"].search([
                        ("account_id", "=", account.id),
                        ("parent_state", "=", "posted")]).mapped("balance"))
            tile(_("The money"), _("Cash and bank"), self._money(cash),
                 _("Across %s account(s)", len(banks)),
                 tone="bad" if cash < 0 else "good",
                 model="account.journal",
                 domain=[("type", "in", ("bank", "cash"))])

            due = sum(receivable.mapped("amount_residual"))
            late = sum(overdue.mapped("amount_residual"))
            tile(_("The money"), _("Owed to us"), self._money(due),
                 (_("%(amount)s of it overdue", amount=self._money(late))
                  if late else _("None of it overdue")),
                 tone="bad" if late else "good",
                 model="account.move",
                 domain=[("move_type", "=", "out_invoice"),
                         ("state", "=", "posted"),
                         ("payment_state", "in", ("not_paid", "partial"))])

            tile(_("The money"), _("Owed by us"),
                 self._money(sum(payable.mapped("amount_residual"))),
                 _("%s supplier document(s) open", len(payable)),
                 model="account.move",
                 domain=[("move_type", "=", "in_invoice"),
                         ("state", "=", "posted"),
                         ("payment_state", "in", ("not_paid", "partial"))])

            retention = sum(running.mapped("retention_held"))
            tile(_("The money"), _("Retention held by clients"),
                 self._money(retention),
                 _("Released at handover, not before"),
                 tone="watch" if retention else "plain",
                 model="mizan.contract", domain=[("state", "=", "running")])

        # ---------------------------------------------- compliance and close
        if role == "cfo":
            drafts = Move.search_count([("state", "=", "draft"),
                                        ("move_type", "!=", "entry")])
            tile(_("Before the close"), _("Documents in draft"), str(drafts),
                 _("Outside the ledger and the VAT return"),
                 tone="bad" if drafts else "good",
                 model="account.move",
                 domain=[("state", "=", "draft"), ("move_type", "!=", "entry")])

            unmatched = self.env["account.bank.statement.line"].search_count(
                [("is_reconciled", "=", False)])
            tile(_("Before the close"), _("Bank lines unmatched"),
                 str(unmatched), _("Money the ledger does not explain"),
                 tone="watch" if unmatched else "good",
                 model="account.bank.statement.line",
                 domain=[("is_reconciled", "=", False)])

            if not company.vat:
                tile(_("Before the close"), _("Company TRN"), _("NOT SET"),
                     _("Every invoice you issue says so, in red"), tone="bad",
                     model="res.company", domain=[("id", "=", company.id)])

            advances = self.env["mizan.employee.advance"].search(
                [("state", "=", "paid"), ("amount_outstanding", ">", 0)]) \
                if "mizan.employee.advance" in self.env else None
            if advances is not None:
                tile(_("Before the close"), _("Advances outstanding"),
                     self._money(sum(advances.mapped("amount_outstanding"))),
                     _("Held by %s employee(s)",
                       len(advances.mapped("employee_id"))),
                     tone="watch" if advances else "good",
                     model="mizan.employee.advance",
                     domain=[("state", "=", "paid"),
                             ("amount_outstanding", ">", 0)])

        # --------------------------------------------------------- the jobs
        if role in ("gm", "pm"):
            for contract in running:
                over = (contract.cost_at_completion
                        > contract.revised_contract_value)
                tile(_("The jobs"), contract.name,
                     "%.0f%%" % contract.completion_percent,
                     _("%(margin)s forecast margin · %(billed)s billed",
                       margin=self._money(contract.forecast_margin),
                       billed=self._money(contract.billed_to_date)),
                     tone="bad" if over else (
                         "watch" if contract.forecast_margin_percent < 5
                         else "good"),
                     model="mizan.contract", domain=[("id", "=", contract.id)])

        return rows

    @api.model
    def _role(self):
        user = self.env.user
        if user.has_group("account.group_account_manager"):
            return "cfo"
        if user.has_group("mizan_hub.group_general_manager"):
            return "gm"
        if user.has_group("project.group_project_manager"):
            return "pm"
        if user.has_group("account.group_account_readonly"):
            return "gm"
        return "pm"

    @api.model
    def action_refresh(self, role=None):
        self.search([("create_uid", "=", self.env.uid)]).unlink()
        rows = self._tiles_for(role or self._role())
        if rows:
            self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Dashboard"),
            "res_model": "mizan.dashboard.tile",
            "view_mode": "kanban",
            "target": "current",
            "context": {"search_default_group_section": 1},
        }
