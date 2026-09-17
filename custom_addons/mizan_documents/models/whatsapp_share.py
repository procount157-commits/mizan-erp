# -*- coding: utf-8 -*-
from urllib.parse import quote

from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang, format_date


class MizanWhatsappMixin(models.AbstractModel):
    """Send a document to a client over WhatsApp using a click-to-chat link.

    Odoo's WhatsApp integration is Enterprise, and the Business API it relies on
    is a paid, approval-gated service. What is free is wa.me: a link that opens
    WhatsApp with the recipient and the message already filled in, which the
    user then sends themselves.

    That difference matters and is not hidden here — the PDF cannot ride along
    on a wa.me link, so the message carries the figures and the portal link
    instead, and the client views or downloads the document from there.
    """

    _name = "mizan.whatsapp.mixin"
    _description = "WhatsApp Share"

    def _mizan_whatsapp_number(self, partner):
        """Return the partner's number as wa.me expects it: digits only."""
        raw = partner.mobile or partner.phone or ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            raise UserError(_(
                "%s has no mobile or phone number, so there is nobody to open "
                "WhatsApp with. Add one on their contact record.",
                partner.display_name))
        # wa.me only resolves a full international number. A local 05x… has to
        # gain its country code, and the partner often has no country set — so
        # fall back to the company's, which is the right guess for a local
        # client and the only one available.
        if digits.startswith("00"):
            return digits[2:]
        if digits.startswith("0"):
            code = partner.country_id.phone_code or self.company_id.country_id.phone_code
            if not code:
                raise UserError(_(
                    "%s has a local number (%s) but no country, so the "
                    "international dialling code cannot be worked out. Set the "
                    "country on their contact record.",
                    partner.display_name, raw))
            return "%s%s" % (code, digits[1:])
        return digits

    def _mizan_whatsapp_message(self):
        """Each document type supplies its own wording."""
        self.ensure_one()
        return ""

    def action_send_whatsapp(self):
        self.ensure_one()
        partner = self.partner_id
        number = self._mizan_whatsapp_number(partner)
        return {
            "type": "ir.actions.act_url",
            "url": "https://wa.me/%s?text=%s" % (
                number, quote(self._mizan_whatsapp_message())),
            "target": "new",
        }


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mizan.whatsapp.mixin"]

    def _mizan_whatsapp_message(self):
        self.ensure_one()
        amount = formatLang(
            self.env, self.amount_total, currency_obj=self.currency_id)
        lines = [
            _("Dear %s,", self.partner_id.name),
            "",
            _("Invoice %(number)s dated %(date)s for %(amount)s.",
              number=self.name, date=format_date(self.env, self.invoice_date),
              amount=amount),
        ]
        if self.invoice_date_due:
            lines.append(_("Due on %s.", format_date(self.env, self.invoice_date_due)))
        url = self.get_portal_url() if hasattr(self, "get_portal_url") else ""
        if url:
            base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            lines += ["", _("View or download: %s%s", base, url)]
        lines += ["", self.company_id.name]
        return "\n".join(lines)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "mizan.whatsapp.mixin"]

    def _mizan_whatsapp_message(self):
        self.ensure_one()
        amount = formatLang(
            self.env, self.amount_total, currency_obj=self.currency_id)
        lines = [
            _("Dear %s,", self.partner_id.name),
            "",
            _("Quotation %(number)s for %(amount)s.",
              number=self.name, amount=amount),
        ]
        if self.validity_date:
            lines.append(_("Valid until %s.", format_date(self.env, self.validity_date)))
        url = self.get_portal_url() if hasattr(self, "get_portal_url") else ""
        if url:
            base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            lines += ["", _("View or accept: %s%s", base, url)]
        lines += ["", self.company_id.name]
        return "\n".join(lines)


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "mizan.whatsapp.mixin"]

    def _mizan_whatsapp_message(self):
        self.ensure_one()
        amount = formatLang(
            self.env, self.amount, currency_obj=self.currency_id)
        kind = _("Receipt voucher") if self.payment_type == "inbound" \
            else _("Payment voucher")
        return "\n".join([
            _("Dear %s,", self.partner_id.name),
            "",
            _("%(kind)s %(number)s for %(amount)s dated %(date)s.",
              kind=kind, number=self.name, amount=amount,
              date=format_date(self.env, self.date)),
            "",
            self.company_id.name,
        ])
