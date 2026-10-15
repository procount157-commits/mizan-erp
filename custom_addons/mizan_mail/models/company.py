# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_auto_send_invoice = fields.Boolean(
        string="Email invoices when confirmed",
        help="A customer invoice is emailed to the customer the moment it is "
             "confirmed, if the customer has an email address.")
    mizan_reminder_enabled = fields.Boolean(
        string="Send payment reminders by themselves",
        help="Every day, overdue invoices get a reminder by email, on the "
             "schedule below.")
    mizan_reminder_first_days = fields.Integer(
        string="First reminder after (days overdue)", default=3)
    mizan_reminder_every_days = fields.Integer(
        string="Then every (days)", default=7)
    mizan_reminder_max = fields.Integer(
        string="Stop after (reminders)", default=3,
        help="After this many reminders the invoice is left to a person: "
             "a fourth automatic email rarely gets paid and often annoys.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_auto_send_invoice = fields.Boolean(
        related="company_id.mizan_auto_send_invoice", readonly=False)
    mizan_reminder_enabled = fields.Boolean(
        related="company_id.mizan_reminder_enabled", readonly=False)
    mizan_reminder_first_days = fields.Integer(
        related="company_id.mizan_reminder_first_days", readonly=False)
    mizan_reminder_every_days = fields.Integer(
        related="company_id.mizan_reminder_every_days", readonly=False)
    mizan_reminder_max = fields.Integer(
        related="company_id.mizan_reminder_max", readonly=False)
    mizan_mail_server_ok = fields.Boolean(compute="_compute_mizan_mail_status")
    mizan_mail_server_label = fields.Char(compute="_compute_mizan_mail_status")

    def _compute_mizan_mail_status(self):
        server = self.env["ir.mail_server"].sudo().search([], order="sequence", limit=1)
        for settings in self:
            settings.mizan_mail_server_ok = bool(server)
            settings.mizan_mail_server_label = server.smtp_user or server.name or ""

    def action_mizan_mail_setup(self):
        return self.env["mizan.mail.setup"].action_open()
