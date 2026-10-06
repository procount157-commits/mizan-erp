# -*- coding: utf-8 -*-
"""A second opinion on the books, deliberately not sharing code with health_check.py.

    docker exec mizan-odoo sh -c "odoo shell -d DB --no-http \
        --config=/etc/odoo/odoo.conf --db_user odoo --db_password PASS" \
        < scripts/audit_ledger.py

health_check.py asks whether the ledger balances and whether the apps are
joined up. This asks the next question: whether the figures mean what the
documents say they mean, and whether anything here would cost money. The two
are deliberately written apart. An audit that reuses the code it is auditing
agrees with it for the same reason it is wrong.

Three groups, and the distinction matters when reading the output:

  * TIES -- a subledger recomputed from the documents against the account that
    is supposed to hold it. A failure means the ledger and the paperwork
    disagree, and one of them is being shown to somebody.
  * EXPOSURE -- correct arithmetic that still costs money: tax not charged,
    a vendor reference billed twice, revenue recognised ahead of the work.
  * ODDITIES -- not wrong, but not usually deliberate either. Each one is
    something a person should look at once and then either fix or ignore.

Read-only. It opens no transaction that writes.
"""

from collections import defaultdict

from odoo import fields

FAILS, WARNS, PASSES = [], [], []


def m(v):
    return "{:>16,.2f}".format(v or 0.0)


def check(label, ok, detail="", warn=False):
    bucket = PASSES if ok else (WARNS if warn else FAILS)
    bucket.append((label, detail))
    print("  [%s] %-50s %s"
          % ("OK  " if ok else ("WARN" if warn else "FAIL"), label, detail))


def heading(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def account_by_code(code):
    return env["account.account"].search([("code", "=", code)], limit=1)


def posted_balance(account):
    """What the ledger holds on an account, posted entries only."""
    if not account:
        return None
    return sum(env["account.move.line"].search(
        [("account_id", "=", account.id),
         ("parent_state", "=", "posted")]).mapped("balance"))


company = env.company
today = fields.Date.context_today(env.user)
print("Auditing %s — %s — %s" % (company.name, company.currency_id.name, today))

sales = env["account.move"].search(
    [("move_type", "=", "out_invoice"), ("state", "=", "posted")])
bills = env["account.move"].search(
    [("move_type", "=", "in_invoice"), ("state", "=", "posted")])

# ---------------------------------------------------------------------- TIES
heading("TIES — the accounts against the documents behind them")

# The tax accounts are read off the taxes themselves rather than guessed from
# a code. A chart can number them anywhere, and an audit that guesses the
# account is auditing its own guess.
output_accounts = env["account.account"]
input_accounts = env["account.account"]
for tax in env["account.tax"].search([]):
    accounts = (tax.invoice_repartition_line_ids.mapped("account_id")
                | tax.refund_repartition_line_ids.mapped("account_id"))
    if tax.type_tax_use == "sale":
        output_accounts |= accounts.filtered(
            lambda a: a.account_type.startswith("liability"))
    else:
        input_accounts |= accounts.filtered(
            lambda a: a.account_type.startswith("asset"))

for label, accounts, types in (
        ("output VAT = tax on sales documents", output_accounts,
         ("out_invoice", "out_refund")),
        ("input VAT = tax on purchase documents", input_accounts,
         ("in_invoice", "in_refund"))):
    if not accounts:
        check(label, False, "no account is mapped on any tax", warn=True)
        continue
    gl = sum(posted_balance(a) or 0.0 for a in accounts)
    doc = sum(env["account.move.line"].search([
        ("parent_state", "=", "posted"), ("tax_line_id", "!=", False),
        ("account_id", "in", accounts.ids),
        ("move_id.move_type", "in", types)]).mapped("balance"))
    check(label, abs(gl - doc) < 0.01,
          "%s vs %s  (%s)" % (m(gl), m(doc),
                              ", ".join(accounts.mapped("code"))))

claims = env["mizan.progress.claim"].search(
    [("state", "in", ("certified", "invoiced"))])
retention_account = account_by_code("107003")
if retention_account:
    gl = posted_balance(retention_account)
    doc = sum(claims.mapped("retention_amount"))
    check("retention held = retention on the claims",
          abs((gl or 0.0) - doc) < 0.01, "%s vs %s" % (m(gl), m(doc)))

advance_account = account_by_code("204002")
if advance_account:
    gl = abs(posted_balance(advance_account) or 0.0)
    doc = sum(env["mizan.contract"].search([]).mapped("advance_outstanding"))
    check("advance held = advance still to recover",
          abs(gl - doc) < 0.01, "%s vs %s" % (m(gl), m(doc)))

# Costs only, by the account the line hits. Summing every analytic line
# instead would add the revenue side in and report a difference on a contract
# that is perfectly correct -- which this check did on its first run.
COST_TYPES = ("expense_direct_cost", "expense", "expense_depreciation")
drift = []
for contract in env["mizan.contract"].search([("state", "!=", "cancel")]):
    if not contract.analytic_account_id:
        continue
    analytic = -sum(env["account.analytic.line"].search([
        ("account_id", "=", contract.analytic_account_id.id),
        ("general_account_id.account_type", "in", COST_TYPES),
    ]).mapped("amount"))
    if abs(analytic - (contract.cost_incurred or 0.0)) > 0.01:
        drift.append("%s: analytic %s, contract says %s"
                     % (contract.code, m(analytic), m(contract.cost_incurred)))
check("cost to date = the analytic lines behind it", not drift,
      drift[0] if drift else "every contract agrees")

# ------------------------------------------------------------------ EXPOSURE
heading("EXPOSURE — arithmetic that is right and still costs money")

untaxed = sales.invoice_line_ids.filtered(
    lambda l: l.display_type == "product" and not l.tax_ids
    and not l.currency_id.is_zero(l.price_subtotal))
check("every posted sales line carries a tax", not untaxed,
      "; ".join("%s %s" % (l.move_id.name, m(l.price_subtotal))
                for l in untaxed[:3])
      or "%s invoice(s) checked" % len(sales))
if untaxed:
    print("        VAT not charged on %s of turnover"
          % m(sum(untaxed.mapped("price_subtotal")) * 0.05))

wrong_rate = []
for invoice in sales:
    base = sum(invoice.invoice_line_ids.filtered(
        lambda l: l.display_type == "product"
        and any(t.amount == 5.0 for t in l.tax_ids)).mapped("price_subtotal"))
    if abs(base * 0.05 - invoice.amount_tax) > 0.01:
        wrong_rate.append("%s: 5%% of %s is not %s"
                          % (invoice.name, m(base), m(invoice.amount_tax)))
check("VAT is 5% of the standard-rated base", not wrong_rate,
      wrong_rate[0] if wrong_rate else "%s invoice(s) checked" % len(sales))

# A reference billed twice is the cheapest way for a contractor to lose money,
# and the one nobody notices, because both bills are individually correct.
by_reference = defaultdict(list)
for bill in bills:
    if bill.ref:
        by_reference[(bill.partner_id.id, bill.ref.strip().lower())].append(bill)
duplicates = [v for v in by_reference.values() if len(v) > 1]
check("no vendor reference billed twice", not duplicates,
      "; ".join("%s = %s" % (b[0].ref, ", ".join(x.name for x in b))
                for b in duplicates[:2])
      or "%s bill(s) checked" % len(bills))
if duplicates:
    print("        at risk: %s"
          % m(sum(b[1].amount_total for b in duplicates)))

ahead = []
for contract in env["mizan.contract"].search([("state", "!=", "cancel")]):
    earned = ((contract.contract_value or 0.0)
              * (contract.completion_percent or 0.0) / 100.0)
    if (contract.revenue_recognised or 0.0) > earned + 0.01:
        ahead.append("%s: recognised %s, earned %s"
                     % (contract.code, m(contract.revenue_recognised), m(earned)))
check("no revenue recognised ahead of the work", not ahead,
      ahead[0] if ahead else "%s contract(s) checked"
      % env["mizan.contract"].search_count([("state", "!=", "cancel")]))

over_measured = []
for line in env["mizan.contract.boq.line"].search([]):
    last = env["mizan.progress.claim.line"].search(
        [("boq_line_id", "=", line.id),
         ("state", "in", ("certified", "invoiced"))], order="id desc", limit=1)
    cumulative = getattr(last, "cumulative_quantity", 0.0) or 0.0
    if cumulative > (line.quantity or 0.0) + 0.0001:
        over_measured.append("%s: %s certified against %s in the bill"
                             % (line.item_no, cumulative, line.quantity))
check("nothing measured beyond the bill of quantities", not over_measured,
      over_measured[0] if over_measured
      else "%s item(s) checked" % env["mizan.contract.boq.line"].search_count([]))

# --------------------------------------------------------------- ODDITIES
heading("ODDITIES — not wrong, but somebody should look once")

own_partners = (company.partner_id | company.partner_id.child_ids)
self_billed = (sales | bills).filtered(
    lambda mv: mv.commercial_partner_id in own_partners.mapped("commercial_partner_id"))
check("no invoice issued to the company itself", not self_billed,
      "; ".join("%s %s" % (mv.name, m(mv.amount_total)) for mv in self_billed[:3])
      or "none", warn=True)

unlabelled = (sales | bills).invoice_line_ids.filtered(
    lambda l: l.display_type == "product" and not l.name)
check("every invoice line says what it is for", not unlabelled,
      "%s line(s) with no description" % len(unlabelled), warn=True)

future = env["account.move"].search(
    [("state", "=", "posted"), ("date", ">", today)])
check("nothing posted with a future date", not future,
      "%s entry(ies)" % len(future), warn=True)

credit_customers = []
receivables = env["account.account"].search(
    [("account_type", "=", "asset_receivable")])
for group in env["account.move.line"].read_group(
        [("account_id", "in", receivables.ids), ("parent_state", "=", "posted"),
         ("partner_id", "!=", False)], ["balance"], ["partner_id"]):
    if group["balance"] < -0.01:
        credit_customers.append("%s %s" % (group["partner_id"][1],
                                           m(group["balance"])))
check("no customer sitting in credit on receivables", not credit_customers,
      "; ".join(credit_customers[:2]) or "every customer is a debtor", warn=True)

open_lines = env["account.bank.statement.line"].search(
    [("is_reconciled", "=", False)])
check("every bank line is explained", not open_lines,
      "%s line(s) open" % len(open_lines), warn=True)

no_trn = env["res.partner"].search([
    ("is_company", "=", True), ("vat", "=", False),
    "|", ("customer_rank", ">", 0), ("supplier_rank", ">", 0)])
check("every company we trade with has a TRN", not no_trn,
      "; ".join(no_trn.mapped("name")[:3]) or "none missing", warn=True)

heading("%s failure(s), %s warning(s), %s passed"
        % (len(FAILS), len(WARNS), len(PASSES)))
if FAILS:
    print("The ledger and the documents disagree. In order:")
    for label, detail in FAILS:
        print("  * %s — %s" % (label, detail))
else:
    print("Nothing here contradicts the documents.")
if WARNS:
    print()
    print("Worth one look each:")
    for label, detail in WARNS:
        print("  * %s — %s" % (label, detail))
print("=" * 78)
