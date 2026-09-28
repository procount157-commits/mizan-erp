# -*- coding: utf-8 -*-
"""Every document knows its own next step, and offers one button for it.

The complaint this answers is real: a user looking at a certified progress
claim has eleven buttons in the header and no way to know which one the
process expects next. Odoo's own answer is the statusbar, which says where the
document IS but not what to DO about it.

So each document with a pipeline declares that pipeline, and this mixin works
out which step is current and what the button for it should say. The button
reimplements nothing: it calls the document's own method, so every guard,
constraint and journal entry behaves exactly as when pressed directly.

The method name is never taken from the client. It is recomputed on the server
from the record's own state immediately before it is called, so a crafted
request cannot name a method of its own choosing.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanNextActionMixin(models.AbstractModel):
    _name = "mizan.next.action.mixin"
    _description = "Next Action"

    mizan_next_label = fields.Char(
        string="Next Action", compute="_compute_mizan_next")
    mizan_next_method = fields.Char(compute="_compute_mizan_next")
    mizan_next_hint = fields.Char(
        string="What happens", compute="_compute_mizan_next",
        help="What pressing the button will do, said before it is pressed.")
    mizan_next_blocked = fields.Char(
        string="Blocked by", compute="_compute_mizan_next")
    mizan_pipeline = fields.Char(
        string="Pipeline", compute="_compute_mizan_next")

    # ------------------------------------------------------------------
    # Each model overrides this and returns a dict:
    #   steps    — ordered [(state, label)] describing the whole pipeline
    #   current  — the state to mark as current in that pipeline
    #   label    — the button caption for the step that comes next
    #   method   — the method the button calls
    #   hint     — what pressing it will do, in one line
    #   blocked  — why the next step cannot be taken yet, or False
    # ------------------------------------------------------------------
    def _mizan_next_action(self):
        self.ensure_one()
        return {}

    def _compute_mizan_next(self):
        for record in self:
            try:
                info = record._mizan_next_action() or {}
            except Exception:  # noqa: BLE001 — see below
                # Working out a hint must never be the reason a form fails to
                # open. If this breaks, the document itself still works.
                info = {}
            record.mizan_next_label = info.get("label") or ""
            record.mizan_next_method = info.get("method") or ""
            record.mizan_next_hint = info.get("hint") or ""
            record.mizan_next_blocked = info.get("blocked") or ""
            current = info.get("current")
            record.mizan_pipeline = "  ›  ".join(
                ("• %s" % label) if state == current else label
                for state, label in (info.get("steps") or []))

    def action_mizan_next(self):
        """Take the next step.

        Dispatches only to the method the record names for its own current
        state — never to one supplied by the caller."""
        self.ensure_one()
        info = self._mizan_next_action() or {}
        if info.get("blocked"):
            raise UserError(info["blocked"])
        method = info.get("method")
        if not method or not method.startswith("action_"):
            raise UserError(_("This document has no next step waiting."))
        return getattr(self, method)()


# ---------------------------------------------------------------- claims
class MizanProgressClaim(models.Model):
    _name = "mizan.progress.claim"
    _inherit = ["mizan.progress.claim", "mizan.next.action.mixin"]

    def _mizan_next_action(self):
        self.ensure_one()
        base = {
            "steps": [("draft", _("Drafted")),
                      ("submitted", _("With the consultant")),
                      ("certified", _("Certified")),
                      ("invoiced", _("Invoiced"))],
            "current": self.state,
        }
        if self.state == "draft":
            blocked = False
            if not self.line_ids:
                blocked = _("Load the bill of quantities first — a claim with "
                            "no lines certifies nothing.")
            return dict(base, label=_("Submit to the consultant"),
                        method="action_submit", blocked=blocked,
                        hint=_("Locks the quantities and sends the claim out "
                               "for certification."))
        if self.state == "submitted":
            return dict(base, label=_("Record the certification"),
                        method="action_certify",
                        hint=_("Records what the consultant certified. The "
                               "certified amount is what gets invoiced."))
        if self.state == "certified":
            if self.invoice_id:
                return dict(base, label=_("Open the invoice"),
                            method="action_view_invoice",
                            hint=_("The invoice for this claim already exists."))
            return dict(base, label=_("Raise the tax invoice"),
                        method="action_create_invoice",
                        hint=_("Creates the invoice for the certified amount, "
                               "less retention and advance recovery."))
        return base


# --------------------------------------------------------------- cheques
class MizanCheque(models.Model):
    _name = "mizan.cheque"
    _inherit = ["mizan.cheque", "mizan.next.action.mixin"]

    def _mizan_next_action(self):
        self.ensure_one()
        base = {
            "steps": [("draft", _("Drafted")),
                      ("to_approve", _("Waiting approval")),
                      ("registered", _("In hand")),
                      ("deposited", _("Deposited")),
                      ("cleared", _("Cleared"))],
            "current": self.state,
        }
        if self.state == "draft":
            if self.cheque_type == "issued":
                return dict(base, label=_("Send for approval"),
                            method="action_submit_approval",
                            hint=_("A cheque leaving the company is approved "
                                   "before it is written into the ledger."))
            return dict(base, label=_("Register the cheque"),
                        method="action_register",
                        hint=_("Posts it to cheques under collection — out of "
                               "receivables, and not yet cash."))
        if self.state == "to_approve":
            blocked = False
            if self.needs_second_approval and self.approved_by_id \
                    and not self.second_approved_by_id \
                    and self.approved_by_id == self.env.user:
                blocked = _("This cheque needs a second signature, and you "
                            "gave the first one.")
            return dict(base, label=_("Approve"), method="action_approve",
                        blocked=blocked,
                        hint=_("Approves the cheque and registers it."))
        if self.state == "registered":
            return dict(base, label=_("Deposit at the bank"),
                        method="action_deposit",
                        hint=_("Marks it lodged. No entry is posted until it "
                               "clears."))
        if self.state == "deposited":
            return dict(base, label=_("Record it cleared"),
                        method="action_clear",
                        hint=_("Moves the amount into the bank account. Use "
                               "Bounced instead if the bank returned it."))
        return base


# -------------------------------------------------------------- documents
class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mizan.next.action.mixin"]

    def _mizan_next_action(self):
        self.ensure_one()
        if self.move_type == "entry":
            return {}
        current = self.state
        if self.state == "posted" and self.payment_state in ("paid", "in_payment"):
            current = "paid"
        base = {
            "steps": [("draft", _("Draft")), ("posted", _("Posted")),
                      ("paid", _("Settled"))],
            "current": current,
        }
        if self.state == "draft":
            blocked = False
            if not self.invoice_line_ids.filtered(
                    lambda line: line.display_type == "product"):
                blocked = _("Add at least one line before posting.")
            return dict(base, label=_("Post"), method="action_post",
                        blocked=blocked,
                        hint=_("Puts the document in the ledger. After this it "
                               "can be reversed, not edited."))
        if self.state == "posted" and self.payment_state == "not_paid":
            return dict(base, label=_("Register payment"),
                        method="action_register_payment",
                        hint=_("Opens the payment window for the amount still "
                               "outstanding."))
        return base


# --------------------------------------------------------- expense claims
class HrExpenseSheet(models.Model):
    _name = "hr.expense.sheet"
    _inherit = ["hr.expense.sheet", "mizan.next.action.mixin"]

    def _mizan_next_action(self):
        self.ensure_one()
        base = {
            "steps": [("draft", _("To submit")), ("submit", _("Submitted")),
                      ("approve", _("Approved")), ("post", _("Posted")),
                      ("done", _("Paid"))],
            "current": self.state,
        }
        if self.state == "draft":
            return dict(base, label=_("Submit to the manager"),
                        method="action_submit_sheet",
                        hint=_("Sends the claim for approval."))
        if self.state == "submit":
            return dict(base, label=_("Approve"),
                        method="action_approve_expense_sheets",
                        hint=_("Approves the claim. It still has to be posted "
                               "before it reaches the ledger."))
        if self.state == "approve":
            return dict(base, label=_("Post to the ledger"),
                        method="action_sheet_move_post",
                        hint=_("Creates the journal entry owing the employee."))
        return base


# ------------------------------------------------------- variation orders
class MizanContractVariation(models.Model):
    _name = "mizan.contract.variation"
    _inherit = ["mizan.contract.variation", "mizan.next.action.mixin"]

    def _mizan_next_action(self):
        self.ensure_one()
        base = {
            "steps": [("draft", _("Drafted")),
                      ("submitted", _("With the client")),
                      ("approved", _("Approved"))],
            "current": self.state,
        }
        if self.state == "draft":
            return dict(base, label=_("Submit to the client"),
                        method="action_submit",
                        hint=_("Counts towards pending variations until the "
                               "client approves it."))
        if self.state == "submitted":
            return dict(base, label=_("Record the approval"),
                        method="action_approve",
                        hint=_("Raises the contract value and the expected "
                               "cost, and recomputes the forecast margin."))
        return base
