# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_owner_alert_amount = fields.Monetary(
        string="Notify the owner from", currency_field="currency_id", default=10000.0,
        help="A deposit, a withdrawal or a supplier bill at or above this "
             "amount sends the owner a notification at once.")
    mizan_owner_notify_invoices = fields.Boolean(
        string="Notify every new sales invoice", default=True)
    mizan_owner_daily_digest = fields.Boolean(string="Evening summary", default=True)
    mizan_owner_weekly_digest = fields.Boolean(string="Sunday summary", default=True)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_owner_alert_amount = fields.Monetary(
        related="company_id.mizan_owner_alert_amount", readonly=False,
        currency_field="currency_id")
    mizan_owner_notify_invoices = fields.Boolean(
        related="company_id.mizan_owner_notify_invoices", readonly=False)
    mizan_owner_daily_digest = fields.Boolean(
        related="company_id.mizan_owner_daily_digest", readonly=False)
    mizan_owner_weekly_digest = fields.Boolean(
        related="company_id.mizan_owner_weekly_digest", readonly=False)

    def action_mizan_create_owner(self):
        return {"type": "ir.actions.act_window", "res_model": "mizan.owner.create",
                "view_mode": "form", "views": [[False, "form"]], "target": "new"}
