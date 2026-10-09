# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanSiteCapture(models.TransientModel):
    _inherit = "mizan.site.capture"

    paid_by = fields.Selection(
        selection_add=[("cash", "From my petty cash")],
        ondelete={"cash": "set default"},
        default=lambda self: "cash" if self._my_cash()["held"] > 0 else "me")
    cash_available = fields.Monetary(
        string="Petty cash available", compute="_compute_cash")
    cash_held = fields.Boolean(compute="_compute_cash")
    spend_kind = fields.Selection(
        [("PC-SITE", "Site materials"), ("PC-FUEL", "Fuel"),
         ("PC-HOSP", "Hospitality"), ("PC-GOV", "Government fees"),
         ("PC-GEN", "Other")],
        string="Kind", default="PC-SITE",
        help="Decides the expense account, so the cost lands under the right "
             "heading without the office recoding it.")
    vat_on_receipt = fields.Boolean(
        string="Receipt shows 5% VAT", default=True,
        help="Only a tax invoice with the supplier's TRN lets the company "
             "recover the VAT. A plain receipt is booked without it, in full.")

    def _create_expense(self):
        """Category and VAT on the claim, so it posts without anyone
        recoding it: a UAE entry with no tax chosen is refused, and rightly."""
        expense = super()._create_expense()
        product = self.env["product.product"].search(
            [("default_code", "=", self.spend_kind), ("can_be_expensed", "=", True)],
            limit=1)
        Tax = self.env["account.tax"]
        domain = [("type_tax_use", "=", "purchase"),
                  ("company_id", "=", self.env.company.id)]
        if self.vat_on_receipt:
            tax = (product.supplier_taxes_id.filtered(lambda t: t.amount == 5)[:1]
                   or self.env.company.account_purchase_tax_id)
        else:
            tax = (Tax.search(domain + [("amount", "=", 0), ("name", "ilike", "exempt")], limit=1)
                   or Tax.search(domain + [("amount", "=", 0)], limit=1))
        values = {"tax_ids": [(6, 0, tax.ids)]}
        if product:
            values["product_id"] = product.id
        total = expense.total_amount_currency
        expense.write(values)
        # Changing the product re-prices the line; the receipt's total is
        # the one figure that must not move.
        if expense.total_amount_currency != total:
            expense.total_amount_currency = total
        return expense

    @api.model
    def _my_employee(self):
        return self.env["hr.employee"].search([("user_id", "=", self.env.uid)], limit=1)

    @api.model
    def _my_cash(self):
        employee = self._my_employee()
        if not employee:
            return {"held": 0.0, "available": 0.0, "advances": self.env["mizan.employee.advance"]}
        return self.env["mizan.employee.advance"]._petty_cash(employee)

    def _compute_cash(self):
        cash = self._my_cash()
        for capture in self:
            capture.cash_available = cash["available"]
            capture.cash_held = bool(cash["advances"])

    def _create_from_cash(self):
        """Claimed against his advance and submitted, in the one tap.

        The receipt becomes an expense on his name, an expense report of its
        own linked to the advance, and goes to his manager. One report per
        receipt is deliberate: the manager approves or refuses a receipt, not a
        bundle with one bad line in it."""
        cash = self._my_cash()
        open_advances = cash["advances"]
        if not open_advances:
            raise UserError(_(
                "You hold no petty cash, so there is nothing to spend this "
                "from. Choose \"I paid it\" to claim it back, or ask for "
                "petty cash first."))
        expense = self._create_expense()
        sheet = expense._create_sheets_from_expense()
        # The oldest float first, so the oldest one is the first to close.
        advance = (open_advances.filtered(lambda a: a.amount_outstanding > 0)
                   or open_advances)[:1]
        sheet.write({"mizan_advance_id": advance.id,
                     "name": expense.name})
        sheet.action_submit_sheet()
        return sheet, cash["available"] - self.amount

    def action_save(self):
        self.ensure_one()
        if self.paid_by != "cash":
            return super().action_save()
        sheet, left = self._create_from_cash()
        currency = self.currency_id or self.env.company.currency_id
        if left < 0:
            message = _("Sent to your manager. It is %s more than the petty "
                        "cash you hold; the office reimburses the difference.",
                        "{:,.2f} {}".format(-left, currency.name))
            kind = "warning"
        else:
            message = _("Sent to your manager. Petty cash left: %s",
                        "{:,.2f} {}".format(left, currency.name))
            kind = "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Done"), "message": message, "type": kind,
                "sticky": False,
                "next": self.env["ir.actions.actions"]._for_xml_id(
                    "mizan_site.action_site_capture"),
            },
        }
