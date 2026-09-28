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

WHY A SCORE AND NOT A YES. "Matched" and "not matched" treat two very
different situations alike. The bank quoting the invoice number against the
exact open balance is not a match in the same sense as the only open document
for that customer happening to be the same amount — the first is a fact, the
second is an inference that is usually right. Collapsing them into a boolean
means either the inference posts silently, or the fact waits for a human.

So each candidate carries a score built from named signals, and the line keeps
the best candidate it did NOT take along with the reason. Below the threshold
nothing is posted, but the person opening the line is handed the proposal and
what it rests on, instead of an empty screen. The threshold is a company
setting, because how much inference a business will accept is a business
decision and not a constant in somebody's code.
"""

import re

from odoo import _, api, fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    mizan_auto_matched = fields.Boolean(
        string="Matched Automatically", readonly=True, copy=False,
        help="Settled by the importer rather than by hand.")
    mizan_match_confidence = fields.Integer(
        string="Match Confidence", readonly=True, copy=False,
        help="How much of the match rests on fact and how much on inference. "
             "The bank quoting the invoice number against the exact open "
             "balance scores near a hundred; the only open document of that "
             "amount for that customer scores in the nineties and waits for "
             "a person.")
    mizan_match_reason = fields.Char(
        string="Why", readonly=True, copy=False,
        help="The signals behind the score, so the proposal can be judged "
             "rather than trusted.")
    mizan_match_candidate_id = fields.Many2one(
        "account.move", string="Proposed Document", readonly=True, copy=False,
        help="The best candidate the importer found and did not post, because "
             "it scored below the threshold.")

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

    # --------------------------------------------------------- scoring it
    # Each signal is worth what it is worth as evidence, not as a feeling.
    # The bank echoing the document number is the strongest thing available
    # short of the customer telling you; an exact residual is nearly as good;
    # the partner agreeing is corroboration rather than evidence on its own,
    # because the bank fills that in from a name that is often wrong.
    SIGNAL_REFERENCE = 60      # the document number appears in the narrative
    SIGNAL_EXACT_AMOUNT = 35   # equals the open balance to the cent
    SIGNAL_PARTNER = 5         # the bank's partner matches the document's
    SIGNAL_PARTNER_ONLY = 40   # partner is all there is to go on
    SIGNAL_SOLE_CANDIDATE = 17  # nothing else it could be
    SIGNAL_RULE = 95           # a rule the accountant wrote, so a decision
    #                            already taken by a person

    def _mizan_score_candidates(self):
        """Every document this line could be, with what the score rests on."""
        self.ensure_one()
        scored = []

        named = self._mizan_candidate_documents()
        for move in named:
            open_line = self._mizan_open_line(move)
            if not open_line:
                continue
            exact = self.currency_id.compare_amounts(
                abs(sum(open_line.mapped("amount_residual"))),
                abs(self.amount)) == 0
            score = self.SIGNAL_REFERENCE
            why = [_("its number is in the bank's narrative")]
            if exact:
                score += self.SIGNAL_EXACT_AMOUNT
                why.append(_("the amount equals the open balance exactly"))
            if self.partner_id and move.partner_id.commercial_partner_id == \
                    self.partner_id.commercial_partner_id:
                score += self.SIGNAL_PARTNER
                why.append(_("the party agrees"))
            scored.append((min(score, 100), move, why))

        if not scored:
            sole = self._mizan_exact_partner_match()[:1]
            if sole:
                scored.append((
                    min(self.SIGNAL_PARTNER_ONLY + self.SIGNAL_EXACT_AMOUNT
                        + self.SIGNAL_SOLE_CANDIDATE, 100),
                    sole,
                    [_("the only open document of exactly this amount for "
                       "this party"), _("nothing names it")]))

        scored.sort(key=lambda row: row[0], reverse=True)
        # Two candidates scoring the same is the case a person has to look at,
        # so neither is allowed to win on its own.
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            scored[0] = (min(scored[0][0], 60), scored[0][1],
                         scored[0][2] + [_("another document scores the same")])
        return scored

    # ------------------------------------------------------------ doing it
    def mizan_auto_reconcile(self):
        """Settle what scores above the threshold. Returns a summary."""
        matched = by_rule = held = skipped = 0
        reasons = {}
        threshold = self.env.company.mizan_auto_match_threshold or 95
        for line in self:
            if line.is_reconciled:
                continue
            scored = line._mizan_score_candidates()
            if scored:
                score, move, why = scored[0]
                line.write({
                    "mizan_match_confidence": score,
                    "mizan_match_reason": " · ".join(why),
                    "mizan_match_candidate_id": move.id,
                })
                if score >= threshold:
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
                else:
                    # Deliberately not posted. The proposal and its reason stay
                    # on the line so the person is handed the inference rather
                    # than an empty screen.
                    held += 1
                    continue

            # Nothing named; fall back to the rules, which is what settles a
            # bank charge nobody raised a document for.
            line.clean_reconcile()
            if line.can_reconcile:
                line.reconcile_bank_line()
                line.write({"mizan_auto_matched": True,
                            "mizan_match_confidence": self.SIGNAL_RULE,
                            "mizan_match_reason": _("a reconciliation rule "
                                                    "you configured")})
                by_rule += 1
                continue

            skipped += 1
            reasons[line.id] = line.payment_ref or line.ref or str(line.id)
        return {"matched": matched, "by_rule": by_rule, "held": held,
                "skipped": skipped, "left": reasons}

    def action_mizan_auto_reconcile(self):
        summary = self.mizan_auto_reconcile()
        parts = []
        if summary["matched"]:
            parts.append(_("%s matched to their document", summary["matched"]))
        if summary["by_rule"]:
            parts.append(_("%s posted by rule", summary["by_rule"]))
        if summary.get("held"):
            parts.append(_("%s proposed but below the threshold — open them "
                           "to accept or change", summary["held"]))
        if summary["skipped"]:
            parts.append(_("%s with nothing to propose", summary["skipped"]))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Automatic reconciliation"),
                "message": "\n".join("• %s" % p for p in parts)
                           or _("Nothing left to reconcile."),
                "type": ("success" if not (summary["skipped"]
                                          or summary.get("held"))
                         else "warning"),
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


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_auto_match_threshold = fields.Integer(
        string="Auto-Match Threshold", default=95,
        help="A bank line is reconciled without asking only at or above this "
             "confidence. Below it the proposal is kept and shown, and a "
             "person decides. How much inference a business will accept is a "
             "business decision, which is why it is a setting.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_auto_match_threshold = fields.Integer(
        related="company_id.mizan_auto_match_threshold", readonly=False)
