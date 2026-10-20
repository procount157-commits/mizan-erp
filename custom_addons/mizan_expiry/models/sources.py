# -*- coding: utf-8 -*-
"""Rows that come from other records, kept in step.

A worker's visa, labour card, Emirates ID, passport and medical insurance are
on his employee record (Odoo has the visa and the work permit; the other three
are added here). A subcontractor's insurance is on the subcontract. Each date
filled in there has one row in the register; changing it there changes the
row, clearing it archives the row, and a renewal from the register writes the
new date back."""
from odoo import _, api, fields, models

from .expiry import users_lang

# (model, field, kind, label)
EMPLOYEE_FIELDS = [
    ("visa_expire", "visa", "Residence visa"),
    ("work_permit_expiration_date", "labour_card", "Labour card"),
    ("mizan_eid_expiry", "eid", "Emirates ID"),
    ("mizan_passport_expiry", "passport", "Passport"),
    ("mizan_medical_expiry", "medical", "Medical insurance"),
]
EMPLOYEE_REFS = {"visa_expire": "visa_no", "work_permit_expiration_date": "permit_no",
                 "mizan_eid_expiry": "mizan_eid_number", "mizan_passport_expiry": "passport_id"}


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    mizan_eid_number = fields.Char(string="Emirates ID number", groups="hr.group_hr_user")
    mizan_eid_expiry = fields.Date(string="Emirates ID expiry", groups="hr.group_hr_user")
    mizan_passport_expiry = fields.Date(string="Passport expiry", groups="hr.group_hr_user")
    mizan_medical_expiry = fields.Date(string="Medical insurance expiry", groups="hr.group_hr_user")
    mizan_expiry_count = fields.Integer(compute="_compute_mizan_expiry_count", groups="hr.group_hr_user")

    def _compute_mizan_expiry_count(self):
        Doc = self.env["mizan.expiry.document"].sudo()
        for employee in self:
            employee.mizan_expiry_count = Doc.search_count([("employee_id", "=", employee.id)])

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._mizan_sync_expiry()
        return employees

    def write(self, vals):
        res = super().write(vals)
        watched = {f for f, _k, _l in EMPLOYEE_FIELDS} | set(EMPLOYEE_REFS.values()) | {"name", "active"}
        if watched & set(vals):
            self._mizan_sync_expiry()
        return res

    def _mizan_sync_expiry(self):
        # Names in the company's language, whoever (or whichever cron) syncs.
        lang = users_lang(self.env)
        self = self.with_context(lang=lang)
        Doc = self.env["mizan.expiry.document"].sudo().with_context(active_test=False)
        for employee in self.sudo():
            for field, kind, label in EMPLOYEE_FIELDS:
                if field not in employee._fields:
                    continue
                date = employee[field]
                row = Doc.search([("source_model", "=", "hr.employee"), ("source_id", "=", employee.id),
                                  ("source_field", "=", field)], limit=1)
                if not date or not employee.active:
                    if row.active:
                        row.active = False
                    continue
                ref_field = EMPLOYEE_REFS.get(field)
                values = {
                    "name": "%s — %s" % (_(label), employee.name),
                    "expiry_date": date,
                    "reference": employee[ref_field] if ref_field and ref_field in employee._fields else False,
                    "employee_id": employee.id, "active": True,
                    "company_id": employee.company_id.id or self.env.company.id,
                }
                if row:
                    changes = {k: v for k, v in values.items()
                               if (row[k].id if hasattr(row[k], "id") else row[k]) != v}
                    if changes:
                        row.write(changes)
                else:
                    Doc.create(dict(values, kind=kind, source_model="hr.employee", source_id=employee.id,
                                    source_field=field, responsible_id=self._mizan_hr_responsible().id))

    @api.model
    def _mizan_hr_responsible(self):
        group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
        users = group.users.filtered(lambda u: u.active and not u.share) if group else self.env["res.users"]
        return users[:1] or self.env.user

    def action_mizan_expiries(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": _("Expiries"), "res_model": "mizan.expiry.document",
                "view_mode": "list,form", "domain": [("employee_id", "=", self.id)],
                "context": {"default_employee_id": self.id}}


class MizanSubcontract(models.Model):
    _inherit = "mizan.subcontract"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._mizan_sync_expiry()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"insurance_expiry", "partner_id", "state"} & set(vals):
            self._mizan_sync_expiry()
        return res

    def _mizan_sync_expiry(self):
        lang = users_lang(self.env)
        self = self.with_context(lang=lang)
        Doc = self.env["mizan.expiry.document"].sudo().with_context(active_test=False)
        for sub in self.sudo():
            row = Doc.search([("source_model", "=", "mizan.subcontract"), ("source_id", "=", sub.id),
                              ("source_field", "=", "insurance_expiry")], limit=1)
            live = sub.insurance_expiry and sub.state not in ("cancel", "closed", "done")
            if not live:
                if row.active:
                    row.active = False
                continue
            values = {"name": _("Insurance — %s", sub.partner_id.name or sub.display_name),
                      "expiry_date": sub.insurance_expiry, "partner_id": sub.partner_id.id,
                      "contract_id": sub.contract_id.id if "contract_id" in sub._fields else False,
                      "active": True}
            if row:
                row.write(values)
            else:
                Doc.create(dict(values, kind="sub_insurance", source_model="mizan.subcontract",
                                source_id=sub.id, source_field="insurance_expiry"))


class MizanExpiryDocument(models.Model):
    _inherit = "mizan.expiry.document"

    @api.model
    def _sync_sources(self):
        self.env["hr.employee"].sudo().with_context(active_test=False).search([])._mizan_sync_expiry()
        if "insurance_expiry" in self.env["mizan.subcontract"]._fields:
            self.env["mizan.subcontract"].sudo().search([])._mizan_sync_expiry()
        return True
