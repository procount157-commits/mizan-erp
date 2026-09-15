# -*- coding: utf-8 -*-
from odoo import models, fields

class MizanConstructionProject(models.Model):
    _name = 'mizan.contract.project'
    _description = 'Construction Project'

    name = fields.Char(string='Project Name', required=True)
    code = fields.Char(string='Project Code', required=True)
    budget = fields.Float(string='Contract Value')

class MizanGoldFixingContract(models.Model):
    _name = 'mizan.gold.contract'
    _description = 'Gold Price Fixing Contract'

    name = fields.Char(string='Contract Ref', required=True)
    gold_weight_grams = fields.Float(string='Weight (Grams)', required=True)
    fixed_price_per_gram = fields.Float(string='Fixed Price / Gram', required=True)
