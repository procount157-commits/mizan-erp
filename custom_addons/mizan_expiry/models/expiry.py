# -*- coding: utf-8 -*-
"""The register of everything that expires.

One row per document: what it is, whose it is, when it lapses, who renews it.
The status and the days left are refreshed every night (they change with the
calendar, not with an edit), and the warnings go out as the date comes
closer: once at the kind's notice period, once a week before, once on the
day it lapses. Each warning goes out once per stage; renewing the document
starts it again."""
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

KINDS = [
    ("trade_licence", "Trade licence"),
    ("licence", "Licence or permit"),
    ("insurance", "Insurance policy"),
    ("vehicle", "Vehicle registration"),
    ("plant", "Plant inspection or registration"),
    ("visa", "Residence visa"),
    ("eid", "Emirates ID"),
    ("passport", "Passport"),
    ("labour_card", "Labour card"),
    ("medical", "Medical insurance"),
    ("sub_insurance", "Subcontractor insurance"),
    ("other", "Other"),
]
# Days of notice before the date, by kind: a licence takes weeks of paperwork,
# a passport months through an embassy, a visa a few weeks.
NOTICE = {"trade_licence": 60, "licence": 60, "insurance": 45, "passport": 90, "plant": 30,
          "vehicle": 30, "visa": 30, "eid": 30, "labour_card": 30, "medical": 30, "sub_insurance": 30, "other": 30}
STAGES = ["none", "notice", "week", "expired"]


def users_lang(env):
    """The language most people in the office use: what a night job writes
    in, since it runs as nobody in particular."""
    langs = env["res.users"].sudo().search([("share", "=", False), ("active", "=", True)]).mapped("lang")
    return max(set(langs), key=langs.count) if langs else env.user.lang


class MizanExpiryDocument(models.Model):
    _name = "mizan.expiry.document"
    _description = "Document that expires"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiry_date, id"

    name = fields.Char(required=True, tracking=True,
                       help="As the people who renew it call it: Trade licence, CAR policy, Ahmed's visa.")
    kind = fields.Selection(KINDS, required=True, default="other", tracking=True)
    reference = fields.Char(string="Number", help="Licence, policy, plate, visa or ID number.")
    issuer = fields.Char(string="Issued by", help="DED, Civil Defence, the insurer, the RTA…")
    issue_date = fields.Date(tracking=True)
    expiry_date = fields.Date(required=True, tracking=True)
    notice_days = fields.Integer(string="Warn days before", default=30,
                                 help="The first warning goes out this many days before the date.")
    responsible_id = fields.Many2one("res.users", string="Renewed by", default=lambda self: self.env.user,
                                     tracking=True, domain=[("share", "=", False)])
    employee_id = fields.Many2one("hr.employee", string="Employee", index=True)
    partner_id = fields.Many2one("res.partner", string="Subcontractor / company")
    plant_id = fields.Many2one("mizan.plant", string="Plant or vehicle")
    contract_id = fields.Many2one("mizan.contract", string="Project")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    renewal_cost = fields.Monetary(string="Last renewal cost")
    attachment = fields.Binary(string="Copy of the document", attachment=True)
    attachment_name = fields.Char()
    note = fields.Text()
    active = fields.Boolean(default=True)

    days_left = fields.Integer(readonly=True, help="Refreshed every night.")
    state = fields.Selection([("valid", "Valid"), ("soon", "Expires soon"), ("expired", "Expired")],
                             readonly=True, default="valid", index=True)
    alert_stage = fields.Selection([(s, s) for s in STAGES], default="none", readonly=True, copy=False)

    # Rows kept in step with another record (the employee's visa, the
    # subcontract's insurance) say where they come from; their date is edited
    # there, and a renewal here writes it back.
    source_model = fields.Char(readonly=True, copy=False)
    source_id = fields.Integer(readonly=True, copy=False)
    source_field = fields.Char(readonly=True, copy=False)

    _sql_constraints = [
        ("source_uniq", "unique(source_model, source_id, source_field)", "This record already has its expiry row."),
    ]

    # ------------------------------------------------------------ status
    @api.onchange("kind")
    def _onchange_kind(self):
        self.notice_days = NOTICE.get(self.kind, 30)

    def _refresh_status(self):
        today = fields.Date.context_today(self)
        for doc in self:
            days = (doc.expiry_date - today).days if doc.expiry_date else 0
            state = "expired" if days < 0 else "soon" if days <= (doc.notice_days or 30) else "valid"
            if doc.days_left != days or doc.state != state:
                doc.write({"days_left": days, "state": state})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("notice_days") and vals.get("kind"):
                vals["notice_days"] = NOTICE.get(vals["kind"], 30)
        docs = super().create(vals_list)
        docs._refresh_status()
        return docs

    def write(self, vals):
        res = super().write(vals)
        if "expiry_date" in vals or "notice_days" in vals:
            if "expiry_date" in vals and "alert_stage" not in vals:
                # A new date is a new countdown.
                super().write({"alert_stage": "none"})
            self._refresh_status()
        return res

    # ------------------------------------------------------------ warnings
    def _stage_due(self):
        self.ensure_one()
        if self.days_left < 0:
            return "expired"
        if self.days_left <= 7:
            return "week"
        if self.days_left <= (self.notice_days or 30):
            return "notice"
        return "none"

    @api.model
    def _managers(self):
        users = self.env["res.users"]
        for xmlid in ("mizan_owner.group_owner", "mizan_hub.group_general_manager"):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                users |= group.users.filtered(lambda u: u.active and not u.share)
        if "mizan_app_role" in users._fields:
            users |= users.sudo().search([("mizan_app_role", "=", "manager"), ("share", "=", False)])
        return users

    def _warn(self, stage):
        self.ensure_one()
        who = self.employee_id.name or self.partner_id.name or self.plant_id.display_name or ""
        what = "%s%s" % (self.name, (" — %s" % who) if who and who not in self.name else "")
        if stage == "expired":
            subject = _("Expired: %s", what)
            body = _("%(what)s expired on %(date)s. Renew it now.", what=what,
                     date=self.expiry_date.strftime("%d/%m/%Y"))
        else:
            subject = _("Expires in %(d)s day(s): %(what)s", d=self.days_left, what=what)
            body = _("%(what)s expires on %(date)s (%(d)s day(s) left). %(who)s renews it.", what=what,
                     date=self.expiry_date.strftime("%d/%m/%Y"), d=self.days_left,
                     who=self.responsible_id.name or _("Nobody"))
        partners = (self.responsible_id | self._managers()).partner_id
        if partners:
            self.message_notify(partner_ids=partners.ids, subject=subject, body=body,
                                author_id=self.env.ref("base.partner_root").id,
                                email_layout_xmlid="mail.mail_notification_light")
        if stage == "notice" and self.responsible_id:
            self.activity_schedule("mail.mail_activity_data_todo", date_deadline=self.expiry_date,
                                   user_id=self.responsible_id.id, summary=_("Renew %s", what))

    @api.model
    def _cron_daily(self):
        self = self.with_context(lang=users_lang(self.env))
        self._sync_sources()
        docs = self.search([])
        docs._refresh_status()
        for doc in docs:
            due = doc._stage_due()
            if due != "none" and STAGES.index(due) > STAGES.index(doc.alert_stage or "none"):
                doc._warn(due)
                doc.alert_stage = due

    @api.model
    def _sync_sources(self):
        """Overridden in sources.py: rows kept in step with other records."""
        return True

    # ------------------------------------------------------------ renewal
    def action_renew(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Renew %s", self.name),
            "res_model": "mizan.expiry.renew", "view_mode": "form", "target": "new",
            "context": {"default_document_id": self.id},
        }

    def _write_back(self, date):
        """A synced row's date belongs to its source; write it there."""
        self.ensure_one()
        if self.source_model and self.source_id and self.source_field:
            record = self.env[self.source_model].sudo().browse(self.source_id).exists()
            if record:
                record.write({self.source_field: date})


class MizanExpiryRenew(models.TransientModel):
    _name = "mizan.expiry.renew"
    _description = "Renew a document"

    document_id = fields.Many2one("mizan.expiry.document", required=True)
    issue_date = fields.Date(string="New issue date", default=fields.Date.context_today, required=True)
    expiry_date = fields.Date(string="New expiry date", required=True,
                              default=lambda self: fields.Date.context_today(self) + relativedelta(years=1))
    reference = fields.Char(string="New number", help="Leave empty if the number did not change.")
    cost = fields.Float(string="Renewal cost")
    attachment = fields.Binary(string="Copy of the renewed document")
    attachment_name = fields.Char()

    def action_confirm(self):
        self.ensure_one()
        doc = self.document_id
        if self.expiry_date <= self.issue_date:
            raise UserError(_("The new expiry date must come after the issue date."))
        old = doc.expiry_date
        values = {"issue_date": self.issue_date, "expiry_date": self.expiry_date}
        if self.reference:
            values["reference"] = self.reference
        if self.cost:
            values["renewal_cost"] = self.cost
        if self.attachment:
            values.update(attachment=self.attachment, attachment_name=self.attachment_name)
        doc.write(values)
        doc._write_back(self.expiry_date)
        doc.activity_ids.filtered(lambda a: a.activity_type_id == self.env.ref("mail.mail_activity_data_todo")) \
            .action_feedback(feedback=_("Renewed until %s", self.expiry_date.strftime("%d/%m/%Y")))
        doc.message_post(body=_("Renewed by %(who)s: %(old)s → %(new)s%(cost)s.", who=self.env.user.name,
                                old=old.strftime("%d/%m/%Y") if old else "-",
                                new=self.expiry_date.strftime("%d/%m/%Y"),
                                cost=(_(", cost %s", "{:,.2f}".format(self.cost)) if self.cost else "")))
        return {"type": "ir.actions.act_window_close"}
