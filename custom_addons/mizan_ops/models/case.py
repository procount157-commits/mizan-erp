# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanWorkflowCase(models.Model):
    """One job in progress: a workflow started for a client or a project.

    The case is the folder. Its tasks are the steps, its chatter is the
    conversation, its attachments and its tasks' attachments are the papers.
    Progress is counted from the tasks, never typed."""
    _name = "mizan.workflow.case"
    _description = "Workflow in Progress"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "state, date_due, id desc"

    name = fields.Char(string="File", required=True, tracking=True)
    template_id = fields.Many2one("mizan.workflow.template", string="Workflow", tracking=True)
    category = fields.Selection(related="template_id.category", store=True)
    partner_id = fields.Many2one("res.partner", string="Client", tracking=True)
    project_id = fields.Many2one(
        "project.project", string="Project", required=True,
        default=lambda self: self.env.ref("mizan_ops.project_ops", raise_if_not_found=False))
    responsible_id = fields.Many2one(
        "res.users", string="Owner", required=True, default=lambda self: self.env.user, tracking=True)
    date_start = fields.Date(default=fields.Date.context_today, required=True)
    date_due = fields.Date(string="Due", compute="_compute_due", store=True, readonly=False)
    state = fields.Selection(
        [("open", "In progress"), ("done", "Done"), ("cancel", "Cancelled")],
        default="open", required=True, tracking=True)
    task_ids = fields.One2many("project.task", "mizan_case_id", string="Steps")
    task_count = fields.Integer(compute="_compute_task_stats")
    task_done = fields.Integer(compute="_compute_task_stats")
    progress = fields.Float(compute="_compute_progress", store=True, aggregator="avg")
    next_step = fields.Char(compute="_compute_task_stats", string="Next step")
    is_late = fields.Boolean(compute="_compute_task_stats", search="_search_is_late")
    attachment_count = fields.Integer(compute="_compute_attachments")
    missing_files = fields.Integer(
        compute="_compute_attachments", string="Steps needing a file",
        help="Steps marked as needing a document and finished without one.")
    note = fields.Html(string="Notes")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    # ----------------------------------------------------------- computes
    @api.depends("task_ids.date_deadline", "date_start")
    def _compute_due(self):
        for case in self:
            deadlines = [d.date() for d in case.task_ids.mapped("date_deadline") if d]
            case.date_due = max(deadlines) if deadlines else case.date_due or case.date_start

    @api.depends("task_ids.state", "task_ids.is_closed", "state")
    def _compute_progress(self):
        """Stored, so lists and kanbans sort and average on it."""
        for case in self:
            tasks = case.task_ids
            done = tasks.filtered("is_closed")
            case.progress = (len(done) / len(tasks) * 100.0) if tasks else (100.0 if case.state == "done" else 0.0)

    @api.depends("task_ids.state", "task_ids.is_closed", "task_ids.date_deadline", "state")
    def _compute_task_stats(self):
        today = fields.Date.context_today(self)
        for case in self:
            tasks = case.task_ids
            done = tasks.filtered("is_closed")
            case.task_count = len(tasks)
            case.task_done = len(done)
            nxt = (tasks - done).sorted(lambda t: (t.date_deadline or fields.Datetime.now(), t.id))[:1]
            case.next_step = nxt.name if nxt else ""
            case.is_late = bool(case.state == "open" and any(
                t.date_deadline and t.date_deadline.date() < today for t in tasks - done))

    def _search_is_late(self, operator, value):
        today = fields.Datetime.now()
        late = self.env["project.task"].search([
            ("mizan_case_id", "!=", False), ("is_closed", "=", False), ("date_deadline", "<", today)])
        ids = late.mapped("mizan_case_id").filtered(lambda c: c.state == "open").ids
        want = (operator == "=" and value) or (operator == "!=" and not value)
        return [("id", "in" if want else "not in", ids)]

    def _attachment_domain(self):
        self.ensure_one()
        return ["|", "&", ("res_model", "=", self._name), ("res_id", "=", self.id),
                "&", ("res_model", "=", "project.task"), ("res_id", "in", self.task_ids.ids)]

    def _compute_attachments(self):
        Attachment = self.env["ir.attachment"]
        for case in self:
            case.attachment_count = Attachment.search_count(case._attachment_domain()) if case.id else 0
            with_file = Attachment.search([("res_model", "=", "project.task"),
                                           ("res_id", "in", case.task_ids.ids)]).mapped("res_id")
            case.missing_files = len(case.task_ids.filtered(
                lambda t: t.mizan_requires_file and t.is_closed and t.id not in with_file))

    # ------------------------------------------------------------ actions
    def action_done(self):
        for case in self:
            open_tasks = case.task_ids.filtered(lambda t: not t.is_closed)
            if open_tasks:
                raise UserError(_(
                    "%(n)s step(s) are still open on %(name)s: %(steps)s. Finish or cancel them first.",
                    n=len(open_tasks), name=case.name,
                    steps=", ".join(open_tasks.mapped("name")[:5])))
            case.state = "done"
        return True

    def action_cancel(self):
        self.task_ids.filtered(lambda t: not t.is_closed).write({"state": "1_canceled"})
        self.write({"state": "cancel"})
        return True

    def action_reopen(self):
        self.write({"state": "open"})
        return True

    def action_view_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Steps — %s", self.name),
            "res_model": "project.task",
            "view_mode": "list,kanban,form",
            "domain": [("mizan_case_id", "=", self.id)],
            "context": {"default_mizan_case_id": self.id, "default_project_id": self.project_id.id,
                        "default_partner_id": self.partner_id.id},
        }

    def action_view_files(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Files — %s", self.name),
            "res_model": "ir.attachment",
            "view_mode": "kanban,list,form",
            "domain": self._attachment_domain(),
            "context": {"default_res_model": self._name, "default_res_id": self.id},
        }

    def action_upload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Upload a file"),
            "res_model": "mizan.ops.upload",
            "view_mode": "form",
            "target": "new",
            "context": {"default_case_id": self.id},
        }

    def action_add_step(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("New step"),
            "res_model": "project.task",
            "view_mode": "form",
            "target": "new",
            "context": {"default_mizan_case_id": self.id, "default_project_id": self.project_id.id,
                        "default_partner_id": self.partner_id.id,
                        "default_user_ids": [(6, 0, self.responsible_id.ids)]},
        }

    # ----------------------------------------------------------- creation
    def _create_steps(self):
        """Every template step becomes a task: assigned, dated, instructed."""
        Task = self.env["project.task"]
        for case in self:
            if not case.template_id:
                continue
            for step in case.template_id.step_ids:
                Task.create({
                    "name": step.name,
                    "project_id": case.project_id.id,
                    "partner_id": case.partner_id.id,
                    "mizan_case_id": case.id,
                    "mizan_requires_file": step.requires_file,
                    "mizan_needs_client": step.needs_client,
                    "sequence": step.sequence,
                    "user_ids": [(6, 0, (step.assignee_id or case.responsible_id).ids)],
                    "date_deadline": fields.Datetime.to_datetime(
                        case.date_start + timedelta(days=step.days)).replace(hour=14),
                    "description": step.instructions or False,
                })
        return True
