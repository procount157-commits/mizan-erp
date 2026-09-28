# -*- coding: utf-8 -*-
"""Two screens the health check already knows how to produce.

scripts/health_check.py finds these today and prints them to a terminal
nobody opens. The proposal was to put them on a screen; this is that screen,
running the same checks against the same ledger.

Transient and rebuilt on open, for the reason the inbox is: a stored copy of
"what is wrong right now" is wrong the moment somebody fixes something.
"""

from odoo import api, fields, models, _


class MizanPreviewCheck(models.TransientModel):
    _name = "mizan.preview.check"
    _description = "Data Quality Finding"
    _order = "severity, category"

    category = fields.Char(string="Area", readonly=True)
    name = fields.Char(string="Finding", readonly=True)
    count = fields.Integer(string="Records", readonly=True)
    severity = fields.Selection(
        [("1", "Blocks the close"), ("2", "Should be fixed"), ("3", "Clean")],
        string="Severity", readonly=True)
    detail = fields.Char(string="What it means", readonly=True)
    res_model = fields.Char(readonly=True)
    domain = fields.Char(readonly=True)

    def action_open_records(self):
        self.ensure_one()
        if not self.res_model:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.res_model,
            "domain": eval(self.domain or "[]"),
            "views": [[False, "list"], [False, "form"]],
        }

    # ---------------------------------------------------------------- checks
    @api.model
    def _run(self):
        Line = self.env["account.move.line"]
        Move = self.env["account.move"]
        rows = []

        def add(category, name, count, severity, detail,
                model=False, domain=False):
            rows.append({
                "category": category, "name": name, "count": count,
                "severity": "3" if not count else severity,
                "detail": detail, "res_model": model,
                "domain": str(domain) if domain else False,
            })

        drafts = Move.search([("state", "=", "draft"),
                              ("move_type", "!=", "entry")])
        add(_("Documents"), _("Invoices and bills still in draft"),
            len(drafts), "1",
            _("A draft is not in the ledger. The month cannot close over it."),
            "account.move",
            [("state", "=", "draft"), ("move_type", "!=", "entry")])

        direct = Line.search([
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "=", "expense_direct_cost")])
        untagged = direct.filtered(lambda l: not l.analytic_distribution)
        add(_("Job costing"), _("Direct cost with no cost centre"),
            len(untagged), "1",
            _("It never reaches a project, so completion is understated."),
            "account.move.line", [("id", "in", untagged.ids)])

        no_code = direct.filtered(lambda l: not l.mizan_cost_code_id)
        add(_("Job costing"), _("Direct cost with no cost code"),
            len(no_code), "2",
            _("It lands on the job but not on a trade, so the variance "
              "report cannot say where."),
            "account.move.line", [("id", "in", no_code.ids)])

        customers = self.env["res.partner"].search([
            ("country_id.code", "=", "AE"), ("customer_rank", ">", 0)])
        no_emirate = customers.filtered(lambda p: not p.state_id)
        add(_("VAT"), _("UAE customer with no emirate"), len(no_emirate), "1",
            _("Form 201 reports sales by emirate. With none, the revenue "
              "lands in the wrong box or is zero-rated."),
            "res.partner", [("id", "in", no_emirate.ids)])

        no_trn = customers.filtered(lambda p: not p.vat and p.is_company)
        add(_("VAT"), _("Business customer with no TRN"), len(no_trn), "2",
            _("A tax invoice without the buyer's TRN is not a tax invoice."),
            "res.partner", [("id", "in", no_trn.ids)])

        Statement = self.env["account.bank.statement.line"]
        open_lines = Statement.search([("is_reconciled", "=", False)])
        add(_("Banking"), _("Bank lines not matched"), len(open_lines), "1",
            _("The bank and the ledger disagree until every line is explained."),
            "account.bank.statement.line", [("is_reconciled", "=", False)])

        Bond = self.env["mizan.contract.bond"]
        expiring = Bond.search([("state", "=", "active")]).filtered(
            lambda b: 0 <= b.days_to_expiry <= 30)
        add(_("Contracting"), _("Guarantee expiring within 30 days"),
            len(expiring), "2",
            _("An expired guarantee holds up the claims."),
            "mizan.contract.bond", [("id", "in", expiring.ids)])

        Claim = self.env["mizan.progress.claim"]
        uninvoiced = Claim.search([("state", "=", "certified")])
        add(_("Contracting"), _("Claim certified but not invoiced"),
            len(uninvoiced), "1",
            _("Work the client has accepted and nobody has billed."),
            "mizan.progress.claim", [("state", "=", "certified")])

        accounts = self.env["account.account"].search([])
        used = set(Line.search([]).mapped("account_id").ids)
        unused = [a.id for a in accounts if a.id not in used]
        add(_("Chart"), _("Accounts never posted to"), len(unused), "2",
            _("%s of %s. A wall of unused accounts is how the wrong one "
              "gets picked.", len(unused), len(accounts)),
            "account.account", [("id", "in", unused)])

        return rows

    @api.model
    def action_refresh(self):
        self.search([]).unlink()
        self.create(self._run())
        return {
            "type": "ir.actions.act_window",
            "name": _("Data Quality"),
            "res_model": "mizan.preview.check",
            "view_mode": "list",
            "target": "current",
            "context": {"search_default_group_severity": 1},
        }

    @api.model
    def action_closing(self):
        """The same checks, read as: can the month close?"""
        self.search([]).unlink()
        self.create(self._run())
        return {
            "type": "ir.actions.act_window",
            "name": _("Month-End Readiness"),
            "res_model": "mizan.preview.check",
            "view_mode": "list",
            "target": "current",
            "domain": [("severity", "=", "1")],
            "context": {"search_default_group_category": 1},
        }
