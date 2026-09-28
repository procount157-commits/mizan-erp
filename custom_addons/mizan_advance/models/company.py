# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    mizan_advance_account_id = fields.Many2one(
        "account.account", string="Employee Advances Account",
        domain="[('account_type', '=', 'asset_current')]",
        help="Where an advance sits while the employee still holds it. It is "
             "an asset — the company is owed the money — and not an expense, "
             "which is the mistake that makes advances disappear.")
    mizan_advance_journal_id = fields.Many2one(
        "account.journal", string="Advance Payment Journal",
        domain="[('type', 'in', ('bank', 'cash'))]",
        help="The account the advance is actually paid from.")
    mizan_advance_limit = fields.Monetary(
        string="Advance Limit per Employee",
        help="Above this an advance needs the override right. Zero means no "
             "ceiling.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    mizan_advance_account_id = fields.Many2one(
        related="company_id.mizan_advance_account_id", readonly=False)
    mizan_advance_journal_id = fields.Many2one(
        related="company_id.mizan_advance_journal_id", readonly=False)
    mizan_advance_limit = fields.Monetary(
        related="company_id.mizan_advance_limit", readonly=False)
