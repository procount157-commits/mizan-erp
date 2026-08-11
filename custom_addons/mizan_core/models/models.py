# -*- coding: utf-8 -*-

from odoo import api, fields, models


class MizanContact(models.Model):
    _name = "mizan.contact"
    _description = "Mizan Contact"
    _order = "name"

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
    )

    contact_type = fields.Selection(
        [
            ("customer", "Customer"),
            ("vendor", "Vendor"),
            ("both", "Customer & Vendor"),
        ],
        string="Type",
        required=True,
        default="customer",
    )

    email = fields.Char(
        string="Email",
    )

    phone = fields.Char(
        string="Phone",
    )

    tax_number = fields.Char(
        string="Tax Registration Number",
        index=True,
    )

    address = fields.Text(
        string="Address",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )


class MizanTax(models.Model):
    _name = "mizan.tax"
    _description = "Mizan Tax"
    _order = "name"

    name = fields.Char(
        string="Tax Name",
        required=True,
    )

    rate = fields.Float(
        string="Rate (%)",
        required=True,
        default=5.0,
    )

    tax_type = fields.Selection(
        [
            ("output", "Output VAT"),
            ("input", "Input VAT"),
        ],
        string="Tax Type",
        required=True,
        default="output",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )


class MizanInvoice(models.Model):
    _name = "mizan.invoice"
    _description = "Mizan Invoice"
    _order = "invoice_date desc, id desc"

    name = fields.Char(
        string="Invoice Number",
        required=True,
        index=True,
    )

    invoice_date = fields.Date(
        string="Invoice Date",
        required=True,
        default=fields.Date.context_today,
    )

    contact_id = fields.Many2one(
        "mizan.contact",
        string="Customer / Vendor",
        required=True,
        ondelete="restrict",
    )

    invoice_type = fields.Selection(
        [
            ("sale", "Sales Invoice"),
            ("purchase", "Purchase Invoice"),
        ],
        string="Invoice Type",
        required=True,
        default="sale",
    )

    line_ids = fields.One2many(
        "mizan.invoice.line",
        "invoice_id",
        string="Invoice Lines",
    )

    untaxed_amount = fields.Float(
        string="Untaxed Amount",
        compute="_compute_totals",
        store=True,
    )

    tax_amount = fields.Float(
        string="Tax Amount",
        compute="_compute_totals",
        store=True,
    )

    total_amount = fields.Float(
        string="Total Amount",
        compute="_compute_totals",
        store=True,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
    )

    notes = fields.Text(
        string="Notes",
    )

    @api.depends(
        "line_ids.quantity",
        "line_ids.unit_price",
        "line_ids.tax_rate",
    )
    def _compute_totals(self):
        for invoice in self:
            untaxed = 0.0
            tax = 0.0

            for line in invoice.line_ids:
                line_untaxed = line.quantity * line.unit_price
                line_tax = line_untaxed * line.tax_rate / 100.0

                untaxed += line_untaxed
                tax += line_tax

            invoice.untaxed_amount = untaxed
            invoice.tax_amount = tax
            invoice.total_amount = untaxed + tax


class MizanInvoiceLine(models.Model):
    _name = "mizan.invoice.line"
    _description = "Mizan Invoice Line"

    invoice_id = fields.Many2one(
        "mizan.invoice",
        string="Invoice",
        required=True,
        ondelete="cascade",
    )

    description = fields.Char(
        string="Description",
        required=True,
    )

    quantity = fields.Float(
        string="Quantity",
        default=1.0,
    )

    unit_price = fields.Float(
        string="Unit Price",
        default=0.0,
    )

    tax_id = fields.Many2one(
        "mizan.tax",
        string="Tax",
        ondelete="restrict",
    )

    tax_rate = fields.Float(
        string="Tax Rate (%)",
        related="tax_id.rate",
        store=True,
    )

    subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_amounts",
        store=True,
    )

    tax_amount = fields.Float(
        string="Tax Amount",
        compute="_compute_amounts",
        store=True,
    )

    total = fields.Float(
        string="Total",
        compute="_compute_amounts",
        store=True,
    )

    @api.depends(
        "quantity",
        "unit_price",
        "tax_rate",
    )
    def _compute_amounts(self):
        for line in self:
            subtotal = line.quantity * line.unit_price
            tax = subtotal * line.tax_rate / 100.0

            line.subtotal = subtotal
            line.tax_amount = tax
            line.total = subtotal + tax
