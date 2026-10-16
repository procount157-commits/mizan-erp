# -*- coding: utf-8 -*-
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def mizan_switch_lang(self):
        """Arabic to English and back, for the person signed in."""
        user = self.env.user
        target = "en_US" if (user.lang or "").startswith("ar") else "ar_001"
        langs = self.env["res.lang"].get_installed()
        if target not in dict(langs):
            target = next((code for code, _name in langs if code != user.lang), user.lang)
        user.write({"lang": target})
        return target
