# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class MizanAssetLinks(http.Controller):
    """Vouch for the Android app, so it opens full screen.

    The app is a trusted web activity: Chrome shows the system without an
    address bar only if this domain names the app's package and the
    fingerprint of the key it was signed with. Both are public. A server that
    sells the system under another package or key sets the two parameters.
    """

    PACKAGE = "ae.miqyas.app"
    FINGERPRINT = ("18:9E:13:95:1B:33:07:C3:4C:B1:88:83:22:CE:ED:62:C8:45:0B:33:"
                   "B7:AD:2C:D0:44:2A:A0:B2:EC:31:B5:81")

    @http.route("/.well-known/assetlinks.json", type="http", auth="none",
                methods=["GET"], save_session=False)
    def assetlinks(self):
        package, fingerprints = self.PACKAGE, [self.FINGERPRINT]
        if request.db:
            params = request.env["ir.config_parameter"].sudo()
            package = params.get_param("mizan.android_package") or package
            extra = params.get_param("mizan.android_sha256")
            if extra:
                fingerprints = [f.strip() for f in extra.split(",") if f.strip()]
        body = [{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package,
                "sha256_cert_fingerprints": fingerprints,
            },
        }]
        return request.make_response(json.dumps(body), headers=[
            ("Content-Type", "application/json"),
            ("Cache-Control", "public, max-age=3600"),
        ])
