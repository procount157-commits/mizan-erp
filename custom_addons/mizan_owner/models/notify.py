# -*- coding: utf-8 -*-
"""Tell the owner when money moves.

Notifications go through Odoo's own message_notify, so they reach the owner's
inbox, the browser and the Miqyas app (Android web push, iPhone APNs) by the
same road as every other notification. Sent after the transaction commits:
an invoice that was rolled back must not have buzzed anybody's phone."""
import logging

from markupsafe import Markup, escape

from odoo import api, fields, models, SUPERUSER_ID, _

_logger = logging.getLogger(__name__)


def _owners(env):
    group = env.ref("mizan_owner.group_owner", raise_if_not_found=False)
    if not group:
        return env["res.partner"]
    return group.sudo().users.filtered(lambda u: u.active and not u.share).partner_id


def _notify(record, subject, body):
    """Queue a notification to the owners about this record, after commit."""
    env = record.env
    partners = _owners(env) - env.user.partner_id   # nobody is told what they did themselves
    if not partners:
        return
    model, res_id, partner_ids = record._name, record.id, partners.ids
    dbname = env.cr.dbname

    @env.cr.postcommit.add
    def _send():
        from odoo.modules.registry import Registry
        try:
            with Registry(dbname).cursor() as cr:
                new_env = api.Environment(cr, SUPERUSER_ID, {})
                target = new_env[model].browse(res_id).exists()
                if target:
                    target.message_notify(
                        partner_ids=partner_ids, subject=subject, body=body,
                        author_id=new_env.ref("base.partner_root").id,
                        email_layout_xmlid="mail.mail_notification_light")
        except Exception:
            _logger.exception("Owner notification failed (%s %s)", model, res_id)


def _money(env, amount):
    currency = env.company.currency_id
    lang = env.context.get("lang") or env.user.lang or ""
    unit = "د.إ" if (lang.startswith("ar") and currency.name == "AED") else currency.name
    return "%s %s" % ("{:,.2f}".format(amount or 0.0), unit)


def _lines(parts):
    """Lines of plain text joined as HTML, each escaped: a description from a
    bank file must never be able to inject markup into a notification."""
    return Markup("<br/>").join(escape(p) for p in parts)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted:
            company = move.company_id
            if move.move_type == "out_invoice" and company.mizan_owner_notify_invoices:
                _notify(move, _("New invoice: %s", move.partner_id.name),
                        _("Invoice %(n)s to %(p)s for %(a)s.", n=move.name, p=move.partner_id.name,
                          a=_money(self.env, move.amount_total)))
            elif move.move_type == "in_invoice" and move.amount_total >= (company.mizan_owner_alert_amount or 0):
                _notify(move, _("Large supplier bill: %s", move.partner_id.name),
                        _("Bill %(n)s from %(p)s for %(a)s, due %(d)s.", n=move.name or move.ref or "",
                          p=move.partner_id.name, a=_money(self.env, move.amount_total),
                          d=move.invoice_date_due and move.invoice_date_due.strftime("%d/%m/%Y") or "-"))
        return posted


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        res = super().action_post()
        for pay in self.filtered(lambda p: p.payment_type == "inbound" and p.partner_type == "customer"):
            _notify(pay, _("Payment received: %s", _money(self.env, pay.amount)),
                    _("%(p)s paid %(a)s.", p=pay.partner_id.name or "-", a=_money(self.env, pay.amount)))
        return res


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # A statement imports dozens of lines at once: one notification for
        # the large ones, not one per line.
        threshold = self.env.company.mizan_owner_alert_amount or 0
        big = lines.filtered(lambda l: abs(l.amount) >= threshold) if threshold else lines.browse()
        if big:
            ins = big.filtered(lambda l: l.amount > 0)
            outs = big - ins
            parts = []
            for line in (ins | outs)[:6]:
                parts.append("%s %s — %s" % ("⬇" if line.amount > 0 else "⬆",
                                             _money(self.env, abs(line.amount)), (line.payment_ref or "")[:60]))
            subject = (_("Deposit in the bank: %s", _money(self.env, sum(ins.mapped("amount"))))
                       if ins and not outs else
                       _("Withdrawal from the bank: %s", _money(self.env, -sum(outs.mapped("amount"))))
                       if outs and not ins else
                       _("Bank: %(i)s in, %(o)s out", i=_money(self.env, sum(ins.mapped("amount"))),
                         o=_money(self.env, -sum(outs.mapped("amount")))))
            _notify(big[0].move_id, subject, _lines(parts))
        return lines


class MizanCheque(models.Model):
    _inherit = "mizan.cheque"

    def action_bounce(self):
        res = super().action_bounce()
        for cheque in self.filtered(lambda c: c.state == "bounced"):
            _notify(cheque, _("Cheque bounced: %s", _money(self.env, cheque.amount)),
                    _("Cheque %(n)s from %(p)s for %(a)s was returned unpaid.", n=cheque.name or "",
                      p=cheque.partner_id.name or "-", a=_money(self.env, cheque.amount)))
        return res


class MizanOwnerDigest(models.AbstractModel):
    _inherit = "mizan.owner"

    @api.model
    def _cron_digest(self, period="day"):
        """The evening and Sunday summaries, in the owner's language."""
        for company in self.env["res.company"].search([]):
            if (period == "day" and not company.mizan_owner_daily_digest) or \
                    (period == "week" and not company.mizan_owner_weekly_digest):
                continue
            group = self.env.ref("mizan_owner.group_owner")
            owners = group.users.filtered(lambda u: u.active and not u.share and company in u.company_ids)
            for user in owners:
                env = self.with_user(user).with_company(company).with_context(lang=user.lang)
                try:
                    data = env.get_summary()
                except Exception:
                    _logger.exception("Owner summary failed for %s", user.login)
                    continue
                cards = {c["key"]: c for c in data["cards"]}
                title = _("Today at %s", company.name) if period == "day" else _("This week at %s", company.name)
                lines = [data["headline"],
                         "%s: %s" % (cards["cash"]["title"], cards["cash"]["value"]),
                         " · ".join(cards["cash"]["lines"][:2]),
                         "%s: %s (%s)" % (cards["profit"]["title"], cards["profit"]["value"], cards["profit"]["lines"][0]),
                         "%s: %s" % (cards["owed"]["title"], cards["owed"]["value"]),
                         "%s: %s" % (cards["due"]["title"], cards["due"]["value"])]
                user.partner_id.sudo().with_context(lang=user.lang).message_notify(
                    partner_ids=user.partner_id.ids, subject=title,
                    body=_lines(lines),
                    author_id=self.env.ref("base.partner_root").id,
                    email_layout_xmlid="mail.mail_notification_light")
