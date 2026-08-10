# -*- coding: utf-8 -*-
# from odoo import http


# class MizanCore(http.Controller):
#     @http.route('/mizan_core/mizan_core', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/mizan_core/mizan_core/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('mizan_core.listing', {
#             'root': '/mizan_core/mizan_core',
#             'objects': http.request.env['mizan_core.mizan_core'].search([]),
#         })

#     @http.route('/mizan_core/mizan_core/objects/<model("mizan_core.mizan_core"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('mizan_core.object', {
#             'object': obj
#         })

