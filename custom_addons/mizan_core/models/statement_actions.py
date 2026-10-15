# -*- coding: utf-8 -*-
"""Give every one-click financial statement the context its widget needs.

The balance sheet and the profit and loss open mis_builder's result view
directly, the way its own Preview button does. What Preview carries without
saying so is the context of the click: a button on a record always sends
active_model and active_id. The report widget finds its instance in exactly
that place -- it looks at props.value first, which Odoo 17 and later never
pass to a field widget, and then at context.active_id. An action written by
hand with only res_id therefore opens a report with no instance, and the
screen dies on "Invalid ids list" before anything is drawn.

The actions are built per database by scripts/build_financial_statements.py,
because res_id is the instance built there. So the repair runs from data on
every install and update instead of trusting each database to have been built
with the fixed script, and it covers any such action, not only the two named
today.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class IrActionsActWindow(models.Model):
    _inherit = "ir.actions.act_window"

    @api.model
    def _mizan_fix_statement_actions(self):
        result_view = self.env.ref(
            "mis_builder.mis_report_instance_result_view_form",
            raise_if_not_found=False)
        if not result_view:
            return
        fixed = []
        for action in self.sudo().search([
                ("res_model", "=", "mis.report.instance"),
                ("view_id", "=", result_view.id),
                ("res_id", "!=", False)]):
            wanted = ("{'active_model': 'mis.report.instance', 'active_id': %d}"
                      % action.res_id)
            if action.context != wanted:
                action.context = wanted
                fixed.append(action.with_context(lang="en_US").name)
        if fixed:
            _logger.info("Statement actions given their instance: %s",
                         ", ".join(fixed))
