# -*- coding: utf-8 -*-
"""Subcontractors on their own, each with a payable and a retention account.

The first subcontract for a partner creates 2031NN "مقاول باطن – name"
(their payable, set on the partner) and 2041NN "محتجزات – name". A bill then
posts Dr project WIP / Cr 2031NN; paying it posts Dr 2031NN / Cr bank /
Cr 2041NN; releasing the retention posts Dr 2041NN / Cr 2031NN."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

SC_SPECS = [
    ("mizan_sc_payable_account_id", "2031", "مقاول باطن – %s", "liability_payable", True),
    ("mizan_sc_retention_account_id", "2041", "محتجزات – %s", "liability_current", True),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    mizan_is_subcontractor = fields.Boolean(string="Subcontractor")
    mizan_sc_payable_account_id = fields.Many2one("account.account", string="Subcontractor payable account",
                                                  readonly=True, copy=False)
    mizan_sc_retention_account_id = fields.Many2one("account.account", string="Subcontractor retention account",
                                                    readonly=True, copy=False)

    def _mizan_sc_next_suffix(self, company):
        Account = self.env["account.account"].with_company(company)
        for n in range(1, 100):
            suffix = "%02d" % n
            if not Account.search_count([("code", "in", [p + suffix for _f, p, _n, _t, _r in SC_SPECS])]):
                return suffix
        raise UserError(_("All 99 subcontractor account numbers are used; extend the chart."))

    def action_create_subcontractor_accounts(self):
        Account = self.env["account.account"]
        for partner in self.filtered(lambda p: not p.mizan_sc_payable_account_id):
            company = self.env.company
            company._mizan_ensure_project_company_accounts()
            suffix = partner._mizan_sc_next_suffix(company)
            values = {"mizan_is_subcontractor": True}
            for field, prefix, name, kind, reconcile in SC_SPECS:
                values[field] = Account.with_company(company).create({
                    "code": prefix + suffix, "name": name % partner.name,
                    "account_type": kind, "reconcile": reconcile}).id
            partner.write(values)
            partner.with_company(company).property_account_payable_id = values["mizan_sc_payable_account_id"]
        return True

    def write(self, vals):
        res = super().write(vals)
        if vals.get("mizan_is_subcontractor"):
            self.filtered(lambda p: not p.mizan_sc_payable_account_id).action_create_subcontractor_accounts()
        return res


class MizanSubcontract(models.Model):
    _inherit = "mizan.subcontract"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.partner_id.action_create_subcontractor_accounts()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("partner_id"):
            self.partner_id.action_create_subcontractor_accounts()
        return res

    def _compute_certified(self):
        super()._compute_certified()
        Line = self.env["account.move.line"]
        for record in self.filtered(lambda s: s.partner_id.mizan_sc_retention_account_id):
            account = record.partner_id.mizan_sc_retention_account_id
            groups = Line._read_group(
                [("account_id", "=", account.id), ("parent_state", "=", "posted"),
                 ("move_id.mizan_subcontract_id", "=", record.id)],
                [], ["debit:sum", "credit:sum"])
            debit, credit = groups[0] if groups else (0.0, 0.0)
            record.retention_held = (credit or 0.0) - (debit or 0.0)

    def action_pay(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Pay a subcontractor"),
            "res_model": "mizan.subcontract.payment", "view_mode": "form", "target": "new",
            "context": {"default_subcontract_id": self.id},
        }

    def action_release_retention(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Release subcontractor retention"),
            "res_model": "mizan.subcontract.release", "view_mode": "form", "target": "new",
            "context": {"default_subcontract_id": self.id},
        }
