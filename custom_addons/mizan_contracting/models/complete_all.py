# -*- coding: utf-8 -*-
"""One button that finishes the document and lands it in the accounts.

A progress claim passes through five steps and an invoice through three, and
every one of them is a separate click on a separate screen. In practice that
means claims sitting certified but not invoiced, invoices posted but with the
retention never withheld, and the advance recovered on a spreadsheet — each of
which is a correct-looking document and a wrong ledger.

So: one button, run every remaining step in order, stop at the first thing that
genuinely needs a human, and say what was done. Nothing here skips a control —
over-measurement is still refused, an uncertified claim is still not a debt.
What it removes is the walking between screens, which is where the steps got
lost.
"""

from odoo import models, _
from odoo.exceptions import UserError


class MizanProgressClaim(models.Model):
    _inherit = "mizan.progress.claim"

    def action_complete_all(self):
        """Submit, certify, invoice, post, withhold, recover — in one go."""
        self.ensure_one()
        done = []

        if self.state == "cancel":
            raise UserError(_("%s is cancelled.", self.name))

        if self.state == "draft":
            self.action_submit()
            done.append(_("submitted to the consultant"))

        if self.state == "submitted":
            if not self.certified_by:
                raise UserError(_(
                    "%s is with the consultant. Record who certified it before "
                    "finishing — the name on the certificate is the whole point "
                    "of the step, and the system will not invent it.", self.name))
            self.action_certify()
            done.append(_("certified"))

        raised = False
        if self.state == "certified":
            self.action_create_invoice()
            raised = True

        if self.state == "invoiced":
            invoice = self.invoice_id
            if invoice.state == "draft":
                invoice.action_post()
                # Reported only here, and only once: Odoo assigns the number
                # when the document is posted, so naming it at creation prints
                # False.
                done.append(_("tax invoice %s raised and posted", invoice.name)
                            if raised else _("invoice %s posted", invoice.name))
            elif raised:
                done.append(_("tax invoice %s raised", invoice.name))
            if self.retention_amount and not invoice.mizan_retention_move_id:
                invoice.action_withhold_retention()
                done.append(_("retention %s withheld",
                              self._mizan_money(invoice.mizan_retention_amount)))
            if self.advance_recovery and not invoice.mizan_advance_move_id:
                invoice.action_recover_advance()
                done.append(_("advance %s recovered",
                              self._mizan_money(invoice.mizan_advance_recovered)))

        if not done:
            raise UserError(_("%s has nothing left to do.", self.name))

        self.message_post(body=_(
            "Completed in one step: %s.", "; ".join(done)))
        return self._mizan_notify(
            _("%s completed", self.name), "\n".join("• %s" % d for d in done))

    def _mizan_money(self, amount):
        return "%s %s" % ("{:,.2f}".format(amount), self.currency_id.name)

    def _mizan_notify(self, title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": title, "message": message,
                       "type": "success", "sticky": True},
        }


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_mizan_complete_all(self):
        """Post the document and apply whatever the contract says follows it.

        Works on one record or on a whole selection, because the place this is
        needed most is a list of claims at month end, not one invoice at a time.
        """
        posted = retained = recovered = 0
        skipped = []
        for move in self:
            if move.state == "cancel":
                skipped.append(_("%s is cancelled", move.name))
                continue
            if move.move_type == "entry" and not move.mizan_contract_id:
                skipped.append(_("%s is a journal entry", move.name))
                continue

            if move.state == "draft":
                move.action_post()
                posted += 1

            contract = move.mizan_contract_id
            if (move.mizan_retention_percent
                    and not move.mizan_retention_move_id
                    and move.currency_id.round(
                        move.amount_untaxed * move.mizan_retention_percent
                        / 100.0) > 0):
                move.action_withhold_retention()
                retained += 1

            if (contract and move.move_type == "out_invoice"
                    and not move.mizan_advance_move_id
                    and contract.advance_outstanding > 0
                    and (contract.advance_recovery_percent
                         or contract.advance_percent)):
                move.action_recover_advance()
                recovered += 1

        lines = []
        if posted:
            lines.append(_("%s posted", posted))
        if retained:
            lines.append(_("retention withheld on %s", retained))
        if recovered:
            lines.append(_("advance recovered on %s", recovered))
        if not lines and not skipped:
            raise UserError(_("Nothing left to do on what you selected."))
        lines.extend(skipped)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Completed"),
                "message": "\n".join("• %s" % line for line in lines),
                "type": "success" if not skipped else "warning",
                "sticky": True,
            },
        }
