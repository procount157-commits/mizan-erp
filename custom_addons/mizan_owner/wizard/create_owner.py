# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanOwnerCreate(models.TransientModel):
    """An owner account in one step: read-only on the books, the owner page as
    the first screen, notifications on. The password is then set by the
    administrator in Odoo's own Change Password screen, which opens next."""
    _name = "mizan.owner.create"
    _description = "Create the owner's account"

    name = fields.Char(string="Owner's name", required=True)
    login = fields.Char(string="Email (used to sign in)", required=True)
    mobile = fields.Char(string="Mobile")

    def action_create(self):
        self.ensure_one()
        login = (self.login or "").strip().lower()
        if "@" not in login:
            raise UserError(_("Type the owner's email address; it is the sign-in name."))
        Users = self.env["res.users"].sudo()
        user = Users.with_context(active_test=False).search([("login", "=", login)], limit=1)
        groups = [(4, self.env.ref("base.group_user").id), (4, self.env.ref("mizan_owner.group_owner").id)]
        home = self.env.ref("mizan_owner.action_owner_page")
        values = {"name": self.name, "login": login, "email": login, "groups_id": groups,
                  "action_id": home.id, "notification_type": "inbox", "lang": self.env.user.lang,
                  "tz": self.env.user.tz or "Asia/Dubai", "active": True}
        if user:
            user.write(values)
        else:
            user = Users.create(values)
        if self.mobile:
            user.partner_id.mobile = self.mobile
        return {
            "type": "ir.actions.act_window", "name": _("Set the owner's password"),
            "res_model": "change.password.wizard", "view_mode": "form", "target": "new",
            "context": {"active_model": "res.users", "active_ids": user.ids, "active_id": user.id},
        }
