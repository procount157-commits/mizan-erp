# -*- coding: utf-8 -*-
"""What is waiting for me, on one screen.

A PROTOTYPE. It gathers work that is already sitting in six different apps and
puts it in one list, so the question "what needs me today?" is answered without
opening each app and remembering which filter to apply.

Built on a transient model refreshed on open rather than a stored one kept in
step by triggers. A stored inbox has to be invalidated by every model it
watches, and the first missed trigger leaves a manager looking at a task that
was done yesterday — which is worse than no inbox. Rebuilding on open costs a
few queries and cannot go stale.

Read-only on purpose. Every row opens the real document with its real buttons;
nothing is approved or posted from here. A prototype that can post is not a
prototype any more.
"""

from odoo import api, fields, models, _


class MizanInboxItem(models.TransientModel):
    _name = "mizan.inbox.item"
    _description = "Work Inbox Item"
    _order = "urgency, amount desc"

    name = fields.Char(string="Task", readonly=True)
    source = fields.Char(string="Source", readonly=True)
    partner_name = fields.Char(string="Party", readonly=True)
    amount = fields.Monetary(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    urgency = fields.Selection(
        [("1", "Needs a decision"),
         ("2", "Needs checking"),
         ("3", "Worth knowing")],
        string="Priority", readonly=True)
    note = fields.Char(string="Why", readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    def action_open(self):
        """Open the real document, where the real buttons are."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [[False, "form"]],
            "target": "current",
        }

    # ------------------------------------------------------------ gathering
    @api.model
    def _gather(self):
        company = self.env.company
        currency = company.currency_id
        rows = []

        def add(name, source, party, amount, urgency, note, record):
            rows.append({
                "name": name, "source": source, "partner_name": party,
                "amount": amount or 0.0, "currency_id": currency.id,
                "urgency": urgency, "note": note,
                "res_model": record._name, "res_id": record.id,
            })

        # --- claims waiting on the consultant or on an invoice
        Claim = self.env["mizan.progress.claim"]
        for claim in Claim.search([("state", "in", ("submitted", "certified"))]):
            if claim.state == "certified":
                add(_("Raise the tax invoice for %s", claim.name),
                    _("Contracting"), claim.partner_id.display_name,
                    claim.amount_this_period, "1",
                    _("Certified and not invoiced"), claim)
            else:
                add(_("%s is with the consultant", claim.name),
                    _("Contracting"), claim.partner_id.display_name,
                    claim.amount_this_period, "3",
                    _("Waiting for certification"), claim)

        # --- cheques an approver is holding up
        Cheque = self.env["mizan.cheque"]
        for cheque in Cheque.search([("state", "=", "to_approve")]):
            add(_("Approve cheque %s", cheque.name), _("Banking"),
                cheque.partner_id.display_name, cheque.amount, "1",
                _("Second signature required")
                if cheque.needs_second_approval else _("Waiting for approval"),
                cheque)
        for cheque in Cheque.search([("state", "=", "bounced")]):
            add(_("Cheque %s bounced", cheque.name), _("Banking"),
                cheque.partner_id.display_name, cheque.amount, "1",
                _("Raise a claim or write it off"), cheque)

        # --- expense claims a manager has not approved
        Sheet = self.env["hr.expense.sheet"]
        for sheet in Sheet.search([("state", "=", "submit")]):
            add(_("Approve %s", sheet.name), _("Petty Cash"),
                sheet.employee_id.name, sheet.total_amount, "1",
                _("Submitted and waiting"), sheet)

        # --- documents still in draft
        Move = self.env["account.move"]
        # A draft invoice has no number yet — Odoo shows "/" — so naming the
        # task after it reads as "Post /". The party and the kind are what a
        # person recognises the document by before it is numbered.
        kinds = dict(Move._fields["move_type"]._description_selection(self.env))
        for move in Move.search([("state", "=", "draft"),
                                 ("move_type", "!=", "entry")]):
            numbered = move.name and move.name not in ("/", False)
            label = (_("Post %s", move.name) if numbered
                     else _("Post a draft %(kind)s for %(party)s",
                            kind=kinds.get(move.move_type, _("document")),
                            party=move.partner_id.display_name or _("no party")))
            add(label, _("Accounting"), move.partner_id.display_name,
                move.amount_total, "2", _("Draft, not posted"), move)

        # --- bank lines nobody has explained
        Line = self.env["account.bank.statement.line"]
        open_lines = Line.search([("is_reconciled", "=", False)])
        for line in open_lines:
            add(_("Reconcile: %s", (line.payment_ref or "")[:40]),
                _("Banking"), line.partner_id.display_name or "",
                abs(line.amount), "2", _("Bank line not matched"), line)

        # --- guarantees about to lapse
        Bond = self.env["mizan.contract.bond"]
        for bond in Bond.search([("state", "=", "active")]):
            if 0 <= bond.days_to_expiry <= 30:
                add(_("Guarantee %s expires in %s days",
                      bond.name, bond.days_to_expiry),
                    _("Contracting"), bond.contract_id.partner_id.display_name,
                    bond.amount, "1",
                    _("An expired guarantee holds up the claims"), bond)

        # --- advances still outstanding
        Contract = self.env["mizan.contract"]
        for contract in Contract.search([("advance_amount", ">", 0)]):
            if contract.advance_outstanding > 0:
                add(_("Advance outstanding on %s", contract.code),
                    _("Contracting"), contract.partner_id.display_name,
                    contract.advance_outstanding, "3",
                    _("Recovered from each claim"), contract)

        return rows

    @api.model
    def action_refresh(self):
        """Rebuild the list and show it."""
        self.search([]).unlink()
        rows = self._gather()
        if rows:
            self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Work Inbox"),
            "res_model": "mizan.inbox.item",
            "view_mode": "list",
            "target": "current",
            "context": {"search_default_group_urgency": 1},
        }
