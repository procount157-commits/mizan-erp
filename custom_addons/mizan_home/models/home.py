# -*- coding: utf-8 -*-
"""The home page's content, built on the server for the person asking.

Everything the page shows is decided here, in one place that can read the
books: which cards a role gets, which figure is red today, which screens are
installed. The browser side only draws. A card or a figure that cannot be
read (an optional module missing, a right the person does not have) is left
out, never an error page.
"""
from ast import literal_eval
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class MizanHome(models.AbstractModel):
    _name = "mizan.home"
    _description = "Home"

    # ------------------------------------------------------------ helpers
    @api.model
    def _has(self, *groups):
        """Does the user hold any of these groups? Unknown groups count as no."""
        user = self.env.user
        for group in groups:
            try:
                if user.has_group(group):
                    return True
            except ValueError:
                continue
        return False

    @api.model
    def _count(self, model, domain):
        if model not in self.env:
            return None
        try:
            return self.env[model].search_count(domain)
        except Exception:
            return None

    @api.model
    def _sum(self, model, domain, field):
        if model not in self.env:
            return None
        try:
            return sum(self.env[model].search(domain).mapped(field))
        except Exception:
            return None

    @api.model
    def _money(self, amount):
        return "%s %s" % ("{:,.0f}".format(amount or 0.0),
                          self.env.company.currency_id.name)

    @api.model
    def _resolves(self, xmlid):
        return bool(xmlid and self.env.ref(xmlid, raise_if_not_found=False))

    # ------------------------------------------------------------ opening
    @api.model
    def resolve_link(self, link):
        """Turn a link the page holds into the action to run.

        Fetched rather than rebuilt where an xmlid exists, so the destination
        keeps its own views, filters and rights; only narrowed by the link's
        domain and context."""
        action = None
        xmlid = link.get("xmlid")
        if self._resolves(xmlid):
            action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        elif link.get("model") and link["model"] in self.env:
            # The web client's doAction reads action.views, so a hand-built
            # action must carry it; view_mode alone is not enough.
            action = {
                "type": "ir.actions.act_window",
                "name": link.get("label") or link["model"],
                "res_model": link["model"],
                "view_mode": "list,form",
                "views": [[False, "list"], [False, "form"]],
            }
        if not action:
            return False
        if link.get("domain"):
            action["domain"] = link["domain"]
        if link.get("creates"):
            action["views"] = [[False, "form"]]
            action["view_mode"] = "form"
            action["res_id"] = False
            action.pop("domain", None)
        if link.get("context"):
            base = action.get("context") or {}
            if isinstance(base, str):
                try:
                    base = literal_eval(base)
                except Exception:
                    base = {}
            base = dict(base)
            base.update(link["context"])
            action["context"] = base
        action["target"] = "current"
        return action

    @api.model
    def search(self, query):
        """Find anything, from the box at the top of the page."""
        finder = self.env["mizan.find"].create({"query": (query or "").strip()})
        return finder.action_search()

    # ------------------------------------------------------------ the page
    @api.model
    def get_home(self):
        env = self.env
        user = env.user
        company = env.company
        today = fields.Date.context_today(self)
        week = today + timedelta(days=7)
        month_start = today.replace(day=1)
        sections = []

        def readable(model_name):
            """A link to records the person cannot read is a link to an error."""
            if not model_name or model_name not in env:
                return False
            try:
                return env[model_name].has_access("read")
            except Exception:
                return False

        def link(label, xmlid=None, model=None, icon="fa-angle-left",
                 domain=None, context=None, creates=False, count=None, tone=None):
            if self._resolves(xmlid):
                target = env.ref(xmlid)
                if target._name == "ir.actions.act_window" and not readable(target.res_model):
                    return None
            elif not readable(model):
                return None
            return {"label": label, "xmlid": xmlid if self._resolves(xmlid) else None,
                    "model": model, "icon": icon, "domain": domain or [],
                    "context": context or {}, "creates": creates,
                    "count": count, "tone": tone or ("plain" if not count else "watch")}

        def section(key, title, icon, figures, links, groups=None, hint=""):
            if groups and not self._has(*groups):
                return
            links = [l for l in links if l]
            figures = [f for f in figures if f]
            if not links and not figures:
                return
            sections.append({"key": key, "title": title, "icon": icon,
                             "hint": hint, "figures": figures, "links": links})

        def fig(label, value, tone="plain", link_=None):
            if value is None:
                return None
            return {"label": label, "value": value, "tone": tone, "link": link_}

        accountant = self._has("account.group_account_invoice", "account.group_account_manager")
        reads_books = accountant or self._has("account.group_account_readonly",
                                              "mizan_hub.group_general_manager")
        site = self._has("mizan_site.group_site_engineer")
        approver = self._has("hr_expense.group_hr_expense_team_approver",
                             "hr_expense.group_hr_expense_manager")

        # ------------------------------------------------- waiting for you
        waiting = []
        try:
            rows = env["mizan.work.item"]._gather()
            if rows:
                waiting.append({"label": _("In your work inbox"), "count": len(rows),
                                "link": link(_("Work Inbox"), "mizan_hub.action_inbox_open",
                                             icon="fa-inbox")})
        except Exception:
            pass
        n = self._count("mail.activity", [("user_id", "=", user.id), ("date_deadline", "<=", today)])
        if n:
            waiting.append({"label": _("To do today"), "count": n,
                            "link": link(_("My activities"), model="mail.activity", icon="fa-check-square-o",
                                         domain=[("user_id", "=", user.id), ("date_deadline", "<=", today)])})
        if "project.task" in env:
            n = self._count("project.task", [("user_ids", "in", user.id), ("is_closed", "=", False),
                                             ("date_deadline", "<", fields.Datetime.now())])
            if n:
                waiting.append({"label": _("Tasks past their deadline"), "count": n,
                                "link": link(_("My tasks"), model="project.task", icon="fa-tasks",
                                             domain=[("user_ids", "in", user.id), ("is_closed", "=", False)])})
        if approver and "hr.expense.sheet" in env:
            try:
                sheets = env["hr.expense.sheet"].search([("state", "=", "submit")])
                mine = sheets.filtered("can_approve")
                if mine:
                    waiting.append({"label": _("Receipts waiting for your approval"), "count": len(mine),
                                    "link": link(_("Receipts to approve"),
                                                 "mizan_pettycash.action_approve_receipts", icon="fa-camera")})
            except Exception:
                pass
        if accountant:
            n = self._count("account.move", [("state", "=", "draft"), ("move_type", "!=", "entry")])
            if n:
                waiting.append({"label": _("Draft invoices and bills"), "count": n,
                                "link": link(_("Drafts"), model="account.move", icon="fa-file-o",
                                             domain=[("state", "=", "draft"), ("move_type", "!=", "entry")])})
            n = self._count("mizan.cheque", [("state", "in", ("registered", "deposited")),
                                             ("due_date", "<=", week)])
            if n:
                waiting.append({"label": _("Cheques due within a week"), "count": n,
                                "link": link(_("Cheques due"), model="mizan.cheque", icon="fa-money",
                                             domain=[("state", "in", ("registered", "deposited")),
                                                     ("due_date", "<=", week)])})

        # ------------------------------------------------- my site (engineers)
        if site:
            employee = env["hr.employee"].search([("user_id", "=", user.id)], limit=1)
            held = None
            if employee and "mizan.employee.advance" in env:
                try:
                    cash = env["mizan.employee.advance"]._petty_cash(employee)
                    held = cash["available"]
                except Exception:
                    held = None
            filed = self._count("mizan.site.report", [("author_id", "=", user.id), ("date", "=", today)])
            section("site", _("My site"), "fa-hard-hat fa-building-o", [
                fig(_("Petty cash available"), self._money(held) if held is not None else None,
                    "bad" if (held or 0) < 0 else "good"),
                fig(_("Today's report"), _("Filed") if filed else _("Not yet"),
                    "good" if filed else "watch"),
            ], [
                link(_("Photograph a bill"), "mizan_site.action_site_capture", icon="fa-camera"),
                link(_("Daily report"), "mizan_site.action_site_report", icon="fa-pencil-square-o"),
                link(_("My petty cash"), "mizan_pettycash.action_my_receipts", icon="fa-money"),
                link(_("Ask for a top-up"), "mizan_pettycash.action_topup", icon="fa-plus-circle"),
                link(_("My projects"), model="project.project", icon="fa-folder-open-o",
                     domain=[("message_partner_ids", "in", user.partner_id.ids)]),
            ])

        # ------------------------------------------------- accounting
        if reads_books:
            receivable = self._sum("account.move", [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                                                   ("payment_state", "in", ("not_paid", "partial"))], "amount_residual")
            overdue = self._sum("account.move", [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                                                ("payment_state", "in", ("not_paid", "partial")),
                                                ("invoice_date_due", "<", today)], "amount_residual")
            payable = self._sum("account.move", [("move_type", "=", "in_invoice"), ("state", "=", "posted"),
                                                ("payment_state", "in", ("not_paid", "partial"))], "amount_residual")
            drafts = self._count("account.move", [("state", "=", "draft"), ("move_type", "!=", "entry")])
            section("accounting", _("Accounting"), "fa-book", [
                fig(_("Owed to us"), self._money(receivable),
                    "watch" if (overdue or 0) > 0 else "plain",
                    link(_("Open invoices"), "account.action_move_out_invoice_type",
                         domain=[("payment_state", "in", ("not_paid", "partial")), ("state", "=", "posted")])),
                fig(_("Of it overdue"), self._money(overdue), "bad" if (overdue or 0) > 0 else "good"),
                fig(_("We owe"), self._money(payable), "plain",
                    link(_("Open bills"), "account.action_move_in_invoice_type",
                         domain=[("payment_state", "in", ("not_paid", "partial")), ("state", "=", "posted")])),
                fig(_("Drafts"), str(drafts or 0), "watch" if drafts else "good"),
            ], [
                link(_("New invoice"), "account.action_move_out_invoice_type", icon="fa-plus",
                     creates=True, context={"default_move_type": "out_invoice"}) if accountant else None,
                link(_("New bill"), "account.action_move_in_invoice_type", icon="fa-plus",
                     creates=True, context={"default_move_type": "in_invoice"}) if accountant else None,
                link(_("Customer invoices"), "account.action_move_out_invoice_type", icon="fa-file-text-o"),
                link(_("Vendor bills"), "account.action_move_in_invoice_type", icon="fa-file-text"),
                link(_("Payments"), "account.action_account_payments", icon="fa-exchange"),
                link(_("Journal entries"), "account.action_move_journal_line", icon="fa-list"),
                link(_("Chart of accounts"), "account.action_account_form", icon="fa-sitemap"),
                link(_("Work inbox"), "mizan_hub.action_inbox_open", icon="fa-inbox"),
                link(_("Month-end close"), "mizan_closing.action_month_close", icon="fa-lock"),
                link(_("Data quality"), "mizan_hub.action_quality_open", icon="fa-check-circle-o"),
            ], hint=_("Invoices, bills, payments and the ledger"))

        # ------------------------------------------------- VAT
        if reads_books:
            q_start = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
            q_end_month = q_start.month + 2
            q_end = (q_start.replace(month=q_end_month + 1, day=1) - timedelta(days=1)) if q_end_month < 12 \
                else q_start.replace(month=12, day=31)
            due_201 = q_end + timedelta(days=28)
            Tax = env["account.tax"]
            out_accounts = Tax.search([("type_tax_use", "=", "sale"), ("company_id", "=", company.id)]) \
                .invoice_repartition_line_ids.account_id
            in_accounts = Tax.search([("type_tax_use", "=", "purchase"), ("company_id", "=", company.id)]) \
                .invoice_repartition_line_ids.account_id
            period = [("parent_state", "=", "posted"), ("date", ">=", q_start), ("date", "<=", q_end)]
            output = self._sum("account.move.line", period + [("account_id", "in", out_accounts.ids)], "balance")
            inp = self._sum("account.move.line", period + [("account_id", "in", in_accounts.ids)], "balance")
            net = None
            if output is not None and inp is not None:
                net = -(output or 0.0) - (inp or 0.0)   # output is a credit (negative balance)
            no_trn = self._count("res.partner", [("is_company", "=", True), ("vat", "=", False),
                                                 ("customer_rank", ">", 0)])
            days_left = (due_201 - today).days
            section("vat", _("VAT"), "fa-percent", [
                fig(_("Net VAT this quarter"), self._money(net) if net is not None else None,
                    "watch" if (net or 0) > 0 else "plain"),
                fig(_("Form 201 due"), due_201.strftime("%d/%m"),
                    "bad" if days_left <= 7 else ("watch" if days_left <= 21 else "plain")),
                fig(_("Customers without a TRN"), str(no_trn or 0), "watch" if no_trn else "good",
                    link(_("Customers without a TRN"), model="res.partner",
                         domain=[("is_company", "=", True), ("vat", "=", False), ("customer_rank", ">", 0)])),
            ], [
                link(_("VAT return (Form 201)"), "account_financial_report.action_vat_report_wizard", icon="fa-file-text-o"),
                link(_("Taxes"), "account.action_tax_form", icon="fa-percent"),
                link(_("Tax entries this quarter"), model="account.move.line", icon="fa-list",
                     domain=period + [("account_id", "in", (out_accounts | in_accounts).ids)]),
                link(_("E-invoicing readiness"), "mizan_einvoice.action_mizan_einvoice_readiness", icon="fa-bolt"),
            ], hint=_("The return is due 28 days after the quarter ends"))

        # ------------------------------------------------- cheques & banks
        if reads_books:
            recv_due = self._count("mizan.cheque", [("cheque_type", "=", "received"),
                                                    ("state", "in", ("registered", "deposited")), ("due_date", "<=", week)])
            issued_due = self._count("mizan.cheque", [("cheque_type", "=", "issued"),
                                                      ("state", "in", ("registered", "deposited")), ("due_date", "<=", week)])
            bounced = self._count("mizan.cheque", [("state", "=", "bounced")])
            open_lines = self._count("account.bank.statement.line", [("is_reconciled", "=", False)])
            cash = self._sum("account.move.line", [("parent_state", "=", "posted"),
                                                   ("account_id.account_type", "=", "asset_cash")], "balance")
            section("banking", _("Cheques & banks"), "fa-university", [
                fig(_("Cash & banks"), self._money(cash), "plain"),
                fig(_("Cheques to collect this week"), str(recv_due or 0), "watch" if recv_due else "plain",
                    link(_("Cheques received"), "mizan_cheque.action_mizan_cheque_received",
                         domain=[("state", "in", ("registered", "deposited")), ("due_date", "<=", week)])),
                fig(_("Our cheques due this week"), str(issued_due or 0), "bad" if issued_due else "plain",
                    link(_("Cheques issued"), "mizan_cheque.action_mizan_cheque_issued",
                         domain=[("state", "in", ("registered", "deposited")), ("due_date", "<=", week)])),
                fig(_("Bank lines unexplained"), str(open_lines or 0), "watch" if open_lines else "good",
                    link(_("Bank reconciliation"), "mizan_core.action_mizan_bank_reconcile")),
            ], [
                link(_("Cheques received"), "mizan_cheque.action_mizan_cheque_received", icon="fa-arrow-circle-down"),
                link(_("Cheques issued"), "mizan_cheque.action_mizan_cheque_issued", icon="fa-arrow-circle-up"),
                link(_("Bounced & under claim"), "mizan_cheque.action_mizan_cheque_claims", icon="fa-exclamation-circle",
                     count=bounced or None, tone="bad" if bounced else None),
                link(_("Bank reconciliation"), "mizan_core.action_mizan_bank_reconcile", icon="fa-balance-scale"),
                link(_("Bank statements"), "mizan_core.action_mizan_bank_statements", icon="fa-file-o"),
                link(_("Guarantees & bonds"), "mizan_contracting.action_bond_register", icon="fa-shield"),
            ])

        # ------------------------------------------------- projects & claims
        if "mizan.contract" in env and (reads_books or self._has("project.group_project_manager")):
            running = None
            try:
                contracts = env["mizan.contract"].search([("state", "=", "running")])
                running = len(contracts)
                over = contracts.filtered(lambda c: c.cost_at_completion > c.revised_contract_value)
            except Exception:
                contracts = env["mizan.contract"].browse()
                over = contracts
            to_invoice = self._count("mizan.progress.claim", [("state", "=", "certified")])
            retention = self._sum("mizan.progress.claim", [("state", "=", "invoiced")], "retention_amount")
            section("projects", _("Projects & claims"), "fa-building", [
                fig(_("Running contracts"), str(running) if running is not None else None,
                    "bad" if over else "plain",
                    link(_("Contracts"), "mizan_contracting.action_mizan_contract")),
                fig(_("Contracts over budget"), str(len(over)), "bad" if over else "good",
                    link(_("Over budget"), "mizan_contracting.action_mizan_contract",
                         domain=[("id", "in", over.ids)]) if over else None),
                fig(_("Certified, not yet invoiced"), str(to_invoice or 0), "watch" if to_invoice else "good",
                    link(_("Claims to invoice"), "mizan_contracting.action_progress_claim",
                         domain=[("state", "=", "certified")])),
                fig(_("Retention held by clients"), self._money(retention), "plain"),
            ], [
                link(_("New progress claim"), "mizan_contracting.action_progress_claim", icon="fa-plus", creates=True),
                link(_("Contracts"), "mizan_contracting.action_mizan_contract", icon="fa-file-text-o"),
                link(_("Progress claims"), "mizan_contracting.action_progress_claim", icon="fa-tasks"),
                link(_("Variation orders"), "mizan_contracting.action_variation", icon="fa-random"),
                link(_("Project health"), "mizan_hub.action_health_open", icon="fa-heartbeat"),
                link(_("Overhead allocation"), "mizan_contracting.action_overhead_allocation", icon="fa-pie-chart"),
                link(_("Subcontracts"), "mizan_contracting.action_subcontract", icon="fa-handshake-o"),
                link(_("Plant & equipment"), "mizan_contracting.action_plant", icon="fa-truck"),
                link(_("Site reports"), "mizan_site.action_site_report_office", icon="fa-clipboard"),
            ])

        # ------------------------------------------------- petty cash & expenses
        if not site:
            to_approve = None
            if approver and "hr.expense.sheet" in env:
                try:
                    to_approve = len(env["hr.expense.sheet"].search(
                        [("state", "=", "submit"), ("mizan_advance_id", "!=", False)]).filtered("can_approve"))
                except Exception:
                    to_approve = None
            out = self._sum("mizan.employee.advance", [("state", "=", "paid")], "amount_outstanding")
            to_post = self._count("hr.expense.sheet", [("state", "=", "approve")]) if accountant else None
            section("petty", _("Petty cash & expenses"), "fa-money", [
                fig(_("Cash out on site"), self._money(out) if out is not None else None, "plain",
                    link(_("Who holds cash"), "mizan_pettycash.action_balances")),
                fig(_("Receipts waiting for you"), str(to_approve) if to_approve is not None else None,
                    "watch" if to_approve else "good",
                    link(_("Receipts to approve"), "mizan_pettycash.action_approve_receipts")),
                fig(_("Approved, to post"), str(to_post) if to_post is not None else None,
                    "watch" if to_post else "good",
                    link(_("Receipts to post"), "mizan_pettycash.action_post_receipts")),
            ], [
                link(_("Photograph a bill"), "mizan_site.action_site_capture", icon="fa-camera"),
                link(_("Receipts to approve"), "mizan_pettycash.action_approve_receipts", icon="fa-check"),
                link(_("Who holds cash"), "mizan_pettycash.action_balances", icon="fa-users"),
                link(_("Advances & top-ups"), "mizan_advance.action_employee_advance", icon="fa-arrow-circle-up"),
                link(_("Expense claims"), "hr_expense.hr_expense_actions_my_all", icon="fa-credit-card"),
            ])

        # ------------------------------------------------- people & payroll
        if self._has("hr.group_hr_user", "hr_holidays.group_hr_holidays_user", "base.group_system"):
            staff = self._count("hr.employee", [("active", "=", True)])
            leaves = self._count("hr.leave", [("state", "in", ("confirm", "validate1"))])
            slips = self._count("hr.payslip", [("state", "=", "draft"), ("date_from", ">=", month_start)])
            section("people", _("People & payroll"), "fa-users", [
                fig(_("Employees"), str(staff or 0), "plain", link(_("Employees"), "hr.open_view_employee_list_my")),
                fig(_("Leave requests to approve"), str(leaves or 0), "watch" if leaves else "good",
                    link(_("Leave requests"), model="hr.leave", domain=[("state", "in", ("confirm", "validate1"))])),
                fig(_("Payslips in draft this month"), str(slips) if slips is not None else None,
                    "watch" if slips else "plain", link(_("Payslips"), model="hr.payslip")),
            ], [
                link(_("Employees"), "hr.open_view_employee_list_my", model="hr.employee", icon="fa-id-card-o"),
                link(_("Leave requests"), model="hr.leave", icon="fa-plane"),
                link(_("Attendance"), model="hr.attendance", icon="fa-clock-o"),
                link(_("Payslips"), model="hr.payslip", icon="fa-file-text-o"),
                link(_("WPS salary file"), "mizan_wps.action_mizan_wps", icon="fa-bank"),
                link(_("Employee advances"), "mizan_advance.action_employee_advance", icon="fa-money"),
            ])

        # ------------------------------------------------- operations & tasks
        if "project.task" in env and self._has("project.group_project_user"):
            mine = [("user_ids", "in", user.id), ("is_closed", "=", False)]
            my_open = self._count("project.task", mine)
            my_late = self._count("project.task", mine + [("date_deadline", "<", fields.Datetime.now())])
            cases = self._count("mizan.workflow.case", [("state", "=", "open")])
            section("ops", _("Operations & tasks"), "fa-check-square-o", [
                fig(_("My open tasks"), str(my_open or 0), "plain",
                    link(_("My tasks"), model="project.task", domain=mine)),
                fig(_("Past their deadline"), str(my_late or 0), "bad" if my_late else "good",
                    link(_("Late tasks"), model="project.task",
                         domain=mine + [("date_deadline", "<", fields.Datetime.now())])),
                fig(_("Workflows in progress"), str(cases) if cases is not None else None, "plain",
                    link(_("Workflows in progress"), "mizan_ops.action_ops_case")),
            ], [
                link(_("My tasks"), "mizan_ops.action_ops_my_tasks", model="project.task", icon="fa-tasks",
                     domain=mine, context={"search_default_my_tasks": 1}),
                link(_("New task"), "mizan_ops.action_ops_new_task", icon="fa-plus"),
                link(_("Start a workflow"), "mizan_ops.action_ops_start", icon="fa-play-circle-o"),
                link(_("Upload a file"), "mizan_ops.action_ops_upload", icon="fa-cloud-upload"),
                link(_("Workflows in progress"), "mizan_ops.action_ops_case", icon="fa-folder-open-o"),
                link(_("Documents"), "mizan_ops.action_ops_files", icon="fa-paperclip"),
                link(_("Projects"), "project.open_view_project_all", model="project.project", icon="fa-cubes"),
            ])

        # ------------------------------------------------- sales & customers
        if self._has("sales_team.group_sale_salesman"):
            opps = self._count("crm.lead", [("type", "=", "opportunity"), ("probability", "<", 100), ("active", "=", True)])
            pipeline = self._sum("crm.lead", [("type", "=", "opportunity"), ("probability", "<", 100),
                                              ("active", "=", True)], "expected_revenue")
            quotes = self._count("sale.order", [("state", "in", ("draft", "sent"))])
            section("sales", _("Sales & customers"), "fa-handshake-o", [
                fig(_("Open opportunities"), str(opps or 0), "plain",
                    link(_("Pipeline"), "crm.crm_lead_action_pipeline", model="crm.lead")),
                fig(_("Pipeline value"), self._money(pipeline), "plain"),
                fig(_("Quotations awaiting"), str(quotes or 0), "watch" if quotes else "plain",
                    link(_("Quotations"), "sale.action_quotations_with_onboarding", model="sale.order",
                         domain=[("state", "in", ("draft", "sent"))])),
            ], [
                link(_("New customer"), "base.action_partner_form", model="res.partner", icon="fa-user-plus",
                     creates=True, context={"default_customer_rank": 1, "default_is_company": True}),
                link(_("Customers"), "base.action_partner_form", model="res.partner", icon="fa-address-book-o",
                     domain=[("customer_rank", ">", 0)]),
                link(_("Pipeline"), "crm.crm_lead_action_pipeline", model="crm.lead", icon="fa-filter"),
                link(_("Quotations"), "sale.action_quotations_with_onboarding", model="sale.order", icon="fa-file-text-o"),
                link(_("Sales orders"), "sale.action_orders", model="sale.order", icon="fa-shopping-cart",
                     domain=[("state", "=", "sale")]),
                link(_("Purchase orders"), "purchase.purchase_form_action", model="purchase.order", icon="fa-truck"),
            ])

        # ------------------------------------------------- reports
        if reads_books:
            section("reports", _("Reports"), "fa-bar-chart", [], [
                link(_("Dashboard"), "mizan_hub.action_dashboard", icon="fa-tachometer"),
                link(_("Profit & loss"), "mizan_core.action_profit_loss", icon="fa-line-chart"),
                link(_("Balance sheet"), "mizan_core.action_balance_sheet", icon="fa-balance-scale"),
                link(_("Trial balance"), "account_financial_report.action_trial_balance_wizard", icon="fa-table"),
                link(_("General ledger"), "account_financial_report.action_general_ledger_wizard", icon="fa-book"),
                link(_("Aged receivables & payables"), "account_financial_report.action_aged_partner_balance_wizard", icon="fa-hourglass-half"),
                link(_("VAT return"), "account_financial_report.action_vat_report_wizard", icon="fa-percent"),
                link(_("Project health"), "mizan_hub.action_health_open", icon="fa-heartbeat"),
                link(_("Revenue recognition"), "mizan_contracting.action_mizan_recognition", icon="fa-calculator"),
                link(_("Budgets"), model="budget.budget", icon="fa-bullseye"),
            ], hint=_("Every report in Arabic and English, to Excel or PDF"))

        # ------------------------------------------------- administration
        if self._has("base.group_system"):
            alerts = self._count("mizan.alert.log", [("state", "=", "open")])
            section("admin", _("Administration"), "fa-cog", [
                fig(_("Open alerts"), str(alerts) if alerts is not None else None,
                    "watch" if alerts else "good", link(_("Alert log"), "mizan_alert.action_alert_log")),
            ], [
                link(_("Users & rights"), "base.action_res_users", model="res.users", icon="fa-user"),
                link(_("Company"), "base.action_res_company_form", model="res.company", icon="fa-building-o"),
                link(_("Alert rules"), "mizan_alert.action_alert_rules", icon="fa-bell-o"),
                link(_("Workflow templates"), "mizan_ops.action_ops_template", icon="fa-sitemap"),
                link(_("Phones with the app"), "mizan_mobile.action_native_devices", icon="fa-mobile"),
                link(_("Data quality"), "mizan_hub.action_quality_open", icon="fa-check-circle-o"),
            ])

        hour = fields.Datetime.context_timestamp(self, fields.Datetime.now()).hour
        greeting = _("Good morning") if hour < 12 else (_("Good afternoon") if hour < 17 else _("Good evening"))
        return {
            "greeting": "%s، %s" % (greeting, user.name.split(" ")[0]),
            "user": user.name,
            "company": company.name,
            "date": fields.Date.context_today(self).strftime("%d/%m/%Y"),
            "waiting": waiting,
            "sections": sections,
        }
