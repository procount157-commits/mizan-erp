# -*- coding: utf-8 -*-
"""Share head-office overhead across the jobs, without lying about progress.

Every contractor asks the same question at month end: the office cost 20,000
this month — rent, admin salaries, the licence, the phones — so how much of it
did each job eat, and which jobs actually made money once it is paid for?

The tempting answer is to post the overhead into each job's cost centre. That
answer is wrong, and in this system it is wrong twice over. Progress here is
measured cost-to-cost: cost to date divided by the cost at completion. Office
rent pushed into a job raises its cost to date, so the job reports itself
further along than the site is, and revenue is recognised for work nobody has
done. IFRS 15 (paragraph 98) says as much: general and administrative costs are
not costs of fulfilling a contract unless the contract lets you charge them to
the client.

So the allocation is MANAGEMENT ANALYSIS, kept apart from the ledger:

  * No journal entry. The overhead stays in the profit and loss where it was
    booked; the trial balance, the VAT return and the statements do not move.
  * Analytic lines on each job's cost centre, carrying no general account and
    marked as an allocation, so the cost-to-cost calculation never sees them.
  * On the contract, three figures side by side: margin to date, the overhead
    share, and the margin left after it. That last figure is the one a
    contractor prices the next tender from.

Costs that genuinely belong to a site — the site engineer, the site office, the
plant — are not overhead and should never reach this pool: they are charged to
the job's cost centre when they are booked, and they DO drive progress.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


BASES = [
    ("cost_to_date", "Direct cost to date"),
    ("direct_cost", "Direct cost in the period"),
    ("billing", "Amount invoiced in the period"),
    ("contract_value", "Contract value"),
    ("equal", "Equally between jobs"),
]


class MizanOverheadAllocation(models.Model):
    _name = "mizan.overhead.allocation"
    _description = "Overhead Allocation"
    _inherit = ["mail.thread"]
    _order = "date_to desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    state = fields.Selection([("draft", "Draft"), ("posted", "Allocated")],
                             default="draft", required=True, tracking=True)

    basis = fields.Selection(
        BASES, required=True, default="cost_to_date", tracking=True,
        help="What each job's share is proportional to. Direct cost is the "
             "usual choice: a job that kept the office busy carries more of the "
             "office. Cost TO DATE is the default because one month's cost is "
             "lumpy — a quiet month on one site would hand the whole office to "
             "the other.")
    account_ids = fields.Many2many(
        "account.account", string="Overhead accounts",
        domain="[('account_type', 'in', ('expense', 'expense_depreciation'))]",
        default=lambda self: self._default_accounts(),
        help="The expense accounts the pool is drawn from. Only lines carrying "
             "no cost centre are counted: a cost already charged to a job is "
             "not overhead.")
    pool_amount = fields.Monetary(
        string="Overhead in the period", compute="_compute_pool",
        help="Posted, in the chosen accounts, between the two dates, and "
             "charged to no job.")
    amount_override = fields.Monetary(
        string="Allocate instead",
        help="Leave empty to allocate the whole pool. Fill it to allocate a "
             "different figure — a budgeted monthly overhead, for instance.")
    amount_to_allocate = fields.Monetary(compute="_compute_pool")

    line_ids = fields.One2many("mizan.overhead.allocation.line",
                               "allocation_id", string="Jobs")
    allocated_total = fields.Monetary(compute="_compute_totals")
    note = fields.Text()

    _sql_constraints = [
        ("period_uniq", "unique(company_id, date_from, date_to)",
         "This period already has an overhead allocation."),
    ]

    @api.model
    def _default_accounts(self):
        return self.env["account.account"].search([
            ("account_type", "in", ("expense", "expense_depreciation")),
            ("company_ids", "in", self.env.company.id)])

    @api.depends("date_to")
    def _compute_name(self):
        for record in self:
            record.name = (_("Overhead %s", record.date_to.strftime("%Y-%m"))
                           if record.date_to else _("New allocation"))

    def _pool_lines(self):
        self.ensure_one()
        return self.env["account.move.line"].search([
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
            ("date", ">=", self.date_from), ("date", "<=", self.date_to),
            ("account_id", "in", self.account_ids.ids),
            ("analytic_distribution", "=", False),
        ])

    @api.depends("date_from", "date_to", "account_ids", "amount_override")
    def _compute_pool(self):
        for record in self:
            if record.date_from and record.date_to and record.account_ids:
                record.pool_amount = sum(record._pool_lines().mapped("balance"))
            else:
                record.pool_amount = 0.0
            record.amount_to_allocate = (record.amount_override
                                         or record.pool_amount)

    @api.depends("line_ids.amount")
    def _compute_totals(self):
        for record in self:
            record.allocated_total = sum(record.line_ids.mapped("amount"))

    # ------------------------------------------------------------ bases
    def _basis_value(self, contract):
        self.ensure_one()
        if self.basis == "equal":
            return 1.0
        if self.basis == "cost_to_date":
            return contract.cost_incurred
        if self.basis == "contract_value":
            return contract.revised_contract_value or contract.contract_value
        if self.basis == "billing":
            invoices = contract.claim_ids.mapped("invoice_id").filtered(
                lambda move: move.state == "posted"
                and self.date_from <= move.invoice_date <= self.date_to)
            return sum(invoices.mapped("amount_untaxed"))
        # Direct cost booked to the job in the period — the same lines the
        # progress calculation counts, never the allocations themselves.
        lines = self.env["account.analytic.line"].search([
            ("account_id", "=", contract.analytic_account_id.id),
            ("date", ">=", self.date_from), ("date", "<=", self.date_to),
            ("mizan_overhead_allocation_id", "=", False),
            ("general_account_id.account_type", "in",
             ("expense_direct_cost", "expense", "expense_depreciation")),
        ])
        return -sum(lines.mapped("amount"))

    def action_compute(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Reset it to draft before recomputing."))
            contracts = self.env["mizan.contract"].search([
                ("company_id", "=", record.company_id.id),
                ("state", "=", "running")])
            values = {c: max(record._basis_value(c), 0.0) for c in contracts}
            total = sum(values.values())
            if not total:
                raise UserError(_(
                    "No running job has anything on this basis in the period, "
                    "so there is nothing to share the overhead by. Try another "
                    "basis."))
            amount = record.amount_to_allocate
            rows, given = [], 0.0
            ordered = sorted(values.items(), key=lambda item: -item[1])
            for index, (contract, value) in enumerate(ordered):
                share = value / total
                # The last job takes the rounding, so the parts add up to the
                # whole to the fils.
                part = (record.currency_id.round(amount - given)
                        if index == len(ordered) - 1
                        else record.currency_id.round(amount * share))
                given += part
                rows.append((0, 0, {"contract_id": contract.id,
                                    "basis_value": value,
                                    "share_percent": share * 100,
                                    "amount": part}))
            record.line_ids = [(5, 0, 0)] + rows
        return True

    def action_post(self):
        Line = self.env["account.analytic.line"]
        for record in self:
            if not record.line_ids:
                record.action_compute()
            for line in record.line_ids:
                if not line.contract_id.analytic_account_id or not line.amount:
                    continue
                # No general account on purpose: the line is a management
                # figure, not a booking, and the cost-to-cost calculation only
                # counts lines that carry one.
                line.analytic_line_id = Line.create({
                    "name": _("Overhead share — %(period)s (%(basis)s)",
                              period=record.name,
                              basis=dict(BASES)[record.basis]),
                    "account_id": line.contract_id.analytic_account_id.id,
                    "date": record.date_to,
                    "amount": -line.amount,
                    "company_id": record.company_id.id,
                    "mizan_overhead_allocation_id": record.id,
                })
            record.state = "posted"
        return True

    def action_reset(self):
        for record in self:
            record.line_ids.mapped("analytic_line_id").unlink()
            record.state = "draft"
        return True

    def unlink(self):
        if any(record.state == "posted" for record in self):
            raise UserError(_("Reset the allocation to draft before deleting it."))
        return super().unlink()


class MizanOverheadAllocationLine(models.Model):
    _name = "mizan.overhead.allocation.line"
    _description = "Overhead Allocation Line"
    _order = "amount desc"

    allocation_id = fields.Many2one("mizan.overhead.allocation", required=True,
                                    ondelete="cascade")
    currency_id = fields.Many2one(related="allocation_id.currency_id")
    contract_id = fields.Many2one("mizan.contract", required=True)
    basis_value = fields.Monetary(string="Basis")
    share_percent = fields.Float(string="Share %", digits=(5, 2))
    amount = fields.Monetary(string="Overhead share")
    analytic_line_id = fields.Many2one("account.analytic.line", readonly=True)


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    mizan_overhead_allocation_id = fields.Many2one(
        "mizan.overhead.allocation", string="Overhead allocation",
        index=True, ondelete="cascade", readonly=True)


class MizanContract(models.Model):
    _inherit = "mizan.contract"

    overhead_allocated = fields.Monetary(
        string="Overhead share to date", compute="_compute_overhead",
        help="Head-office overhead allocated to this job for management "
             "analysis. It is not part of the job's cost and does not move "
             "progress or revenue.")
    margin_to_date = fields.Monetary(
        string="Margin to date", compute="_compute_overhead",
        help="Revenue recognised less direct cost to date.")
    margin_after_overhead = fields.Monetary(
        string="Margin after overhead", compute="_compute_overhead",
        help="What the job has really contributed once it carries its share "
             "of the office. The figure to price the next tender from.")

    def _compute_overhead(self):
        Line = self.env["account.analytic.line"]
        for contract in self:
            shares = Line.search([
                ("account_id", "=", contract.analytic_account_id.id),
                ("mizan_overhead_allocation_id", "!=", False)]) \
                if contract.analytic_account_id else Line
            contract.overhead_allocated = -sum(shares.mapped("amount"))
            contract.margin_to_date = (contract.revenue_recognised
                                       - contract.cost_incurred)
            contract.margin_after_overhead = (contract.margin_to_date
                                              - contract.overhead_allocated)
