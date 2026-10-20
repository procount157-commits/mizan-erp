# -*- coding: utf-8 -*-
"""The lowest week of the next thirteen, on the owner's page and the phone."""
from odoo import _, api, models


class MizanOwner(models.AbstractModel):
    _inherit = "mizan.owner"

    @api.model
    def get_summary(self):
        summary = super().get_summary()
        try:
            weeks = self.env["mizan.cashflow.week"].get_forecast()
        except Exception:  # noqa: BLE001 - the page shows without the forecast
            return summary
        if not weeks:
            return summary
        low = min(weeks, key=lambda w: w.closing)
        first4 = weeks[:4]
        inflow, outflow = sum(first4.mapped("inflow")), sum(first4.mapped("outflow"))
        opening = weeks[0].opening
        tone = "bad" if low.closing < 0 else "watch" if low.closing < 0.2 * max(opening, 1) else "good"
        short = weeks.filtered("short")[:1]
        lines = [_("Lowest in the week of %s", low.name)]
        if short:
            lines.insert(0, _("Runs short in the week of %s", short.name))
        lines += [_("Next 4 weeks: in %(i)s · out %(o)s", i=self._money(inflow, short=True), o=self._money(outflow, short=True)),
                  _("In 13 weeks: %s", self._money(weeks[-1].closing, short=True))]
        summary.setdefault("cards", []).append({
            "key": "forecast", "title": _("Lowest cash, next 13 weeks"), "value": self._money(low.closing),
            "tone": tone, "lines": lines,
            "action": {"type": "ir.actions.act_window", "name": _("Cash flow forecast"),
                       "res_model": "mizan.cashflow.week", "views": [[False, "list"], [False, "graph"]],
                       "domain": [("company_id", "=", self.env.company.id)], "target": "current"},
        })
        return summary
