# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class MizanWorkflowStart(models.TransientModel):
    """Start a workflow: pick the template, say who it is for, and go."""
    _name = "mizan.workflow.start"
    _description = "Start a Workflow"

    template_id = fields.Many2one("mizan.workflow.template", string="Workflow", required=True)
    partner_id = fields.Many2one("res.partner", string="Client")
    # precompute: required columns must hold a value at insert time, and a
    # stored compute without it is written only after the row exists.
    name = fields.Char(string="File name", compute="_compute_name", store=True, readonly=False,
                       required=True, precompute=True)
    responsible_id = fields.Many2one(
        "res.users", string="Owner", required=True,
        default=lambda self: self.env.user)
    project_id = fields.Many2one("project.project", string="Project", required=True,
                                 compute="_compute_project", store=True, readonly=False, precompute=True)
    date_start = fields.Date(default=fields.Date.context_today, required=True)
    step_count = fields.Integer(related="template_id.step_count")
    days_total = fields.Integer(related="template_id.days_total")
    note = fields.Text(string="Note for the team")

    @api.depends("template_id", "partner_id")
    def _compute_name(self):
        for wiz in self:
            if wiz.template_id:
                wiz.name = "%s — %s" % (wiz.template_id.name, wiz.partner_id.name) \
                    if wiz.partner_id else wiz.template_id.name

    @api.depends("template_id")
    def _compute_project(self):
        default = self.env.ref("mizan_ops.project_ops", raise_if_not_found=False)
        for wiz in self:
            wiz.project_id = wiz.template_id.project_id or default
            if wiz.template_id.responsible_id and wiz.responsible_id == self.env.user:
                wiz.responsible_id = wiz.template_id.responsible_id

    def action_start(self):
        self.ensure_one()
        case = self.env["mizan.workflow.case"].create({
            "name": self.name,
            "template_id": self.template_id.id,
            "partner_id": self.partner_id.id,
            "project_id": self.project_id.id,
            "responsible_id": self.responsible_id.id,
            "date_start": self.date_start,
        })
        case._create_steps()
        if self.note:
            case.message_post(body=self.note)
        # Whoever got a step hears about it; the owner follows the whole file.
        case.message_subscribe(partner_ids=(case.task_ids.user_ids | case.responsible_id).partner_id.ids)
        return {
            "type": "ir.actions.act_window",
            "res_model": "mizan.workflow.case",
            "res_id": case.id,
            "view_mode": "form",
            "target": "current",
        }
