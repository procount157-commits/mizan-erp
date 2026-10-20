# -*- coding: utf-8 -*-
"""Each person hears about what concerns them, on the phone.

The manager: a supplier bill or a subcontractor payment that waits for him,
and a receipt nobody else is set to approve. The engineer: his receipt was
approved. Odoo already tells the approver of a submitted receipt (an
activity) and the employee of a refusal (a message); these fill the gaps.

Everything goes through message_notify after the transaction commits, so
the inbox, the browser and the phone (Firebase / APNs) get it by the same
road, and a rolled-back action never buzzes anybody."""
import logging

from odoo import SUPERUSER_ID, _, api, models

_logger = logging.getLogger(__name__)


def _managers(env):
    """The people who approve: app role manager, or owner / general manager
    when nobody chose roles."""
    Users = env["res.users"].sudo()
    chosen = Users.search([("mizan_app_role", "=", "manager"), ("share", "=", False)])
    groups = [env.ref(x, raise_if_not_found=False) for x in
              ("mizan_owner.group_owner", "mizan_hub.group_general_manager")]
    auto = Users.browse()
    for group in groups:
        if group:
            auto |= group.sudo().users.filtered(
                lambda u: u.active and not u.share and u.mizan_app_role in (False, "auto", "manager"))
    return (chosen | auto).partner_id


def tell(record, partners, subject, body):
    """Queue a notification about ``record`` to ``partners`` after commit;
    nobody is told what they did themselves."""
    env = record.env
    partners = partners - env.user.partner_id
    if not partners or not record:
        return
    model, res_id, partner_ids, dbname = record._name, record.id, partners.ids, env.cr.dbname

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
        except Exception:  # a notification never breaks the action behind it
            _logger.exception("Phone notification failed (%s %s)", model, res_id)


def _amount(value):
    return "{:,.2f}".format(value or 0.0)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        waiting_before = {m.id for m in self if m.mizan_approval_state == "to_approve"}
        posted = super()._post(soft=soft)
        managers = _managers(self.env)
        for move in posted.filtered(lambda m: m.mizan_approval_state == "to_approve" and m.id not in waiting_before):
            tell(move, managers, _("A supplier bill waits for your approval"),
                 _("%(who)s — %(name)s for %(amount)s. It cannot be paid until you approve it.",
                   who=move.partner_id.name or "", name=move.name, amount=_amount(move.amount_total)))
        return posted


class MizanPaymentRequest(models.Model):
    _inherit = "mizan.payment.request"

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        managers = _managers(self.env)
        for req in requests:
            tell(req, managers, _("A subcontractor payment waits for your approval"),
                 _("%(who)s asks to pay %(partner)s %(amount)s (%(contract)s).",
                   who=req.requested_by_id.name or "", partner=req.partner_id.name or "",
                   amount=_amount(req.amount), contract=req.contract_id.name or ""))
        return requests


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    def _do_submit(self):
        res = super()._do_submit()
        # Odoo gives the approval to the employee's expense manager; with
        # none set it falls back to the employee himself — then the managers
        # must hear of it, or the receipt waits for ever.
        for sheet in self:
            responsible = sheet.sudo()._get_responsible_for_approval() - sheet.employee_id.user_id
            if not responsible:
                tell(sheet, _managers(self.env), _("A receipt waits for your approval"),
                     _("%(who)s sent %(name)s for %(amount)s.", who=sheet.employee_id.name,
                       name=sheet.name, amount=_amount(sheet.total_amount)))
        return res

    def _do_approve(self):
        waiting = self.filtered(lambda s: s.state in ("submit", "draft"))
        res = super()._do_approve()
        for sheet in waiting.filtered(lambda s: s.state in ("approve", "post", "done")):
            partner = sheet.employee_id.sudo().user_id.partner_id
            if partner:
                tell(sheet, partner, _("Your receipt is approved"),
                     _("%(name)s for %(amount)s was approved by %(by)s.", name=sheet.name,
                       amount=_amount(sheet.total_amount), by=self.env.user.name))
        return res
