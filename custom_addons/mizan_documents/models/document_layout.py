# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanLayoutMixin(models.AbstractModel):
    """Let a single document override the company-wide print layout.

    Odoo picks one layout for the whole company, which breaks as soon as a
    contractor wants a plain sheet for a government tender and the branded one
    for private clients. Leaving the field empty keeps the company default, so
    nothing changes for users who do not care.
    """

    _name = "mizan.layout.mixin"
    _description = "Per-document Print Layout"

    mizan_layout_id = fields.Many2one(
        "report.layout", string="Print Template",
        help="Leave empty to use the company template set in "
             "Documents → Document Design.")

    def _mizan_effective_layout(self):
        self.ensure_one()
        if self.mizan_layout_id:
            return self.mizan_layout_id.view_id
        return self.company_id.external_report_layout_id


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mizan.layout.mixin"]

    def unlink(self):
        # Odoo already blocks posted entries. The risk left is a draft invoice
        # that was numbered and sent — deleting it leaves a hole in the sequence
        # that an FTA audit will ask about.
        for move in self:
            numbered = move.name and move.name != "/"
            if numbered and move.move_type in (
                    "out_invoice", "out_refund", "in_invoice", "in_refund"):
                raise UserError(_(
                    "Invoice %(name)s already carries a number.\n\n"
                    "Deleting it would leave a gap in the sequence, which the "
                    "FTA treats as a missing invoice. Cancel it instead — a "
                    "cancelled invoice keeps its number and stays auditable.",
                    name=move.name))
        return super().unlink()


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "mizan.layout.mixin"]


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "mizan.layout.mixin"]


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    @api.model
    def _get_report_layout_for_record(self, record):
        """Return the layout a record should print with, honouring its override."""
        if hasattr(record, "_mizan_effective_layout"):
            return record._mizan_effective_layout()
        return record.company_id.external_report_layout_id
