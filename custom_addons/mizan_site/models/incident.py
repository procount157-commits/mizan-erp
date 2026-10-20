# -*- coding: utf-8 -*-
"""A safety incident, raised from the site the moment it happens.

A fall, a cut hand, a near miss under a crane, a small fire: the contractor
must record each one, the consultant asks for the log, and a lost-time injury
has to reach the office the same hour, not at the weekly meeting. The engineer
raises it from his phone with a photograph; the project's manager and the
managers are told at once; the office investigates and closes it with the
cause and what was changed so it does not happen again.

The count that matters on a site board — days since the last lost-time
injury — is worked out from the register, not kept by hand."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

SERIOUS = ("medical", "lost_time", "fire")


class MizanSiteIncident(models.Model):
    _name = "mizan.site.incident"
    _description = "Safety Incident"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(readonly=True, copy=False, default=lambda s: _("New"))
    date = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)
    project_id = fields.Many2one("project.project", string="Project", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    reporter_id = fields.Many2one("res.users", string="Reported by", required=True, readonly=True,
                                  default=lambda self: self.env.user)
    kind = fields.Selection([
        ("near_miss", "Near miss"), ("first_aid", "First aid"), ("medical", "Medical treatment"),
        ("lost_time", "Lost-time injury"), ("property", "Damage to property or plant"),
        ("environment", "Spill or environmental"), ("fire", "Fire"), ("other", "Other"),
    ], required=True, default="near_miss", tracking=True)
    severity = fields.Selection([("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                                required=True, default="low", tracking=True)
    description = fields.Text(string="What happened", required=True)
    location = fields.Char(string="Where on site", help="Level 3 slab, gate 2, crane base…")
    injured_name = fields.Char(string="Who was hurt")
    injured_employee_id = fields.Many2one("hr.employee", string="Employee hurt")
    immediate_action = fields.Text(string="What was done at once")
    photo = fields.Image(max_width=1920, max_height=1920)
    lost_days = fields.Integer(string="Working days lost")

    state = fields.Selection([("reported", "Reported"), ("investigating", "Investigating"), ("closed", "Closed")],
                             default="reported", required=True, tracking=True)
    root_cause = fields.Text(string="Why it happened")
    corrective_action = fields.Text(string="What was changed so it does not happen again")
    closed_by_id = fields.Many2one("res.users", readonly=True)
    closed_date = fields.Date(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mizan.site.incident") or _("New")
        incidents = super().create(vals_list)
        incidents._mizan_alert()
        return incidents

    # ------------------------------------------------------------ who hears
    def _mizan_people(self):
        self.ensure_one()
        users = self.env["res.users"]
        for xmlid in ("mizan_site.group_site_manager", "mizan_hub.group_general_manager", "mizan_owner.group_owner"):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                users |= group.sudo().users
        if "mizan_app_role" in users._fields:
            # Whoever the administrator made a manager in the phone app.
            users |= users.sudo().search([("mizan_app_role", "=", "manager")])
        users |= self.project_id.sudo().user_id
        return users.filtered(lambda u: u.active and not u.share) - self.env.user

    def _mizan_alert(self):
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        for incident in self:
            people = incident._mizan_people()
            if not people:
                continue
            serious = incident.kind in SERIOUS or incident.severity in ("high", "critical")
            subject = (_("Serious incident: %(kind)s on %(project)s") if serious
                       else _("Safety incident: %(kind)s on %(project)s")) % {
                "kind": kinds.get(incident.kind, ""), "project": incident.project_id.name}
            body = _("%(who)s reported %(name)s: %(what)s", who=incident.reporter_id.name, name=incident.name,
                     what=(incident.description or "")[:300])
            incident.sudo().message_notify(partner_ids=people.partner_id.ids, subject=subject, body=body,
                                           email_layout_xmlid="mail.mail_notification_light")
            manager = incident.project_id.sudo().user_id or people[:1]
            if manager:
                incident.sudo().activity_schedule(
                    "mail.mail_activity_data_todo", user_id=manager.id,
                    date_deadline=fields.Date.context_today(incident),
                    summary=_("Investigate %s", incident.name))

    # ------------------------------------------------------------ workflow
    def action_investigate(self):
        self.write({"state": "investigating"})
        return True

    def action_close(self):
        for incident in self:
            if incident.kind != "near_miss" and not (incident.root_cause and incident.corrective_action):
                raise UserError(_("Write why it happened and what was changed before closing %s.", incident.name))
            incident.write({"state": "closed", "closed_by_id": self.env.user.id,
                            "closed_date": fields.Date.context_today(incident)})
            incident.activity_ids.action_feedback(feedback=_("Closed"))
            if incident.reporter_id.partner_id and incident.reporter_id != self.env.user:
                incident.message_notify(partner_ids=incident.reporter_id.partner_id.ids,
                                        subject=_("Incident closed: %s", incident.name),
                                        body=_("Cause: %(c)s. Changed: %(a)s", c=incident.root_cause or "-",
                                               a=incident.corrective_action or "-"))
        return True

    def action_reopen(self):
        self.write({"state": "investigating", "closed_by_id": False, "closed_date": False})
        return True

    # ------------------------------------------------------------ the board
    @api.model
    def days_without_lost_time(self):
        """Days since the last lost-time injury; None when there has never
        been one (a count from an arbitrary start would be a made-up figure)."""
        last = self.sudo().search([("kind", "=", "lost_time")], order="date desc", limit=1)
        if not last:
            return None
        return (fields.Date.context_today(self) - fields.Datetime.context_timestamp(self, last.date).date()).days
