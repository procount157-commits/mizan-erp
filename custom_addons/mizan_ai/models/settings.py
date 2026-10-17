# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

from .ai_client import DEFAULT_MODELS, P


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_ai_provider = fields.Selection(
        [("openrouter", "OpenRouter"), ("groq", "Groq"), ("custom", "Other (OpenAI-compatible)")],
        string="AI service", config_parameter=P + "provider", default="openrouter")
    mizan_ai_base_url = fields.Char(string="Service address", config_parameter=P + "base_url",
                                    help="Only for “Other”: the address ending in /v1.")
    mizan_ai_invoice_model = fields.Char(
        string="Model", config_parameter=P + "invoice_model",
        help="The model that reads invoices. It must accept images and files: "
             "on OpenRouter, filter the models by image input. Free models end in :free.")
    # The key is write-only: a new one can be typed, the saved one is never shown.
    mizan_ai_new_key = fields.Char(string="New API key")
    mizan_ai_key_set = fields.Boolean(compute="_compute_mizan_ai_key_set")

    def _compute_mizan_ai_key_set(self):
        has = bool(self.env["ir.config_parameter"].sudo().get_param(P + "api_key"))
        for record in self:
            record.mizan_ai_key_set = has

    @api.onchange("mizan_ai_provider")
    def _onchange_mizan_ai_provider(self):
        if self.mizan_ai_provider in DEFAULT_MODELS:
            self.mizan_ai_invoice_model = DEFAULT_MODELS[self.mizan_ai_provider]

    def set_values(self):
        super().set_values()
        for record in self:
            if record.mizan_ai_new_key and self.env.user.has_group("base.group_system"):
                self.env["ir.config_parameter"].sudo().set_param(P + "api_key", record.mizan_ai_new_key.strip())
                record.mizan_ai_new_key = False

    def action_mizan_ai_test(self):
        self.execute()
        return self.env["mizan.ai"].action_test()

    def action_mizan_ai_forget_key(self):
        self.env["ir.config_parameter"].sudo().set_param(P + "api_key", False)
        return True
