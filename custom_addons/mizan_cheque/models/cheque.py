# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanCheque(models.Model):
    """Post-dated cheque register.

    Gulf trade runs on post-dated cheques: a customer settles an invoice with a
    cheque dated months ahead, and the money is neither cash nor a normal
    receivable until it clears. Odoo has no concept of that in-between state, so
    each cheque is tracked here through its own lifecycle and posts its own
    journal entries at the two moments that matter — when it is received and
    when it clears or bounces.
    """

    _name = "mizan.cheque"
    _description = "Post-Dated Cheque"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "due_date, id"

    name = fields.Char(
        string="Cheque No.", required=True, copy=False, tracking=True)
    cheque_type = fields.Selection(
        [("received", "Received"), ("issued", "Issued")],
        string="Type", required=True, default="received", tracking=True)

    partner_id = fields.Many2one(
        "res.partner", string="Drawer / Beneficiary", required=True, tracking=True)
    bank_id = fields.Many2one(
        "res.bank", string="Drawee Bank", tracking=True,
        help="l10n_ae loads the 174 UAE banks and exchange houses, so this is a "
             "pick list rather than free text — which keeps cheque reports "
             "groupable by bank.")

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount = fields.Monetary(required=True, tracking=True)

    issue_date = fields.Date(
        string="Cheque Date", required=True, default=fields.Date.context_today)
    due_date = fields.Date(
        string="Due Date", required=True, tracking=True,
        help="The date written on the cheque — when it may be presented.")
    settle_date = fields.Date(string="Cleared / Bounced On", readonly=True)

    state = fields.Selection(
        [("draft", "Draft"),
         ("registered", "In Hand"),
         ("deposited", "Deposited"),
         ("cleared", "Cleared"),
         ("bounced", "Bounced"),
         ("cancel", "Cancelled")],
        default="draft", required=True, tracking=True)

    is_overdue = fields.Boolean(
        string="Overdue", compute="_compute_is_overdue", search="_search_is_overdue")

    journal_id = fields.Many2one(
        "account.journal", string="Bank Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="Where the money lands once the cheque clears.")
    cheque_account_id = fields.Many2one(
        "account.account", string="Cheques Under Collection",
        help="Holding account for cheques received but not yet cleared. "
             "The UAE chart ships 102013 for exactly this.")
    counterpart_account_id = fields.Many2one(
        "account.account", string="Counterpart Account",
        help="Customer receivable for a received cheque, vendor payable for an "
             "issued one.")

    move_register_id = fields.Many2one(
        "account.move", string="Registration Entry", readonly=True, copy=False)
    move_settle_id = fields.Many2one(
        "account.move", string="Settlement Entry", readonly=True, copy=False)

    note = fields.Text()

    _sql_constraints = [
        ("name_partner_uniq", "unique(name, partner_id, company_id)",
         "This cheque number is already registered for that party."),
    ]

    @api.depends("due_date", "state")
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for cheque in self:
            cheque.is_overdue = bool(
                cheque.due_date
                and cheque.due_date < today
                and cheque.state in ("registered", "deposited"))

    def _search_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        domain = [("due_date", "<", today),
                  ("state", "in", ("registered", "deposited"))]
        if (operator == "=" and not value) or (operator == "!=" and value):
            return ["!"] + domain
        return domain

    def _check_accounts(self):
        for cheque in self:
            missing = not (cheque.journal_id and cheque.cheque_account_id
                           and cheque.counterpart_account_id)
            if missing:
                raise UserError(_(
                    "Set the bank journal, the cheques-under-collection account "
                    "and the counterpart account on cheque %s first.", cheque.name))

    def _post_entry(self, date, ref, debit_account, credit_account):
        self.ensure_one()
        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "date": date,
            "ref": ref,
            "line_ids": [
                (0, 0, {
                    "name": ref,
                    "account_id": debit_account.id,
                    "partner_id": self.partner_id.id,
                    "debit": self.amount,
                    "credit": 0.0,
                }),
                (0, 0, {
                    "name": ref,
                    "account_id": credit_account.id,
                    "partner_id": self.partner_id.id,
                    "debit": 0.0,
                    "credit": self.amount,
                }),
            ],
        })
        move.action_post()
        return move

    def action_register(self):
        """Move the amount out of the customer balance into cheques-in-hand."""
        for cheque in self:
            cheque._check_accounts()
            if cheque.cheque_type == "received":
                debit, credit = cheque.cheque_account_id, cheque.counterpart_account_id
                ref = _("Cheque %s received from %s",
                        cheque.name, cheque.partner_id.display_name)
            else:
                debit, credit = cheque.counterpart_account_id, cheque.cheque_account_id
                ref = _("Cheque %s issued to %s",
                        cheque.name, cheque.partner_id.display_name)
            move = cheque._post_entry(cheque.issue_date, ref, debit, credit)
            cheque.write({"move_register_id": move.id, "state": "registered"})

    def action_deposit(self):
        for cheque in self:
            if cheque.state != "registered":
                raise UserError(_("Only a cheque in hand can be deposited."))
        self.write({"state": "deposited"})

    def action_clear(self):
        """Cheque honoured: the bank account finally receives the money."""
        for cheque in self:
            if cheque.state not in ("registered", "deposited"):
                raise UserError(_("Only a registered or deposited cheque can clear."))
            bank_account = cheque.journal_id.default_account_id
            if not bank_account:
                raise UserError(_(
                    "Journal %s has no default account.", cheque.journal_id.name))
            today = fields.Date.context_today(cheque)
            if cheque.cheque_type == "received":
                debit, credit = bank_account, cheque.cheque_account_id
                ref = _("Cheque %s cleared", cheque.name)
            else:
                debit, credit = cheque.cheque_account_id, bank_account
                ref = _("Cheque %s paid", cheque.name)
            move = cheque._post_entry(today, ref, debit, credit)
            cheque.write({
                "move_settle_id": move.id,
                "state": "cleared",
                "settle_date": today,
            })

    def action_bounce(self):
        """Cheque dishonoured: put the debt back on the party."""
        for cheque in self:
            if cheque.state not in ("registered", "deposited"):
                raise UserError(_("Only a registered or deposited cheque can bounce."))
            today = fields.Date.context_today(cheque)
            if cheque.cheque_type == "received":
                debit, credit = cheque.counterpart_account_id, cheque.cheque_account_id
            else:
                debit, credit = cheque.cheque_account_id, cheque.counterpart_account_id
            ref = _("Cheque %s bounced", cheque.name)
            move = cheque._post_entry(today, ref, debit, credit)
            cheque.write({
                "move_settle_id": move.id,
                "state": "bounced",
                "settle_date": today,
            })

    def action_cancel(self):
        for cheque in self:
            if cheque.move_register_id or cheque.move_settle_id:
                raise UserError(_(
                    "Cheque %s already has journal entries. Reverse them before "
                    "cancelling.", cheque.name))
        self.write({"state": "cancel"})

    def action_draft(self):
        self.filtered(lambda c: c.state == "cancel").write({"state": "draft"})

    def action_view_moves(self):
        self.ensure_one()
        moves = self.move_register_id | self.move_settle_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entries"),
            "res_model": "account.move",
            "domain": [("id", "in", moves.ids)],
            "views": [[False, "list"], [False, "form"]],
        }
