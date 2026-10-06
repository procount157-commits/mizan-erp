# -*- coding: utf-8 -*-
"""An advance to an employee, from the request to the last dirham back.

The accounting is deliberately ordinary double entry, because the failure this
module exists to prevent is not an accounting one:

    paid        Dr Employee Advances      Cr Bank
    settled     Dr Employee Payable       Cr Employee Advances
    returned    Dr Bank                   Cr Employee Advances

The advance sits in an ASSET account the whole time it is outstanding. Booking
it straight to expense is what makes advances vanish — the cost is recognised
before anything was bought, and nobody is chasing a balance that is no longer
on the balance sheet.

Settlement is measured from the expense claims POSTED against the advance, not
from a figure anyone types. An outstanding balance that a person maintains is
a balance that is wrong by the end of the quarter.

The rule that matters is the refusal: no second advance while the first is
outstanding, unless the person holds the override right, and the override is
recorded on the record itself. Sites run on trust and the accounts have to run
on something else.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MizanEmployeeAdvance(models.Model):
    _name = "mizan.employee.advance"
    _description = "Employee Advance"
    _inherit = ["mail.thread", "mail.activity.mixin",
                "mizan.next.action.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Reference", copy=False, readonly=True,
                       default=lambda self: _("New"))
    employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
    partner_id = fields.Many2one(
        "res.partner", related="employee_id.work_contact_id", store=True,
        string="Employee Contact",
        help="The advance is settled against what the company owes this "
             "person on their expense claims, so both sides must point at the "
             "same partner.")
    department_id = fields.Many2one(
        "hr.department", related="employee_id.department_id", store=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    date = fields.Date(required=True, default=fields.Date.context_today,
                       tracking=True)
    amount = fields.Monetary(required=True, tracking=True)
    purpose = fields.Char(required=True,
                          help="What the money is for. A blank purpose is how "
                               "an advance becomes impossible to settle.")
    project_id = fields.Many2one("project.project", string="Project")
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Cost Center")

    state = fields.Selection(
        [("draft", "Draft"),
         ("submitted", "Submitted"),
         ("approved", "Approved"),
         ("paid", "Paid"),
         ("settled", "Settled"),
         ("cancel", "Cancelled")],
        default="draft", required=True, tracking=True)

    # --- accounting ------------------------------------------------------
    journal_id = fields.Many2one(
        "account.journal", string="Paid From",
        domain="[('type', 'in', ('bank', 'cash'))]",
        default=lambda self: self.env.company.mizan_advance_journal_id)
    move_pay_id = fields.Many2one("account.move", string="Payment Entry",
                                  readonly=True, copy=False)
    move_settle_ids = fields.Many2many(
        "account.move", string="Settlement Entries", readonly=True, copy=False)

    # --- what is left ----------------------------------------------------
    expense_sheet_ids = fields.One2many(
        "hr.expense.sheet", "mizan_advance_id", string="Claims against it")
    amount_spent = fields.Monetary(
        compute="_compute_balance", store=True,
        help="From the expense claims POSTED against this advance. Not typed "
             "by anybody.")
    amount_returned = fields.Monetary(
        readonly=True, copy=False,
        help="Cash the employee handed back.")
    amount_outstanding = fields.Monetary(compute="_compute_balance", store=True)
    settlement_percent = fields.Float(compute="_compute_balance", store=True)

    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False,
                                     tracking=True)
    override_by_id = fields.Many2one(
        "res.users", readonly=True, copy=False, string="Limit overridden by",
        help="Recorded when somebody allowed a second advance, or one above "
             "the ceiling. The exception is part of the record, not a "
             "conversation nobody can find later.")
    override_reason = fields.Char(readonly=True, copy=False)
    note = fields.Text()

    @api.depends("amount", "amount_returned",
                 "expense_sheet_ids.state", "expense_sheet_ids.total_amount")
    def _compute_balance(self):
        for advance in self:
            posted = advance.expense_sheet_ids.filtered(
                lambda sheet: sheet.state in ("post", "done"))
            advance.amount_spent = sum(posted.mapped("total_amount"))
            advance.amount_outstanding = (
                advance.amount - advance.amount_spent - advance.amount_returned)
            advance.settlement_percent = (
                (advance.amount_spent + advance.amount_returned)
                / advance.amount * 100) if advance.amount else 0.0

    @api.constrains("amount")
    def _check_amount(self):
        for advance in self:
            if advance.amount <= 0:
                raise ValidationError(_("An advance has to be more than zero."))

    # ---------------------------------------------------------- the refusal
    def _outstanding_advances(self):
        """Other advances this employee has not finished with."""
        self.ensure_one()
        return self.search([
            ("employee_id", "=", self.employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("approved", "paid")),
            ("id", "!=", self.id),
        ])

    def _check_allowed(self):
        """Refuse a second advance, and one above the ceiling, unless the
        person approving holds the override right."""
        self.ensure_one()
        may_override = self.env.user.has_group(
            "mizan_advance.group_advance_override")
        outstanding = self._outstanding_advances().filtered(
            lambda other: other.amount_outstanding > 0)
        if outstanding and not may_override:
            raise UserError(_(
                "%(name)s still has %(amount)s outstanding on %(ref)s. Settle "
                "that before advancing more, or ask someone with the override "
                "right.",
                name=self.employee_id.name,
                amount="{:,.2f}".format(sum(outstanding.mapped(
                    "amount_outstanding"))),
                ref=", ".join(outstanding.mapped("name"))))
        limit = self.company_id.mizan_advance_limit
        if limit and self.amount > limit and not may_override:
            raise UserError(_(
                "%(amount)s is above the advance limit of %(limit)s.",
                amount="{:,.2f}".format(self.amount),
                limit="{:,.2f}".format(limit)))
        if (outstanding or (limit and self.amount > limit)) and may_override:
            self.override_by_id = self.env.user
            self.override_reason = (
                _("Second advance while %s is outstanding",
                  ", ".join(outstanding.mapped("name")))
                if outstanding else _("Above the advance limit"))

    # ------------------------------------------------------------- workflow
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mizan.employee.advance") or _("New")
        return super().create(vals_list)

    def _notify_employee(self, body, subject):
        """Tell the employee what happened to his money.

        An advance approved and paid while the engineer is on site is no use to
        him until he knows; one refused is worse if he finds out at the till."""
        for advance in self:
            partner = advance.employee_id.user_id.partner_id
            if partner and partner != self.env.user.partner_id:
                advance.message_notify(
                    partner_ids=partner.ids, subject=subject,
                    body=body % {"ref": advance.name,
                                 "amount": "{:,.2f}".format(advance.amount)})

    def action_submit(self):
        for advance in self:
            if advance.state != "draft":
                raise UserError(_("Only a draft can be submitted."))
            advance.state = "submitted"
        return True

    def action_approve(self):
        for advance in self:
            if advance.state != "submitted":
                raise UserError(_("Only a submitted advance can be approved."))
            advance._check_allowed()
            advance.write({"state": "approved",
                           "approved_by_id": self.env.user.id})
        self._notify_employee(_("Your advance %(ref)s for %(amount)s is "
                                "approved. Payment follows."),
                              _("Advance approved"))
        return True

    def action_refuse(self):
        for advance in self:
            advance.state = "cancel"
        self._notify_employee(_("Your advance %(ref)s for %(amount)s was "
                                "refused."), _("Advance refused"))
        return True

    def action_draft(self):
        for advance in self:
            if advance.move_pay_id:
                raise UserError(_("It has been paid. Settle or return it "
                                  "instead of resetting it."))
            advance.write({"state": "draft", "approved_by_id": False,
                           "override_by_id": False, "override_reason": False})
        return True

    def _accounts(self):
        self.ensure_one()
        advance_account = self.company_id.mizan_advance_account_id
        if not advance_account:
            raise UserError(_(
                "Set the Employee Advances account on the company first. "
                "Without it the advance would have to be posted somewhere "
                "arbitrary, and an advance in the wrong account is an advance "
                "nobody chases."))
        journal = self.journal_id or self.company_id.mizan_advance_journal_id
        if not journal:
            raise UserError(_("Choose the account the advance is paid from."))
        if not journal.default_account_id:
            raise UserError(_("%s has no default account.", journal.name))
        return advance_account, journal

    def action_pay(self):
        """Dr Employee Advances / Cr Bank."""
        for advance in self:
            if advance.state != "approved":
                raise UserError(_("Approve it before paying it."))
            advance_account, journal = advance._accounts()
            move = self.env["account.move"].create({
                "journal_id": journal.id,
                "date": advance.date,
                "ref": _("Advance %(ref)s — %(name)s", ref=advance.name,
                         name=advance.employee_id.name),
                "line_ids": [
                    (0, 0, {
                        "name": advance.purpose,
                        "account_id": advance_account.id,
                        "partner_id": advance.partner_id.id,
                        "debit": advance.amount, "credit": 0.0,
                        "analytic_distribution": (
                            {str(advance.analytic_account_id.id): 100}
                            if advance.analytic_account_id else False),
                    }),
                    (0, 0, {
                        "name": advance.purpose,
                        "account_id": journal.default_account_id.id,
                        "partner_id": advance.partner_id.id,
                        "debit": 0.0, "credit": advance.amount,
                    }),
                ],
            })
            move.action_post()
            advance.write({"move_pay_id": move.id, "state": "paid"})
        self._notify_employee(_("Your advance %(ref)s for %(amount)s has been "
                                "paid. Claim your receipts against it."),
                              _("Advance paid"))
        return True

    def action_settle(self):
        """Clear the advance against what the company owes on the claims.

        Dr Employee Payable / Cr Employee Advances, for the amount of the
        expense claims posted against this advance and not yet cleared."""
        for advance in self:
            if advance.state != "paid":
                raise UserError(_("Only a paid advance can be settled."))
            if not advance.partner_id:
                raise UserError(_(
                    "%s has no work contact, so there is no partner to settle "
                    "against.", advance.employee_id.name))
            advance_account, journal = advance._accounts()
            already = sum(
                line.credit
                for move in advance.move_settle_ids
                for line in move.line_ids
                if line.account_id == advance_account)
            to_clear = advance.amount_spent - already
            if to_clear <= 0:
                raise UserError(_(
                    "There is nothing new to settle. Post the employee's "
                    "expense claims against this advance first."))
            payable = advance.partner_id.property_account_payable_id
            move = self.env["account.move"].create({
                "journal_id": (self.company_id.mizan_advance_journal_id
                               or journal).id,
                "date": fields.Date.context_today(advance),
                "ref": _("Settling advance %s", advance.name),
                "line_ids": [
                    (0, 0, {"name": _("Settling advance %s", advance.name),
                            "account_id": payable.id,
                            "partner_id": advance.partner_id.id,
                            "debit": to_clear, "credit": 0.0}),
                    (0, 0, {"name": _("Settling advance %s", advance.name),
                            "account_id": advance_account.id,
                            "partner_id": advance.partner_id.id,
                            "debit": 0.0, "credit": to_clear}),
                ],
            })
            move.action_post()
            advance.move_settle_ids = [(4, move.id)]
            if advance.amount_outstanding <= 0:
                advance.state = "settled"
        return True

    def action_return_balance(self):
        """The employee hands back what is left. Dr Bank / Cr Advances."""
        for advance in self:
            if advance.state != "paid":
                raise UserError(_("Only a paid advance can be returned."))
            balance = advance.amount_outstanding
            if balance <= 0:
                raise UserError(_("There is nothing left to return."))
            advance_account, journal = advance._accounts()
            move = self.env["account.move"].create({
                "journal_id": journal.id,
                "date": fields.Date.context_today(advance),
                "ref": _("Balance returned on advance %s", advance.name),
                "line_ids": [
                    (0, 0, {"name": _("Balance returned"),
                            "account_id": journal.default_account_id.id,
                            "partner_id": advance.partner_id.id,
                            "debit": balance, "credit": 0.0}),
                    (0, 0, {"name": _("Balance returned"),
                            "account_id": advance_account.id,
                            "partner_id": advance.partner_id.id,
                            "debit": 0.0, "credit": balance}),
                ],
            })
            move.action_post()
            advance.move_settle_ids = [(4, move.id)]
            advance.amount_returned += balance
            advance.state = "settled"
        return True

    def action_view_moves(self):
        self.ensure_one()
        moves = self.move_pay_id | self.move_settle_ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Entries"),
            "res_model": "account.move",
            "domain": [("id", "in", moves.ids)],
            "view_mode": "list,form",
        }

    # --------------------------------------------------------- next action
    def _mizan_next_action(self):
        self.ensure_one()
        base = {
            "steps": [("draft", _("Drafted")), ("submitted", _("Submitted")),
                      ("approved", _("Approved")), ("paid", _("Paid")),
                      ("settled", _("Settled"))],
            "current": self.state,
        }
        if self.state == "draft":
            return dict(base, label=_("Submit"), method="action_submit",
                        hint=_("Sends the request for approval."))
        if self.state == "submitted":
            return dict(base, label=_("Approve"), method="action_approve",
                        hint=_("Approves it. Refused if the employee already "
                               "holds an advance that is not settled."))
        if self.state == "approved":
            return dict(base, label=_("Pay"), method="action_pay",
                        hint=_("Posts the payment and puts the amount in the "
                               "employee advances account."))
        if self.state == "paid":
            if self.amount_spent:
                return dict(base, label=_("Settle against the claims"),
                            method="action_settle",
                            hint=_("Clears the advance against what the "
                                   "company owes on the posted claims."))
            return dict(base, label=_("Record the balance returned"),
                        method="action_return_balance",
                        hint=_("The employee hands back what is left."))
        return base


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    mizan_advance_id = fields.Many2one(
        "mizan.employee.advance", string="Against Advance",
        domain="[('employee_id', '=', employee_id), ('state', '=', 'paid')]",
        help="Spend the claim against an advance the employee already holds, "
             "instead of the company paying twice.")
