# -*- coding: utf-8 -*-
from odoo import models, _


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_send_receipt_email(self):
        """Open the mail composer with the voucher PDF already attached.

        Invoices ship with a send-and-print flow; payments do not, even though a
        client who has just paid expects the receipt in their inbox the same
        day. This reuses Odoo's composer so the wording, language and follower
        rules behave exactly as they do elsewhere.
        """
        self.ensure_one()
        template = self.env.ref(
            "mizan_documents.mail_template_payment_receipt", raise_if_not_found=False)
        compose_form = self.env.ref("mail.email_compose_message_wizard_form")
        is_inbound = self.payment_type == "inbound"
        return {
            "type": "ir.actions.act_window",
            "name": _("Send Receipt Voucher") if is_inbound else _("Send Payment Voucher"),
            "res_model": "mail.compose.message",
            "views": [(compose_form.id, "form")],
            "target": "new",
            "context": {
                "default_model": "account.payment",
                "default_res_ids": self.ids,
                "default_template_id": template.id if template else False,
                "default_composition_mode": "comment",
                "default_partner_ids": self.partner_id.ids,
                "mark_payment_as_sent": True,
                "force_email": True,
            },
        }
