# -*- coding: utf-8 -*-
"""Issuing stock to a project, with a voucher and an entry.

Materials come in on the supplier's bill (into inventory) and go out to a
job on an issue voucher signed by the engineer or the storekeeper. The
voucher moves the stock from the warehouse to the project's site location
and posts Dr project WIP / Cr inventory for the value the valuation layers
give the moves — manual valuation keeps no entries of its own."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MizanStockIssue(models.Model):
    _name = "mizan.stock.issue"
    _description = "Stock issue to a project"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(default="/", readonly=True, copy=False)
    contract_id = fields.Many2one("mizan.contract", string="Project", required=True,
                                  domain="[('state', '=', 'running'), ('stock_location_id', '!=', False)]", tracking=True)
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    responsible_id = fields.Many2one("res.users", string="Issued by", required=True,
                                     default=lambda self: self.env.user, tracking=True)
    received_by = fields.Char(string="Received on site by")
    line_ids = fields.One2many("mizan.stock.issue.line", "issue_id", string="Items")
    picking_id = fields.Many2one("stock.picking", string="Transfer", readonly=True, copy=False)
    move_id = fields.Many2one("account.move", string="Entry", readonly=True, copy=False)
    value = fields.Monetary(string="Value issued", readonly=True, copy=False)
    state = fields.Selection([("draft", "Draft"), ("done", "Issued"), ("cancel", "Cancelled")],
                             default="draft", readonly=True, tracking=True)
    note = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("mizan.stock.issue") or "/"
        return super().create(vals_list)

    def _mizan_picking_type(self):
        self.ensure_one()
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("No warehouse in %s.", self.company_id.name))
        PickingType = self.env["stock.picking.type"].sudo()
        kind = PickingType.search([("company_id", "=", self.company_id.id), ("sequence_code", "=", "ISS")], limit=1)
        if not kind:
            kind = PickingType.create({
                "name": "صرف للمشاريع", "code": "internal", "sequence_code": "ISS",
                "warehouse_id": warehouse.id, "company_id": self.company_id.id,
                "default_location_src_id": warehouse.lot_stock_id.id,
                "default_location_dest_id": self.contract_id.stock_location_id.id,
            })
        return kind, warehouse

    def _mizan_inventory_account(self, product):
        category = product.categ_id
        account = category.property_stock_valuation_account_id or self.company_id.mizan_inventory_account_id
        if not account:
            self.company_id._mizan_ensure_project_company_accounts()
            account = self.company_id.mizan_inventory_account_id
        if not account:
            raise UserError(_("Set the stock valuation account on the product category %s first.", category.name))
        return account

    def action_issue(self):
        for issue in self:
            if issue.state != "draft":
                continue
            if not issue.line_ids:
                raise UserError(_("Add the items to issue."))
            contract = issue.contract_id
            kind, warehouse = issue._mizan_picking_type()
            picking = self.env["stock.picking"].sudo().create({
                "picking_type_id": kind.id, "origin": issue.name,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": contract.stock_location_id.id,
                "move_ids": [(0, 0, {
                    "name": line.product_id.display_name, "product_id": line.product_id.id,
                    "product_uom_qty": line.quantity, "product_uom": line.product_id.uom_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": contract.stock_location_id.id,
                }) for line in issue.line_ids],
            })
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
            if picking.state != "done":
                raise UserError(_("The transfer could not be completed: %s", picking.state))
            total = 0.0
            lines = []
            by_account = {}
            for move in picking.move_ids:
                value = -sum(move.stock_valuation_layer_ids.mapped("value"))
                if value <= 0:
                    value = move.product_id.standard_price * move.quantity
                line = issue.line_ids.filtered(lambda l: l.product_id == move.product_id)[:1]
                if line:
                    line.sudo().value = value
                account = issue._mizan_inventory_account(move.product_id)
                by_account[account] = by_account.get(account, 0.0) + value
                total += value
            analytic = contract.analytic_account_id
            distribution = {str(analytic.id): 100} if analytic else False
            if total > 0:
                lines.append((0, 0, {"name": _("Materials issued — %s", issue.name),
                                     "account_id": contract.wip_account_id.id, "debit": total, "credit": 0.0,
                                     "analytic_distribution": distribution}))
                for account, value in by_account.items():
                    lines.append((0, 0, {"name": _("Materials issued — %s", issue.name),
                                         "account_id": account.id, "debit": 0.0, "credit": value}))
                journal = self.env["account.journal"].search(
                    [("type", "=", "general"), ("company_id", "=", issue.company_id.id)], limit=1)
                move = self.env["account.move"].sudo().with_context(mizan_routing=True).create({
                    "move_type": "entry", "journal_id": journal.id, "date": issue.date,
                    "ref": _("Stock issue %(n)s — %(c)s", n=issue.name, c=contract.code),
                    "mizan_contract_id": contract.id, "mizan_source_kind": "stock", "line_ids": lines})
                move.action_post()
                issue.sudo().move_id = move
            issue.sudo().write({"picking_id": picking.id, "value": total, "state": "done"})
            contract._mizan_invalidate_figures()
        return True

    def action_cancel(self):
        for issue in self:
            if issue.state == "done":
                raise UserError(_("%s is issued; return the materials with a new transfer instead.", issue.name))
            issue.state = "cancel"


class MizanStockIssueLine(models.Model):
    _name = "mizan.stock.issue.line"
    _description = "Stock issue line"

    issue_id = fields.Many2one("mizan.stock.issue", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True, domain="[('is_storable', '=', True)]")
    quantity = fields.Float(required=True, default=1.0, digits="Product Unit of Measure")
    uom_id = fields.Many2one(related="product_id.uom_id")
    on_hand = fields.Float(related="product_id.qty_available", string="On hand")
    currency_id = fields.Many2one(related="issue_id.currency_id")
    value = fields.Monetary(readonly=True)
