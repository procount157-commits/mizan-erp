# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class MizanWorkflowTemplate(models.Model):
    """The steps a recurring job always takes, written once.

    A template is not a project plan; it is the office's memory of how a
    licence renewal or a VAT return is done, so the third person to do one
    does it the way the first one learned to."""
    _name = "mizan.workflow.template"
    _description = "Workflow Template"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection([
        ("client", "Client service"),
        ("finance", "Finance & tax"),
        ("project", "Projects & sites"),
        ("hr", "People"),
        ("internal", "Internal"),
    ], default="client", required=True)
    description = fields.Text(
        help="When this workflow is used, and what the result should be.")
    project_id = fields.Many2one(
        "project.project", string="Tasks go to project",
        help="Where the steps are created. Empty means the Operations project.")
    responsible_id = fields.Many2one(
        "res.users", string="Default owner",
        help="Who owns a file started from this template, unless changed at the start.")
    step_ids = fields.One2many("mizan.workflow.step", "template_id", string="Steps", copy=True)
    step_count = fields.Integer(compute="_compute_counts")
    days_total = fields.Integer(string="Days, start to finish", compute="_compute_counts")
    case_count = fields.Integer(compute="_compute_counts")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.depends("step_ids.days")
    def _compute_counts(self):
        Case = self.env["mizan.workflow.case"]
        for template in self:
            template.step_count = len(template.step_ids)
            template.days_total = max(template.step_ids.mapped("days") or [0])
            template.case_count = Case.search_count([("template_id", "=", template.id)])

    def action_start(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Start: %s", self.name),
            "res_model": "mizan.workflow.start",
            "view_mode": "form",
            "target": "new",
            "context": {"default_template_id": self.id},
        }

    def action_view_cases(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("mizan_ops.action_ops_case")
        action["domain"] = [("template_id", "=", self.id)]
        action["context"] = {"default_template_id": self.id}
        return action


class MizanWorkflowStep(models.Model):
    _name = "mizan.workflow.step"
    _description = "Workflow Step"
    _order = "sequence, id"

    template_id = fields.Many2one("mizan.workflow.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Step", required=True, translate=True)
    instructions = fields.Html(
        translate=True,
        help="What exactly is done, where, and what the result looks like. "
             "Written for the person doing it for the first time.")
    days = fields.Integer(
        string="Due after (days)", default=1,
        help="Days after the workflow starts by which this step is due.")
    assignee_id = fields.Many2one(
        "res.users", string="Usually done by",
        help="Left empty, the step goes to whoever owns the file.")
    requires_file = fields.Boolean(
        string="Needs a file",
        help="The step is not done until a document is attached: a licence, "
             "a receipt, a signed form.")
    needs_client = fields.Boolean(
        string="Waits on the client",
        help="Something the client has to send or sign. Shown so the office "
             "chases them rather than waiting.")
