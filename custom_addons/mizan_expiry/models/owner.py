# -*- coding: utf-8 -*-
"""What lapses this month, on the owner's page and the phone."""
from odoo import _, api, models


class MizanOwner(models.AbstractModel):
    _inherit = "mizan.owner"

    @api.model
    def get_summary(self):
        summary = super().get_summary()
        Doc = self.env["mizan.expiry.document"].sudo()
        docs = Doc.search([("state", "in", ("soon", "expired")), ("days_left", "<=", 30)], order="days_left")
        if not docs:
            return summary
        expired = docs.filtered(lambda d: d.state == "expired")
        lines = []
        for doc in docs[:3]:
            lines.append(_("%(n)s: expired %(d)s day(s) ago", n=doc.name, d=-doc.days_left) if doc.days_left < 0
                         else _("%(n)s: %(d)s day(s) left", n=doc.name, d=doc.days_left))
        if len(docs) > 3:
            lines.append(_("and %s more", len(docs) - 3))
        summary.setdefault("cards", []).append({
            "key": "expiry",
            "title": _("Expired") if expired and len(expired) == len(docs) else _("Expiring within 30 days"),
            "value": _("%s document(s)", len(docs)),
            "tone": "bad" if expired else "watch",
            "lines": lines,
            "action": self._act(_("Expiries"), "mizan.expiry.document",
                                [("state", "in", ("soon", "expired"))]),
        })
        return summary
