# -*- coding: utf-8 -*-
"""Photograph a bill on site, and have it arrive where it belongs.

An engineer comes back from the builders' merchant with two kinds of paper,
and until now both went into a pocket and reached the office days later, if at
all:

  * a RECEIPT he paid himself, out of his own pocket or out of an advance. That
    is an expense claim: the company owes him, or it settles his advance.

  * a SUPPLIER'S INVOICE addressed to the company, handed over with a delivery.
    The company owes the supplier. That is a vendor bill, and it belongs to the
    accountant — the engineer has no business in the ledger and is not given
    one.

So the screen asks one question — who paid? — and routes the photograph:
the first becomes a draft expense under his name, the second a draft vendor
bill for accounting to check and post. Both carry the project's cost centre,
so the cost lands on the job rather than in a suspense account, and both keep
the photograph as their main attachment, which is what an auditor asks for.

Nothing is read off the image. Odoo's receipt digitisation is an Enterprise
service, and this product carries no AI by decision. The engineer types the
amount while the paper is in his hand, which takes three seconds and is the
one figure that matters.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanSiteCapture(models.TransientModel):
    _name = "mizan.site.capture"
    _description = "Photograph a Bill"

    photo = fields.Image(string="Photograph", required=True,
                         max_width=2048, max_height=2048)
    paid_by = fields.Selection(
        [("me", "I paid it — claim it back"),
         ("supplier", "The supplier will invoice the company")],
        string="Who paid?", required=True, default="me")
    project_id = fields.Many2one(
        "project.project", string="Project", required=True,
        default=lambda self: self._default_project())
    amount = fields.Monetary(
        string="Amount",
        help="The total on the paper, tax included.")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id)
    description = fields.Char(
        string="What it was for",
        help="Cement, diesel, a hired pump. The office reads this before it "
             "reads the photograph.")
    supplier_id = fields.Many2one(
        "res.partner", string="Supplier",
        help="If the supplier is already in the system. Leave it empty and "
             "write the name below; accounting will match it.")
    supplier_name = fields.Char(string="Supplier name")
    date = fields.Date(default=fields.Date.context_today, required=True)

    @api.model
    def _default_project(self):
        """The project this engineer filed his last report against.

        On site the answer is almost always the same job as yesterday, and a
        field that is right by default is one nobody gets wrong."""
        last = self.env["mizan.site.report"].search(
            [("author_id", "=", self.env.uid)], order="date desc, id desc",
            limit=1)
        if last:
            return last.project_id
        # Nothing filed yet: the job he follows. An engineer on one site — the
        # usual case — then never has to choose at all.
        return self.env["project.project"].search(
            [("message_partner_ids", "in", self.env.user.partner_id.ids)],
            limit=1)

    # ------------------------------------------------------------ routing
    def _attach(self, record):
        attachment = self.env["ir.attachment"].create({
            "name": "%s-%s.jpg" % (
                _("receipt") if self.paid_by == "me" else _("bill"),
                fields.Date.to_string(self.date)),
            "datas": self.photo,
            "res_model": record._name,
            "res_id": record.id,
            "mimetype": "image/jpeg",
        })
        record._message_set_main_attachment_id(attachment, force=True)
        return attachment

    def _analytic(self):
        account = self.project_id.sudo().account_id
        return {str(account.id): 100} if account else False

    def _create_expense(self):
        employee = self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid)], limit=1)
        if not employee:
            raise UserError(_(
                "Your login is not linked to an employee record, so there is "
                "nobody to reimburse. Ask the office to link it."))
        if not self.amount:
            raise UserError(_(
                "Type the amount on the receipt. It is the one figure the "
                "office cannot read reliably from a photograph."))
        product = self.env["product.product"].search(
            [("can_be_expensed", "=", True), ("default_code", "=", "EXP_GEN")],
            limit=1) or self.env["product.product"].search(
            [("can_be_expensed", "=", True)], limit=1)
        if not product:
            raise UserError(_("No expense category exists yet. Ask the office "
                              "to create one."))
        expense = self.env["hr.expense"].create({
            "name": self.description or _("Site purchase — %s",
                                          self.project_id.name),
            "employee_id": employee.id,
            "product_id": product.id,
            "date": self.date,
            "quantity": 1,
            "total_amount_currency": self.amount,
            "payment_mode": "own_account",
            "analytic_distribution": self._analytic(),
        })
        self._attach(expense)
        return expense

    def _create_bill(self):
        """A draft the engineer cannot see the inside of.

        Created as superuser because a site engineer is deliberately not given
        the ledger; it stays a DRAFT, and the accountant is the one who checks
        it against the delivery and posts it."""
        Move = self.env["account.move"].sudo()
        journal = self.env["account.journal"].sudo().search(
            [("type", "=", "purchase"),
             ("company_id", "=", self.env.company.id)], limit=1)
        lines = []
        if self.amount:
            # The engineer types the total printed on the paper, tax included.
            # The bill line is priced before tax and Odoo adds the company's
            # purchase VAT on top, so the price is backed out of the total —
            # otherwise a 4,200 invoice is booked at 4,410 and the supplier
            # is overpaid by exactly the VAT.
            tax = self.env.company.sudo().account_purchase_tax_id
            price = self.amount
            if tax and tax.amount_type == "percent" and not tax.price_include:
                price = self.currency_id.round(
                    self.amount / (1 + tax.amount / 100.0))
            lines.append((0, 0, {
                "name": self.description or _("Delivered to %s",
                                              self.project_id.name),
                "quantity": 1,
                "price_unit": price,
                "tax_ids": [(6, 0, tax.ids)] if tax else False,
                "analytic_distribution": self._analytic(),
            }))
        bill = Move.create({
            "move_type": "in_invoice",
            "journal_id": journal.id,
            "partner_id": self.supplier_id.id or False,
            "invoice_date": self.date,
            "ref": self.supplier_name or False,
            "narration": _(
                "Photographed on site by %(user)s for %(project)s. %(what)s",
                user=self.env.user.name, project=self.project_id.name,
                what=self.description or ""),
            "invoice_line_ids": lines,
        })
        # The attachment follows the bill's own access: an engineer cannot
        # attach to a record he cannot read, so it is attached as superuser
        # too. He sees the photograph again only through accounting.
        self.sudo()._attach(bill)
        self._notify_accounts(bill)
        return bill

    def _notify_accounts(self, bill):
        """Tell the people who will post it that it exists."""
        group = self.env.ref("account.group_account_invoice")
        accountants = group.sudo().users.filtered(
            lambda user: user.active and not user.share
            and not user.has_group("mizan_site.group_site_engineer"))
        if accountants:
            bill.sudo().message_notify(
                partner_ids=accountants.partner_id.ids,
                subject=_("A supplier bill from site"),
                body=_("%(user)s photographed a supplier bill for %(project)s. "
                       "It is a draft waiting for you to check and post.",
                       user=self.env.user.name,
                       project=self.project_id.name),
            )

    def action_save(self):
        self.ensure_one()
        if self.paid_by == "me":
            record = self._create_expense()
            message = _("Saved as your expense claim. Submit it when the "
                        "day's receipts are in.")
        else:
            record = self._create_bill()
            message = _("Sent to accounting as a draft supplier bill.")
        # Straight back to the camera: receipts come in handfuls, and one
        # screen between each photograph is one screen too many.
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Done"),
                "message": message,
                "type": "success",
                "sticky": False,
                "next": self.env["ir.actions.actions"]._for_xml_id(
                    "mizan_site.action_site_capture"),
            },
        }
