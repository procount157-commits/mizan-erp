# -*- coding: utf-8 -*-
import base64
import io
import csv

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanWpsFile(models.Model):
    """UAE Wage Protection System salary file.

    Every UAE employer must pay wages through WPS: a fixed-format SIF file is
    uploaded to the bank, which pays each employee and reports the transfer to
    the Ministry of Human Resources. The format is two record types in one file —
    EDR lines, one per employee, followed by a single SCR summary line — and the
    bank rejects the whole file if a total or a count disagrees.

    Generating it from posted payslips means the figures cannot drift from the
    ledger, which is the usual cause of rejection when the file is typed by hand.
    """

    _name = "mizan.wps.file"
    _description = "WPS Salary Information File"
    _inherit = ["mail.thread"]
    _order = "date_to desc, id desc"

    name = fields.Char(required=True, copy=False, default=lambda s: _("New"))
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    date_from = fields.Date(string="Period From", required=True)
    date_to = fields.Date(string="Period To", required=True)

    employer_eid = fields.Char(
        string="Employer MOL ID", required=True,
        help="13-digit establishment ID issued by the Ministry of Human "
             "Resources and Emiratisation.")
    employer_bank_code = fields.Char(
        string="Employer Bank Code", required=True,
        help="Routing code of the bank the salaries are paid from.")
    salary_month = fields.Char(
        string="Salary Month", compute="_compute_salary_month", store=True,
        help="MMYYYY as the SIF format requires.")

    payslip_ids = fields.Many2many(
        "hr.payslip", string="Payslips",
        domain="[('state', '=', 'done'), ('company_id', '=', company_id)]")
    line_ids = fields.One2many("mizan.wps.line", "file_id", string="Employee Records")

    employee_count = fields.Integer(compute="_compute_totals", store=True)
    total_salary = fields.Monetary(compute="_compute_totals", store=True)

    state = fields.Selection(
        [("draft", "Draft"), ("generated", "Generated"), ("sent", "Sent to Bank")],
        default="draft", required=True, tracking=True)

    sif_file = fields.Binary(string="SIF File", readonly=True, attachment=True)
    sif_filename = fields.Char(readonly=True)

    @api.depends("date_to")
    def _compute_salary_month(self):
        for rec in self:
            rec.salary_month = rec.date_to.strftime("%m%Y") if rec.date_to else False

    @api.depends("line_ids.net_salary")
    def _compute_totals(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids)
            rec.total_salary = sum(rec.line_ids.mapped("net_salary"))

    def action_collect_payslips(self):
        """Pull every posted payslip in the period and build one line each."""
        for rec in self:
            slips = self.env["hr.payslip"].search([
                ("state", "=", "done"),
                ("company_id", "=", rec.company_id.id),
                ("date_from", ">=", rec.date_from),
                ("date_to", "<=", rec.date_to),
            ])
            if not slips:
                raise UserError(_(
                    "No confirmed payslips found between %(start)s and %(end)s. "
                    "Confirm the payslips first — a WPS file built from drafts "
                    "would not match the ledger.",
                    start=rec.date_from, end=rec.date_to))
            rec.line_ids.unlink()
            rec.payslip_ids = [(6, 0, slips.ids)]
            for slip in slips:
                employee = slip.employee_id
                bank = employee.bank_account_id
                net_line = slip.line_ids.filtered(lambda l: l.code == "NET")
                basic_line = slip.line_ids.filtered(lambda l: l.code == "BASIC")
                self.env["mizan.wps.line"].create({
                    "file_id": rec.id,
                    "payslip_id": slip.id,
                    "employee_id": employee.id,
                    "employee_eid": employee.identification_id or "",
                    "iban": bank.acc_number if bank else "",
                    "bank_code": (bank.bank_id.bic or "") if bank and bank.bank_id else "",
                    "basic_salary": sum(basic_line.mapped("total")),
                    "net_salary": sum(net_line.mapped("total")),
                })

    def _validate_before_generate(self):
        """The bank rejects the whole file for one bad row, so check here first."""
        self.ensure_one()
        problems = []
        if not self.line_ids:
            problems.append(_("No employee records — collect the payslips first."))
        for line in self.line_ids:
            who = line.employee_id.display_name
            if not line.employee_eid:
                problems.append(_("%s has no Emirates ID / labour card number.", who))
            if not line.iban:
                problems.append(_("%s has no bank account on their record.", who))
            if not line.bank_code:
                problems.append(_(
                    "%s: their bank has no SWIFT/BIC code — set it on the bank "
                    "record, the file is rejected without it.", who))
            if line.net_salary <= 0:
                problems.append(_("%s has a net salary of zero.", who))
        if problems:
            raise UserError(
                _("The bank would reject this file:\n\n• %s", "\n• ".join(problems)))

    def action_generate(self):
        for rec in self:
            rec._validate_before_generate()
            buff = io.StringIO()
            writer = csv.writer(buff, lineterminator="\n")

            # EDR — Employee Detail Record, one per employee.
            for line in rec.line_ids:
                writer.writerow([
                    "EDR",
                    line.employee_eid,
                    line.iban,
                    line.bank_code,
                    rec.date_from.strftime("%Y-%m-%d"),
                    rec.date_to.strftime("%Y-%m-%d"),
                    30,                                   # days in the pay period
                    "%.2f" % line.basic_salary,
                    "%.2f" % (line.net_salary - line.basic_salary),
                    0,                                    # days of unpaid leave
                ])

            # SCR — Salary Control Record, exactly one, closing the file.
            writer.writerow([
                "SCR",
                rec.employer_eid,
                rec.employer_bank_code,
                fields.Date.context_today(rec).strftime("%Y-%m-%d"),
                fields.Datetime.now().strftime("%H%M"),
                rec.salary_month,
                rec.employee_count,
                "%.2f" % rec.total_salary,
                rec.currency_id.name,
            ])

            content = buff.getvalue()
            rec.write({
                "sif_file": base64.b64encode(content.encode("utf-8")),
                "sif_filename": "SIF_%s_%s.csv" % (rec.employer_eid, rec.salary_month),
                "state": "generated",
                "name": rec.name if rec.name != _("New")
                        else "WPS/%s" % rec.salary_month,
            })

    def action_mark_sent(self):
        self.write({"state": "sent"})

    def action_draft(self):
        self.write({"state": "draft", "sif_file": False, "sif_filename": False})


class MizanWpsLine(models.Model):
    _name = "mizan.wps.line"
    _description = "WPS Employee Record"

    file_id = fields.Many2one("mizan.wps.file", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="file_id.company_id", store=True)
    currency_id = fields.Many2one(related="file_id.currency_id")

    payslip_id = fields.Many2one("hr.payslip", string="Payslip", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", required=True)
    employee_eid = fields.Char(string="Emirates ID / Labour Card")
    iban = fields.Char(string="IBAN")
    bank_code = fields.Char(string="Bank Code")

    basic_salary = fields.Monetary(string="Basic")
    net_salary = fields.Monetary(string="Net Paid")
