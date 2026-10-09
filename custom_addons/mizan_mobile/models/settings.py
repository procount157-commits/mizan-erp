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

    @api.model
    def _mizan_apns_config(self):
        params = self.env["ir.config_parameter"].sudo()
        config = {name: params.get_param(PREFIX + name)
                  for name in ("team_id", "key_id", "bundle_id", "key", "environment")}
        if not all(config[name] for name in ("team_id", "key_id", "bundle_id", "key")):
            return None
        return config
