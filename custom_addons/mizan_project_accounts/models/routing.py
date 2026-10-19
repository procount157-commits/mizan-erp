# -*- coding: utf-8 -*-
"""The one rule: a cost that names a project goes to the project's WIP.

Whatever screen wrote the line — a supplier bill, a subcontractor bill, a
petty-cash claim, an employee expense, a direct journal entry, a payslip —
if it carries the contract (on the move, or through its analytic cost
centre) and sits on a profit-and-loss expense account, it is moved to the
contract's work-in-progress account. The cost code is kept, or taken from
the account the screen chose. Lines already on a project account are left
alone, so the recognition entries are not re-routed."""
from odoo import api, fields, models

from .accounts import EXPENSE_TYPES


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    mizan_source = fields.Selection([
        ("bill", "Supplier bill"), ("subcontract", "Subcontractor bill"),
        ("petty", "Petty cash"), ("expense", "Employee expense"),
        ("payroll", "Payroll"), ("labour", "Labour card"), ("stock", "Stock issue"),
        ("claim", "Progress claim"), ("recognition", "Revenue recognition"),
        ("advance", "Customer advance"), ("payment", "Payment"), ("retention", "Retention"),
        ("entry", "Journal entry"),
    ], string="Source", compute="_compute_mizan_source")

    def _compute_mizan_source(self):
        # Only asks where an entry came from (a payslip, an expense claim…);
        # someone who may read the ledger line may know its source, even
        # without rights on payroll itself.
        Recognition = self.env["mizan.contract.recognition"].sudo()
        Claim = self.env["mizan.progress.claim"].sudo()
        for line in self:
            move = line.move_id.sudo()
            line.mizan_source = move._mizan_source(Recognition, Claim)

    def _mizan_contract_from_analytic(self):
        self.ensure_one()
        distribution = self.analytic_distribution or {}
        ids = set()
        for key in distribution:
            for part in str(key).split(","):
                if part.strip().isdigit():
                    ids.add(int(part))
        if not ids:
            return self.env["mizan.contract"]
        return self.env["mizan.contract"].search(
            [("analytic_account_id", "in", list(ids)), ("wip_account_id", "!=", False)], limit=1)

    def _mizan_route_storable(self):
        """A supplier bill of storable materials goes to inventory, not to a
        job: the job is charged when the storekeeper issues the materials."""
        self.ensure_one()
        if self.move_id.move_type not in ("in_invoice", "in_refund") or not self.product_id.is_storable:
            return False
        company = self.move_id.company_id
        account = self.product_id.categ_id.property_stock_valuation_account_id or company.mizan_inventory_account_id
        if not account:
            company._mizan_ensure_project_company_accounts()
            account = company.mizan_inventory_account_id
        if account and self.account_id != account:
            self.with_context(mizan_routing=True).write({"account_id": account.id})
        return True

    def _mizan_route_to_project(self):
        CostCode = self.env["mizan.cost.code"]
        for line in self:
            if line.display_type != "product" or line.parent_state != "draft":
                continue
            contract = line.move_id.mizan_contract_id or line.move_id.mizan_subcontract_id.contract_id
            if not contract or not contract.wip_account_id:
                contract = line._mizan_contract_from_analytic()
            if not contract or not contract.wip_account_id:
                continue
            account = line.account_id
            if account.account_type not in EXPENSE_TYPES or account in contract._mizan_project_accounts():
                continue
            if line._mizan_route_storable():
                continue
            values = {"account_id": contract.wip_account_id.id}
            if not line.mizan_cost_code_id:
                code = CostCode.search([("account_id", "=", account.id)], limit=1)
                if code:
                    values["mizan_cost_code_id"] = code.id
            line.with_context(mizan_routing=True).write(values)
            if not line.move_id.mizan_contract_id:
                line.move_id.with_context(mizan_routing=True).mizan_contract_id = contract

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if not self.env.context.get("mizan_routing"):
            lines._mizan_route_to_project()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("mizan_routing") and (
                "analytic_distribution" in vals or "account_id" in vals or "product_id" in vals):
            self._mizan_route_to_project()
        return res


class AccountMove(models.Model):
    _inherit = "account.move"

    mizan_source_kind = fields.Selection([
        ("advance", "Customer advance"), ("payment", "Customer payment"),
        ("sc_payment", "Subcontractor payment"), ("retention", "Retention release"),
        ("labour", "Labour card"), ("stock", "Stock issue"),
    ], string="Created by", readonly=True, copy=False)

    def _mizan_source(self, Recognition=None, Claim=None):
        self.ensure_one()
        if self.mizan_source_kind in ("advance", "labour", "stock", "retention"):
            return self.mizan_source_kind
        if self.mizan_source_kind in ("payment", "sc_payment"):
            return "payment"
        if "expense_sheet_id" in self._fields and self.expense_sheet_id:
            return "petty" if self.expense_sheet_id.mizan_advance_id else "expense"
        if self.mizan_subcontract_id:
            return "subcontract"
        if self.move_type in ("in_invoice", "in_refund"):
            return "bill"
        if self.move_type in ("out_invoice", "out_refund"):
            return "claim"
        if ("origin_payment_id" in self._fields and self.origin_payment_id) or (
                "payment_id" in self._fields and self.payment_id):
            return "payment"
        Recognition = Recognition or self.env["mizan.contract.recognition"]
        if Recognition.search_count([("move_id", "=", self.id)]):
            return "recognition"
        if "hr.payslip" in self.env and self.env["hr.payslip"].search_count([("move_id", "=", self.id)]):
            return "payroll"
        if self.mizan_retention_move_id or self.env["account.move"].search_count(
                [("mizan_retention_move_id", "=", self.id)]):
            return "retention"
        return "entry"

    def write(self, vals):
        res = super().write(vals)
        # A contract chosen on the bill after the lines were typed still
        # routes them.
        if "mizan_contract_id" in vals and vals["mizan_contract_id"] and not self.env.context.get("mizan_routing"):
            self.filtered(lambda m: m.state == "draft").line_ids._mizan_route_to_project()
        return res
