# -*- coding: utf-8 -*-
"""Match the bank file against the ledger without a human touching a line.

Importing a statement gets the bank's rows into Odoo. It does not reconcile
them: OCA's widget computes a PROPOSAL when you open a line, and waits for
someone to press the button. On a month with three hundred rows that is not
reconciliation, it is data entry with extra steps.

This closes the loop. For every unreconciled line it tries, in order:

  1. the document named in the reference — banks echo the invoice number back
     in the narrative, and when the amount matches the open balance exactly
     there is nothing for a human to decide;
  2. the partner's single open document of that exact amount, when the
     reference says nothing but only one thing it could be;
  3. the reconciliation rules, which is what catches bank charges.

Anything it cannot settle beyond doubt it leaves alone, on purpose. A
reconciliation that guesses is worse than one that stops: the wrong invoice
marked paid sends a statement to a customer who has not paid, and nobody
looks at it again for a month.
"""

import re

from odoo import _, api, fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    mizan_auto_matched = fields.Boolean(
        string="Matched Automatically", readonly=True, copy=False,
        help="Settled by the importer rather than by hand.")

    # ------------------------------------------------------------ finding it
    def _mizan_candidate_documents(self):
        """Documents whose number appears in the bank's own narrative."""
        self.ensure_one()
        text = " ".join(filter(None, [self.payment_ref, self.ref,
                                      self.narration or ""]))
        if not text:
            return self.env["account.move"]
        # Invoice numbers carry slashes; the bank may strip or keep them.
        tokens = set(re.findall(r"[A-Za-z]{2,}[/\-][\w/\-]+", text))
        tokens |= set(re.findall(r"[A-Za-z]{2,}\d{4,}", text))
        if not tokens:
            return self.env["account.move"]
        return self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
            ("name", "in", list(tokens)),
        ])

    def _mizan_open_line(self, move):
        return move.line_ids.filtered(
            lambda l: l.account_id.account_type in
            ("asset_receivable", "liability_payable")
            and not l.reconciled and l.amount_residual)

    def _mizan_exact_partner_match(self):
        """One open document of exactly this amount, for this partner."""
        self.ensure_one()
        if not self.partner_id:
            return self.env["account.move"]
        types = (("out_invoice", "out_refund") if self.amount > 0
                 else ("in_invoice", "in_refund"))
        moves = self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", types),
            ("partner_id", "=", self.partner_id.commercial_partner_id.id),
            ("payment_state", "in", ("not_paid", "partial")),
        ])
        target = abs(self.amount)
        hits = moves.filtered(
            lambda m: self.currency_id.compare_amounts(
                abs(m.amount_residual), target) == 0)
        # Only when there is exactly one. Two invoices for the same amount is
        # precisely the case a person has to look at.
        return hits if len(hits) == 1 else self.env["account.move"]

    # ------------------------------------------------------------ doing it
    def mizan_auto_reconcile(self):
        """Settle what can be settled beyond doubt. Returns a summary."""
        matched = by_rule = skipped = 0
        reasons = {}
        for line in self:
            if line.is_reconciled:
                continue
            move = None
            for candidate in line._mizan_candidate_documents():
                open_line = line._mizan_open_line(candidate)
                if open_line and line.currency_id.compare_amounts(
                        abs(open_line.amount_residual), abs(line.amount)) == 0:
                    move = candidate
                    break
            if not move:
                move = line._mizan_exact_partner_match()[:1]

            if move:
                open_line = line._mizan_open_line(move)[:1]
                if open_line:
                    line.clean_reconcile()
                    line._add_account_move_line(open_line)
                    line.can_reconcile = line.reconcile_data_info.get(
                        "can_reconcile", False)
                    if line.can_reconcile:
                        line.reconcile_bank_line()
                        line.mizan_auto_matched = True
                        matched += 1
                        continue

            # Nothing named; fall back to the rules, which is what settles a
            # bank charge nobody raised a document for.
            line.clean_reconcile()
            if line.can_reconcile:
                line.reconcile_bank_line()
                line.mizan_auto_matched = True
                by_rule += 1
                continue

            skipped += 1
            reasons[line.id] = line.payment_ref or line.ref or str(line.id)
        return {"matched": matched, "by_rule": by_rule,
                "skipped": skipped, "left": reasons}

    def action_mizan_auto_reconcile(self):
        summary = self.mizan_auto_reconcile()
        parts = []
        if summary["matched"]:
            parts.append(_("%s matched to their document", summary["matched"]))
        if summary["by_rule"]:
            parts.append(_("%s posted by rule", summary["by_rule"]))
        if summary["skipped"]:
            parts.append(_("%s left for you", summary["skipped"]))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Automatic reconciliation"),
                "message": "\n".join("• %s" % p for p in parts)
                           or _("Nothing left to reconcile."),
                "type": "success" if not summary["skipped"] else "warning",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class AccountStatementImport(models.TransientModel):
    _inherit = "account.statement.import"

    def import_file_button(self):
        """Import, then reconcile what the file makes obvious.

        Doing it here rather than on a button is the whole point: the person
        uploads the bank's file and comes back to a screen holding only the
        lines that genuinely need a decision.
        """
        before = self.env["account.bank.statement.line"].search([]).ids
        result = super().import_file_button()
        fresh = self.env["account.bank.statement.line"].search(
            [("id", "not in", before)])
        if fresh:
            fresh.mizan_auto_reconcile()
        return result
