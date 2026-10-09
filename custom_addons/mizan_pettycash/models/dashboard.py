# -*- coding: utf-8 -*-
"""Petty cash on every role's first screen.

The engineer sees what he holds; whoever approves sees what is waiting for
him and how much cash is out on site. Nobody opens the expenses app to find
either."""

from odoo import api, models, _
from odoo.exceptions import AccessError


class MizanDashboardTile(models.TransientModel):
    _inherit = "mizan.dashboard.tile"

    @api.model
    def _role(self):
        role = super()._role()
        # The engineers' manager: he is not the project manager and must not
        # be shown contract values, but he is more than an engineer — his
        # team's receipts and cash are his to watch.
        if role == "site" and self.env.user.has_group("mizan_site.group_site_manager"):
            return "sitemgr"
        return role

    @api.model
    def _tiles_for(self, role):
        rows = super()._tiles_for("site" if role == "sitemgr" else role)
        extra = []

        def tile(section, name, value, sublabel="", tone="plain", model=False,
                 domain=None, xmlid=False):
            extra.append({
                "sequence": 0,
                "section": section, "name": name, "value": value,
                "sublabel": sublabel, "tone": tone, "res_model": model,
                "domain": repr(domain or []), "action_xmlid": xmlid or "",
            })

        section = _("Petty cash")
        Advance = self.env["mizan.employee.advance"]
        employee = self.env["hr.employee"].search([("user_id", "=", self.env.uid)], limit=1)
        try:
            if employee:
                cash = Advance._petty_cash(employee)
                if cash["advances"] or role in ("site", "sitemgr"):
                    tile(section, _("My petty cash"), self._money(cash["available"]),
                         _("%(held)s held · %(n)s receipt(s) waiting",
                           held=self._money(cash["held"]), n=cash["waiting_count"]),
                         tone="bad" if cash["available"] < 0 else (
                             "watch" if cash["advances"] and cash["available"]
                             < 0.2 * sum(cash["advances"].mapped("amount")) else "good"),
                         xmlid="mizan_pettycash.action_my_receipts")
            if role != "site":
                waiting = self.env["hr.expense.sheet"].search([
                    ("state", "=", "submit"), ("mizan_advance_id", "!=", False),
                    ("employee_id.user_id", "!=", self.env.uid)])
                mine = waiting.filtered("can_approve")
                if mine or role == "sitemgr":
                    tile(section, _("Receipts waiting for you"), str(len(mine)),
                         self._money(sum(mine.mapped("total_amount"))),
                         tone="watch" if mine else "good",
                         xmlid="mizan_pettycash.action_approve_receipts")
                if self.env.user.has_group("account.group_account_invoice"):
                    to_post = self.env["hr.expense.sheet"].search([
                        ("state", "=", "approve"), ("mizan_advance_id", "!=", False)])
                    if to_post:
                        tile(section, _("Approved, to post"), str(len(to_post)),
                             self._money(sum(to_post.mapped("total_amount"))),
                             tone="watch", xmlid="mizan_pettycash.action_post_receipts")
                paid = Advance.search([("state", "=", "paid")])
                if paid:
                    out = sum(paid.mapped("amount_outstanding"))
                    tile(section, _("Cash out on site"), self._money(out),
                         _("With %s people", len(paid.employee_id)),
                         xmlid="mizan_pettycash.action_balances")
                asked = Advance.search([("state", "=", "submitted")])
                if asked:
                    tile(section, _("Cash requests to approve"), str(len(asked)),
                         self._money(sum(asked.mapped("amount"))), tone="watch",
                         model="mizan.employee.advance",
                         domain=[("state", "=", "submitted")])
        except AccessError:
            pass

        # The things done from a phone, one tap from the first screen.
        quick = _("Do it now")
        tile(quick, _("Photograph a bill"), "📷",
             _("A receipt or a supplier's invoice"), xmlid="mizan_site.action_site_capture")
        if role in ("site", "sitemgr"):
            tile(quick, _("Daily report"), "📝", _("Today's site report"),
                 xmlid="mizan_site.action_site_report")
            tile(quick, _("Ask for a top-up"), "💵", _("Petty cash"),
                 xmlid="mizan_pettycash.action_topup")
        # Cash first: it is the figure that changes every day.
        combined = extra + rows
        for index, row in enumerate(combined):
            row["sequence"] = index * 10
        return combined
