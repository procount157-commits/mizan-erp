# -*- coding: utf-8 -*-
"""No UAE invoice leaves here with no tax decision on a line.

The defaults already put 5% on every line through the account, and the
emirate's fiscal position maps it to the right box. But a default is a
suggestion: somebody clears the tax cell in a hurry and the invoice posts,
understating output VAT on a document the FTA will read.

So posting is refused when a line carries NO tax at all. That is different
from refusing a line that is not charged 5% — zero-rated exports, exempt
supplies and reverse charge are all legitimate, and all of them are a TAX,
chosen deliberately, that the return reports in its own box. What cannot
happen is an empty tax cell, which is not a decision but an omission, and
which the VAT return cannot report anywhere.

Section 1 of the checks a health_check run flags; this stops it at the door
instead.
"""

from odoo import api, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _mizan_vat_applies(self):
        self.ensure_one()
        return (self.move_type in ("out_invoice", "out_refund",
                                   "in_invoice", "in_refund")
                and self.company_id.country_id.code == "AE")

    @api.model
    def _mizan_untaxed_lines(self, move):
        # display_type is 'product' on a real invoice line in Odoo 17+, not
        # empty — testing "not display_type" silently matched nothing and the
        # guard never fired once.
        return move.invoice_line_ids.filtered(
            lambda l: l.display_type == "product" and not l.tax_ids
            and not l.currency_id.is_zero(l.price_subtotal))

    def action_post(self):
        for move in self:
            if not move._mizan_vat_applies():
                continue
            missing = self._mizan_untaxed_lines(move)
            if not missing:
                continue
            raise UserError(_(
                "%(name)s has %(count)d line(s) with no tax at all:\n\n"
                "%(lines)s\n\n"
                "Every line on a UAE invoice needs a tax chosen — 5%%, "
                "zero-rated, exempt or reverse charge. An empty tax is not a "
                "choice, and the VAT return has no box to report it in.",
                name=move.name or _("This document"),
                count=len(missing),
                lines="\n".join(
                    "  • %s" % (line.name or line.product_id.display_name or "-")[:70]
                    for line in missing[:8])))
        return super().action_post()
