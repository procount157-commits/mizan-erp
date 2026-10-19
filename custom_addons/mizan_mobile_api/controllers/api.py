# -*- coding: utf-8 -*-
"""The phone app's door: JSON in, JSON out, an ordinary Odoo session.

Sign-in creates the same session the website uses, so rights, record rules
and logging all apply unchanged; every other route needs that session."""
from odoo import http
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.http import request

METHODS = {
    "me", "counts", "manager_summary", "projects", "alerts", "alerts_read", "approvals", "decide",
    "manager_insights", "my_cash", "submit_receipt", "request_topup", "crew", "save_crew",
}


class MizanMobileApi(http.Controller):

    @http.route("/mizan/api/login", type="json", auth="none", methods=["POST"], csrf=False)
    def login(self, login, password, **kw):
        db = request.db
        if not db:
            return {"ok": False, "error": "no_database"}
        try:
            request.session.authenticate(db, {"login": login, "password": password, "type": "password"})
        except AccessDenied:
            return {"ok": False, "error": "wrong_login"}
        env = request.env(user=request.session.uid)
        return {"ok": True, "me": env["mizan.mobile"].with_context(lang=env.user.lang).me()}

    @http.route("/mizan/api/logout", type="json", auth="user", methods=["POST"], csrf=False)
    def logout(self, **kw):
        request.session.logout(keep_db=True)
        return {"ok": True}

    @http.route("/mizan/api/<string:method>", type="json", auth="user", methods=["POST"], csrf=False)
    def call(self, method, **params):
        if method not in METHODS:
            return {"ok": False, "error": "unknown"}
        mobile = request.env["mizan.mobile"].with_context(lang=request.env.user.lang)
        try:
            return {"ok": True, "data": getattr(mobile, method)(**params)}
        except (UserError, AccessError) as error:
            request.env.cr.rollback()
            return {"ok": False, "error": "refused", "message": str(error.args[0] if error.args else error)}
