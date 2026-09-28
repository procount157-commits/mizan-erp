# -*- coding: utf-8 -*-
"""The things that are not wrong today, and are how a month end goes wrong.

The integrity script already finds these. What it cannot do is let anyone act
on them: it prints "7 job costs with no cost centre" to a terminal, and the
finance manager who needs to fix them never sees it. This is the same set of
checks with the records attached, so every count opens the rows it counted.

On fixing automatically: only where exactly one answer is derivable from data
already in the database, and never where the answer would have to be invented.
An emirate can be derived from a city, so that is offered. A tax registration
number cannot be derived from anything — a system that filled one in would be
producing a false tax invoice, which is a worse failure than the blank it
replaced. Those are listed for a person to fill in, and say so.

Nothing here posts, reverses or deletes.
"""

from ast import literal_eval

from odoo import api, fields, models, _


class MizanDataQuality(models.TransientModel):
    _name = "mizan.data.quality"
    _description = "Data Quality"
    _order = "severity desc, count desc"

    name = fields.Char(string="Issue", readonly=True)
    category = fields.Selection(
        [("tax", "Tax & compliance"),
         ("costing", "Costing"),
         ("ledger", "Ledger"),
         ("master", "Master data"),
         ("contract", "Contracts")],
        readonly=True)
    count = fields.Integer(string="Records", readonly=True)
    severity = fields.Selection(
        [("3", "Blocks a return or a close"),
         ("2", "Distorts a report"),
         ("1", "Untidy")],
        string="Impact", readonly=True)
    note = fields.Char(string="What it costs you", readonly=True)
    res_model = fields.Char(readonly=True)
    domain = fields.Char(readonly=True)
    fix_method = fields.Char(readonly=True)
    fixable = fields.Boolean(string="Can be fixed automatically", readonly=True)

    def action_review(self):
        """Open the records this row counted."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self.res_model,
            "domain": self.domain or "[]",
            "view_mode": "list,form",
            "target": "current",
        }

    def action_fix(self):
        """Apply the one derivable correction, for the rows that have one.

        Only rows the check itself marked fixable, and only through the named
        derivation. The domain is read with literal_eval rather than eval:
        these strings are written by the server, but a data-quality screen is
        not a reason to leave a path that would run whatever a string said."""
        fixed, left = 0, 0
        for row in self.filtered("fixable"):
            records = self.env[row.res_model].search(
                literal_eval(row.domain or "[]"))
            if row.fix_method == "emirate":
                records._mizan_apply_emirate()
                fixed += len(records.filtered("state_id"))
                left += len(records.filtered(lambda p: not p.state_id))
        action = self.action_refresh()
        message = _("%s corrected.", fixed)
        if left:
            message += " " + _("%s could not be worked out and need a person.",
                               left)
        action["context"] = dict(action.get("context") or {},
                                 mizan_fix_message=message)
        return action

    # -------------------------------------------------------------- checks
    @api.model
    def _checks(self):
        """Every check, as data. Each one is a domain on a model, so the count
        and the records the user opens can never disagree."""
        today = fields.Date.context_today(self)
        company = self.env.company
        checks = []

        def add(name, category, severity, model, domain, note,
                fix_method=False):
            count = self.env[model].search_count(domain)
            if count:
                checks.append({
                    "name": name, "category": category, "severity": severity,
                    "count": count, "note": note, "res_model": model,
                    "domain": repr(domain), "fix_method": fix_method or "",
                    "fixable": bool(fix_method),
                })

        # --- tax and compliance
        add(_("Customers with no tax registration number"), "tax", "3",
            "res.partner",
            [("customer_rank", ">", 0), ("vat", "=", False),
             ("country_id.code", "=", "AE")],
            _("A tax invoice without the buyer's TRN cannot be used by them to "
              "reclaim the input tax."))
        add(_("Partners with no emirate"), "tax", "3", "res.partner",
            [("state_id", "=", False), ("country_id.code", "=", "AE"),
             "|", ("customer_rank", ">", 0), ("supplier_rank", ">", 0)],
            _("Form 201 reports sales by emirate. Without one the revenue "
              "lands in the wrong box."),
            fix_method="emirate")
        # Counted on the LINE, not the invoice. Two one2many conditions on
        # account.move are matched independently, so an invoice with a taxed
        # product line and an untaxed note line satisfies both and is reported
        # wrongly. The line itself cannot be ambiguous.
        add(_("Posted invoice lines carrying no tax"), "tax", "3",
            "account.move.line",
            [("parent_state", "=", "posted"),
             ("move_id.move_type", "in", ("out_invoice", "out_refund")),
             ("display_type", "=", "product"), ("tax_ids", "=", False)],
            _("Zero-rated, exempt and reverse charge are each a decision the "
              "return reports. A blank is not a decision."))

        # --- costing
        # DIRECT cost accounts only, which is the same definition
        # scripts/health_check.py uses. Counting general expense accounts as
        # well would report the office rent as an untagged job cost, and a
        # screen that disagrees with the integrity check is worse than either
        # alone — nobody knows which to believe.
        direct = [("parent_state", "=", "posted"),
                  ("account_id.account_type", "=", "expense_direct_cost")]
        add(_("Direct job costs with no cost centre"), "costing", "2",
            "account.move.line",
            direct + [("analytic_distribution", "=", False)],
            _("A cost outside every cost centre is outside every project's "
              "progress calculation, so revenue is understated."))
        add(_("Direct job costs with no cost code"), "costing", "2",
            "account.move.line",
            direct + [("mizan_cost_code_id", "=", False)],
            _("It reaches the project total but no budget line, so the "
              "breakdown stops adding up to the whole."))

        # --- ledger
        add(_("Documents still in draft"), "ledger", "2", "account.move",
            [("state", "=", "draft"), ("move_type", "!=", "entry")],
            _("Not in the ledger, not in the VAT return, and invisible to "
              "every report."))
        add(_("Bank lines not matched"), "ledger", "2",
            "account.bank.statement.line", [("is_reconciled", "=", False)],
            _("The bank moved money that nothing in the ledger explains."))
        add(_("Vendor bills with no purchase order"), "ledger", "1",
            "account.move",
            [("state", "=", "posted"), ("move_type", "=", "in_invoice"),
             ("invoice_origin", "=", False)],
            _("Not an error on its own. A hundred of them means the purchase "
              "process is being bypassed."))

        # --- contracts
        add(_("Guarantees expiring within 30 days"), "contract", "3",
            "mizan.contract.bond",
            [("state", "=", "active"), ("expiry_date", "<=",
                                        fields.Date.add(today, days=30)),
             ("expiry_date", ">=", today)],
            _("An expired guarantee holds up the next claim."))
        add(_("Contracts with no cost breakdown"), "contract", "2",
            "mizan.contract",
            [("state", "=", "running"), ("budget_line_ids", "=", False)],
            _("Progress is measured against one number for the whole job, so "
              "an overrun only shows once it is total."))
        add(_("Certified claims not yet invoiced"), "contract", "3",
            "mizan.progress.claim", [("state", "=", "certified"),
                                     ("invoice_id", "=", False)],
            _("Work the client has agreed to pay for and has not been asked "
              "to pay for."))

        # --- master data
        add(_("Customers with no email"), "master", "1", "res.partner",
            [("customer_rank", ">", 0), ("email", "=", False)],
            _("Every invoice to them has to be sent by hand."))
        if company.partner_id and not company.vat:
            checks.append({
                "name": _("The company has no tax registration number"),
                "category": "tax", "severity": "3", "count": 1,
                "note": _("Every invoice you issue prints TRN NOT SET, and is "
                          "not a valid tax invoice."),
                "res_model": "res.company",
                "domain": repr([("id", "=", company.id)]),
                "fix_method": "", "fixable": False,
            })
        return checks

    @api.model
    def action_refresh(self):
        self.search([("create_uid", "=", self.env.uid)]).unlink()
        rows = self._checks()
        if rows:
            self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Data Quality"),
            "res_model": "mizan.data.quality",
            "view_mode": "list,form",
            "target": "current",
            "context": {"search_default_group_category": 1},
        }
