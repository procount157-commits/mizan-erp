# -*- coding: utf-8 -*-
"""Authorisation on the way out, acknowledgement on the way in, and what
happens after a cheque bounces.

The register tracked a cheque from draft to cleared, which is the accounting.
It did not track the three things a contractor's finance office actually
argues about:

  * An ISSUED cheque left the company the moment somebody typed it. A company
    signing cheques for subcontractors needs an authorisation step, with a
    limit above which a second signature is required — that is what the
    mandate lodged with the bank says, and the system should not be looser
    than the mandate.

  * A RECEIVED cheque was "registered", a word that means nothing to the
    person handing it over. Accepting a cheque is an act: somebody takes
    custody of a piece of paper and the customer expects an acknowledgement.

  * A BOUNCED cheque was an end state. In the UAE it is the beginning of one:
    the bank charges a fee, a notice goes out, and the amount becomes a claim
    that is either recovered or written off. Leaving it at "bounced" means the
    receivable sits there and nobody owns it.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_cheque_approval_limit = fields.Monetary(
        string="Cheque Approval Limit",
        help="An issued cheque above this needs a second authorisation. Set it "
             "to match the mandate lodged with the bank; zero means every "
             "issued cheque needs one approval only.")
    mizan_cheque_bounce_charge_account_id = fields.Many2one(
        "account.account", string="Bounced Cheque Charges",
        domain="[('account_type', '=', 'expense')]",
        help="Where the bank's fee for a returned cheque is posted.")
    mizan_cheque_writeoff_account_id = fields.Many2one(
        "account.account", string="Bad Debt Account",
        domain="[('account_type', '=', 'expense')]",
        help="Where a claim nobody could recover is written off to.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_cheque_approval_limit = fields.Monetary(
        related="company_id.mizan_cheque_approval_limit", readonly=False)
    mizan_cheque_bounce_charge_account_id = fields.Many2one(
        related="company_id.mizan_cheque_bounce_charge_account_id", readonly=False)
    mizan_cheque_writeoff_account_id = fields.Many2one(
        related="company_id.mizan_cheque_writeoff_account_id", readonly=False)


class MizanCheque(models.Model):
    _inherit = "mizan.cheque"

    state = fields.Selection(
        selection_add=[
            ("to_approve", "Waiting Approval"),
            ("registered",),
            ("claimed", "Under Claim"),
            ("recovered", "Recovered"),
            ("written_off", "Written Off"),
        ],
        ondelete={"to_approve": "set default", "claimed": "set default",
                  "recovered": "set default", "written_off": "set default"})

    # --- authorisation (issued) ------------------------------------------
    approved_by_id = fields.Many2one(
        "res.users", string="Approved By", readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    second_approved_by_id = fields.Many2one(
        "res.users", string="Second Approval", readonly=True, copy=False)
    second_approved_on = fields.Datetime(readonly=True, copy=False)
    needs_second_approval = fields.Boolean(compute="_compute_needs_second")

    # --- acknowledgement (received) --------------------------------------
    accepted_by_id = fields.Many2one(
        "res.users", string="Accepted By", readonly=True, copy=False)
    accepted_on = fields.Datetime(readonly=True, copy=False)

    # --- what happens after it bounces -----------------------------------
    bounce_reason = fields.Selection(
        [("funds", "Insufficient Funds"),
         ("signature", "Signature Mismatch"),
         ("stopped", "Payment Stopped"),
         ("account", "Account Closed or Frozen"),
         ("technical", "Date or Amount Irregular"),
         ("other", "Other")],
        string="Reason Returned", tracking=True)
    bounce_charge = fields.Monetary(
        string="Bank Charge on Return",
        help="What the bank took for the returned cheque. Real money, and it "
             "is charged to whoever caused it, not absorbed.")
    bounce_charge_move_id = fields.Many2one(
        "account.move", string="Charge Entry", readonly=True, copy=False)

    claim_reference = fields.Char(string="Claim / Case Reference", tracking=True)
    claim_date = fields.Date(string="Claim Raised On", tracking=True)
    claim_note = fields.Text(string="Claim Notes")
    recovered_on = fields.Date(readonly=True, copy=False)
    move_claim_id = fields.Many2one(
        "account.move", string="Claim Settlement Entry", readonly=True, copy=False)

    @api.depends("amount", "cheque_type", "company_id")
    def _compute_needs_second(self):
        for cheque in self:
            limit = cheque.company_id.mizan_cheque_approval_limit
            cheque.needs_second_approval = bool(
                cheque.cheque_type == "issued" and limit
                and cheque.amount > limit)

    # ------------------------------------------------------- issued: approve
    def action_submit_approval(self):
        for cheque in self:
            if cheque.cheque_type != "issued":
                raise UserError(_(
                    "Only an issued cheque goes for approval. A cheque you "
                    "received is accepted, not approved."))
            if cheque.state != "draft":
                raise UserError(_("%s is not a draft.", cheque.name))
            cheque._check_accounts()
            cheque.state = "to_approve"
            cheque.message_post(body=_("Submitted for authorisation."))

    def action_approve(self):
        """Authorise an issued cheque, then release it into the register."""
        for cheque in self:
            if cheque.state != "to_approve":
                raise UserError(_(
                    "%s is not waiting for approval.", cheque.name))
            now = fields.Datetime.now()
            if not cheque.approved_by_id:
                cheque.write({"approved_by_id": self.env.user.id,
                              "approved_on": now})
                cheque.message_post(body=_("Approved by %s.", self.env.user.name))
            elif cheque.needs_second_approval and not cheque.second_approved_by_id:
                if cheque.approved_by_id == self.env.user:
                    raise UserError(_(
                        "%(cheque)s is above the %(limit)s approval limit and "
                        "needs a second person. You gave the first approval.",
                        cheque=cheque.name,
                        limit=cheque.company_id.mizan_cheque_approval_limit))
                cheque.write({"second_approved_by_id": self.env.user.id,
                              "second_approved_on": now})
                cheque.message_post(
                    body=_("Second approval by %s.", self.env.user.name))
            if cheque.needs_second_approval and not cheque.second_approved_by_id:
                continue
            cheque.action_register()
        return True

    def action_refuse_approval(self):
        for cheque in self:
            if cheque.state != "to_approve":
                raise UserError(_("%s is not waiting for approval.", cheque.name))
            cheque.write({"state": "draft", "approved_by_id": False,
                          "approved_on": False})
            cheque.message_post(body=_("Authorisation refused; back to draft."))

    # ------------------------------------------------------ received: accept
    def action_accept(self):
        """Take a customer's cheque into custody and record who took it."""
        for cheque in self:
            if cheque.cheque_type != "received":
                raise UserError(_(
                    "Only a cheque you received is accepted. An issued cheque "
                    "is approved."))
            if cheque.state != "draft":
                raise UserError(_("%s is not a draft.", cheque.name))
            cheque.write({"accepted_by_id": self.env.user.id,
                          "accepted_on": fields.Datetime.now()})
            cheque.action_register()
            cheque.message_post(body=_(
                "Cheque accepted from %s and taken into hand.",
                cheque.partner_id.display_name))

    # -------------------------------------------------- after it bounces
    def action_post_bounce_charge(self):
        """Book what the bank took for returning it."""
        for cheque in self:
            if cheque.state not in ("bounced", "claimed"):
                raise UserError(_("%s has not bounced.", cheque.name))
            if cheque.bounce_charge_move_id:
                raise UserError(_("The charge on %s is already posted.",
                                  cheque.name))
            if not cheque.bounce_charge:
                raise UserError(_("Enter the bank's charge first."))
            account = cheque.company_id.mizan_cheque_bounce_charge_account_id
            bank = cheque.journal_id.default_account_id
            if not account or not bank:
                raise UserError(_(
                    "Set the bounced-cheque charge account on the company and "
                    "a default account on journal %s.", cheque.journal_id.name))
            label = _("Return charge on cheque %s", cheque.name)
            move = self.env["account.move"].create({
                "move_type": "entry",
                "journal_id": cheque.journal_id.id,
                "date": cheque.settle_date or fields.Date.context_today(cheque),
                "ref": label,
                "line_ids": [
                    (0, 0, {"account_id": account.id, "name": label,
                            "partner_id": cheque.partner_id.id,
                            "debit": cheque.bounce_charge, "credit": 0.0}),
                    (0, 0, {"account_id": bank.id, "name": label,
                            "partner_id": cheque.partner_id.id,
                            "debit": 0.0, "credit": cheque.bounce_charge}),
                ],
            })
            move.action_post()
            cheque.bounce_charge_move_id = move.id
        return True

    def action_raise_claim(self):
        """A bounced cheque becomes something somebody owns and chases."""
        for cheque in self:
            if cheque.state != "bounced":
                raise UserError(_(
                    "Only a bounced cheque can be claimed. %s is %s.",
                    cheque.name, cheque.state))
            cheque.write({
                "state": "claimed",
                "claim_date": cheque.claim_date or fields.Date.context_today(cheque),
            })
            cheque.message_post(body=_(
                "Claim raised against %(party)s for %(amount)s.",
                party=cheque.partner_id.display_name,
                amount="{:,.2f} {}".format(cheque.amount,
                                           cheque.currency_id.name)))

    def action_claim_recovered(self):
        """The money arrived after all: clear the debt to the bank."""
        for cheque in self:
            if cheque.state != "claimed":
                raise UserError(_("%s is not under claim.", cheque.name))
            bank = cheque.journal_id.default_account_id
            if not bank:
                raise UserError(_("Journal %s has no default account.",
                                  cheque.journal_id.name))
            today = fields.Date.context_today(cheque)
            label = _("Cheque %s recovered after claim", cheque.name)
            if cheque.cheque_type == "received":
                debit, credit = bank, cheque.counterpart_account_id
            else:
                debit, credit = cheque.counterpart_account_id, bank
            move = cheque._post_entry(today, label, debit, credit)
            cheque.write({"move_claim_id": move.id, "state": "recovered",
                          "recovered_on": today})
            cheque.message_post(body=label)

    def action_write_off(self):
        """Nobody is going to pay: take it to bad debts and stop pretending."""
        for cheque in self:
            if cheque.state != "claimed":
                raise UserError(_(
                    "Write off a claim, not a cheque still in play. %s is %s.",
                    cheque.name, cheque.state))
            account = cheque.company_id.mizan_cheque_writeoff_account_id
            if not account:
                raise UserError(_(
                    "Set the bad debt account on the company first."))
            today = fields.Date.context_today(cheque)
            label = _("Cheque %s written off", cheque.name)
            move = cheque._post_entry(
                today, label, account, cheque.counterpart_account_id)
            cheque.write({"move_claim_id": move.id, "state": "written_off"})
            cheque.message_post(body=label)

    def action_view_moves(self):
        result = super().action_view_moves()
        moves = (self.move_register_id | self.move_settle_id
                 | self.move_claim_id | self.bounce_charge_move_id)
        result["domain"] = [("id", "in", moves.ids)]
        return result
