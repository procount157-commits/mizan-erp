# -*- coding: utf-8 -*-
import logging

from odoo import api, models, SUPERUSER_ID

from . import apns

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _notify_thread_by_web_push(self, message, recipients_data, msg_vals=False, **kwargs):
        """Whoever would get a browser notification gets it on the iPhone too.

        Sent after the transaction commits: a message that was rolled back
        must not have buzzed anybody's phone, and Apple's answer must not hold
        up the request that posted it."""
        res = super()._notify_thread_by_web_push(message, recipients_data, msg_vals=msg_vals, **kwargs)
        try:
            self._mizan_native_push(message, recipients_data, msg_vals or {})
        except Exception:  # a notification never breaks the action behind it
            _logger.exception("Could not queue iPhone notifications")
        return res

    def _mizan_native_push(self, message, recipients_data, msg_vals):
        partner_ids = self._extract_partner_ids_for_notifications(message, dict(msg_vals), recipients_data)
        if not partner_ids:
            return
        devices = self.env["mizan.native.device"].sudo().search(
            [("partner_id", "in", partner_ids), ("platform", "=", "ios")])
        if not devices:
            return
        config = self.env["res.config.settings"]._mizan_apns_config()
        if not config:
            return
        payload = self._notify_by_web_push_prepare_payload(message, msg_vals=dict(msg_vals))
        model = payload["options"]["data"].get("model")
        res_id = payload["options"]["data"].get("res_id")
        # Absolute, because one phone can follow several companies: the app
        # opens the address the notification came from, not the last one used.
        url = self.get_base_url() + (("/mail/view?model=%s&res_id=%s" % (model, res_id))
                                     if model and res_id else "/odoo")
        title = payload.get("title") or ""
        body = payload["options"].get("body") or ""  # already plain text
        tokens = devices.mapped("token")
        dbname = self.env.cr.dbname

        def send():
            dead = apns.send(config, tokens, title, body, url)
            if dead:
                from odoo.modules.registry import Registry
                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    env["mizan.native.device"].search([("token", "in", dead)]).unlink()

        self.env.cr.postcommit.add(send)
