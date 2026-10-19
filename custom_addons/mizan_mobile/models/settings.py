# -*- coding: utf-8 -*-
from odoo import api, fields, models

PREFIX = "mizan_mobile.apns_"


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_apns_team_id = fields.Char("Apple Team ID", config_parameter=PREFIX + "team_id")
    mizan_apns_key_id = fields.Char("APNs Key ID", config_parameter=PREFIX + "key_id")
    mizan_apns_bundle_id = fields.Char("iPhone App Bundle ID", config_parameter=PREFIX + "bundle_id",
                                       default="ae.miqyas.app")
    mizan_apns_key = fields.Char("APNs Key (.p8 contents)", config_parameter=PREFIX + "key")
    mizan_apns_environment = fields.Selection(
        [("production", "App Store / TestFlight"), ("sandbox", "Development build")],
        string="APNs Environment", config_parameter=PREFIX + "environment",
        default="production")

    # Firebase, for the Android app: the service-account key file, uploaded
    # once, kept server-side, never shown again.
    mizan_fcm_file = fields.Binary("Firebase service-account key (JSON)")
    mizan_fcm_filename = fields.Char()
    mizan_fcm_project = fields.Char(compute="_compute_mizan_fcm_project", string="Firebase project")

    def _compute_mizan_fcm_project(self):
        account = self._mizan_fcm_account()
        for record in self:
            record.mizan_fcm_project = account and account.get("project_id") or False

    def set_values(self):
        super().set_values()
        import base64
        import json
        for record in self:
            if record.mizan_fcm_file and self.env.user.has_group("base.group_system"):
                try:
                    account = json.loads(base64.b64decode(record.mizan_fcm_file))
                except Exception:
                    from odoo.exceptions import UserError
                    raise UserError("The file is not a Firebase service-account key (JSON).") from None
                if not all(account.get(k) for k in ("project_id", "client_email", "private_key")):
                    from odoo.exceptions import UserError
                    raise UserError("The file is not a Firebase service-account key (JSON).")
                self.env["ir.config_parameter"].sudo().set_param("mizan_mobile.fcm_account", json.dumps(account))
                record.mizan_fcm_file = False

    @api.model
    def _mizan_fcm_account(self):
        import json
        raw = self.env["ir.config_parameter"].sudo().get_param("mizan_mobile.fcm_account")
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    @api.model
    def _mizan_apns_config(self):
        params = self.env["ir.config_parameter"].sudo()
        config = {name: params.get_param(PREFIX + name)
                  for name in ("team_id", "key_id", "bundle_id", "key", "environment")}
        if not all(config[name] for name in ("team_id", "key_id", "bundle_id", "key")):
            return None
        return config
