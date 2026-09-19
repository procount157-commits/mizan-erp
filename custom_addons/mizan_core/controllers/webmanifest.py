# -*- coding: utf-8 -*-
from odoo import _
from odoo.http import request
from odoo.addons.web.controllers.webmanifest import WebManifest


class MizanWebManifest(WebManifest):
    """Brand the installed phone app.

    Odoo's own manifest names the app "Odoo" in Odoo's purple with Odoo's
    icon, so a client who adds the system to their home screen ends up with a
    competitor's brand sitting on their phone. The name is already a
    configuration parameter; the colours and the icon are not, so they are
    overridden here.
    """

    BRAND_COLOR = "#1A3C6E"

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        params = request.env["ir.config_parameter"].sudo()
        manifest["name"] = params.get_param("web.web_app_name") or _("ProAccount")
        manifest["short_name"] = params.get_param(
            "mizan_core.web_app_short_name") or manifest["name"]
        manifest["background_color"] = self.BRAND_COLOR
        manifest["theme_color"] = self.BRAND_COLOR
        manifest["icons"] = [{
            "src": "/mizan_core/static/img/proaccount-icon-%s.png" % size,
            "sizes": size,
            "type": "image/png",
        } for size in ("192x192", "512x512")]
        return manifest

    def _icon_path(self):
        # Used by the offline page the service worker serves.
        return "mizan_core/static/img/proaccount-icon-192x192.png"
