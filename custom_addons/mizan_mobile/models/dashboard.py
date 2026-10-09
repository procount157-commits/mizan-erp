# -*- coding: utf-8 -*-
"""The day's work on the first screen: what is due from me, and the deals I
am following. Petty cash and the jobs are already there; these were the two
things a person still opened an app to find."""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class MizanDashboardTile(models.TransientModel):
    _inherit = "mizan.dashboard.tile"

    @api.model
    def _tiles_for(self, role):
        rows = super()._tiles_for(role)
        uid = self.env.uid
        today = fields.Date.context_today(self)
        section = _("My work")
        extra = []

        def tile(name, value, sublabel="", tone="plain", model=False, domain=None):
            extra.append({"sequence": 0, "section": section, "name": name,
                          "value": value, "sublabel": sublabel, "tone": tone,
                          "res_model": model, "domain": repr(domain or []),
                          "action_xmlid": ""})

        try:
            due = [("user_id", "=", uid), ("date_deadline", "<=", today)]
            activities = self.env["mail.activity"].search(due)
            late = activities.filtered(lambda a: a.date_deadline < today)
            tile(_("To do today"), str(len(activities)),
                 _("%s overdue", len(late)) if late else _("Nothing overdue"),
                 tone="bad" if late else ("watch" if activities else "good"),
                 model="mail.activity", domain=due)
        except AccessError:
            pass

        try:
            mine = [("user_ids", "in", uid), ("is_closed", "=", False)]
            tasks = self.env["project.task"].search(mine)
            overdue = tasks.filtered(lambda t: t.date_deadline and t.date_deadline.date() < today)
            tile(_("My tasks"), str(len(tasks)),
                 _("%s past their deadline", len(overdue)) if overdue else _("On time"),
                 tone="bad" if overdue else "plain",
                 model="project.task", domain=mine)
        except AccessError:
            pass

        if self.env.user.has_group("sales_team.group_sale_salesman"):
            try:
                Lead = self.env["crm.lead"]
                open_domain = [("type", "=", "opportunity"), ("probability", "<", 100),
                               ("active", "=", True)]
                mine = open_domain + [("user_id", "=", uid)]
                deals = Lead.search(mine)
                tile(_("My opportunities"), str(len(deals)),
                     self._money(sum(deals.mapped("expected_revenue"))),
                     model="crm.lead", domain=mine)
                if self.env.user.has_group("sales_team.group_sale_manager") or role in ("gm", "cfo"):
                    pipeline = Lead.search(open_domain)
                    month = today.replace(day=1)
                    won = Lead.search([("type", "=", "opportunity"), ("probability", "=", 100),
                                       ("date_closed", ">=", month)])
                    tile(_("Pipeline"), self._money(sum(pipeline.mapped("expected_revenue"))),
                         _("%(n)s open · %(won)s won this month", n=len(pipeline),
                           won=self._money(sum(won.mapped("expected_revenue")))),
                         model="crm.lead", domain=open_domain)
            except AccessError:
                pass

        combined = rows + extra
        for index, row in enumerate(combined):
            row["sequence"] = index * 10
        return combined
