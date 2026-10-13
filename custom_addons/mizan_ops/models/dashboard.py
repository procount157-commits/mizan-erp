# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import AccessError


class MizanDashboardTile(models.TransientModel):
    _inherit = "mizan.dashboard.tile"

    @api.model
    def _tiles_for(self, role):
        rows = super()._tiles_for(role)
        if not self.env.user.has_group("project.group_project_user"):
            return rows
        try:
            Case = self.env["mizan.workflow.case"]
            mine = [("state", "=", "open"), ("responsible_id", "=", self.env.uid)]
            cases = Case.search(mine)
            late = cases.filtered("is_late")
            rows.append({
                "sequence": len(rows) * 10, "section": _("My work"),
                "name": _("Workflows I own"), "value": str(len(cases)),
                "sublabel": _("%s running late", len(late)) if late else _("All on time"),
                "tone": "bad" if late else "plain",
                "res_model": "mizan.workflow.case", "domain": repr(mine), "action_xmlid": "",
            })
        except AccessError:
            pass
        return rows
