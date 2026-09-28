# -*- coding: utf-8 -*-
"""The thirty proposals, with a decision the finance manager records himself.

This is the point of the preview app. The other screens show what a proposal
would look like; this one is where he walks the list and says yes, no or later
to each, with a reason. It is a persistent model on purpose — every other
screen here is transient, but a decision has to survive the next refresh.

Each row states honestly whether the thing already exists. Four of the six
that do need a screen rather than logic, and asking someone to approve
building what is already built is how a roadmap loses its credibility.
"""

from odoo import fields, models


class MizanPreviewProposal(models.Model):
    _name = "mizan.preview.proposal"
    _description = "Roadmap Proposal"
    _inherit = ["mail.thread"]
    _order = "priority, sequence"

    sequence = fields.Integer(default=10)
    # translate=True so the finance manager reads the list in Arabic and I
    # can keep the English wording for the repository.
    name = fields.Char(string="Proposal", required=True, translate=True)
    detail = fields.Text(string="What it does", translate=True)
    area = fields.Selection(
        [("ux", "Daily use"), ("finance", "Accounting"),
         ("contracting", "Contracting"), ("ops", "Running the service"),
         ("compliance", "UAE compliance")],
        string="Area", required=True)

    build_state = fields.Selection(
        [("built", "Already built"),
         ("partial", "Partly built"),
         ("new", "Not built")],
        string="Status today", required=True, default="new")
    gap = fields.Char(string="What is actually missing", translate=True)

    recommendation = fields.Selection(
        [("yes", "Recommended"),
         ("differ", "I would change it"),
         ("no", "Recommend against"),
         ("done", "Nothing to decide")],
        string="My recommendation", required=True, default="yes")
    reasoning = fields.Text(string="Why", translate=True)
    effort = fields.Selection(
        [("s", "Under a day"), ("m", "Two to four days"),
         ("l", "A week or more")], string="Effort")
    priority = fields.Integer(string="Order", default=99)

    decision = fields.Selection(
        [("approved", "Approved — build it"),
         ("later", "Later"),
         ("rejected", "Rejected")],
        string="Decision", tracking=True)
    decided_by_id = fields.Many2one("res.users", string="Decided by",
                                    readonly=True, tracking=True)
    decided_on = fields.Datetime(readonly=True, tracking=True)
    decision_note = fields.Text(string="Finance manager's note")

    def _record_decision(self, value):
        self.write({
            "decision": value,
            "decided_by_id": self.env.user.id,
            "decided_on": fields.Datetime.now(),
        })
        return True

    def action_approve(self):
        return self._record_decision("approved")

    def action_later(self):
        return self._record_decision("later")

    def action_reject(self):
        return self._record_decision("rejected")

    def action_clear(self):
        return self.write({"decision": False, "decided_by_id": False,
                           "decided_on": False})
