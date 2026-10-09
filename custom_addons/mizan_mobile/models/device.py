# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MizanNativeDevice(models.Model):
    """A phone that installed the app and allowed notifications."""
    _name = "mizan.native.device"
    _description = "Phone App Device"
    _order = "last_seen desc"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    partner_id = fields.Many2one(related="user_id.partner_id", store=True, index=True)
    platform = fields.Selection([("ios", "iPhone"), ("android", "Android")],
                                required=True, default="ios")
    token = fields.Char(required=True, index=True)
    app_id = fields.Char(string="App")
    last_seen = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [("token_unique", "unique(token)",
                         "This device is already registered.")]

    @api.model
    def _mizan_register(self, token, platform, app_id):
        """Same phone, new login: the token moves to whoever is signed in
        now, so the last person's notifications stop arriving on it."""
        device = self.sudo().search([("token", "=", token)], limit=1)
        values = {"user_id": self.env.uid, "platform": platform,
                  "app_id": app_id, "last_seen": fields.Datetime.now()}
        if device:
            device.write(values)
        else:
            self.sudo().create(dict(values, token=token))
        return True
