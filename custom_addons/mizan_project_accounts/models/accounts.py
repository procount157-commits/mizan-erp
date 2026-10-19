# -*- coding: utf-8 -*-
"""The accounts a project owns, created the day the contract starts.

Five accounts per contract, numbered with one shared two-digit suffix so the
chart reads as a set: 1021NN the client, 1071NN billing, 1072NN work in
progress, 1073NN client retention, 4011NN contract cost. Plus the cost
centre, the project and the site stock location when they are missing, so
petty cash, site reports, tasks and stock issues all land on one job."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# field, code prefix, account name (Arabic, as the chart is), type, reconcilable
ACCOUNT_SPECS = [
    ("receivable_account_id", "1021", "عميل – %s", "asset_receivable", True),
    ("billing_account_id", "1071", "فوترة – %s", "asset_current", False),
    ("wip_account_id", "1072", "تكاليف تحت التنفيذ – %s", "asset_current", False),
    ("retention_account_id", "1073", "محتجزات العميل – %s", "asset_current", True),
    ("cost_account_id", "4011", "تكلفة العقد – %s", "expense_direct_cost", False),
]
COMPANY_ACCOUNTS = [
    ("mizan_advance_clearing_account_id", "107900", "دفعات مقدمة من العملاء – وسيط", "asset_current", False),
    ("mizan_site_wages_account_id", "201090", "أجور عمال المواقع المستحقة", "liability_current", False),
    ("mizan_inventory_account_id", "103001", "المخزون – مواد", "asset_current", False),
]
EXPENSE_TYPES = ("expense", "expense_direct_cost", "expense_depreciation")


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_advance_clearing_account_id = fields.Many2one(
        "account.account", string="Customer advance clearing account",
        help="Debited when an advance is received and credited by the bank "
             "entry in the same breath, so it always reads zero.")
    mizan_site_wages_account_id = fields.Many2one(
        "account.account", string="Accrued site wages account",
        help="Credited by the daily labour cards; settled by payroll.")
    mizan_inventory_account_id = fields.Many2one(
        "account.account", string="Materials inventory account",
        help="Supplier bills of storable products are debited here; issue "
             "vouchers credit it when materials go to a project.")

    def _mizan_ensure_project_company_accounts(self):
        Account = self.env["account.account"]
        Group = self.env["account.group"]
        for company in self:
            for field, code, name, kind, reconcile in COMPANY_ACCOUNTS:
                if company[field]:
                    continue
                account = Account.with_company(company).search([("code", "=", code)], limit=1)
                if not account:
                    account = Account.with_company(company).create({
                        "code": code, "name": name, "account_type": kind, "reconcile": reconcile})
                company[field] = account
            # Subcontractors on their own, under liabilities.
            if not Group.search([("code_prefix_start", "=", "203")], limit=1):
                parent = Group.search([("code_prefix_start", "=", "2")], limit=1)
                Group.create({"name": "مقاولو الباطن", "code_prefix_start": "203",
                              "code_prefix_end": "203", "parent_id": parent.id if parent else False})


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    receivable_account_id = fields.Many2one("account.account", string="Client account", readonly=True, copy=False)
    billing_account_id = fields.Many2one("account.account", string="Billing account", readonly=True, copy=False)
    wip_account_id = fields.Many2one("account.account", string="Work-in-progress account", readonly=True, copy=False)
    retention_account_id = fields.Many2one("account.account", string="Client retention account", readonly=True, copy=False)
    cost_account_id = fields.Many2one("account.account", string="Contract cost account", readonly=True, copy=False)
    stock_location_id = fields.Many2one("stock.location", string="Site location", readonly=True, copy=False)
    has_project_accounts = fields.Boolean(compute="_compute_has_project_accounts")
    billing_mode = fields.Selection([
        ("progress", "Progress claims (cumulative work)"),
        ("schedule", "Payment schedule (progress typed separately)"),
    ], string="Billing", default="progress", required=True, tracking=True,
        help="Progress claims: each invoice states the cumulative work and "
             "posts the recognition. Payment schedule: invoices follow the "
             "agreed instalments; the percent complete is typed in its own "
             "window and drives the recognition.")

    @api.depends("receivable_account_id", "billing_account_id", "wip_account_id",
                 "retention_account_id", "cost_account_id")
    def _compute_has_project_accounts(self):
        for contract in self:
            contract.has_project_accounts = bool(
                contract.receivable_account_id and contract.billing_account_id
                and contract.wip_account_id and contract.retention_account_id
                and contract.cost_account_id)

    def _mizan_project_accounts(self):
        self.ensure_one()
        return (self.receivable_account_id | self.billing_account_id | self.wip_account_id
                | self.retention_account_id | self.cost_account_id)

    # ---------------------------------------------------------------- create
    def _mizan_next_suffix(self):
        Account = self.env["account.account"].with_company(self.company_id)
        for n in range(1, 100):
            suffix = "%02d" % n
            taken = Account.search_count([("code", "in", [p + suffix for _f, p, _n, _t, _r in ACCOUNT_SPECS])])
            if not taken:
                return suffix
        raise UserError(_("All 99 project account numbers are used; extend the chart."))

    def action_create_project_accounts(self):
        Account = self.env["account.account"]
        for contract in self:
            company = contract.company_id
            company._mizan_ensure_project_company_accounts()
            label = contract.name
            if not contract.has_project_accounts:
                suffix = contract._mizan_next_suffix()
                values = {}
                for field, prefix, name, kind, reconcile in ACCOUNT_SPECS:
                    if contract[field]:
                        continue
                    values[field] = Account.with_company(company).create({
                        "code": prefix + suffix, "name": name % label,
                        "account_type": kind, "reconcile": reconcile}).id
                contract.write(values)
            if not contract.analytic_account_id:
                plan = self.env["account.analytic.plan"].search([], limit=1)
                contract.analytic_account_id = self.env["account.analytic.account"].create({
                    "name": label, "plan_id": plan.id, "company_id": company.id})
            if not contract.project_id:
                project = self.env["project.project"].search(
                    [("account_id", "=", contract.analytic_account_id.id)], limit=1)
                contract.project_id = project or self.env["project.project"].create({
                    "name": label, "partner_id": contract.partner_id.id,
                    "account_id": contract.analytic_account_id.id, "company_id": company.id})
            elif not contract.project_id.account_id:
                contract.project_id.account_id = contract.analytic_account_id
            if not contract.stock_location_id and "stock.warehouse" in self.env:
                warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
                if warehouse:
                    contract.stock_location_id = self.env["stock.location"].create({
                        "name": "موقع – %s" % label, "usage": "production",
                        "location_id": warehouse.view_location_id.id, "company_id": company.id})
            contract.message_post(body=_("Project accounts created: %s",
                                         ", ".join(contract._mizan_project_accounts().mapped("code"))))
        return True

    def action_start(self):
        res = super().action_start()
        self.action_create_project_accounts()
        return res

    # --------------------------------------------------------------- figures
    def _mizan_balance(self, account, side=None):
        """Posted balance of one of the project's accounts; 'debit' or
        'credit' for that side alone."""
        self.ensure_one()
        if not account:
            return 0.0
        groups = self.env["account.move.line"]._read_group(
            [("account_id", "=", account.id), ("parent_state", "=", "posted"),
             ("company_id", "=", self.company_id.id)],
            [], ["debit:sum", "credit:sum"])
        debit, credit = (groups[0] if groups else (0.0, 0.0))
        if side == "debit":
            return debit or 0.0
        if side == "credit":
            return credit or 0.0
        return (debit or 0.0) - (credit or 0.0)

    wip_balance = fields.Monetary(compute="_compute_project_figures", string="WIP not yet recognised")
    cost_recognised = fields.Monetary(compute="_compute_project_figures", string="Cost recognised")
    billed_net = fields.Monetary(compute="_compute_project_figures", string="Billed (net of VAT)")
    billing_balance = fields.Monetary(compute="_compute_project_figures", string="Billing account balance",
                                      help="Positive: revenue recognised ahead of billing (under-billed). "
                                           "Negative: billed ahead of the work (over-billed).")
    client_balance = fields.Monetary(compute="_compute_project_figures", string="Client owes")
    retention_balance = fields.Monetary(compute="_compute_project_figures", string="Client holds (retention)")

    @api.depends("receivable_account_id", "billing_account_id", "wip_account_id",
                 "retention_account_id", "cost_account_id")
    def _compute_project_figures(self):
        for contract in self:
            contract.wip_balance = contract._mizan_balance(contract.wip_account_id)
            contract.cost_recognised = contract._mizan_balance(contract.cost_account_id)
            contract.billed_net = contract._mizan_balance(contract.billing_account_id, "credit")
            contract.billing_balance = contract._mizan_balance(contract.billing_account_id)
            contract.client_balance = contract._mizan_balance(contract.receivable_account_id)
            contract.retention_balance = contract._mizan_balance(contract.retention_account_id)

    @api.depends("analytic_account_id", "wip_account_id", "cost_account_id")
    def _compute_cost_incurred(self):
        """With project accounts, cost is read from the ledger: what sits in
        WIP plus what was already moved to contract cost."""
        with_accounts = self.filtered("wip_account_id")
        for contract in with_accounts:
            contract.cost_incurred = (contract._mizan_balance(contract.wip_account_id)
                                      + contract._mizan_balance(contract.cost_account_id))
        super(MizanContract, self - with_accounts)._compute_cost_incurred()

    cost_bills = fields.Monetary(compute="_compute_cost_by_source", string="Supplier bills")
    cost_subcontract = fields.Monetary(compute="_compute_cost_by_source", string="Subcontractors")
    cost_petty = fields.Monetary(compute="_compute_cost_by_source", string="Petty cash")
    cost_labour = fields.Monetary(compute="_compute_cost_by_source", string="Labour cards")
    cost_stock = fields.Monetary(compute="_compute_cost_by_source", string="Stock issued")
    cost_other = fields.Monetary(compute="_compute_cost_by_source", string="Journal entries and other")
    margin_to_date = fields.Monetary(compute="_compute_cost_by_source", string="Margin recognised",
                                     help="Revenue recognised less cost recognised.")

    SOURCE_FIELDS = {"bill": "cost_bills", "subcontract": "cost_subcontract", "petty": "cost_petty",
                     "expense": "cost_petty", "labour": "cost_labour", "stock": "cost_stock"}

    def _compute_cost_by_source(self):
        """Where the project's cost came from, read from the WIP account's
        debits (the recognition moves cost out of WIP, so it is skipped)."""
        Line = self.env["account.move.line"]
        for contract in self:
            totals = dict.fromkeys(set(self.SOURCE_FIELDS.values()) | {"cost_other"}, 0.0)
            if contract.wip_account_id:
                lines = Line.search([("account_id", "=", contract.wip_account_id.id),
                                     ("parent_state", "=", "posted")])
                for line in lines:
                    source = line.mizan_source
                    if source == "recognition":
                        continue
                    totals[self.SOURCE_FIELDS.get(source, "cost_other")] += line.debit - line.credit
            for field, value in totals.items():
                contract[field] = value
            contract.margin_to_date = contract.revenue_recognised - contract.cost_recognised

    def _mizan_invalidate_figures(self):
        """The figures read the ledger; after an entry is posted in the same
        transaction they must be read again."""
        self.invalidate_recordset(["wip_balance", "cost_recognised", "billed_net", "billing_balance",
                                   "client_balance", "retention_balance", "cost_incurred",
                                   "completion_percent", "revenue_earned", "revenue_recognised",
                                   "revenue_to_recognise", "cost_bills", "cost_subcontract", "cost_petty",
                                   "cost_labour", "cost_stock", "cost_other", "margin_to_date"])

    def _mizan_ledger_action(self, accounts, name):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": name,
            "res_model": "account.move.line",
            "views": [[self.env.ref("mizan_project_accounts.view_project_ledger_list").id, "list"],
                      [False, "form"]],
            "domain": [("account_id", "in", accounts.ids), ("parent_state", "!=", "cancel")],
            "context": {"search_default_posted": 1, "create": 0, "edit": 0},
            "target": "current",
        }

    def action_ledger_all(self):
        return self._mizan_ledger_action(self._mizan_project_accounts(), _("Project ledger — %s", self.name))

    def action_ledger_cost(self):
        return self._mizan_ledger_action(self.wip_account_id | self.cost_account_id, _("Costs — %s", self.name))

    def action_ledger_billing(self):
        return self._mizan_ledger_action(self.billing_account_id, _("Billing — %s", self.name))

    def action_ledger_client(self):
        return self._mizan_ledger_action(self.receivable_account_id, _("Client account — %s", self.name))

    def action_ledger_retention(self):
        return self._mizan_ledger_action(self.retention_account_id, _("Retention — %s", self.name))
