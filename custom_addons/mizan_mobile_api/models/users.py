# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    mizan_app_role = fields.Selection([
        ("auto", "Automatic (from the user's rights)"),
        ("manager", "Manager: figures, insights, approvals, projects"),
        ("accountant", "Accountant: posting, receivables, payables, bank"),
        ("engineer", "Site engineer: crew and petty cash"),
        ("staff", "Staff: petty cash only"),
    ], string="Phone app role", default="auto", required=True,
        help="Which screens this person sees in the Miqyas phone app. Automatic reads their rights: "
             "owner or general manager → manager; accounting → accountant; site engineer → engineer.")
