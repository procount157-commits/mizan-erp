# -*- coding: utf-8 -*-
"""Type a number, see everything it touches.

Odoo searches inside whichever list is open. That is the right behaviour for a
list and the wrong one for the question people actually ask: somebody rings
about INV/2026/00005, and answering means opening the invoice, then the claim
behind it, then the payment against it, then the journal entry, then the bank
line — five screens and the knowledge of which five.

This searches across the documents that refer to one another and returns them
together, each saying what it is and how it relates to the thing that was
typed. It is deliberately a small, fixed set of models rather than everything
in the database: a search that returns two hundred analytic lines has not
answered the question either.

Read-only. Every row opens the real document.
"""

from odoo import api, fields, models, _


class MizanFindResult(models.TransientModel):
    _name = "mizan.find.result"
    _description = "Search Result"
    _order = "sequence, id"

    sequence = fields.Integer()
    find_id = fields.Many2one("mizan.find", ondelete="cascade")
    kind = fields.Char(string="What it is", readonly=True)
    name = fields.Char(readonly=True)
    detail = fields.Char(string="Detail", readonly=True)
    amount = fields.Monetary(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    state = fields.Char(readonly=True)
    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    def action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [[False, "form"]],
            "target": "current",
        }


class MizanFind(models.TransientModel):
    _name = "mizan.find"
    _description = "Find Anything"

    query = fields.Char(string="Find",
                        help="An invoice number, a contract number, a client, "
                             "a cheque, a tax number — anything printed on a "
                             "document somebody is holding.")
    result_ids = fields.One2many("mizan.find.result", "find_id",
                                 string="Results")
    searched = fields.Boolean(readonly=True)

    # Each entry: model, the fields to look in, how to label a hit, and a line
    # of detail. Kept as data so adding a document type is one row.
    def _sources(self):
        return [
            ("account.move", ["name", "ref", "payment_reference"],
             _("Document"), "partner_id"),
            ("mizan.progress.claim", ["name", "consultant_ref"],
             _("Progress claim"), "partner_id"),
            ("mizan.contract", ["name", "code"], _("Contract"), "partner_id"),
            ("mizan.contract.variation", ["reference", "name",
                                          "client_reference"],
             _("Variation order"), "contract_id"),
            ("mizan.cheque", ["name"], _("Cheque"), "partner_id"),
            ("account.payment", ["name", "memo"], _("Payment"), "partner_id"),
            ("account.bank.statement.line", ["payment_ref", "ref"],
             _("Bank line"), "partner_id"),
            ("mizan.contract.bond", ["name"], _("Guarantee"), "contract_id"),
            ("res.partner", ["name", "vat", "ref"], _("Party"), False),
            ("project.project", ["name"], _("Project"), "partner_id"),
        ]

    def action_search(self):
        self.ensure_one()
        self.result_ids.unlink()
        term = (self.query or "").strip()
        if not term:
            return self._reopen()

        rows = []
        for model, search_fields, label, party_field in self._sources():
            if model not in self.env:
                continue
            Model = self.env[model]
            # Build the conditions first and count the ORs from what survived.
            # A field can be absent because an optional module is not
            # installed, and a domain with the wrong number of "|" in it fails
            # in a way that is very hard to read.
            conditions = [(name, "ilike", term) for name in search_fields
                          if name in Model._fields]
            if not conditions:
                continue
            domain = ["|"] * (len(conditions) - 1) + conditions
            try:
                records = Model.search(domain, limit=15)
            except Exception:  # noqa: BLE001
                # A model this user may not read is not a reason for the whole
                # search to fail — it is a reason for it to return less.
                continue
            for record in records:
                party = ""
                if party_field and party_field in record._fields:
                    party = record[party_field].display_name or ""
                amount = 0.0
                for candidate in ("amount_total", "amount",
                                  "amount_this_period", "contract_value"):
                    if candidate in record._fields:
                        amount = record[candidate] or 0.0
                        break
                rows.append({
                    "find_id": self.id,
                    "sequence": len(rows) * 10,
                    "kind": label,
                    "name": record.display_name,
                    "detail": party,
                    "amount": amount,
                    "currency_id": (
                        record.currency_id.id
                        if "currency_id" in record._fields and record.currency_id
                        else self.env.company.currency_id.id),
                    "state": (dict(record._fields["state"]._description_selection(
                        self.env)).get(record.state, record.state)
                        if "state" in record._fields else ""),
                    "res_model": model,
                    "res_id": record.id,
                })
        if rows:
            self.env["mizan.find.result"].create(rows)
        self.searched = True
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Find anything"),
            "res_model": "mizan.find",
            "res_id": self.id,
            "views": [[False, "form"]],
            "target": "new",
        }

    @api.model
    def action_open(self):
        return self.create({"query": ""})._reopen()
