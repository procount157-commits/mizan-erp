# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_reminder_count = fields.Integer(
        string="Reminders sent", readonly=True, copy=False, default=0)
    mizan_last_reminder = fields.Date(
        string="Last reminder", readonly=True, copy=False)
    mizan_is_overdue = fields.Boolean(
        compute="_compute_mizan_is_overdue", search="_search_mizan_is_overdue",
        string="Overdue")

    def _compute_mizan_is_overdue(self):
        today = fields.Date.context_today(self)
        for move in self:
            move.mizan_is_overdue = bool(
                move.move_type == "out_invoice" and move.state == "posted"
                and move.payment_state in ("not_paid", "partial")
                and move.invoice_date_due and move.invoice_date_due < today)

    def _search_mizan_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        overdue = [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
                   ("payment_state", "in", ("not_paid", "partial")),
                   ("invoice_date_due", "<", today)]
        want = (operator == "=" and value) or (operator == "!=" and not value)
        if want:
            return overdue
        return [("id", "not in", self._search(overdue))]

    # ------------------------------------------------------------ templates
    def _get_mail_template(self):
        """Customer invoices go out in the bilingual Miqyas email."""
        if all(move.move_type == "out_invoice" for move in self):
            template = self.env.ref("mizan_mail.mail_template_invoice", raise_if_not_found=False)
            if template:
                return template
        return super()._get_mail_template()

    @api.model
    def _mizan_mail_ready(self):
        return bool(self.env["ir.mail_server"].sudo().search_count([]))

    # ------------------------------------------------------------ reminders
    def action_mizan_send_reminder(self):
        """Email a payment reminder on each selected overdue invoice."""
        moves = self.filtered(lambda m: m.mizan_is_overdue)
        if not moves:
            raise UserError(_("None of the selected invoices is overdue and unpaid."))
        if not self._mizan_mail_ready():
            raise UserError(_(
                "Email is not set up yet. Open Settings → Email and connect the "
                "address invoices are sent from."))
        no_email = moves.filtered(lambda m: not m.partner_id.email)
        if no_email and no_email == moves:
            raise UserError(_(
                "These customers have no email address: %s. Add one on the customer first.",
                ", ".join(no_email.partner_id.mapped("display_name"))))
        sent = (moves - no_email)._mizan_send_reminders()
        message = _("%(n)s reminder(s) sent.", n=len(sent))
        if no_email:
            message += " " + _("Skipped, no email address: %s.",
                               ", ".join(no_email.partner_id.mapped("display_name")))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Payment reminders"), "message": message,
                       "type": "warning" if no_email else "success", "sticky": bool(no_email),
                       "next": {"type": "ir.actions.client", "tag": "soft_reload"}},
        }

    def _mizan_send_reminders(self):
        """Post the reminder on each invoice's chatter and email it, PDF attached.

        The composer in comment mode does exactly what a person pressing Send
        would: renders per invoice, attaches the PDF, notifies the customer
        and keeps a copy in the invoice's history."""
        template = self.env.ref("mizan_mail.mail_template_reminder")
        today = fields.Date.context_today(self)
        sent = self.browse()
        for move in self:
            composer = self.env["mail.compose.message"].with_context(
                default_model="account.move", default_res_ids=move.ids,
                default_template_id=template.id, default_composition_mode="comment",
                mail_notify_force_send=True,
                # The attached PDF is the invoice itself; without this Odoo
                # tries to import it as a new invoice and logs a note saying so.
                no_new_invoice=True,
            ).create({})
            composer._action_send_mail()
            move.sudo().write({"mizan_reminder_count": move.mizan_reminder_count + 1,
                               "mizan_last_reminder": today})
            sent |= move
        return sent

    @api.model
    def _cron_mizan_reminders(self):
        """Daily: remind overdue customers on each company's schedule."""
        if not self._mizan_mail_ready():
            return
        today = fields.Date.context_today(self)
        for company in self.env["res.company"].search([("mizan_reminder_enabled", "=", True)]):
            first = max(company.mizan_reminder_first_days, 0)
            every = max(company.mizan_reminder_every_days, 1)
            candidates = self.search([
                ("company_id", "=", company.id), ("mizan_is_overdue", "=", True),
                ("partner_id.email", "!=", False),
                ("mizan_reminder_count", "<", company.mizan_reminder_max or 3),
                ("invoice_date_due", "<=", today - timedelta(days=first)),
            ])
            due = candidates.filtered(lambda m: not m.mizan_last_reminder
                                      or m.mizan_last_reminder <= today - timedelta(days=every))
            for move in due:
                try:
                    with self.env.cr.savepoint():
                        move.with_company(company)._mizan_send_reminders()
                except Exception:
                    _logger.exception("Payment reminder failed on %s", move.name)

    # ------------------------------------------------------------ auto send
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        to_send = posted.filtered(
            lambda m: m.move_type == "out_invoice" and m.company_id.mizan_auto_send_invoice
            and m.partner_id.email and not m.is_move_sent)
        if to_send and self._mizan_mail_ready():
            # After commit: the invoice is confirmed whatever the mail server
            # says, and a slow server does not hold up the person confirming.
            ids, dbname, uid = to_send.ids, self.env.cr.dbname, self.env.uid
            ctx = dict(self.env.context)

            @self.env.cr.postcommit.add
            def _send():
                from odoo.modules.registry import Registry
                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, uid, ctx)
                    moves = env["account.move"].browse(ids).exists()
                    try:
                        env["account.move.send"]._generate_and_send_invoices(
                            moves, allow_raising=False, sending_methods={"email"})
                    except Exception:
                        _logger.exception("Automatic invoice email failed for %s", ids)
        return posted
