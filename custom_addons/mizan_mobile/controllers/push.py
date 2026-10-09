# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class MizanPush(http.Controller):
    """Called by the iPhone app from inside the signed-in page, so the token
    lands on whoever is logged in — never on a user the app guessed."""

    @http.route("/mizan/push/register", type="json", auth="user", methods=["POST"])
    def register(self, token, platform="ios", app_id=None):
        token = (token or "").strip()
        if not token or len(token) > 400:
            return {"ok": False}
        request.env["mizan.native.device"]._mizan_register(token, platform, app_id)
        return {"ok": True}

    @http.route("/mizan/push/unregister", type="json", auth="user", methods=["POST"])
    def unregister(self, token):
        request.env["mizan.native.device"].sudo().search(
            [("token", "=", token), ("user_id", "=", request.env.uid)]).unlink()
        return {"ok": True}
