# -*- coding: utf-8 -*-
"""Advance payments and the guarantees that secure them.

A contract usually opens with an advance of 10-20%, recovered proportionally
from every claim until it is repaid. Account 204002 existed for it and had
never been written to, which means somebody was working the recovery out by
hand on each claim — and a mistake there bills the client for money they have
already paid.

Guarantees are the other half of the same transaction. A performance bond and
an advance-payment guarantee both expire, and an expired one stops the claims
until it is renewed. Nothing in the system knew they existed, let alone when
they lapse.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    advance_percent = fields.Float(
        string="Advance %", default=0.0,
        help="Percentage of the contract paid up front.")
    advance_amount = fields.Monetary(
        string="Advance Certified", readonly=True, copy=False,
        help="Raises a receivable against the client, the way an advance "
             "payment certificate does. The cash itself is recorded as an "
             "ordinary receipt against that receivable.")
    advance_recovered = fields.Monetary(
        string="Advance Recovered", compute="_compute_advance")
    advance_outstanding = fields.Monetary(
        string="Advance Outstanding", compute="_compute_advance")
    advance_recovery_percent = fields.Float(
        string="Recovery Rate %",
        help="Deducted from each claim. Left empty, the advance percentage is "
             "used, which repays the advance exactly as the work is billed.")
    advance_move_id = fields.Many2one(
        "account.move", string="Advance Entry", readonly=True, copy=False)
    bond_ids = fields.One2many("mizan.contract.bond", "contract_id")
    bond_expiring = fields.Boolean(compute="_compute_bond_alert")
    bond_alert = fields.Char(compute="_compute_bond_alert")

    @api.depends("advance_amount")
    def _compute_advance(self):
        Line = self.env["account.move.line"]
        for contract in self:
            recovered = 0.0
            if contract.advance_move_id:
                account = self.env["account.account"].search(
                    [("code", "=", "204002")], limit=1)
                if account and contract.partner_id:
                    # Debits to the advance account are recoveries; the credit
                    # that created it is the advance itself.
                    entries = Line.search([
                        ("parent_state", "=", "posted"),
                        ("account_id", "=", account.id),
                        ("partner_id", "=", contract.partner_id.id),
                        ("debit", ">", 0),
                    ])
                    recovered = sum(entries.mapped("debit"))
            contract.advance_recovered = recovered
            contract.advance_outstanding = max(
                contract.advance_amount - recovered, 0.0)

    def _compute_bond_alert(self):
        today = fields.Date.context_today(self)
        for contract in self:
            soon = contract.bond_ids.filtered(
                lambda b: b.state == "active" and b.expiry_date
                and (b.expiry_date - today).days <= 30)
            contract.bond_expiring = bool(soon)
            contract.bond_alert = ", ".join(
                "%s expires %s" % (b.name, b.expiry_date) for b in soon)

    def action_record_advance(self):
        """Certify the advance: raise the receivable and the liability.

        Not a cash entry. A contractor certifies the advance, the client pays
        it, and the two are separate events — booking cash here would invent a
        receipt that may be weeks away.
        """
        for contract in self:
            if contract.advance_move_id:
                raise UserError(_("The advance on %s is already recorded.",
                                  contract.code))
            if not contract.advance_percent:
                raise UserError(_("Set the advance percentage first."))
            amount = contract.currency_id.round(
                contract.contract_value * contract.advance_percent / 100.0)
            Account = self.env["account.account"]
            advance = Account.search([("code", "=", "204002")], limit=1)
            receivable = contract.partner_id.property_account_receivable_id
            if not advance:
                raise UserError(_(
                    "Account 204002 is missing. Run scripts/complete_coa.py."))
            journal = self.env["account.journal"].search(
                [("type", "=", "general"),
                 ("company_id", "=", contract.company_id.id)], limit=1)
            label = _("Advance payment — %s", contract.code)
            entry = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": contract.date_start or fields.Date.context_today(self),
                "ref": label,
                "line_ids": [
                    (0, 0, {"account_id": receivable.id,
                            "partner_id": contract.partner_id.id,
                            "name": label, "debit": amount, "credit": 0.0}),
                    (0, 0, {"account_id": advance.id,
                            "partner_id": contract.partner_id.id,
                            "name": label, "debit": 0.0, "credit": amount}),
                ],
            })
            entry.action_post()
            contract.write({
                "advance_amount": amount,
                "advance_move_id": entry.id,
            })
        return True


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_advance_recovered = fields.Monetary(
        string="Advance Recovered", readonly=True, copy=False)
    mizan_advance_move_id = fields.Many2one(
        "account.move", string="Advance Recovery Entry", readonly=True, copy=False)

    def action_recover_advance(self):
        """Take this claim's share of the advance back.

        Recovered proportionally to what is being billed, so the advance is
        repaid at the same speed the work is invoiced — which is what the
        contract says and what the client's quantity surveyor will check.
        """
        for move in self:
            contract = move.mizan_contract_id
            if not contract:
                raise UserError(_("Set the contract on %s first.", move.name))
            if move.mizan_advance_move_id:
                raise UserError(_("Advance already recovered on %s.", move.name))
            if contract.advance_outstanding <= 0:
                raise UserError(_(
                    "Nothing left to recover on %s.", contract.code))
            rate = (contract.advance_recovery_percent
                    or contract.advance_percent)
            amount = min(
                move.currency_id.round(move.amount_untaxed * rate / 100.0),
                contract.advance_outstanding)
            Account = self.env["account.account"]
            advance = Account.search([("code", "=", "204002")], limit=1)
            receivable = move.partner_id.property_account_receivable_id
            journal = self.env["account.journal"].search(
                [("type", "=", "general"),
                 ("company_id", "=", move.company_id.id)], limit=1)
            label = _("Advance recovery on %s", move.name)
            entry = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "date": move.invoice_date or move.date,
                "ref": label,
                "line_ids": [
                    (0, 0, {"account_id": advance.id,
                            "partner_id": move.partner_id.id,
                            "name": label, "debit": amount, "credit": 0.0}),
                    (0, 0, {"account_id": receivable.id,
                            "partner_id": move.partner_id.id,
                            "name": label, "debit": 0.0, "credit": amount}),
                ],
            })
            entry.action_post()
            # Settle it against the claim, so the client is asked for the net.
            control = move.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable")
            offset = entry.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable")
            (control | offset).reconcile()
            move.write({
                "mizan_advance_recovered": amount,
                "mizan_advance_move_id": entry.id,
            })
        return True


class MizanContractBond(models.Model):
    """A guarantee lodged with the client, and when it lapses."""

    _name = "mizan.contract.bond"
    _description = "Guarantee / Bond"
    _order = "expiry_date"

    name = fields.Char(string="Reference", required=True)
    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")
    bond_type = fields.Selection(
        [("performance", "Performance Bond"),
         ("advance", "Advance Payment Guarantee"),
         ("retention", "Retention Bond"),
         ("tender", "Tender Bond"),
         ("maintenance", "Maintenance Bond")],
        required=True, default="performance")
    bank_id = fields.Many2one("res.bank", string="Issuing Bank")
    amount = fields.Monetary(required=True)
    issue_date = fields.Date(required=True, default=fields.Date.context_today)
    expiry_date = fields.Date(required=True)
    days_to_expiry = fields.Integer(compute="_compute_expiry")
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"),
         ("released", "Released"), ("expired", "Expired")],
        default="draft", required=True)
    note = fields.Text()

    @api.depends("expiry_date", "state")
    def _compute_expiry(self):
        today = fields.Date.context_today(self)
        for bond in self:
            bond.days_to_expiry = (
                (bond.expiry_date - today).days if bond.expiry_date else 0)

    def action_activate(self):
        self.write({"state": "active"})

    def action_release(self):
        self.write({"state": "released"})

    @api.model
    def cron_flag_expiring(self):
        """Mark lapsed guarantees and warn about the ones about to lapse.

        An expired bond stops the claims. Finding out from the client is the
        expensive way.
        """
        today = fields.Date.context_today(self)
        lapsed = self.search([("state", "=", "active"),
                              ("expiry_date", "<", today)])
        lapsed.write({"state": "expired"})
        for bond in lapsed:
            bond.contract_id.message_post(body=_(
                "Guarantee %(ref)s (%(kind)s) expired on %(date)s. Claims may "
                "be held until it is renewed.",
                ref=bond.name,
                kind=dict(self._fields["bond_type"].selection)[bond.bond_type],
                date=bond.expiry_date))
        return True
