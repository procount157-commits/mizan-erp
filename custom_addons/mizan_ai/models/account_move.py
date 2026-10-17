# -*- coding: utf-8 -*-
"""Read a supplier invoice into a draft bill.

The model reads; the system checks. Every figure the model returns is tested
against the others — lines against the subtotal, VAT against its rate, the
total against both — and against the books (a supplier invoice number already
entered). What passed and what did not is written on the bill, and the bill
stays a draft for an accountant to confirm."""
import base64
import io
import json
import re

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError

PROMPT = """You read supplier invoices for a UAE accounting system.
Return ONLY one JSON object, no prose, with these keys:
{"vendor_name": str, "vendor_trn": str or null, "invoice_number": str or null,
 "invoice_date": "YYYY-MM-DD" or null, "due_date": "YYYY-MM-DD" or null,
 "currency": "AED" or other ISO code,
 "lines": [{"description": str, "quantity": number, "unit_price": number,
            "vat_rate": number (percent, e.g. 5 or 0), "amount": number (before VAT)}],
 "subtotal": number (before VAT), "vat_amount": number, "total": number (with VAT)}
Copy numbers exactly as printed, without thousands separators. Never invent a
value: use null when it is not on the document. Dates as printed, converted to
YYYY-MM-DD (UAE invoices write day/month/year)."""

TOLERANCE = 0.05


def _num(value):
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    try:
        return float(text) if text not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def _date(value):
    try:
        return fields.Date.to_date(value) if value else False
    except (ValueError, TypeError):
        return False


def _fmt(value):
    return "{:,.2f}".format(value)


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_ai_data = fields.Text(string="What the AI read", readonly=True, copy=False)
    mizan_ai_checked = fields.Boolean(string="Read by AI", readonly=True, copy=False)

    # ----------------------------------------------------------- the document
    def _mizan_ai_document(self):
        self.ensure_one()
        attachment = self.message_main_attachment_id
        if not attachment:
            attachment = self.env["ir.attachment"].search(
                [("res_model", "=", "account.move"), ("res_id", "=", self.id),
                 ("res_field", "=", False)], order="id desc", limit=1)
        if not attachment:
            raise UserError(_("Attach the supplier's invoice (PDF or photo) to the bill first."))
        return attachment

    def _mizan_ai_content(self, attachment):
        """The message for the model: the PDF's own text when it has one
        (exact and cheap), the file itself when it is a scan or a photo."""
        data = base64.b64decode(attachment.datas or b"")
        mimetype = attachment.mimetype or ""
        parts = [{"type": "text", "text": PROMPT}]
        if mimetype == "application/pdf" or data[:5] == b"%PDF-":
            text = ""
            try:
                from pdfminer.high_level import extract_text
                text = extract_text(io.BytesIO(data), maxpages=4) or ""
            except Exception:  # noqa: BLE001 - a scan has no text; the file goes instead
                text = ""
            if len(text.strip()) > 80:
                parts.append({"type": "text", "text": "Invoice text:\n" + text[:20000]})
            else:
                parts.append({"type": "file", "file": {
                    "filename": attachment.name or "invoice.pdf",
                    "file_data": "data:application/pdf;base64," + base64.b64encode(data).decode()}})
        elif mimetype.startswith("image/"):
            parts.append({"type": "image_url", "image_url": {
                "url": "data:%s;base64,%s" % (mimetype, base64.b64encode(data).decode())}})
        else:
            raise UserError(_("The attachment is %s; attach a PDF or a photo of the invoice.",
                              mimetype or "unknown"))
        return [{"role": "user", "content": parts}]

    # ------------------------------------------------------------- the action
    def action_mizan_ai_read(self):
        for move in self:
            if move.move_type not in ("in_invoice", "in_refund"):
                raise UserError(_("AI reading is for supplier bills."))
            if move.state != "draft":
                raise UserError(_("Reset %s to draft before reading it again.", move.display_name))
            attachment = move._mizan_ai_document()
            reply = self.env["mizan.ai"]._chat(move._mizan_ai_content(attachment), json_mode=True)
            move._mizan_ai_fill(self.env["mizan.ai"]._json(reply))
        return True

    def _mizan_ai_fill(self, data):
        self.ensure_one()
        notes = []
        partner = self._mizan_ai_partner(data, notes)
        values = {"mizan_ai_data": json.dumps(data, ensure_ascii=False, indent=1),
                  "mizan_ai_checked": True}
        if partner:
            values["partner_id"] = partner.id
        if data.get("invoice_number"):
            values["ref"] = str(data["invoice_number"])[:64]
        if _date(data.get("invoice_date")):
            values["invoice_date"] = _date(data["invoice_date"])
        if _date(data.get("due_date")):
            values["invoice_date_due"] = _date(data["due_date"])
        currency = self.env["res.currency"].search(
            [("name", "=", (data.get("currency") or "").upper())], limit=1)
        if currency:
            values["currency_id"] = currency.id
        account = self._mizan_ai_account(partner)
        lines = [(5, 0, 0)]
        for line in data.get("lines") or []:
            qty = _num(line.get("quantity")) or 1.0
            price = _num(line.get("unit_price")) or (_num(line.get("amount")) / qty)
            vals = {"name": (line.get("description") or "-")[:500], "quantity": qty,
                    "price_unit": price,
                    "tax_ids": [(6, 0, self._mizan_ai_tax(line.get("vat_rate"), data).ids)]}
            if account:
                vals["account_id"] = account.id
            lines.append((0, 0, vals))
        if len(lines) > 1:
            values["invoice_line_ids"] = lines
        self.write(values)
        return self._mizan_ai_check(data, notes)

    def _mizan_ai_partner(self, data, notes):
        Partner = self.env["res.partner"]
        trn = re.sub(r"\D", "", str(data.get("vendor_trn") or ""))
        partner = Partner.browse()
        if trn:
            partner = Partner.search([("vat", "ilike", trn)], limit=1)
        if not partner and data.get("vendor_name"):
            partner = Partner.search([("name", "ilike", str(data["vendor_name"]).strip())], limit=1)
        if not partner:
            notes.append(("bad", _("Supplier not found: %(name)s, TRN %(trn)s. Choose or create the supplier.",
                                   name=data.get("vendor_name") or "?", trn=trn or "-")))
        return partner

    def _mizan_ai_account(self, partner):
        """The expense account this supplier's bills usually go to."""
        Account = self.env["account.account"]
        if not partner:
            return Account
        previous = self.env["account.move.line"].search([
            ("partner_id", "=", partner.id), ("move_id.move_type", "=", "in_invoice"),
            ("move_id.state", "=", "posted"), ("display_type", "=", "product")],
            order="id desc", limit=20)
        counts = {}
        for line in previous:
            counts[line.account_id] = counts.get(line.account_id, 0) + 1
        return max(counts, key=counts.get) if counts else Account

    def _mizan_ai_tax(self, rate, data):
        if rate in (None, ""):
            rate = 5.0 if _num(data.get("vat_amount")) else 0.0
        rate = _num(rate)
        taxes = self.env["account.tax"].search([
            ("type_tax_use", "=", "purchase"), ("amount_type", "=", "percent"),
            ("company_id", "=", self.company_id.id)])
        return taxes.filtered(lambda t: abs(t.amount - rate) < 0.001)[:1]

    # ------------------------------------------------------------- the checks
    def _mizan_ai_check(self, data, notes):
        """Arithmetic, done by the system, on what the model read."""
        lines = data.get("lines") or []
        line_sum = sum(_num(l.get("amount")) or (_num(l.get("quantity")) or 1.0) * _num(l.get("unit_price"))
                       for l in lines)
        subtotal, vat, total = _num(data.get("subtotal")), _num(data.get("vat_amount")), _num(data.get("total"))

        def same(a, b):
            return abs(a - b) <= max(TOLERANCE, abs(b) * 0.0005)

        if subtotal:
            notes.append(("good" if same(line_sum, subtotal) else "bad",
                          _("Lines add up to %(a)s; the invoice's subtotal is %(b)s.",
                            a=_fmt(line_sum), b=_fmt(subtotal))))
        if subtotal and total:
            notes.append(("good" if same(subtotal + vat, total) else "bad",
                          _("Subtotal %(s)s + VAT %(v)s = %(t)s; the invoice says %(i)s.",
                            s=_fmt(subtotal), v=_fmt(vat), t=_fmt(subtotal + vat), i=_fmt(total))))
        rates = {_num(l.get("vat_rate")) for l in lines if l.get("vat_rate") not in (None, "")}
        if subtotal and vat and rates == {5.0}:
            notes.append(("good" if same(round(subtotal * 0.05, 2), vat) else "bad",
                          _("5%% of %(s)s is %(e)s; the invoice shows VAT %(v)s.",
                            s=_fmt(subtotal), e=_fmt(subtotal * 0.05), v=_fmt(vat))))
        if total:
            notes.append(("good" if same(self.amount_total, total) else "bad",
                          _("The draft bill totals %(m)s; the invoice says %(i)s.",
                            m=_fmt(self.amount_total), i=_fmt(total))))
        trn = re.sub(r"\D", "", str(data.get("vendor_trn") or ""))
        if trn:
            notes.append(("good" if len(trn) == 15 else "bad",
                          _("Supplier TRN %(trn)s has %(n)s digits (a UAE TRN has 15).", trn=trn, n=len(trn))))
        if self.partner_id and self.ref:
            twin = self.search([("id", "!=", self.id), ("move_type", "=", self.move_type),
                                ("partner_id", "=", self.partner_id.id), ("ref", "=", self.ref),
                                ("state", "!=", "cancel")], limit=1)
            if twin:
                notes.append(("bad", _("Invoice %(ref)s from this supplier is already entered as %(twin)s.",
                                       ref=self.ref, twin=twin.display_name)))
        if not lines:
            notes.append(("bad", _("No invoice lines were read. Enter them by hand.")))
        bad = sum(1 for tone, _text in notes if tone == "bad")
        head = (_("Read by AI. All checks passed — review and confirm.") if not bad else
                _("Read by AI. %s check(s) need attention before confirming.", bad))
        icon = {"good": "✅", "bad": "⚠️"}
        body = Markup("<p><b>%s</b></p><ul>%s</ul>") % (
            head, Markup("").join(Markup("<li>%s %s</li>") % (icon[t], escape(text)) for t, text in notes))
        self.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note")
        return bad
