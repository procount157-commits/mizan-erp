# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request, Response
import json

class MizanMobileAPI(http.Controller):

    @http.route('/api/mizan/gold_contracts', type='json', auth='user', methods=['POST'], csrf=False)
    def get_gold_contracts(self, **kw):
        contracts = request.env['mizan.gold.contract'].search_read([], ['id', 'name', 'gold_weight_gram', 'fixed_price_per_gram', 'total_amount', 'state'])
        return {'status': 200, 'data': contracts}

    @http.route('/api/mizan/projects', type='json', auth='user', methods=['POST'], csrf=False)
    def get_projects(self, **kw):
        projects = request.env['mizan.contract.project'].search_read([], ['id', 'name', 'budget', 'completion_rate', 'stage'])
        return {'status': 200, 'data': projects}
