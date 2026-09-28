# -*- coding: utf-8 -*-
"""A month end that is a record rather than a memory.

The finance manager's objection to the old way was not that the checks did not
exist — scripts/health_check.py has run them for weeks. It was that running
them was his own discipline, the output went to a terminal, and nothing in the
system knew whether September had been closed or by whom.

So a close is a persistent record: which period, which checks ran, what each
one found, who closed it and when. Re-running the checks replaces the results
and leaves the record; closing writes the lock date and stamps the record.

Two decisions worth stating.

BLOCKING VERSUS WARNING. A check that fails because the ledger does not
balance and a check that fails because a cost carries no cost code are not the
same kind of failure, and treating them alike produces a close nobody can ever
pass — which ends with the whole thing being skipped. Arithmetic and tax block.
Hygiene warns, and the manager may close over it deliberately, which is
recorded.

THE SOFT LOCK. Closing sets fiscalyear_lock_date, not hard_lock_date. The hard
lock cannot be lifted by anyone, ever, including the person who set it. A
month end is a routine operation and must not make an irreversible decision on
a manager's behalf; if a client later needs September reopened for a genuine
correction, that has to remain possible.
"""

from ast import literal_eval
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanMonthClose(models.Model):
    _name = "mizan.month.close"
    _description = "Month-End Close"
    _inherit = ["mail.thread"]
    _order = "date_to desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(string="From", required=True,
                            default=lambda self: self._default_from())
    date_to = fields.Date(string="To", required=True,
                          default=lambda self: self._default_to())

    state = fields.Selection(
        [("draft", "Not started"),
         ("checking", "Checks run"),
         ("closed", "Closed")],
        default="draft", required=True, tracking=True)

    check_ids = fields.One2many("mizan.month.close.check", "close_id",
                                string="Checks")
    blocking_count = fields.Integer(compute="_compute_counts", store=True)
    warning_count = fields.Integer(compute="_compute_counts", store=True)
    checked_on = fields.Datetime(readonly=True)
    ready = fields.Boolean(compute="_compute_counts", store=True,
                           string="Ready to close")

    closed_by_id = fields.Many2one("res.users", readonly=True, tracking=True)
    closed_on = fields.Datetime(readonly=True, tracking=True)
    closed_over_warnings = fields.Integer(
        readonly=True, string="Warnings accepted at close",
        help="How many warnings the manager knowingly closed over. Kept "
             "because 'we closed with eleven open' is a different month from "
             "'we closed clean'.")
    lock_date_before = fields.Date(
        readonly=True,
        help="What the lock date was before this close, so reopening puts it "
             "back rather than guessing.")
    note = fields.Text(string="Manager's note")

    _sql_constraints = [
        ("period_company_uniq", "unique(date_from, date_to, company_id)",
         "This period has already been set up for closing."),
    ]

    @api.model
    def _default_from(self):
        today = fields.Date.context_today(self)
        return (today - relativedelta(months=1)).replace(day=1)

    @api.model
    def _default_to(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1) - relativedelta(days=1)

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        for record in self:
            if record.date_to:
                record.name = record.date_to.strftime("%B %Y")
            else:
                record.name = _("New close")

    @api.depends("check_ids.count", "check_ids.blocking", "check_ids.passed")
    def _compute_counts(self):
        for record in self:
            failed = record.check_ids.filtered(lambda c: not c.passed)
            record.blocking_count = len(failed.filtered("blocking"))
            record.warning_count = len(failed) - record.blocking_count
            record.ready = bool(record.check_ids) and not record.blocking_count

    # ------------------------------------------------------------- checking
    def _check_definitions(self):
        """Every check, as data: a label, a model, a domain, and whether a
        failure is an error or a fact the manager should know."""
        self.ensure_one()
        period = [("date", ">=", self.date_from), ("date", "<=", self.date_to)]
        posted = [("parent_state", "=", "posted")] + period
        company = [("company_id", "=", self.company_id.id)]

        return [
            # --- arithmetic: a failure here is a bug
            {"key": "unbalanced", "category": "arithmetic", "blocking": True,
             "name": _("Posted entries that do not balance on their own"),
             "model": "account.move", "domain": [],
             "custom": "_check_unbalanced",
             "note": _("Each entry must balance by itself, not only in total.")},

            # --- documents that are not decisions yet
            {"key": "draft_moves", "category": "documents", "blocking": True,
             "name": _("Invoices and bills still in draft"),
             "model": "account.move",
             "domain": company + period + [("state", "=", "draft"),
                                           ("move_type", "!=", "entry")],
             "note": _("Not in the ledger, not in the VAT return, and not in "
                       "any report for the month you are closing.")},
            {"key": "draft_entries", "category": "documents", "blocking": True,
             "name": _("Journal entries still in draft"),
             "model": "account.move",
             "domain": company + period + [("state", "=", "draft"),
                                           ("move_type", "=", "entry")],
             "note": _("A month closed over an unposted entry is closed over "
                       "a figure somebody meant to include.")},

            # --- tax: blocks the return, so it blocks the close
            {"key": "untaxed_lines", "category": "tax", "blocking": True,
             "name": _("Posted invoice lines carrying no tax decision"),
             "model": "account.move.line",
             "domain": posted + [
                 ("move_id.move_type", "in", ("out_invoice", "out_refund")),
                 ("display_type", "=", "product"), ("tax_ids", "=", False)],
             "note": _("Zero-rated, exempt and reverse charge are each "
                       "reported in their own box. A blank has no box.")},
            {"key": "no_trn", "category": "tax", "blocking": False,
             "name": _("Customers invoiced this month with no TRN"),
             "model": "account.move",
             "domain": company + period + [
                 ("state", "=", "posted"), ("move_type", "=", "out_invoice"),
                 ("partner_id.vat", "=", False)],
             "note": _("The buyer cannot reclaim the input tax on those "
                       "invoices.")},

            # --- contracting: revenue that belongs to the month
            {"key": "certified_unbilled", "category": "contracting",
             "blocking": True,
             "name": _("Certified claims not invoiced"),
             "model": "mizan.progress.claim",
             "domain": [("state", "=", "certified"), ("invoice_id", "=", False),
                        ("date", "<=", self.date_to)],
             "note": _("Work the client agreed to pay for, in a month that "
                       "will not show the revenue.")},
            {"key": "unrecognised", "category": "contracting", "blocking": False,
             "name": _("Contracts with revenue earned and not recognised"),
             "model": "mizan.contract", "domain": [],
             "custom": "_check_unrecognised",
             "note": _("IFRS 15 puts revenue where the progress is, not where "
                       "the invoice is.")},
            {"key": "loss_unprovided", "category": "contracting",
             "blocking": True,
             "name": _("Loss-making contracts with no provision booked"),
             "model": "mizan.contract",
             "domain": [("state", "=", "running"), ("is_loss_making", "=", True),
                        ("loss_provision_booked", "=", 0)],
             "note": _("The whole expected loss belongs in this period, not "
                       "spread over the periods left.")},

            # --- banking
            {"key": "unreconciled", "category": "banking", "blocking": False,
             "name": _("Bank lines not matched"),
             "model": "account.bank.statement.line",
             "domain": [("is_reconciled", "=", False),
                        ("date", "<=", self.date_to)],
             "note": _("The bank moved money that nothing in the ledger "
                       "explains.")},
            {"key": "cheques_due", "category": "banking", "blocking": False,
             "name": _("Cheques past their date and not settled"),
             "model": "mizan.cheque",
             "domain": [("state", "in", ("deposited", "registered")),
                        ("due_date", "<=", self.date_to)],
             "note": _("Either the bank has not told you, or it bounced and "
                       "nobody recorded it.")},

            # --- costing hygiene
            {"key": "no_cost_centre", "category": "costing", "blocking": False,
             "name": _("Direct job costs with no cost centre"),
             "model": "account.move.line",
             "domain": posted + [
                 ("account_id.account_type", "=", "expense_direct_cost"),
                 ("analytic_distribution", "=", False)],
             "note": _("Outside every project, so it understates progress and "
                       "therefore revenue.")},
            {"key": "no_cost_code", "category": "costing", "blocking": False,
             "name": _("Direct job costs with no cost code"),
             "model": "account.move.line",
             "domain": posted + [
                 ("account_id.account_type", "=", "expense_direct_cost"),
                 ("mizan_cost_code_id", "=", False)],
             "note": _("Reaches the project total but no budget line, so the "
                       "breakdown stops adding up.")},

            # --- things that expire
            {"key": "bonds", "category": "contracting", "blocking": False,
             "name": _("Guarantees expiring within 30 days"),
             "model": "mizan.contract.bond",
             "domain": [("state", "=", "active"),
                        ("expiry_date", "<=", self.date_to
                         + relativedelta(days=30))],
             "note": _("An expired guarantee holds up the next claim.")},
        ]

    # --- checks that are not a simple count -----------------------------
    def _check_unbalanced(self):
        self.ensure_one()
        self.env.cr.execute("""
            select l.move_id
              from account_move_line l
              join account_move m on m.id = l.move_id
             where m.state = 'posted' and m.company_id = %s
               and m.date between %s and %s
             group by l.move_id
            having abs(sum(l.debit) - sum(l.credit)) > 0.005
        """, (self.company_id.id, self.date_from, self.date_to))
        ids = [row[0] for row in self.env.cr.fetchall()]
        return len(ids), [("id", "in", ids)]

    def _check_unrecognised(self):
        self.ensure_one()
        contracts = self.env["mizan.contract"].search(
            [("state", "=", "running"),
             ("company_id", "=", self.company_id.id)])
        # A rounding difference is not a missing recognition; a whole unit of
        # currency is.
        pending = contracts.filtered(
            lambda contract: abs(contract.revenue_to_recognise) >= 1)
        return len(pending), [("id", "in", pending.ids)]

    def action_run_checks(self):
        """Run every check and replace the previous results."""
        for record in self:
            if record.state == "closed":
                raise UserError(_("%s is closed. Reopen it before running the "
                                  "checks again.", record.name))
            record.check_ids.unlink()
            rows = []
            for spec in record._check_definitions():
                custom = spec.get("custom")
                if custom:
                    count, domain = getattr(record, custom)()
                else:
                    domain = spec["domain"]
                    count = record.env[spec["model"]].search_count(domain)
                rows.append({
                    "close_id": record.id,
                    "key": spec["key"],
                    "name": spec["name"],
                    "category": spec["category"],
                    "blocking": spec["blocking"],
                    "count": count,
                    "passed": not count,
                    "note": spec["note"],
                    "res_model": spec["model"],
                    "domain": repr(domain),
                })
            record.check_ids = [(0, 0, row) for row in rows]
            record.checked_on = fields.Datetime.now()
            record.state = "checking"
        return True

    # -------------------------------------------------------------- closing
    def action_close(self):
        self.ensure_one()
        if self.state == "closed":
            raise UserError(_("This period is already closed."))
        if not self.check_ids:
            raise UserError(_("Run the checks before closing. Closing a month "
                              "nobody checked is the thing this screen "
                              "exists to stop."))
        if self.blocking_count:
            raise UserError(_(
                "%s check(s) still block the close. They are not untidiness — "
                "each one is a figure that would be wrong in the month you are "
                "about to freeze.", self.blocking_count))
        self.lock_date_before = self.company_id.fiscalyear_lock_date
        # The SOFT lock. hard_lock_date can never be lifted by anyone, and a
        # routine month end must not take that decision for the client.
        self.company_id.sudo().fiscalyear_lock_date = self.date_to
        self.write({
            "state": "closed",
            "closed_by_id": self.env.user.id,
            "closed_on": fields.Datetime.now(),
            "closed_over_warnings": self.warning_count,
        })
        self.message_post(body=_(
            "Closed to %(date)s with %(warnings)s warning(s) accepted.",
            date=self.date_to, warnings=self.warning_count))
        return True

    def action_reopen(self):
        """Put the lock date back where it was before this close."""
        self.ensure_one()
        if self.state != "closed":
            raise UserError(_("This period is not closed."))
        if self.company_id.fiscalyear_lock_date != self.date_to:
            raise UserError(_(
                "The lock date has moved since this close, so reopening here "
                "would undo somebody else's work. Change it on the company "
                "instead, deliberately."))
        self.company_id.sudo().fiscalyear_lock_date = self.lock_date_before
        self.write({"state": "checking"})
        self.message_post(body=_("Reopened by %s.", self.env.user.display_name))
        return True


class MizanMonthCloseCheck(models.Model):
    _name = "mizan.month.close.check"
    _description = "Month-End Check"
    _order = "blocking desc, count desc"

    close_id = fields.Many2one("mizan.month.close", required=True,
                               ondelete="cascade")
    key = fields.Char(readonly=True)
    name = fields.Char(readonly=True)
    category = fields.Selection(
        [("arithmetic", "Arithmetic"), ("documents", "Documents"),
         ("tax", "Tax"), ("contracting", "Contracting"),
         ("banking", "Banking"), ("costing", "Costing")], readonly=True)
    blocking = fields.Boolean(readonly=True)
    count = fields.Integer(string="Found", readonly=True)
    passed = fields.Boolean(readonly=True)
    note = fields.Char(string="Why it matters", readonly=True)
    res_model = fields.Char(readonly=True)
    domain = fields.Char(readonly=True)

    def action_review(self):
        """Open the records this check counted."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.res_model,
            "domain": literal_eval(self.domain or "[]"),
            "view_mode": "list,form",
            "target": "current",
        }
