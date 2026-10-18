# -*- coding: utf-8 -*-
from . import models
from . import wizard


def post_init_hook(env):
    env["res.company"].search([])._mizan_ensure_project_company_accounts()
