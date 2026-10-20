# -*- coding: utf-8 -*-
"""Plant hours from the site report become the job's plant charge.

The engineer already writes, every day, which machine worked and for how
long. Until now those hours stopped on the report and the job was charged
for plant only when somebody remembered to type a charge. When the office
acknowledges a report, each owned machine on it becomes a draft charge on the
report's contract at the machine's internal rate — hours, days (8 hours) or
months (26 days) by how the machine is rated. Draft: the office posts it, so
nothing reaches the ledger because a site report was read."""
from odoo import _, api, fields, models


class MizanPlantCharge(models.Model):
    _inherit = "mizan.plant.charge"

    site_plant_id = fields.Many2one("mizan.site.plant", string="From site report", readonly=True,
                                    copy=False, index=True, ondelete="set null")

    _sql_constraints = [
        ("site_plant_uniq", "unique(site_plant_id)", "These plant hours are already charged."),
    ]


class MizanSiteReport(models.Model):
    _inherit = "mizan.site.report"

    def action_acknowledge(self):
        res = super().action_acknowledge()
        self.sudo()._mizan_plant_charges()
        return res

    def _mizan_plant_charges(self):
        Charge = self.env["mizan.plant.charge"]
        code = self.env["mizan.cost.code"].search([("code", "=", "30-200")], limit=1)
        made = Charge
        for report in self:
            contract = report.contract_id
            if not contract:
                continue
            mine = Charge
            for row in report.plant_ids.filtered(lambda r: r.plant_id and r.hours > 0):
                if Charge.search_count([("site_plant_id", "=", row.id)]):
                    continue
                plant = row.plant_id
                per = {"hour": 1.0, "day": 8.0, "month": 8.0 * 26}.get(plant.rate_basis, 8.0)
                mine |= Charge.create({
                    "plant_id": plant.id, "contract_id": contract.id, "date": report.date,
                    "quantity": round(row.hours / per, 3), "rate": plant.internal_rate,
                    "cost_code_id": code.id or False, "site_plant_id": row.id,
                    "note": _("%(report)s: %(hours)s h worked, %(idle)s h standing", report=report.name,
                              hours="{:g}".format(row.hours), idle="{:g}".format(row.idle_hours or 0)),
                })
            if mine:
                report.message_post(body=_("%s plant charge(s) drafted for the office to post.", len(mine)))
            made |= mine
        return made
