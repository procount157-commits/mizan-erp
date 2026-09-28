# -*- coding: utf-8 -*-
"""A variation that changes the contract, instead of describing a change.

What existed was an amount, a cost impact and an approval state, and on
approval the contract value moved. That is the money side, and it is the easy
half. The half that was missing is the one a contractor actually argues with
the client about:

  * WHICH ITEMS changed. A variation is a set of new bill items and revisions
    to existing ones. Until those reach the bill of quantities, the next
    progress claim measures against the old quantities and over-measurement is
    refused on work the client has already instructed — which is precisely the
    moment the system looks wrong to the site.

  * HOW MUCH TIME. An instruction that adds six weeks of work and no extension
    turns into a delay claim against the contractor. The days belong on the
    variation, with the revised completion date computed from them.

  * THE PAPER TRAIL. Who instructed it, when, under what reference, who
    approved it and on what date, with the correspondence attached to the
    record rather than in somebody's mail.

On approval the bill of quantities is edited: new items are added carrying the
variation that created them, and revised items have their quantity changed with
the original kept. That is what makes it a change order rather than a note.

A variation whose lines do not add up to its stated value is refused at
approval. Before approval the two may disagree while it is being negotiated —
that is a normal state for a variation and not an error — but the figure that
moves the contract value must be the figure the items justify.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MizanContractVariation(models.Model):
    _name = "mizan.contract.variation"
    _inherit = ["mizan.contract.variation", "mail.thread", "mail.activity.mixin"]

    # --- the paper trail -------------------------------------------------
    client_reference = fields.Char(
        string="Client's Instruction No.", tracking=True,
        help="The consultant's or client's own reference for the instruction. "
             "It is what the argument will be conducted in terms of.")
    date_requested = fields.Date(string="Instructed On", tracking=True)
    requested_by = fields.Char(
        string="Instructed By",
        help="Who on the client's side asked for it.")
    date_approved = fields.Date(string="Approved On", readonly=True,
                                copy=False, tracking=True)
    approved_by_user_id = fields.Many2one(
        "res.users", string="Recorded By", readonly=True, copy=False)

    # --- time -------------------------------------------------------------
    days_impact = fields.Integer(
        string="Extension of Time (days)", tracking=True,
        help="Days the completion date moves by. Zero is a decision too — a "
             "variation accepted with no extension is one the contractor "
             "absorbs.")
    date_end_before = fields.Date(
        readonly=True, copy=False,
        help="The completion date before this variation moved it, so the "
             "change can be undone.")

    # --- the items --------------------------------------------------------
    line_ids = fields.One2many(
        "mizan.contract.variation.line", "variation_id", string="Items")
    amount_from_lines = fields.Monetary(
        compute="_compute_from_lines", string="Items Total")
    cost_from_lines = fields.Monetary(
        compute="_compute_from_lines", string="Items Cost")
    lines_disagree = fields.Boolean(compute="_compute_from_lines")
    applied = fields.Boolean(
        readonly=True, copy=False, string="Applied to the BOQ",
        help="Set once the items have been written into the bill of "
             "quantities, so approving twice cannot add them twice.")

    @api.depends("line_ids.amount", "line_ids.cost_estimate", "amount",
                 "cost_impact")
    def _compute_from_lines(self):
        for variation in self:
            variation.amount_from_lines = sum(variation.line_ids.mapped("amount"))
            variation.cost_from_lines = sum(
                variation.line_ids.mapped("cost_estimate"))
            variation.lines_disagree = bool(variation.line_ids) and (
                abs(variation.amount_from_lines - variation.amount) > 0.01)

    def action_use_line_total(self):
        """Take the items' total as the variation's value."""
        for variation in self:
            variation.amount = variation.amount_from_lines
            if variation.cost_from_lines:
                variation.cost_impact = variation.cost_from_lines
        return True

    # ------------------------------------------------------------- workflow
    def action_approve(self):
        """Approve, and change the contract.

        Overrides the plain state change: an approval that does not reach the
        bill of quantities leaves the next claim measuring against quantities
        the client has already superseded."""
        for variation in self:
            if variation.state == "approved":
                raise UserError(_("%s is already approved.", variation.reference))
            if variation.lines_disagree:
                raise UserError(_(
                    "The items add up to %(lines)s and the variation is valued "
                    "at %(stated)s. Reconcile them before approving — this is "
                    "the figure that moves the contract value.",
                    lines="{:,.2f}".format(variation.amount_from_lines),
                    stated="{:,.2f}".format(variation.amount)))
            variation.write({
                "state": "approved",
                "date_approved": fields.Date.context_today(variation),
                "approved_by_user_id": self.env.user.id,
            })
            variation._apply_to_boq()
            variation._apply_time()
            variation.message_post(body=_(
                "Approved. Contract value %(before)s → %(after)s.",
                before="{:,.2f}".format(
                    variation.contract_id.revised_contract_value
                    - variation.amount),
                after="{:,.2f}".format(
                    variation.contract_id.revised_contract_value)))
        return True

    def action_draft(self):
        """Take it back, and undo what approving it did."""
        for variation in self:
            if variation.state == "approved":
                variation._unapply_time()
                variation._unapply_boq()
            variation.write({"state": "draft", "date_approved": False,
                             "approved_by_user_id": False})
        return True

    # ---------------------------------------------------------- the effects
    def _apply_to_boq(self):
        """Write the items into the bill of quantities."""
        self.ensure_one()
        if self.applied:
            return
        BoqLine = self.env["mizan.contract.boq.line"]
        for line in self.line_ids:
            if line.change_type == "new":
                created = BoqLine.create({
                    "contract_id": self.contract_id.id,
                    "section": line.section or _("Variations"),
                    "item_no": line.item_no,
                    "name": line.name,
                    "unit": line.unit,
                    "quantity": line.quantity,
                    "rate": line.rate,
                    "cost_code_id": line.cost_code_id.id or False,
                    "variation_id": self.id,
                })
                line.boq_line_id = created.id
            else:
                boq = line.boq_line_id
                if not boq:
                    continue
                # Certified quantity is the floor. Reducing an item below what
                # the consultant already certified would make the claims
                # already issued unsupportable by the bill they were measured
                # against.
                if line.quantity_new < boq.qty_certified:
                    raise UserError(_(
                        "%(item)s has %(certified)s certified already, so it "
                        "cannot be revised down to %(new)s.",
                        item=boq.item_no, certified=boq.qty_certified,
                        new=line.quantity_new))
                line.quantity_before = boq.quantity
                boq.quantity = line.quantity_new
        self.applied = True

    def _unapply_boq(self):
        self.ensure_one()
        if not self.applied:
            return
        for line in self.line_ids:
            if line.change_type == "new" and line.boq_line_id:
                if line.boq_line_id.qty_certified:
                    raise UserError(_(
                        "%s has already been certified on a claim, so the "
                        "variation that created it cannot be withdrawn.",
                        line.boq_line_id.item_no))
                line.boq_line_id.unlink()
            elif line.boq_line_id and line.quantity_before:
                # Same floor as applying it. If the consultant certified
                # against the revised quantity, putting the old one back would
                # leave a claim measured against a bill that no longer
                # supports it.
                if line.boq_line_id.qty_certified > line.quantity_before:
                    raise UserError(_(
                        "%(item)s has %(certified)s certified against the "
                        "revised quantity, so it cannot go back to "
                        "%(before)s.",
                        item=line.boq_line_id.item_no,
                        certified=line.boq_line_id.qty_certified,
                        before=line.quantity_before))
                line.boq_line_id.quantity = line.quantity_before
        self.applied = False

    def _apply_time(self):
        self.ensure_one()
        if not self.days_impact or not self.contract_id.date_end:
            return
        self.date_end_before = self.contract_id.date_end
        self.contract_id.date_end = fields.Date.add(
            self.contract_id.date_end, days=self.days_impact)

    def _unapply_time(self):
        self.ensure_one()
        if self.date_end_before:
            self.contract_id.date_end = self.date_end_before
            self.date_end_before = False

    # --------------------------------------------------------- what it does
    revised_completion_date = fields.Date(
        compute="_compute_revised_completion", string="Revised Completion")

    @api.depends("contract_id.date_end", "days_impact", "state")
    def _compute_revised_completion(self):
        for variation in self:
            end = variation.contract_id.date_end
            if not end:
                variation.revised_completion_date = False
            elif variation.state == "approved":
                # Already moved; showing it plus the days again would read as
                # a second extension.
                variation.revised_completion_date = end
            else:
                variation.revised_completion_date = fields.Date.add(
                    end, days=variation.days_impact or 0)


class MizanContractVariationLine(models.Model):
    _name = "mizan.contract.variation.line"
    _description = "Variation Item"
    _order = "variation_id, sequence, id"

    variation_id = fields.Many2one(
        "mizan.contract.variation", required=True, ondelete="cascade",
        index=True)
    contract_id = fields.Many2one(related="variation_id.contract_id", store=True)
    company_id = fields.Many2one(related="variation_id.company_id", store=True)
    currency_id = fields.Many2one(related="variation_id.currency_id")
    sequence = fields.Integer(default=10)

    change_type = fields.Selection(
        [("new", "New item"),
         ("vary", "Revise an existing item")],
        default="new", required=True, string="Change")

    boq_line_id = fields.Many2one(
        "mizan.contract.boq.line", string="Bill Item",
        domain="[('contract_id', '=', contract_id)]",
        help="For a revision, the item being changed. For a new item this is "
             "filled in once the variation is approved and the item exists.")

    section = fields.Char(string="Bill / Section")
    item_no = fields.Char(string="Item No.")
    name = fields.Char(string="Description", required=True)
    unit = fields.Char(string="Unit")
    cost_code_id = fields.Many2one("mizan.cost.code", string="Cost Code")

    # --- new item
    quantity = fields.Float(string="Quantity", digits="Product Unit of Measure")
    rate = fields.Monetary(string="Rate")

    # --- revision
    quantity_original = fields.Float(
        related="boq_line_id.quantity", string="Current Quantity")
    quantity_new = fields.Float(string="Revised Quantity",
                                digits="Product Unit of Measure")
    quantity_before = fields.Float(
        readonly=True, copy=False,
        help="What the bill said before this variation changed it.")

    amount = fields.Monetary(compute="_compute_amount", store=True)
    cost_estimate = fields.Monetary(
        string="Expected Cost",
        help="What this item is expected to cost to build. Left empty the "
             "variation's margin is only as good as the header figure.")
    note = fields.Char()

    @api.depends("change_type", "quantity", "rate", "quantity_new",
                 "boq_line_id.quantity", "boq_line_id.rate")
    def _compute_amount(self):
        for line in self:
            if line.change_type == "new":
                line.amount = line.quantity * line.rate
            elif line.boq_line_id:
                # Only the DIFFERENCE is the variation. The item's existing
                # value is already in the contract.
                delta = line.quantity_new - line.boq_line_id.quantity
                line.amount = delta * (line.rate or line.boq_line_id.rate)
            else:
                line.amount = 0.0

    @api.onchange("boq_line_id")
    def _onchange_boq_line(self):
        for line in self:
            if line.boq_line_id and line.change_type == "vary":
                line.name = line.boq_line_id.name
                line.item_no = line.boq_line_id.item_no
                line.unit = line.boq_line_id.unit
                line.section = line.boq_line_id.section
                line.rate = line.boq_line_id.rate
                line.cost_code_id = line.boq_line_id.cost_code_id
                if not line.quantity_new:
                    line.quantity_new = line.boq_line_id.quantity

    @api.constrains("change_type", "boq_line_id")
    def _check_line(self):
        for line in self:
            if line.change_type == "vary" and not line.boq_line_id:
                raise ValidationError(_(
                    "Choose the bill item being revised on %s.", line.name))
            if line.change_type == "new" and not line.item_no:
                raise ValidationError(_(
                    "A new bill item needs an item number: the consultant "
                    "certifies against it."))
