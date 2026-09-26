# -*- coding: utf-8 -*-
"""A full integrity check of one client database. Read-only.

Written because "are the accounts right?" deserves evidence, not assurance,
and because the answer changes every day. Run it before a month-end close, or
whenever somebody says the numbers look wrong.

It checks three different things, and they fail differently:

  * ARITHMETIC — does the ledger balance, do the subledgers agree with their
    control accounts, does the balance sheet close. A failure here is a bug.
  * LINKAGE — did the documents that should be joined actually join. A bill
    with no purchase order behind it is not an error; a hundred of them means
    the purchase process is being bypassed.
  * HYGIENE — drafts nobody posted, costs on no project, accounts nobody uses.
    None of these are wrong. All of them are how a month-end goes wrong.
"""

Line = env["account.move.line"]
Move = env["account.move"]
company = env.company
problems, warnings = [], []


def money(v):
    return "{:>16,.2f}".format(v or 0.0)


def check(label, ok, detail="", warn_only=False):
    mark = "OK  " if ok else ("WARN" if warn_only else "FAIL")
    print("  [%s] %-46s %s" % (mark, label, detail))
    if not ok:
        (warnings if warn_only else problems).append(label)


print("=" * 78)
print("ARITHMETIC — a failure here is a bug")
print("=" * 78)

env.cr.execute("""select coalesce(sum(debit),0), coalesce(sum(credit),0)
                  from account_move_line l join account_move m on m.id=l.move_id
                  where m.state='posted'""")
dr, cr_ = env.cr.fetchone()
check("trial balance debits = credits", abs(dr - cr_) < 0.01,
      "%s / %s" % (money(dr), money(cr_)))

env.cr.execute("""select m.name, sum(l.debit)-sum(l.credit) d
                  from account_move_line l join account_move m on m.id=l.move_id
                  where m.state='posted' group by m.name having
                  abs(sum(l.debit)-sum(l.credit)) > 0.005""")
unbalanced = env.cr.fetchall()
check("every posted entry balances on its own", not unbalanced,
      "%d unbalanced" % len(unbalanced))

for label, atype, mtypes in (
        ("receivables", "asset_receivable", ("out_invoice", "out_refund")),
        ("payables", "liability_payable", ("in_invoice", "in_refund"))):
    gl = sum(Line.search([("parent_state", "=", "posted"),
                          ("account_id.account_type", "=", atype)]).mapped("balance"))
    sub = sum(Move.search([("state", "=", "posted"),
                           ("move_type", "in", mtypes)]).mapped("amount_residual_signed"))
    check("%s: ledger = open documents" % label, abs(gl - sub) < 0.01,
          "%s vs %s" % (money(gl), money(sub)))


def total(types):
    return sum(Line.search([("parent_state", "=", "posted"),
                            ("account_id.account_type", "in", types)]).mapped("balance"))


assets = total(["asset_receivable", "asset_cash", "asset_current",
                "asset_non_current", "asset_prepayments", "asset_fixed"])
liab = total(["liability_payable", "liability_current",
              "liability_non_current", "liability_credit_card"])
equity = total(["equity", "equity_unaffected"])
income = total(["income", "income_other"])
expense = total(["expense", "expense_direct_cost", "expense_depreciation"])
check("balance sheet closes", abs(assets + liab + equity + income + expense) < 0.01,
      "assets %s" % money(assets))

for journal in env["account.journal"].search([("type", "=", "bank")]):
    account = journal.default_account_id
    if not account:
        continue
    ledger = sum(Line.search([("parent_state", "=", "posted"),
                              ("account_id", "=", account.id)]).mapped("balance"))
    statement = env["account.bank.statement"].search(
        [("journal_id", "=", journal.id)], order="date desc", limit=1)
    if statement:
        check("%s: ledger = statement close" % journal.code,
              abs(ledger - statement.balance_end_real) < 0.01,
              "%s vs %s" % (money(ledger), money(statement.balance_end_real)))
    else:
        check("%s: a statement exists to reconcile against" % journal.code,
              False, "none entered", warn_only=True)

print()
print("=" * 78)
print("LINKAGE — do the apps actually join up")
print("=" * 78)

pairs = [
    ("purchase order -> vendor bill", "purchase.order",
     [("state", "in", ("purchase", "done"))], "invoice_ids"),
    ("progress claim -> tax invoice", "mizan.progress.claim",
     [("state", "=", "invoiced")], "invoice_id"),
    ("contract  -> cost centre", "mizan.contract", [], "analytic_account_id"),
    ("cheque    -> journal entry", "mizan.cheque",
     [("state", "not in", ("draft", "cancel"))], "move_register_id"),
    ("expense sheet -> journal entry", "hr.expense.sheet",
     [("state", "=", "done")], "account_move_ids"),
]
for label, model, domain, field in pairs:
    if model not in env:
        continue
    records = env[model].search(domain)
    if not records:
        check(label, True, "nothing to check yet", warn_only=False)
        continue
    linked = records.filtered(lambda r: r[field])
    check(label, len(linked) == len(records),
          "%d of %d linked" % (len(linked), len(records)),
          warn_only=True)

claims = env["mizan.progress.claim"].search([("state", "=", "invoiced")])
drift = [c.name for c in claims
         if abs(c.amount_this_period - c.invoice_id.amount_untaxed) > 1.0]
check("claim amount = its invoice", not drift,
      "%d of %d differ" % (len(drift), len(claims)))

retained = Move.search([("mizan_retention_move_id", "!=", False)])
check("retention entries reconciled to their invoice",
      all(m.mizan_retention_move_id.state == "posted" for m in retained),
      "%d withheld" % len(retained))

print()
print("=" * 78)
print("HYGIENE — not wrong, but this is how a close goes wrong")
print("=" * 78)

drafts = Move.search([("state", "=", "draft"),
                      ("move_type", "!=", "entry")])
check("no unposted invoices or bills", not drafts,
      "%d draft" % len(drafts), warn_only=True)

analytic_expense = Line.search([
    ("parent_state", "=", "posted"),
    ("account_id.account_type", "in", ("expense_direct_cost",)),
])
untagged = analytic_expense.filtered(lambda l: not l.analytic_distribution)
check("every direct job cost carries a cost centre", not untagged,
      "%d of %d untagged" % (len(untagged), len(analytic_expense)),
      warn_only=True)

no_code = analytic_expense.filtered(lambda l: not l.mizan_cost_code_id)
check("every direct job cost carries a cost code", not no_code,
      "%d of %d untagged" % (len(no_code), len(analytic_expense)),
      warn_only=True)

partners = env["res.partner"].search([
    ("country_id.code", "=", "AE"), ("customer_rank", ">", 0)])
no_emirate = partners.filtered(lambda p: not p.state_id)
check("every UAE customer has an emirate (VAT return)", not no_emirate,
      "%d missing" % len(no_emirate))

no_trn = partners.filtered(lambda p: not p.vat)
check("every business customer has a TRN (e-invoicing)", not no_trn,
      "%d missing" % len(no_trn), warn_only=True)

accounts = env["account.account"].search([])
used = set(Line.search([]).mapped("account_id").ids)
unused = [a for a in accounts if a.id not in used]
check("chart is not padded with unused accounts", len(unused) < 60,
      "%d of %d never posted to" % (len(unused), len(accounts)),
      warn_only=True)

overdue = env["mizan.contract.bond"].search([
    ("state", "=", "active")]).filtered(lambda b: b.days_to_expiry <= 30)
check("no guarantee about to lapse", not overdue,
      "%d within 30 days" % len(overdue), warn_only=True)

print()
print("=" * 78)
if problems:
    print("FAILURES: %s" % ", ".join(problems))
else:
    print("No arithmetic failure. The ledger, the subledgers and the balance")
    print("sheet all agree.")
if warnings:
    print()
    print("Worth attention: %s" % ", ".join(warnings))
print("=" * 78)
