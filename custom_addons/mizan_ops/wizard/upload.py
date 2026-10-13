# -*- coding: utf-8 -*-
"""Upload a file from the phone, to the step or file it belongs to.

On a phone the file picker offers the camera, so a photographed licence or a
signed form reaches the right task from the site, with a line saying what it
is — and the office sees it in the task's thread, not in somebody's gallery.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanOpsUpload(models.TransientModel):
    _name = "mizan.ops.upload"
    _description = "Upload a File"

    case_id = fields.Many2one("mizan.workflow.case", string="Workflow file",
                              domain=[("state", "=", "open")])
    task_id = fields.Many2one(
        "project.task", string="Step",
        domain="[('mizan_case_id', '=', case_id)] if case_id else [('is_closed', '=', False), ('user_ids', 'in', uid)]")
    file = fields.Binary(string="File", required=True, attachment=False)
    filename = fields.Char()
    note = fields.Char(string="What it is", help="Trade licence 2026, signed contract, receipt…")
    mark_done = fields.Boolean(string="And mark the step done")

    @api.onchange("task_id")
    def _onchange_task(self):
        if self.task_id and self.task_id.mizan_case_id and not self.case_id:
            self.case_id = self.task_id.mizan_case_id

    def action_upload(self):
        self.ensure_one()
        target = self.task_id or self.case_id
        if not target:
            raise UserError(_("Choose the step or the file this document belongs to."))
        attachment = self.env["ir.attachment"].create({
            "name": self.filename or (self.note or _("document")),
            "datas": self.file,
            "res_model": target._name,
            "res_id": target.id,
        })
        target.message_post(
            body=self.note or _("File uploaded"),
            attachment_ids=[attachment.id],
            message_type="comment", subtype_xmlid="mail.mt_comment")
        if self.mark_done and self.task_id:
            self.task_id.action_mizan_done()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Uploaded"),
                "message": _("%(file)s is on %(where)s.", file=attachment.name, where=target.display_name),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
