# -*- coding: utf-8 -*-
"""The Contracting app's front door: one icon per project, and behind each
icon the whole project — client account, supplier bills, expenses by where
they came from — with every entry screen one tap away."""
from odoo import _, api, fields, models

# Where a ledger line came from, as a domain the list can filter on.
SOURCE_DOMAINS = {
    "bill": [("move_id.move_type", "in", ("in_invoice", "in_refund")),
             ("move_id.mizan_subcontract_id", "=", False)],
    "subcontract": [("move_id.mizan_subcontract_id", "!=", False),
                    ("move_id.move_type", "in", ("in_invoice", "in_refund"))],
    "petty": [("move_id.expense_sheet_id", "!=", False)],
    "labour": [("move_id.mizan_source_kind", "=", "labour")],
    "stock": [("move_id.mizan_source_kind", "=", "stock")],
    "entry": [("move_id.move_type", "=", "entry"), ("move_id.mizan_source_kind", "=", False),
              ("move_id.expense_sheet_id", "=", False)],
}
COLORS = ["#1BAE5A", "#2563EB", "#D97706", "#7C3AED", "#DC2626", "#0891B2", "#DB2777", "#65A30D", "#4F46E5", "#0F766E"]


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    code = fields.Char(default="/")
    analytic_account_id = fields.Many2one(required=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code") or vals.get("code") == "/":
                vals["code"] = self.env["ir.sequence"].sudo().next_by_code("mizan.contract.project") or "/"
        contracts = super().create(vals_list)
        # A new project gets everything at once: accounts, cost centre,
        # project, site location. Nothing to press afterwards.
        contracts.action_create_project_accounts()
        return contracts

    # ------------------------------------------------------------ the icons
    @api.model
    def get_project_grid(self):
        contracts = self.search([("state", "in", ("draft", "running"))], order="state desc, code")
        items = []
        for contract in contracts:
            words = [w for w in (contract.name or "").replace("—", " ").split() if w and w not in ("عقد", "مشروع")]
            initials = "".join(w[0] for w in words[:2]) or "م"
            items.append({
                "id": contract.id, "name": contract.name, "code": contract.code,
                "client": contract.partner_id.name or "",
                "percent": round(contract.completion_percent or 0.0),
                "state": contract.state, "initials": initials,
                "color": COLORS[contract.id % len(COLORS)],
            })
        return {"projects": items, "can_create": self.env.user.has_group("account.group_account_invoice")
                or self.env.user.has_group("project.group_project_manager")}

    # ------------------------------------------------------------ one project
    def _money(self, value):
        lang = self.env.context.get("lang") or self.env.user.lang or ""
        unit = "د.إ" if lang.startswith("ar") and self.currency_id.name == "AED" else self.currency_id.name
        return "%s %s" % ("{:,.0f}".format(value or 0.0), unit)

    def _ledger(self, accounts, title, source=None):
        domain = [("account_id", "in", accounts.ids), ("parent_state", "!=", "cancel")]
        if source:
            domain += SOURCE_DOMAINS.get(source, [])
        return {
            "type": "ir.actions.act_window", "name": title, "res_model": "account.move.line",
            "views": [[self.env.ref("mizan_project_accounts.view_project_ledger_list").id, "list"], [False, "form"]],
            "domain": domain, "context": {"create": 0, "edit": 0}, "target": "current",
        }

    def _entry_actions(self):
        """The entry screens, opened on this project."""
        self.ensure_one()
        ctx = {"default_mizan_contract_id": self.id}
        purchase = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.company_id.id)], limit=1)
        entries = [
            {"key": "bill", "icon": "fa-file-text", "label": _("Supplier bill"),
             "action": {"type": "ir.actions.act_window", "name": _("Supplier bill — %s", self.name),
                        "res_model": "account.move", "views": [[False, "form"]], "target": "current",
                        "context": dict(ctx, default_move_type="in_invoice", default_journal_id=purchase.id)}},
            {"key": "petty", "icon": "fa-camera", "label": _("Petty cash receipt"),
             "action": {"type": "ir.actions.act_window", "name": _("Photograph a receipt"),
                        "res_model": "mizan.site.capture", "views": [[False, "form"]], "target": "new",
                        "context": {"default_project_id": self.project_id.id, "default_paid_by": "cash"}}},
            {"key": "labour", "icon": "fa-users", "label": _("Today's labour"),
             "action": {"type": "ir.actions.act_window", "name": _("Labour — %s", self.name),
                        "res_model": "mizan.labour.day", "views": [[False, "list"]], "target": "current",
                        "domain": [("contract_id", "=", self.id)],
                        "context": {"default_contract_id": self.id, "search_default_today": 1}}},
            {"key": "stock", "icon": "fa-cubes", "label": _("Issue stock"),
             "action": {"type": "ir.actions.act_window", "name": _("Stock issue — %s", self.name),
                        "res_model": "mizan.stock.issue", "views": [[False, "form"]], "target": "current",
                        "context": {"default_contract_id": self.id}}},
            {"key": "subcontract", "icon": "fa-handshake-o", "label": _("Subcontractors"),
             "action": {"type": "ir.actions.act_window", "name": _("Subcontractors — %s", self.name),
                        "res_model": "mizan.subcontract", "views": [[False, "list"], [False, "form"]],
                        "target": "current", "domain": [("contract_id", "=", self.id)],
                        "context": {"default_contract_id": self.id}}},
        ]
        if self.billing_mode == "progress":
            entries.append({"key": "claim", "icon": "fa-list-ol", "label": _("Progress claim"),
                            "action": {"type": "ir.actions.act_window", "name": _("Progress claims — %s", self.name),
                                       "res_model": "mizan.progress.claim", "views": [[False, "list"], [False, "form"]],
                                       "target": "current", "domain": [("contract_id", "=", self.id)],
                                       "context": {"default_contract_id": self.id}}})
        entries += [
            {"key": "invoice", "icon": "fa-file-text-o", "label": _("Instalment invoice"),
             "action": self.action_invoice_instalment()},
            {"key": "progress", "icon": "fa-percent", "label": _("Progress to date"),
             "action": self.action_progress_window()},
            {"key": "advance", "icon": "fa-download", "label": _("Receive an advance"),
             "action": {"type": "ir.actions.act_window", "name": _("Receive a customer advance"),
                        "res_model": "mizan.customer.advance", "views": [[False, "form"]], "target": "new",
                        "context": {"default_contract_id": self.id}}},
            {"key": "payment", "icon": "fa-money", "label": _("Client payment"),
             "action": {"type": "ir.actions.act_window", "name": _("Record a customer payment"),
                        "res_model": "mizan.customer.payment", "views": [[False, "form"]], "target": "new",
                        "context": {"default_contract_id": self.id}}},
        ]
        return entries

    def get_project_dashboard(self):
        self.ensure_one()
        c = self
        if not c.has_project_accounts:
            c.action_create_project_accounts()
        c._mizan_invalidate_figures()
        m = c._money
        advances = self.env["account.move.line"].search([
            ("account_id", "=", c.receivable_account_id.id), ("parent_state", "=", "posted"),
            ("move_id.mizan_source_kind", "=", "advance")])
        client = [
            {"label": _("Contract value"), "value": m(c.revised_contract_value or c.contract_value)},
            {"label": _("Billed (net)"), "value": m(c.billed_net), "action": c._ledger(c.billing_account_id, _("Billing — %s", c.name))},
            {"label": _("Client owes"), "value": m(c.client_balance), "tone": "watch" if c.client_balance > 0 else "",
             "action": c._ledger(c.receivable_account_id, _("Client account — %s", c.name))},
            {"label": _("Retention held by the client"), "value": m(c.retention_balance),
             "action": c._ledger(c.retention_account_id, _("Retention — %s", c.name))},
            {"label": _("Advances received"), "value": m(sum(advances.mapped("credit"))),
             "action": c._ledger(c.receivable_account_id, _("Advances — %s", c.name)) | {
                 "domain": [("id", "in", advances.ids)]}},
            {"label": _("Revenue recognised"), "value": m(c.revenue_recognised)},
        ]
        wip_cost = c.wip_account_id | c.cost_account_id
        expenses = [
            {"key": "bill", "label": _("Supplier bills"), "value": m(c.cost_bills), "raw": c.cost_bills},
            {"key": "subcontract", "label": _("Subcontractors"), "value": m(c.cost_subcontract), "raw": c.cost_subcontract},
            {"key": "petty", "label": _("Petty cash"), "value": m(c.cost_petty), "raw": c.cost_petty},
            {"key": "labour", "label": _("Labour cards"), "value": m(c.cost_labour), "raw": c.cost_labour},
            {"key": "stock", "label": _("Stock issued"), "value": m(c.cost_stock), "raw": c.cost_stock},
            {"key": "entry", "label": _("Journal entries"), "value": m(c.cost_other), "raw": c.cost_other},
        ]
        for e in expenses:
            e["action"] = c._ledger(c.wip_account_id, "%s — %s" % (e["label"], c.name), e["key"])
        bills = self.env["account.move"].search([
            ("move_type", "in", ("in_invoice", "in_refund")), ("state", "!=", "cancel"),
            "|", ("mizan_contract_id", "=", c.id), ("mizan_subcontract_id.contract_id", "=", c.id)],
            order="invoice_date desc, id desc", limit=8)
        state_label = dict(self.env["account.move"]._fields["payment_state"]._description_selection(self.env))
        bill_rows = [{"id": b.id, "name": b.name if b.name and b.name != "/" else _("Draft"),
                      "partner": b.partner_id.name or "", "date": b.invoice_date and b.invoice_date.strftime("%d/%m/%Y") or "",
                      "amount": m(b.amount_total), "state": _("Draft") if b.state == "draft" else state_label.get(b.payment_state, ""),
                      "action": {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": b.id,
                                 "views": [[False, "form"]], "target": "current"}} for b in bills]
        lines = self.env["account.move.line"].search(
            [("account_id", "in", c._mizan_project_accounts().ids), ("parent_state", "=", "posted")],
            order="date desc, id desc", limit=15)
        source_label = dict(self.env["account.move.line"]._fields["mizan_source"]._description_selection(self.env))
        movements = [{"id": l.id, "date": l.date.strftime("%d/%m/%Y"), "source": source_label.get(l.mizan_source, ""),
                      "source_key": l.mizan_source, "label": l.name or l.move_id.ref or "", "account": l.account_id.code,
                      "debit": "{:,.2f}".format(l.debit) if l.debit else "", "credit": "{:,.2f}".format(l.credit) if l.credit else "",
                      "action": {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": l.move_id.id,
                                 "views": [[False, "form"]], "target": "current"}} for l in lines]
        return {
            "id": c.id, "name": c.name, "code": c.code,
            "percent": round(c.completion_percent or 0.0, 1), "state": c.state,
            "mode": dict(c._fields["billing_mode"]._description_selection(self.env)).get(c.billing_mode),
            "cost_total": m(c.cost_incurred), "margin": m(c.margin_to_date),
            "color": COLORS[c.id % len(COLORS)],
            "entries": c._entry_actions(), "client_figures": client, "expenses": expenses,
            "bills": bill_rows, "movements": movements,
            "ledger": c._ledger(c._mizan_project_accounts(), _("Project ledger — %s", c.name)),
            "form": {"type": "ir.actions.act_window", "res_model": "mizan.contract", "res_id": c.id,
                     "views": [[False, "form"]], "target": "current"},
            "client_name": c.partner_id.name or "",
        }


class MizanProjectNew(models.TransientModel):
    """A new project in one screen; the system does the rest."""
    _name = "mizan.project.new"
    _description = "New project"

    name = fields.Char(string="Project name", required=True)
    partner_id = fields.Many2one("res.partner", string="Client", required=True)
    contract_value = fields.Monetary(string="Contract value", required=True)
    budget_cost = fields.Monetary(string="Budgeted cost")
    retention_percent = fields.Float(string="Retention %", default=5.0)
    advance_percent = fields.Float(string="Advance %")
    billing_mode = fields.Selection(selection=[
        ("progress", "Progress claims (cumulative work)"),
        ("schedule", "Payment schedule (progress typed separately)")],
        string="Billing", default="progress", required=True)
    date_start = fields.Date(string="Start date", default=fields.Date.context_today)
    date_end = fields.Date(string="Completion date")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    def action_create(self):
        self.ensure_one()
        contract = self.env["mizan.contract"].create({
            "name": self.name, "partner_id": self.partner_id.id, "contract_value": self.contract_value,
            "budget_cost": self.budget_cost, "retention_percent": self.retention_percent,
            "advance_percent": self.advance_percent, "billing_mode": self.billing_mode,
            "date_start": self.date_start, "date_end": self.date_end, "company_id": self.company_id.id,
        })
        contract.action_start()
        return {"type": "ir.actions.client", "tag": "mizan_project_dashboard",
                "name": contract.name, "params": {"contract_id": contract.id}}
