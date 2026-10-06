# -*- coding: utf-8 -*-
"""One screen that goes everywhere, and says what it will find when it gets there.

A shortcut bar is cheap to build and nearly useless: it saves two clicks and
tells the user nothing he did not already know. What makes a launcher worth
opening is the number on the tile. "Bank reconciliation" is a menu item.
"Bank reconciliation — 8 lines unexplained" is a reason to click, and the
absence of the number is a reason not to, which saves more time than the
shortcut does.

So every tile here is a destination plus the one figure that says whether it
needs you today. Where no honest figure exists -- the chart of accounts does
not have a state of readiness -- the tile carries a plain description instead
of an invented metric.

Tiles resolve their actions by external id at build time and skip themselves
when it does not resolve. That way this app depends on mizan_core alone: a
client without the cheque module simply has no cheque tiles, and gets them the
day the module is installed, with no upgrade of this one.
"""

from ast import literal_eval

from odoo import api, fields, models, _


class MizanQuickTile(models.TransientModel):
    _name = "mizan.quick.tile"
    _description = "Quick Access"
    _order = "sequence, id"

    sequence = fields.Integer()
    section = fields.Char(readonly=True)
    name = fields.Char(string="Destination", readonly=True)
    value = fields.Char(string="Right now", readonly=True)
    hint = fields.Char(string="What it is", readonly=True)
    icon = fields.Char(readonly=True)
    tone = fields.Selection(
        [("plain", "Plain"), ("good", "Good"), ("watch", "Watch"),
         ("bad", "Needs attention"), ("new", "Creates something")],
        default="plain", readonly=True)
    action_xmlid = fields.Char(readonly=True)
    res_model = fields.Char(readonly=True)
    domain = fields.Char(readonly=True)
    ctx = fields.Char(string="Context", readonly=True)
    creates = fields.Boolean(
        readonly=True,
        help="Opens a blank form rather than the list it would be filed in.")

    # ------------------------------------------------------------- opening
    def action_open(self):
        """Go where the tile says, carrying its filter with it.

        The action is fetched rather than rebuilt so the destination keeps its
        own views, filters and access rules; only the domain and context are
        narrowed, and only when the tile counted something specific.
        """
        self.ensure_one()
        action = None
        if self.action_xmlid:
            action = self.env["ir.actions.actions"]._for_xml_id(self.action_xmlid)
        elif self.res_model:
            action = {
                "type": "ir.actions.act_window",
                "name": self.name,
                "res_model": self.res_model,
                "view_mode": "list,form",
            }
        if not action:
            return False

        if self.domain:
            action["domain"] = literal_eval(self.domain)
        if self.creates:
            # "New invoice" should put the cursor in an invoice, not in the
            # list of invoices with a create button somewhere on it.
            action["views"] = [(False, "form")]
            action["view_mode"] = "form"
            action["res_id"] = False
            action.pop("domain", None)

        if self.ctx:
            context = dict(literal_eval(action.get("context") or "{}")
                           if isinstance(action.get("context"), str)
                           else (action.get("context") or {}))
            context.update(literal_eval(self.ctx))
            action["context"] = context
        action["target"] = "current"
        return action

    # ------------------------------------------------------------- building
    @api.model
    def _money(self, amount):
        return "%s %s" % ("{:,.0f}".format(amount or 0.0),
                          self.env.company.currency_id.name)

    @api.model
    def _plural(self, count, singular, plural):
        """Pick the form, and let a translation leave the number out.

        Arabic says "one cheque" without repeating the digit, so a form with
        no placeholder has to be allowed rather than crash the screen.
        """
        text = singular if count == 1 else plural
        try:
            return text % count
        except TypeError:
            return text

    @api.model
    def _tiles(self):
        """Every tile, in the order a finance manager would want them."""
        env = self.env
        user = env.user
        today = fields.Date.context_today(self)
        rows = []

        def tile(section, name, xmlid, icon, hint="", value="", tone="plain",
                 domain=None, ctx=None, model=None, creates=False):
            """Add a tile, unless the action it points at is not installed."""
            if xmlid and not env.ref(xmlid, raise_if_not_found=False):
                return
            rows.append({
                "sequence": len(rows) * 10,
                "section": section, "name": name, "icon": icon,
                "hint": hint, "value": value, "tone": tone,
                "action_xmlid": xmlid, "res_model": model,
                "domain": str(domain) if domain else False,
                "ctx": str(ctx) if ctx else False,
                "creates": creates,
            })

        def count(model, domain):
            if model not in env:
                return None
            try:
                return env[model].search_count(domain)
            except Exception:
                # A tile is not worth an error page. Missing rights on one
                # model should cost its figure, not the whole screen.
                return None

        accounting = (user.has_group("account.group_account_invoice")
                      or user.has_group("account.group_account_readonly"))

        # ---------------------------------------------------- the statements
        if accounting:
            s = _("Accounts & statements")
            n_accounts = count("account.account", [])
            tile(s, _("Chart of Accounts"), "account.action_account_form",
                 "fa-sitemap",
                 _("Every account, and what it is for"),
                 self._plural(n_accounts or 0, _("%s account"),
                              _("%s accounts")) if n_accounts else "")
            tile(s, _("Balance Sheet"), "mizan_core.action_balance_sheet",
                 "fa-balance-scale", _("What the company owns and owes"))
            tile(s, _("Profit and Loss"), "mizan_core.action_profit_loss",
                 "fa-line-chart", _("Revenue against cost, for a period"))
            tile(s, _("Trial Balance"),
                 "account_financial_report.action_trial_balance_wizard",
                 "fa-calculator", _("Every account, debit against credit"))
            tile(s, _("General Ledger"),
                 "account_financial_report.action_general_ledger_wizard",
                 "fa-book", _("Every movement on an account, in order"))
            tile(s, _("Aged Receivables"),
                 "account_financial_report.action_aged_partner_balance_wizard",
                 "fa-hourglass-half", _("Who owes, and for how long"))
            tile(s, _("VAT Return"),
                 "account_financial_report.action_vat_report_wizard",
                 "fa-percent", _("Form 201, by emirate"))
            tile(s, _("Journal Items"), "account.action_account_moves_all",
                 "fa-list", _("The ledger itself, unfiltered"))

        # ------------------------------------------------------------- bank
        if accounting:
            s = _("Bank & cash")
            unmatched = count("account.bank.statement.line",
                              [("is_reconciled", "=", False)])
            tile(s, _("Bank Reconciliation"),
                 "mizan_core.action_mizan_bank_reconcile", "fa-exchange",
                 _("Match what the bank says against the ledger"),
                 self._plural(unmatched, _("%s line unexplained"),
                              _("%s lines unexplained")) if unmatched else
                 _("everything is matched"),
                 "bad" if unmatched else "good")
            tile(s, _("Bank Statements"),
                 "mizan_core.action_mizan_bank_statements", "fa-university",
                 _("Upload a statement, or open one"))
            tile(s, _("Bank Transactions"),
                 "mizan_core.action_mizan_statement_lines", "fa-list-ul",
                 _("Every line the bank has sent"))
            tile(s, _("Payments"), "account.action_account_payments",
                 "fa-money", _("Received and paid out"))
            petty = count("account.move", [("state", "=", "draft"),
                                           ("move_type", "=", "entry")])
            tile(s, _("Petty Cash to Approve"),
                 "mizan_core.action_mizan_petty_to_approve", "fa-inbox",
                 _("Site spending waiting on a signature"),
                 _("%s waiting", petty) if petty else _("nothing waiting"),
                 "watch" if petty else "good")

        # ---------------------------------------------------------- cheques
        s = _("Cheques")
        week = fields.Date.add(today, days=7)
        live_cheque = [("state", "in", ("registered", "deposited", "to_approve"))]
        due_soon = count("mizan.cheque",
                         live_cheque + [("due_date", "<=", week)])
        tile(s, _("Cheques Received"),
             "mizan_cheque.action_mizan_cheque_received", "fa-download",
             _("Held, deposited, cleared"))
        tile(s, _("Cheques Issued"),
             "mizan_cheque.action_mizan_cheque_issued", "fa-upload",
             _("Signed, handed over, presented"))
        tile(s, _("Due Within a Week"),
             "mizan_cheque.action_mizan_cheque_issued", "fa-clock-o",
             _("Cheques that need the money to be there"),
             self._plural(due_soon, _("%s cheque"), _("%s cheques"))
             if due_soon else _("none this week"),
             "watch" if due_soon else "good",
             domain=live_cheque + [("due_date", "<=", str(week))])
        bounced = count("mizan.cheque", [("state", "in", ("bounced", "claimed"))])
        tile(s, _("Bounced & Under Claim"),
             "mizan_cheque.action_mizan_cheque_claims", "fa-exclamation-triangle",
             _("Money promised that did not arrive"),
             self._plural(bounced, _("%s cheque"), _("%s cheques"))
             if bounced else _("none outstanding"),
             "bad" if bounced else "good")

        # ------------------------------------------------- projects & sites
        s = _("Projects & sites")
        live = count("mizan.contract", [("state", "=", "running")])
        tile(s, _("Contracts"), "mizan_contracting.action_mizan_contract",
             "fa-file-text-o", _("Value, budget, what is left to build"),
             _("%s live", live) if live else _("none running"))
        certified = count("mizan.progress.claim", [("state", "=", "certified")])
        tile(s, _("Progress Claims"),
             "mizan_contracting.action_progress_claim", "fa-tasks",
             _("Measured, certified, invoiced"),
             _("%s certified, not invoiced", certified)
             if certified else _("nothing to bill"),
             "bad" if certified else "good")
        tile(s, _("Variation Orders"), "mizan_contracting.action_variation",
             "fa-random", _("Changes the client asked for"))
        tile(s, _("Guarantees & Bonds"),
             "mizan_contracting.action_bond_register", "fa-shield",
             _("What is lodged, and when it lapses"))
        requests = count("purchase.request", [("state", "=", "to_approve")])
        tile(s, _("Material Requests"),
             "purchase_request.purchase_request_form_action", "fa-cubes",
             _("What the site has asked for"),
             _("%s to approve", requests) if requests
             else _("nothing to approve"),
             "watch" if requests else "good")
        tile(s, _("Site Reports"), "mizan_site.action_site_report_office",
             "fa-building-o",
             _("What the engineers filed from the sites"))
        tile(s, _("Cost Codes"), "mizan_contracting.action_cost_code",
             "fa-tags", _("The trades a job is broken into"))

        # ----------------------------------------------------- create, fast
        s = _("Start something")
        new = _("opens a blank form")
        tile(s, _("Customer Invoice"), "account.action_move_out_invoice",
             "fa-file-text", _("A new tax invoice"), new, "new", creates=True,
             ctx={"default_move_type": "out_invoice"})
        tile(s, _("Vendor Bill"), "account.action_move_in_invoice",
             "fa-file-text-o", _("A bill from a supplier"), new, "new",
             creates=True, ctx={"default_move_type": "in_invoice"})
        tile(s, _("Progress Claim"), "mizan_contracting.action_progress_claim",
             "fa-tasks", _("Measure a period against the bill"), new, "new",
             creates=True)
        tile(s, _("Employee Advance"), "mizan_advance.action_employee_advance",
             "fa-user", _("Site cash, with a settlement to come"), new, "new",
             creates=True)
        tile(s, _("Expense"), "hr_expense.hr_expense_actions_my_all",
             "fa-credit-card", _("A receipt to be reimbursed"), new, "new",
             creates=True)
        tile(s, _("Purchase Order"), "purchase.purchase_form_action",
             "fa-shopping-cart", _("An order that becomes a commitment"),
             new, "new", creates=True)

        # -------------------------------------------------- closing the month
        if accounting:
            s = _("The month")
            tile(s, _("Month-End Close"), "mizan_closing.action_month_close",
                 "fa-lock", _("Check the evidence, then lock the period"))
            tile(s, _("Data Quality"), "mizan_hub.action_quality_open",
                 "fa-check-square-o", _("What will go wrong at the close"))
            tile(s, _("Work Inbox"), "mizan_hub.action_inbox_open",
                 "fa-bell-o", _("Everything waiting on you"))
            drafts = count("account.move", [("state", "=", "draft"),
                                            ("move_type", "!=", "entry")])
            tile(s, _("Draft Invoices & Bills"),
                 "account.action_move_journal_line", "fa-pencil",
                 _("Not in the ledger until they are posted"),
                 self._plural(drafts, _("%s draft"), _("%s drafts"))
                 if drafts else _("none open"),
                 "watch" if drafts else "good",
                 domain=[("state", "=", "draft"), ("move_type", "!=", "entry")])

        return rows

    @api.model
    def action_refresh(self):
        """Rebuilt on every visit: a figure from last week is a lie with a number on it."""
        self.search([]).unlink()
        self.create(self._tiles())
        return {
            "type": "ir.actions.act_window",
            "name": _("Quick Access"),
            "res_model": "mizan.quick.tile",
            "view_mode": "kanban",
            "target": "current",
            "context": {"search_default_group_section": 1},
        }
