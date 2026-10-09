# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    mizan_photo = fields.Binary(
        string="Receipt", compute="_compute_mizan_photo",
        help="The photograph, on the approval list itself: the manager "
             "approves what he can see, without opening each claim.")

    def _compute_mizan_photo(self):
        for sheet in self:
            attachment = sheet.expense_line_ids[:1].message_main_attachment_id
            sheet.mizan_photo = (attachment.datas if attachment
                                 and (attachment.mimetype or "").startswith("image/")
                                 else False)

    def action_sheet_move_post(self):
        """Posting a claim made against an advance also settles the advance.

        Settling was a second step on a second screen, and it was the one
        that got forgotten: the claim posted, the employee showed as owed,
        and the advance showed as still out — both wrong, at once."""
        res = super().action_sheet_move_post()
        for advance in self.filtered(lambda s: s.state in ("post", "done")).mizan_advance_id:
            if advance.state != "paid":
                continue
            try:
                with self.env.cr.savepoint():
                    advance.action_settle()
            except UserError:
                # Nothing new to clear (already settled), or the employee has
                # no partner — the claim is posted either way, and the advance
                # form says why when somebody settles it by hand.
                continue
        return res

    def action_mizan_approve(self):
        """Approve the selected receipts — and, for whoever may post, post
        them too, which settles the advance. One tap for the whole day."""
        sheets = self.filtered(lambda s: s.state == "submit")
        if not sheets:
            raise UserError(_("Select receipts waiting for approval."))
        result = sheets.action_approve_expense_sheets()
        if isinstance(result, dict):
            # Odoo found a possible duplicate and asks about it first.
            return result
        posted = False
        if self.env.user.has_group("account.group_account_invoice"):
            sheets.filtered(lambda s: s.state == "approve").action_sheet_move_post()
            posted = True
        else:
            self._mizan_tell_accounts(sheets)
        return self._mizan_done(
            _("%(n)s receipt(s) approved and posted.", n=len(sheets)) if posted
            else _("%(n)s receipt(s) approved. Accounting will post them.", n=len(sheets)))

    def action_mizan_post(self):
        sheets = self.filtered(lambda s: s.state == "approve")
        if not sheets:
            raise UserError(_("Select approved receipts."))
        sheets.action_sheet_move_post()
        return self._mizan_done(_("%(n)s receipt(s) posted; the advances are "
                                  "settled.", n=len(sheets)))

    def _mizan_tell_accounts(self, sheets):
        group = self.env.ref("account.group_account_invoice")
        accountants = group.sudo().users.filtered(
            lambda u: u.active and not u.share
            and not u.has_group("mizan_site.group_site_engineer"))
        if accountants:
            for sheet in sheets:
                sheet.sudo().message_notify(
                    partner_ids=accountants.partner_id.ids,
                    subject=_("Petty cash ready to post"),
                    body=_("%(who)s approved %(name)s for %(amount)s.",
                           who=self.env.user.name, name=sheet.name,
                           amount="{:,.2f}".format(sheet.total_amount)))

    def _mizan_done(self, message):
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Done"), "message": message,
                       "type": "success",
                       "next": {"type": "ir.actions.client", "tag": "soft_reload"}},
        }
