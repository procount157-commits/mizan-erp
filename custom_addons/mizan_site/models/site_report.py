# -*- coding: utf-8 -*-
"""The day, as the site saw it.

A contractor's day produces one document and until now it lived in a WhatsApp
group: how many men, of which trade, what plant was standing, what got built,
what stopped and why, and photographs. Two months later that is the only
evidence there is, and an extension-of-time claim that cannot say which days
were lost and for what reason is not a claim — it is an assertion.

So the report records the things an argument is later conducted in: the date,
the weather, manpower by trade with hours, plant on site and whether it worked,
progress against the bill items being built, and the reason work stopped.

It posts nothing. An engineer raises; somebody else approves and somebody else
still posts. That separation is the reason a site engineer can be given a login
at all, and it is deliberately not weakened for convenience.

Manpower hours optionally become timesheet entries against the project's cost
centre — but only on submission, only once, and only when the engineer asked
for it. A daily report that quietly wrote labour cost into the ledger every
time somebody saved a draft would put the site in charge of the accounts.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MizanSiteReport(models.Model):
    _name = "mizan.site.report"
    _description = "Daily Site Report"
    _inherit = ["mail.thread", "mail.activity.mixin",
                "mizan.next.action.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(readonly=True, copy=False, default=lambda s: _("New"))
    date = fields.Date(required=True, default=fields.Date.context_today,
                       tracking=True)
    project_id = fields.Many2one(
        "project.project", string="Project", required=True, tracking=True,
        help="The job this day belongs to. Everything else on the report is "
             "read in terms of it.")
    # The contract behind the project, for the office. An engineer must not
    # be able to read mizan.contract — it carries the contract value, the
    # margin and the client's retention — so the field is computed with sudo
    # and then hidden from him at field level. Without the groups= it would
    # raise an AccessError the moment he opened his own report, which is how a
    # link put there for somebody else's convenience becomes a broken screen
    # for the person actually using it.
    contract_id = fields.Many2one(
        "mizan.contract", compute="_compute_contract", store=True,
        compute_sudo=True, string="Contract",
        groups="account.group_account_invoice,account.group_account_readonly,"
               "project.group_project_manager")
    analytic_account_id = fields.Many2one(
        related="contract_id.analytic_account_id", store=True,
        compute_sudo=True, string="Cost Center",
        groups="account.group_account_invoice,account.group_account_readonly,"
               "project.group_project_manager")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)

    author_id = fields.Many2one(
        "res.users", string="Engineer", required=True, readonly=True,
        default=lambda self: self.env.user)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"),
         ("acknowledged", "Read by the office")],
        default="draft", required=True, tracking=True)

    weather = fields.Selection(
        [("clear", "Clear"), ("hot", "Extreme heat"), ("wind", "High wind"),
         ("rain", "Rain"), ("sand", "Sandstorm")],
        default="clear", tracking=True,
        help="Recorded because it is the first thing asked when a day is "
             "claimed as lost.")
    work_stopped = fields.Boolean(string="Work stopped today", tracking=True)
    stop_reason = fields.Selection(
        [("weather", "Weather"), ("material", "Material not on site"),
         ("access", "No access to the area"), ("drawing", "Awaiting drawings"),
         ("instruction", "Awaiting an instruction"),
         ("client", "Client or consultant"), ("labour", "No labour"),
         ("other", "Other")],
        string="Why it stopped", tracking=True)
    stop_hours = fields.Float(string="Hours lost")

    manpower_ids = fields.One2many("mizan.site.manpower", "report_id",
                                   string="Manpower")
    plant_ids = fields.One2many("mizan.site.plant", "report_id",
                                string="Plant on site")
    headcount = fields.Integer(compute="_compute_totals", store=True)
    manhours = fields.Float(compute="_compute_totals", store=True)

    work_done = fields.Text(
        string="What was built today", required=True,
        help="In the words the bill of quantities uses, where it can be. A "
             "report saying 'block work continued' answers nothing later.")
    issues = fields.Text(string="Problems")
    photo = fields.Image(string="Photograph", max_width=1920, max_height=1920)
    timesheet_ids = fields.One2many(
        "account.analytic.line", "mizan_site_report_id", readonly=True,
        string="Timesheet entries")
    timesheets_posted = fields.Boolean(readonly=True, copy=False)

    _sql_constraints = [
        ("day_project_author_uniq", "unique(date, project_id, author_id)",
         "You already filed a report for this project on this date."),
    ]

    @api.depends("project_id")
    def _compute_contract(self):
        Contract = self.env["mizan.contract"].sudo()
        for report in self:
            report.contract_id = Contract.search(
                [("project_id", "=", report.project_id.id)], limit=1)

    @api.depends("manpower_ids.headcount", "manpower_ids.hours")
    def _compute_totals(self):
        for report in self:
            report.headcount = sum(report.manpower_ids.mapped("headcount"))
            report.manhours = sum(
                line.headcount * line.hours for line in report.manpower_ids)

    @api.constrains("work_stopped", "stop_reason")
    def _check_stop(self):
        for report in self:
            if report.work_stopped and not report.stop_reason:
                raise ValidationError(_(
                    "Say why work stopped. 'Work stopped' with no reason is "
                    "the one line a delay claim cannot be built on."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mizan.site.report") or _("New")
        return super().create(vals_list)

    # ------------------------------------------------------------- workflow
    def action_submit(self):
        for report in self:
            if report.state != "draft":
                raise UserError(_("It has already been submitted."))
            report.state = "submitted"
            report.message_post(body=_(
                "%(count)s men, %(hours).0f man-hours. %(work)s",
                count=report.headcount, hours=report.manhours,
                work=(report.work_done or "")[:200]))
        return True

    def action_acknowledge(self):
        self.write({"state": "acknowledged"})
        return True

    def action_reopen(self):
        for report in self:
            if report.timesheets_posted:
                raise UserError(_(
                    "The labour on this report is already on the timesheet. "
                    "Correct the timesheet, not the report it came from."))
            report.state = "draft"
        return True

    def action_post_timesheets(self):
        """Turn the manpower lines into timesheet entries, once.

        Not automatic on submission: labour cost reaching the ledger because
        somebody filled in a site report would put the site in charge of the
        accounts. It is a deliberate act by whoever owns the cost."""
        # Stated here rather than left to the analytic line's own ACL. The ACL
        # does stop it, but with "you have found some very confidential
        # records" — which tells an engineer nothing about why, and reads as a
        # fault rather than as the design.
        if not (self.env.user.has_group("project.group_project_manager")
                or self.env.user.has_group("account.group_account_manager")):
            raise UserError(_(
                "Posting labour to the ledger belongs to whoever owns the "
                "cost. File the report; the office turns the hours into cost."))
        for report in self:
            if report.timesheets_posted:
                raise UserError(_("Already posted for %s.", report.name))
            if report.state == "draft":
                raise UserError(_("Submit the report first."))
            if not report.project_id.allow_timesheets:
                raise UserError(_(
                    "%s does not take timesheets, so there is nowhere for "
                    "these hours to go.", report.project_id.name))
            lines = []
            for row in report.manpower_ids:
                if not row.hours or not row.headcount:
                    continue
                # hr_timesheet will not take a line with nobody on it. When
                # no charge hand is named the hours belong to whoever filed
                # the report — which is true, and is also the only answer
                # available that is not invented.
                employee = row.employee_id or self.env["hr.employee"].sudo().search(
                    [("user_id", "=", report.author_id.id)], limit=1)
                if not employee:
                    raise UserError(_(
                        "%(trade)s has no charge hand named and %(user)s is "
                        "not linked to an employee record, so there is nobody "
                        "to book the hours to.",
                        trade=row.trade_id.display_name,
                        user=report.author_id.display_name))
                lines.append({
                    "name": _("%(trade)s — %(report)s",
                              trade=row.trade_id.display_name,
                              report=report.name),
                    "date": report.date,
                    "project_id": report.project_id.id,
                    "unit_amount": row.headcount * row.hours,
                    "employee_id": employee.id,
                    "mizan_site_report_id": report.id,
                })
            if not lines:
                raise UserError(_("There are no hours on this report."))
            self.env["account.analytic.line"].create(lines)
            report.timesheets_posted = True
        return True

    # --------------------------------------------------------- next action
    def _mizan_next_action(self):
        self.ensure_one()
        base = {
            "steps": [("draft", _("Drafted")), ("submitted", _("Submitted")),
                      ("acknowledged", _("Read by the office"))],
            "current": self.state,
        }
        if self.state == "draft":
            return dict(base, label=_("Submit"), method="action_submit",
                        hint=_("Sends it to the office. It stays editable by "
                               "nobody afterwards."))
        if self.state == "submitted":
            return dict(base, label=_("Acknowledge"),
                        method="action_acknowledge",
                        hint=_("Tells the site the office has read it."))
        return base


class MizanSiteManpower(models.Model):
    _name = "mizan.site.manpower"
    _description = "Manpower on Site"
    _order = "report_id, id"

    report_id = fields.Many2one("mizan.site.report", required=True,
                                ondelete="cascade", index=True)
    trade_id = fields.Many2one("hr.job", string="Trade", required=True,
                               help="Mason, steel fixer, carpenter, helper.")
    employee_id = fields.Many2one(
        "hr.employee", string="Charge hand",
        help="Optional. Naming somebody makes the hours chargeable to a real "
             "person on the timesheet.")
    headcount = fields.Integer(string="Men", required=True, default=1)
    hours = fields.Float(string="Hours each", default=8.0)
    subcontractor_id = fields.Many2one(
        "res.partner", string="Subcontractor",
        help="Leave empty for own labour. A subcontractor's men are counted "
             "here but their cost arrives on his account, not the payroll.")


class MizanSitePlant(models.Model):
    _name = "mizan.site.plant"
    _description = "Plant on Site"
    _order = "report_id, id"

    report_id = fields.Many2one("mizan.site.report", required=True,
                                ondelete="cascade", index=True)
    plant_id = fields.Many2one("mizan.plant", string="Plant")
    name = fields.Char(string="Description",
                       help="For hired plant that is not on the register.")
    hours = fields.Float(string="Hours worked")
    idle_hours = fields.Float(
        string="Hours standing",
        help="Plant paid for and not working. It is the figure a hire "
             "decision is later reviewed against.")
    hired = fields.Boolean(string="Hired in")


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    mizan_site_report_id = fields.Many2one(
        "mizan.site.report", string="From Site Report", readonly=True,
        index=True, ondelete="set null")
