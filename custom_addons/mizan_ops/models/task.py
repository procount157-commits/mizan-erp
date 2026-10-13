# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    mizan_case_id = fields.Many2one(
        "mizan.workflow.case", string="Workflow file", index=True, ondelete="set null", tracking=True)
    mizan_requires_file = fields.Boolean(string="Needs a file")
    mizan_needs_client = fields.Boolean(string="Waits on the client")
    mizan_has_file = fields.Boolean(compute="_compute_mizan_has_file", string="Has a file")
    mizan_file_missing = fields.Boolean(
        compute="_compute_mizan_has_file", search="_search_mizan_file_missing",
        string="File still missing")

    def _compute_mizan_has_file(self):
        Attachment = self.env["ir.attachment"]
        with_file = set(Attachment.search([("res_model", "=", self._name),
                                           ("res_id", "in", self.ids)]).mapped("res_id"))
        for task in self:
            task.mizan_has_file = task.id in with_file
            task.mizan_file_missing = task.mizan_requires_file and task.id not in with_file

    def _search_mizan_file_missing(self, operator, value):
        need = self.search([("mizan_requires_file", "=", True)])
        with_file = set(self.env["ir.attachment"].search(
            [("res_model", "=", self._name), ("res_id", "in", need.ids)]).mapped("res_id"))
        missing = [t.id for t in need if t.id not in with_file]
        want = (operator == "=" and value) or (operator == "!=" and not value)
        return [("id", "in" if want else "not in", missing)]

    def action_mizan_upload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Upload a file",
            "res_model": "mizan.ops.upload",
            "view_mode": "form",
            "target": "new",
            "context": {"default_task_id": self.id, "default_case_id": self.mizan_case_id.id},
        }

    def action_mizan_done(self):
        """One tap from the phone: the step is done."""
        self.write({"state": "1_done"})
        return True
