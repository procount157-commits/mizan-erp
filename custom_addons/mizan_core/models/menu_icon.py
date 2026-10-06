# -*- coding: utf-8 -*-
"""Keep every app icon attached, so none of them go missing.

Odoo does not serve an app icon from the module's file. At install it reads
the file once, stores the bytes as an ``ir.attachment`` on the menu
(``web_icon_data``), and from then on the web client is handed base64 out of
that attachment -- never the file. ``load_menus`` caches the result per user
and language, and the browser caches the whole menu payload for a year under a
hash of it.

That chain has one weak link. If the attachment is missing or stale at the
moment the payload is built -- which is exactly what happens while a module is
being installed, because the menu exists before its icon is attached -- the
client is handed an app with no icon, and it keeps that answer until the hash
changes again. The symptom is an icon that is broken for some apps and not
others, comes back after an upgrade, and disappears again later.

So the repair is not to fix the attachments once by hand. It is to re-derive
every one of them from its file whenever this module is installed or updated,
which is to say on every deploy, and only write the ones that actually differ
so that a deploy changing nothing leaves the browser cache alone.
"""

import base64
import logging

from odoo import api, models, _

_logger = logging.getLogger(__name__)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _mizan_repair_web_icons(self):
        """Re-attach every app icon from the file its menu names.

        Called from data on install and on update, and from Platform › Repair
        App Icons when somebody is looking at a broken one right now.
        """
        menus = self.sudo().with_context(active_test=False).search(
            [("web_icon", "!=", False)])

        repaired, missing = [], []
        for menu in menus:
            # The other form of web_icon is "icon_class,colour,background",
            # which names no file and needs no attachment.
            if len(menu.web_icon.split(",")) != 2:
                continue

            wanted = menu._read_image(menu.web_icon)
            if not wanted:
                missing.append("%s (%s)" % (menu.display_name, menu.web_icon))
                continue

            # _read_image returns base64 with line breaks every 76 characters
            # and the attachment returns it without them, so the two are
            # compared as the bytes they both decode to rather than as text.
            current = menu.web_icon_data
            if current and base64.b64decode(current) == base64.b64decode(wanted):
                continue

            menu.web_icon_data = wanted
            repaired.append(menu.display_name)

        if repaired:
            # The menu payload is cached per user and language; without this
            # the repair is in the database and not on anybody's screen.
            self.env.registry.clear_cache()
            _logger.info("Re-attached %s app icon(s): %s",
                         len(repaired), ", ".join(repaired))
        if missing:
            # Worth saying out loud: the menu points at a file that is not in
            # the addons path, so this app will show Odoo's default icon.
            _logger.warning("No icon file for %s menu(s): %s",
                            len(missing), ", ".join(missing))
        return {"repaired": repaired, "missing": missing}

    @api.model
    def action_mizan_repair_web_icons(self):
        result = self._mizan_repair_web_icons()
        if result["repaired"]:
            message = _(
                "Re-attached %(count)s icon(s). Reload the page with "
                "Ctrl+Shift+R — the browser keeps the old menu for a year.",
                count=len(result["repaired"]))
            kind = "success"
        elif result["missing"]:
            message = _("Every icon is already attached, but %(count)s menu(s) "
                        "name a file that is not installed.",
                        count=len(result["missing"]))
            kind = "warning"
        else:
            message = _("Every app icon is already attached and current.")
            kind = "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("App Icons"), "message": message,
                       "type": kind, "sticky": False},
        }
