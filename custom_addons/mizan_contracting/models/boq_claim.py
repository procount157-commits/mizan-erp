# -*- coding: utf-8 -*-
"""The bill of quantities, and the progress claim drawn from it.

A progress claim on a construction contract is not an invoice with an amount on
it. It is a measured document: every item of the bill of quantities with its
quantity, its rate, how much was certified before, how much is claimed now, and
the resulting percentage. That table is what the site engineer measures, what
the consultant signs, and what the client's quantity surveyor argues with. The
invoice is only its last line.

Billing a contract as a single figure loses all of it. Nobody can see which
items are over-measured, the consultant has nothing to certify against, the
next claim's "previously certified" is a number somebody remembers, and when
the client disputes one item there is no line to dispute. Every specialist
contracting system is built around this table; a general ledger with a project
field is not.

Two rules are enforced rather than trusted:

  * cumulative quantity cannot exceed the bill of quantities, unless a variation
    has added to it. Over-measurement is the most common way a claim comes back
    rejected, and it is arithmetic, so the system can check it.
  * claim 4 cannot be certified before claim 3. "Previously certified" is
    defined by the claims below this one, so certifying out of order silently
    bills the same work twice.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanContractBoqLine(models.Model):
    """One priced item of the contract's bill of quantities."""

    _name = "mizan.contract.boq.line"
    _description = "Bill of Quantities Item"
    _order = "contract_id, sequence, item_no, id"

    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")
    sequence = fields.Integer(default=10)

    section = fields.Char(
        string="Bill / Section",
        help="The heading this item sits under in the priced bill — the "
             "consultant certifies section by section.")
    item_no = fields.Char(string="Item No.", required=True)
    name = fields.Char(string="Description", required=True)
    unit = fields.Char(
        string="Unit",
        help="How the item is measured — m2, m3, ton, No., lm, LS, month. A "
             "plain label rather than a unit of measure record: bill units are "
             "never converted into one another, and every client would "
             "otherwise have to configure a unit category per unit before "
             "pricing its first job.")
    quantity = fields.Float(
        string="Qty", required=True, default=1.0,
        digits="Product Unit of Measure")
    rate = fields.Monetary(string="Rate", required=True)
    amount = fields.Monetary(
        string="Item Value", compute="_compute_amount", store=True)

    cost_code_id = fields.Many2one(
        "mizan.cost.code", string="Cost Code",
        help="Ties the item's revenue to the trade that will spend against it, "
             "so a rate can be compared with what it actually costs.")
    variation_id = fields.Many2one(
        "mizan.contract.variation", string="Variation",
        help="Set when the item came from a variation order rather than the "
             "original bill. Only approved variations add to the measurable "
             "quantity.")
    is_variation = fields.Boolean(compute="_compute_is_variation", store=True)

    qty_certified = fields.Float(
        string="Qty Certified", compute="_compute_certified",
        digits="Product Unit of Measure")
    amount_certified = fields.Monetary(
        string="Certified", compute="_compute_certified")
    percent_certified = fields.Float(
        string="% Certified", compute="_compute_certified")
    qty_remaining = fields.Float(
        string="Qty Remaining", compute="_compute_certified",
        digits="Product Unit of Measure")
    note = fields.Char()

    _sql_constraints = [
        ("item_contract_uniq", "unique(contract_id, item_no)",
         "That item number is already in this contract's bill of quantities."),
    ]

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for line in self:
            line.amount = line.quantity * line.rate

    @api.depends("variation_id")
    def _compute_is_variation(self):
        for line in self:
            line.is_variation = bool(line.variation_id)

    def _compute_certified(self):
        """What has been certified against this item, across every claim.

        Draft claims are excluded on purpose: a quantity somebody is still
        measuring is not certified, and counting it makes the next claim's
        "previously certified" wrong in the client's favour.
        """
        ClaimLine = self.env["mizan.progress.claim.line"]
        for line in self:
            done = ClaimLine.search([
                ("boq_line_id", "=", line.id),
                ("claim_id.state", "in", ("certified", "invoiced")),
            ])
            qty = sum(done.mapped("this_qty"))
            line.qty_certified = qty
            line.amount_certified = qty * line.rate
            line.percent_certified = (
                qty / line.quantity * 100.0) if line.quantity else 0.0
            line.qty_remaining = line.quantity - qty

    @api.depends("item_no", "name")
    def _compute_display_name(self):
        for line in self:
            line.display_name = "%s — %s" % (line.item_no or "", line.name or "")


class MizanProgressClaim(models.Model):
    """A measured progress claim (مستخلص) against a contract."""

    _name = "mizan.progress.claim"
    _description = "Progress Claim"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "contract_id, sequence_no desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    contract_id = fields.Many2one(
        "mizan.contract", required=True, ondelete="restrict", index=True,
        tracking=True, domain="[('state', 'in', ('running', 'done'))]")
    sequence_no = fields.Integer(
        string="Claim No.", required=True, default=0, copy=False,
        help="Numbered per contract, the way the consultant refers to it.")
    company_id = fields.Many2one(related="contract_id.company_id", store=True)
    currency_id = fields.Many2one(related="contract_id.currency_id")
    partner_id = fields.Many2one(related="contract_id.partner_id", store=True)

    date = fields.Date(
        string="Claim Date", required=True, default=fields.Date.context_today,
        tracking=True)
    period_start = fields.Date(string="Period From")
    period_end = fields.Date(string="Period To")

    state = fields.Selection(
        [("draft", "Draft"),
         ("submitted", "Submitted to Consultant"),
         ("certified", "Certified"),
         ("invoiced", "Invoiced"),
         ("cancel", "Cancelled")],
        default="draft", required=True, tracking=True)

    line_ids = fields.One2many(
        "mizan.progress.claim.line", "claim_id", string="Measured Items",
        copy=True)

    # --- the certificate summary -----------------------------------------
    work_done_to_date = fields.Monetary(
        string="Value of Work Done to Date", compute="_compute_totals",
        store=True,
        help="Cumulative measured value across every item of the bill.")
    materials_on_site = fields.Monetary(
        string="Materials on Site",
        help="Cumulative value of material delivered and not yet built in, "
             "where the contract allows it to be claimed.")
    gross_to_date = fields.Monetary(
        string="Gross Value to Date", compute="_compute_totals", store=True)
    previous_certified = fields.Monetary(
        string="Less Previously Certified", compute="_compute_totals",
        store=True)
    amount_this_period = fields.Monetary(
        string="Value This Period", compute="_compute_totals", store=True)

    retention_percent = fields.Float(
        string="Retention %", compute="_compute_retention_percent",
        store=True, readonly=False)
    retention_to_date = fields.Monetary(
        string="Retention to Date", compute="_compute_totals", store=True)
    retention_amount = fields.Monetary(
        string="Less Retention This Period", compute="_compute_totals",
        store=True)
    advance_recovery = fields.Monetary(
        string="Less Advance Recovery", compute="_compute_totals", store=True,
        help="This claim's share of the advance, at the contract's recovery "
             "rate and never more than what is still outstanding.")
    net_payable = fields.Monetary(
        string="Net Payable This Period", compute="_compute_totals", store=True)
    percent_complete = fields.Float(
        string="% of Contract Certified", compute="_compute_totals", store=True)

    # --- the consultant --------------------------------------------------
    consultant_ref = fields.Char(
        string="Consultant's Certificate No.",
        help="The reference on the certificate the consultant issues back.")
    certified_by = fields.Char(string="Certified By")
    certified_date = fields.Date(string="Certified On")
    certified_amount = fields.Monetary(
        string="Amount Certified",
        help="What the consultant actually certified, when it differs from "
             "what was claimed. The difference is what the next claim has to "
             "argue about, so it is recorded rather than overwritten.")
    invoice_id = fields.Many2one(
        "account.move", string="Tax Invoice", readonly=True, copy=False)
    note = fields.Text()

    _sql_constraints = [
        ("claim_no_uniq", "unique(contract_id, sequence_no)",
         "That claim number already exists on this contract."),
    ]

    # ------------------------------------------------------------- computes
    @api.depends("contract_id.code", "sequence_no")
    def _compute_name(self):
        for claim in self:
            claim.name = "%s/IPA-%03d" % (
                claim.contract_id.code or "?", claim.sequence_no or 0)

    @api.depends("contract_id")
    def _compute_retention_percent(self):
        for claim in self:
            if claim.contract_id and not claim.retention_percent:
                claim.retention_percent = claim.contract_id.retention_percent

    def _previous_claims(self):
        """Every claim below this one on the same contract."""
        self.ensure_one()
        if not self.contract_id:
            return self.browse()
        return self.search([
            ("contract_id", "=", self.contract_id.id),
            ("sequence_no", "<", self.sequence_no),
            ("state", "!=", "cancel"),
        ])

    @api.depends("line_ids.this_amount", "line_ids.cumulative_amount",
                 "materials_on_site", "retention_percent", "sequence_no",
                 "contract_id", "state")
    def _compute_totals(self):
        for claim in self:
            cumulative = sum(claim.line_ids.mapped("cumulative_amount"))
            gross = cumulative + claim.materials_on_site
            previous = claim._previous_claims()
            # Previously certified is the highest gross already claimed, not a
            # sum: each claim states the job cumulatively, so adding them would
            # bill the early work once per claim.
            prior_gross = max(previous.mapped("gross_to_date") or [0.0])
            pct = claim.retention_percent or 0.0
            # Rounded here, not left to the store. The period figure below is
            # the difference between two cumulative ones, so if this is still
            # carrying fractions of a fils the difference disagrees with what
            # gets posted by exactly that fraction -- which is how a ledger
            # that is correct ends up not matching the document that made it.
            retention_to_date = claim.currency_id.round(gross * pct / 100.0) \
                if claim.currency_id else gross * pct / 100.0
            prior_retention = max(
                previous.mapped("retention_to_date") or [0.0])

            claim.work_done_to_date = cumulative
            claim.gross_to_date = gross
            claim.previous_certified = prior_gross
            this_period = gross - prior_gross
            claim.amount_this_period = this_period
            claim.retention_to_date = retention_to_date
            claim.retention_amount = retention_to_date - prior_retention

            contract = claim.contract_id
            recovery = 0.0
            if contract and this_period > 0:
                rate = (contract.advance_recovery_percent
                        or contract.advance_percent)
                if rate:
                    recovery = min(this_period * rate / 100.0,
                                   contract.advance_outstanding)
            claim.advance_recovery = recovery
            claim.net_payable = (
                this_period - claim.retention_amount - recovery)

            value = (contract.revised_contract_value
                     or contract.contract_value) if contract else 0.0
            claim.percent_complete = (
                cumulative / value * 100.0) if value else 0.0

    # ------------------------------------------------------------- lifecycle
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("sequence_no"):
                contract = vals.get("contract_id")
                highest = self.search(
                    [("contract_id", "=", contract)],
                    order="sequence_no desc", limit=1)
                vals["sequence_no"] = (highest.sequence_no or 0) + 1
        return super().create(vals_list)

    @api.onchange("contract_id")
    def _onchange_contract(self):
        """Offer the bill of quantities as soon as the contract is chosen."""
        if self.contract_id and not self.line_ids:
            self.line_ids = [
                (0, 0, {"boq_line_id": line.id, "this_qty": 0.0})
                for line in self._claimable_boq_lines()
            ]

    def _claimable_boq_lines(self):
        """Bill items that may be measured: the original bill, plus the
        variations the client has approved. A pending variation is deliberately
        not claimable — billing a change nobody has agreed to pay for is how
        contractors end up writing it off."""
        self.ensure_one()
        return self.contract_id.boq_line_ids.filtered(
            lambda l: not l.variation_id or l.variation_id.state == "approved")

    def action_load_boq(self):
        """Pull in bill items this claim does not carry yet.

        Additive rather than a rebuild: measured quantities already entered
        survive, and a variation approved after the claim was opened appears
        without retyping the sheet.
        """
        for claim in self:
            if claim.state not in ("draft",):
                raise UserError(_(
                    "%s is no longer a draft; its measured sheet is fixed.",
                    claim.name))
            if not claim.contract_id.boq_line_ids:
                raise UserError(_(
                    "%s has no bill of quantities. Add the priced items to the "
                    "contract first.", claim.contract_id.code))
            existing = set(claim.line_ids.mapped("boq_line_id").ids)
            missing = claim._claimable_boq_lines().filtered(
                lambda l: l.id not in existing)
            if not missing:
                raise UserError(_("Every claimable item is already on %s.",
                                  claim.name))
            claim.write({"line_ids": [
                (0, 0, {"boq_line_id": line.id}) for line in missing]})
        return True

    def _check_measurement(self):
        """Refuse a claim that measures more than the bill contains."""
        self.ensure_one()
        over = []
        for line in self.line_ids:
            if line.cumulative_qty - line.quantity > 0.0001:
                over.append("%s %s: %s claimed of %s" % (
                    line.item_no, line.name,
                    line.cumulative_qty, line.quantity))
        if over:
            raise UserError(_(
                "These items measure more than the bill of quantities allows. "
                "Either correct the quantity or raise a variation for the "
                "extra:\n\n%s", "\n".join(over)))
        negative = self.line_ids.filtered(lambda l: l.cumulative_qty < -0.0001)
        if negative:
            raise UserError(_(
                "A cumulative quantity cannot be negative: %s",
                ", ".join(negative.mapped("item_no"))))

    def action_submit(self):
        for claim in self:
            if claim.state != "draft":
                raise UserError(_("%s is not a draft.", claim.name))
            if not claim.line_ids:
                raise UserError(_("%s has nothing measured on it.", claim.name))
            unfinished = claim._previous_claims().filtered(
                lambda c: c.state in ("draft", "submitted"))
            if unfinished:
                raise UserError(_(
                    "Claim %(this)s cannot go out while %(open)s is still "
                    "open. Claims are cumulative: certifying them out of order "
                    "bills the same work twice.",
                    this=claim.name,
                    open=", ".join(unfinished.mapped("name"))))
            claim._check_measurement()
            if claim.amount_this_period <= 0:
                raise UserError(_(
                    "%s claims nothing beyond what was already certified.",
                    claim.name))
            claim.state = "submitted"
            claim.message_post(body=_(
                "Submitted to the consultant: %(amount)s for the period, "
                "%(pct).1f%% of the contract certified to date.",
                amount=claim.amount_this_period, pct=claim.percent_complete))
        return True

    def action_certify(self):
        for claim in self:
            if claim.state != "submitted":
                raise UserError(_(
                    "%s has not been submitted to the consultant.", claim.name))
            if not claim.certified_by:
                raise UserError(_(
                    "Record who certified %s before marking it certified.",
                    claim.name))
            claim._check_measurement()
            claim.write({
                "state": "certified",
                "certified_date": (claim.certified_date
                                   or fields.Date.context_today(claim)),
                "certified_amount": (claim.certified_amount
                                     or claim.amount_this_period),
            })
        return True

    def action_reject(self):
        """Send it back to the site to be re-measured."""
        for claim in self:
            if claim.state != "submitted":
                raise UserError(_("%s is not out with the consultant.",
                                  claim.name))
            claim.state = "draft"
            claim.message_post(body=_("Returned by the consultant for re-measurement."))
        return True

    def action_draft(self):
        for claim in self:
            if claim.invoice_id and claim.invoice_id.state == "posted":
                raise UserError(_(
                    "%s is invoiced on %s. Credit the invoice before reopening "
                    "the claim.", claim.name, claim.invoice_id.name))
            claim.state = "draft"
        return True

    def action_cancel(self):
        for claim in self:
            if claim.invoice_id and claim.invoice_id.state == "posted":
                raise UserError(_(
                    "%s is invoiced on %s.", claim.name, claim.invoice_id.name))
            claim.state = "cancel"
        return True

    # -------------------------------------------------------------- invoicing
    def _claim_revenue_account(self):
        """Progress billings, not revenue.

        The claim is a demand for cash against work certified. Revenue is
        earned by doing the work and is recognised separately on percentage of
        completion. Crediting revenue here as well counts the job twice, and
        the two figures never agree because billing runs ahead of or behind the
        work by design.
        """
        account = self.env["account.account"].search(
            [("code", "=", "204004")], limit=1)
        if not account:
            raise UserError(_(
                "Account 204004 (Billings in Excess of Work Done) is missing. "
                "Run scripts/complete_coa.py against this database."))
        return account

    def action_create_invoice(self):
        """Raise the tax invoice for the certified amount, item by item."""
        self.ensure_one()
        if self.state != "certified":
            raise UserError(_(
                "Certify %s before invoicing it. An uncertified claim is a "
                "request, not a debt.", self.name))
        if self.invoice_id:
            raise UserError(_(
                "%s is already invoiced on %s.", self.name, self.invoice_id.name))
        contract = self.contract_id
        journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", contract.company_id.id)],
            limit=1)
        if not journal:
            raise UserError(_("No sales journal in this company."))
        account = self._claim_revenue_account()
        analytic = ({str(contract.analytic_account_id.id): 100}
                    if contract.analytic_account_id else False)
        # The company's default, not "whichever sale tax sorts first". There
        # are fourteen 5% sale taxes in the UAE chart, one per emirate, and the
        # VAT return reports sales by emirate — picking one arbitrarily files
        # the revenue against the wrong one.
        taxes = contract.company_id.account_sale_tax_id
        if not taxes:
            raise UserError(_(
                "No default sales tax on %s. Set it before invoicing, or the "
                "VAT lands on whichever emirate happens to sort first.",
                contract.company_id.display_name))

        lines = []
        for line in self.line_ids.filtered(
                lambda l: abs(l.this_amount) > 0.0001):
            lines.append((0, 0, {
                "name": "%s %s — %s %s @ %s" % (
                    line.item_no, line.name, line.this_qty,
                    line.unit or "", line.rate),
                "account_id": account.id,
                "quantity": line.this_qty,
                "price_unit": line.rate,
                "tax_ids": [(6, 0, taxes.ids)],
                "analytic_distribution": analytic,
                "mizan_cost_code_id": (line.cost_code_id.id
                                       if line.cost_code_id else False),
            }))
        materials_movement = (
            self.materials_on_site
            - max(self._previous_claims().mapped("materials_on_site") or [0.0]))
        if abs(materials_movement) > 0.0001:
            lines.append((0, 0, {
                "name": _("Materials on site — movement this period"),
                "account_id": account.id,
                "quantity": 1,
                "price_unit": materials_movement,
                "tax_ids": [(6, 0, taxes.ids)],
                "analytic_distribution": analytic,
            }))
        if not lines:
            raise UserError(_("%s has no movement to invoice.", self.name))

        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "journal_id": journal.id,
            "partner_id": contract.partner_id.id,
            "invoice_date": self.date,
            "date": self.date,
            "ref": _("%(claim)s — progress claim %(no)s",
                     claim=contract.code, no=self.sequence_no),
            "mizan_contract_id": contract.id,
            "mizan_retention_percent": self.retention_percent,
            "invoice_line_ids": lines,
        })
        self.write({"state": "invoiced", "invoice_id": invoice.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "views": [[False, "form"]],
        }

    def action_post_invoice_and_deduct(self):
        """Post the invoice, withhold the retention, recover the advance.

        The three belong together. Done by hand they drift apart: the invoice
        gets posted, the retention entry waits for month end, the advance
        recovery is worked out on a spreadsheet, and the client is asked for a
        gross figure the contract says they do not owe.
        """
        self.ensure_one()
        invoice = self.invoice_id
        if not invoice:
            raise UserError(_("Raise the invoice for %s first.", self.name))
        if invoice.state == "draft":
            invoice.action_post()
        if self.retention_amount and not invoice.mizan_retention_move_id:
            invoice.action_withhold_retention()
        if self.advance_recovery and not invoice.mizan_advance_move_id:
            invoice.action_recover_advance()
        return True

    def action_view_invoice(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.invoice_id.id,
            "views": [[False, "form"]],
        }


class MizanProgressClaimLine(models.Model):
    """One measured item on a progress claim."""

    _name = "mizan.progress.claim.line"
    _description = "Progress Claim Item"
    _order = "claim_id, sequence, id"

    claim_id = fields.Many2one(
        "mizan.progress.claim", required=True, ondelete="cascade", index=True)
    boq_line_id = fields.Many2one(
        "mizan.contract.boq.line", string="Bill Item", required=True,
        ondelete="restrict", index=True)
    company_id = fields.Many2one(related="claim_id.company_id", store=True)
    currency_id = fields.Many2one(related="claim_id.currency_id")
    sequence = fields.Integer(related="boq_line_id.sequence", store=True)
    state = fields.Selection(related="claim_id.state", store=True)

    section = fields.Char(related="boq_line_id.section", store=True)
    item_no = fields.Char(related="boq_line_id.item_no", store=True)
    name = fields.Char(related="boq_line_id.name", store=True)
    unit = fields.Char(related="boq_line_id.unit")
    quantity = fields.Float(
        string="Bill Qty", related="boq_line_id.quantity")
    rate = fields.Monetary(string="Rate", related="boq_line_id.rate")
    item_value = fields.Monetary(string="Item Value", related="boq_line_id.amount")
    cost_code_id = fields.Many2one(related="boq_line_id.cost_code_id")

    previous_qty = fields.Float(
        string="Previous Qty", compute="_compute_previous",
        digits="Product Unit of Measure")
    previous_amount = fields.Monetary(
        string="Previous", compute="_compute_previous")

    this_qty = fields.Float(
        string="Qty This Period", digits="Product Unit of Measure",
        help="What was measured on site during this period. Negative to "
             "correct an earlier over-measurement.")
    this_amount = fields.Monetary(
        string="This Period", compute="_compute_amounts", store=True)
    cumulative_qty = fields.Float(
        string="Cumulative Qty", compute="_compute_amounts", store=True,
        digits="Product Unit of Measure")
    cumulative_amount = fields.Monetary(
        string="Cumulative", compute="_compute_amounts", store=True)
    percent_complete = fields.Float(
        string="% Complete", compute="_compute_amounts", store=True)
    is_over_measured = fields.Boolean(compute="_compute_amounts", store=True)
    note = fields.Char()

    _sql_constraints = [
        ("item_claim_uniq", "unique(claim_id, boq_line_id)",
         "That bill item is already measured on this claim."),
    ]

    @api.depends("boq_line_id", "claim_id.sequence_no", "claim_id.contract_id")
    def _compute_previous(self):
        """What earlier claims measured on this same bill item.

        Derived rather than snapshotted: an earlier claim cannot change once it
        is invoiced, so recomputing always gives the same answer, and there is
        no stored copy to fall out of step with the claim it came from.
        """
        for line in self:
            claim = line.claim_id
            if not (line.boq_line_id and claim.contract_id):
                line.previous_qty = 0.0
                line.previous_amount = 0.0
                continue
            earlier = self.search([
                ("boq_line_id", "=", line.boq_line_id.id),
                ("claim_id.contract_id", "=", claim.contract_id.id),
                ("claim_id.sequence_no", "<", claim.sequence_no),
                ("claim_id.state", "!=", "cancel"),
            ])
            qty = sum(earlier.mapped("this_qty"))
            line.previous_qty = qty
            line.previous_amount = qty * line.rate

    @api.depends("this_qty", "previous_qty", "rate", "quantity")
    def _compute_amounts(self):
        for line in self:
            line.this_amount = line.this_qty * line.rate
            line.cumulative_qty = line.previous_qty + line.this_qty
            line.cumulative_amount = line.cumulative_qty * line.rate
            line.percent_complete = (
                line.cumulative_qty / line.quantity * 100.0
                if line.quantity else 0.0)
            line.is_over_measured = (
                line.cumulative_qty - line.quantity > 0.0001)


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    boq_line_ids = fields.One2many(
        "mizan.contract.boq.line", "contract_id", string="Bill of Quantities")
    boq_total = fields.Monetary(
        string="Bill of Quantities Total", compute="_compute_boq_rollup")
    boq_original_total = fields.Monetary(
        string="Original Bill", compute="_compute_boq_rollup")
    boq_variation_total = fields.Monetary(
        string="Variation Items", compute="_compute_boq_rollup")
    boq_mismatch = fields.Boolean(
        compute="_compute_boq_rollup",
        help="The priced items do not add up to the contract value. One of the "
             "two is wrong, and the claims will be measured against the bill.")
    claim_ids = fields.One2many(
        "mizan.progress.claim", "contract_id", string="Progress Claims")
    claim_count = fields.Integer(compute="_compute_claim_rollup")
    certified_to_date = fields.Monetary(
        string="Certified to Date", compute="_compute_claim_rollup",
        help="The highest gross value any certified claim has reached — the "
             "measured position, as against the accounting one.")
    measured_completion_percent = fields.Float(
        string="% Complete (Measured)", compute="_compute_claim_rollup",
        help="Progress by measurement rather than by cost. The consultant "
             "certifies this one; the ledger recognises the other. A wide gap "
             "between them is the earliest sign a job is going wrong.")

    def _compute_boq_rollup(self):
        for contract in self:
            claimable = contract.boq_line_ids.filtered(
                lambda l: not l.variation_id or l.variation_id.state == "approved")
            original = claimable.filtered(lambda l: not l.variation_id)
            contract.boq_original_total = sum(original.mapped("amount"))
            contract.boq_variation_total = sum(
                (claimable - original).mapped("amount"))
            contract.boq_total = sum(claimable.mapped("amount"))
            target = contract.revised_contract_value or contract.contract_value
            contract.boq_mismatch = bool(claimable) and (
                abs(contract.boq_total - target) > 0.01)

    @api.depends("claim_ids.state", "claim_ids.gross_to_date",
                 "claim_ids.work_done_to_date", "revised_contract_value")
    def _compute_claim_rollup(self):
        for contract in self:
            contract.claim_count = len(contract.claim_ids)
            certified = contract.claim_ids.filtered(
                lambda c: c.state in ("certified", "invoiced"))
            contract.certified_to_date = max(
                certified.mapped("gross_to_date") or [0.0])
            value = contract.revised_contract_value or contract.contract_value
            measured = max(certified.mapped("work_done_to_date") or [0.0])
            contract.measured_completion_percent = (
                measured / value * 100.0) if value else 0.0

    def action_value_from_boq(self):
        """Take the contract value from the priced bill.

        The bill is the priced document both sides signed; a contract value
        typed separately is a second version of the same number waiting to
        disagree with it.
        """
        for contract in self:
            if not contract.boq_line_ids:
                raise UserError(_(
                    "%s has no bill of quantities.", contract.code))
            contract.contract_value = contract.boq_original_total
        return True

    def action_view_claims(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Progress Claims"),
            "res_model": "mizan.progress.claim",
            "domain": [("contract_id", "=", self.id)],
            "views": [[False, "list"], [False, "form"]],
            "context": {"default_contract_id": self.id},
        }

    def action_new_claim(self):
        """Open the next claim, pre-measured with what was claimed before."""
        self.ensure_one()
        if not self.boq_line_ids:
            raise UserError(_(
                "Add the priced bill of quantities to %s before claiming "
                "against it.", self.code))
        claim = self.env["mizan.progress.claim"].create({
            "contract_id": self.id,
            "date": fields.Date.context_today(self),
        })
        claim.write({"line_ids": [
            (0, 0, {"boq_line_id": line.id})
            for line in claim._claimable_boq_lines()]})
        return {
            "type": "ir.actions.act_window",
            "res_model": "mizan.progress.claim",
            "res_id": claim.id,
            "views": [[False, "form"]],
        }
