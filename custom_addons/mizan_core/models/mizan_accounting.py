# -*- coding: utf-8 -*-
from odoo import models, fields, api

class MizanAccountChartSetup(models.Model):
    _inherit = 'account.account'

    is_contracting_account = fields.Boolean(string='Contracting Account', default=False)
    cost_center_required = fields.Boolean(string='Requires Cost Center', default=False)

class MizanJournalEntryCustom(models.Model):
    _inherit = 'account.move'

    project_id = fields.Many2one('mizan.contract.project', string='Construction Project')
