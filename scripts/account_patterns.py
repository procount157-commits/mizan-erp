# -*- coding: utf-8 -*-
"""Where every posting landed, against where it belongs.

    docker exec ... odoo shell -d DB ... < scripts/account_patterns.py

health_check.py asks whether the ledger balances, audit_ledger.py whether each
subledger agrees with its documents. A ledger can pass both and still be
wrong: a sale credited to a cost account balances perfectly, and the profit
and loss reads the sale as a smaller cost. This reads every posted line by the
account it hit, the journal that posted it and the kind of document it came
from, and flags the combinations that do not belong together.

Four groups, most serious first:

  * WRONG ACCOUNT -- a document posted to an account of the wrong kind: a sale
    on a cost account, a purchase on a revenue account, VAT typed by hand into
    a VAT account, a receivable with no customer on it.
  * WRONG SIDE -- an account whose balance sits on the side its type never
    should: an asset in credit, revenue in debit. Some are legitimate (an
    overdrawn bank) and each one says so.
  * NOT CLEARED -- transfer, suspense and outstanding accounts exist to empty
    again. A balance left in one is money nobody has finished posting.
  * TIDINESS -- deprecated accounts still in use, direct costs with no cost
    centre.

Read-only. Nothing here writes.
"""

from collections import defaultdict

FAIL, WARN, OK = [], [], []


def m(v):
    return "{:,.2f}".format(v or 0.0)


def report(label, problems, ok_note, warn=False, limit=6):
    bucket = OK if not problems else (WARN if warn else FAIL)
    bucket.append((label, problems))
    tag = "OK  " if not problems else ("WARN" if warn else "FAIL")
    print("  [%s] %s%s" % (tag, label, "" if problems else "  — " + ok_note))
    for p in problems[:limit]:
        print("         · %s" % p)
    if len(problems) > limit:
        print("         · … and %s more" % (len(problems) - limit))


def heading(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


Line = env["account.move.line"]
posted = [("parent_state", "=", "posted")]
lines = Line.search(posted)
company = env.company
print("Posting patterns — %s — %s posted lines on %s accounts"
      % (company.name, len(lines), len(lines.mapped("account_id"))))

INCOME = ("income", "income_other")
EXPENSE = ("expense", "expense_direct_cost", "expense_depreciation")
SALE_DOCS = ("out_invoice", "out_refund", "out_receipt")
BUY_DOCS = ("in_invoice", "in_refund", "in_receipt")

# Contracting legitimately bills progress claims to contract-liability and
# contract-asset accounts (204xxx billings in excess, 107xxx retention and
# unbilled), not to revenue: revenue is recognised separately by percentage of
# completion. Those are the right place for a claim line, so they are allowed.
CONTRACT_PREFIXES = ("204", "107")


def contract_account(a):
    return (a.code or "").startswith(CONTRACT_PREFIXES)


# ------------------------------------------------------------- WRONG ACCOUNT
heading("WRONG ACCOUNT — a document posted where its kind does not belong")

product = lines.filtered(lambda l: l.display_type == "product")

bad = []
for l in product.filtered(lambda l: l.move_id.move_type in SALE_DOCS):
    a = l.account_id
    if a.account_type in INCOME or contract_account(a):
        continue
    bad.append("%s %s → %s %s (%s)  %s"
               % (l.move_id.name, (l.name or "(no description)")[:30],
                  a.code, a.name, a.account_type, m(-l.balance)))
report("sales lines post to revenue or a contract account", bad,
       "%s sales line(s), all on revenue or contract accounts"
       % len(product.filtered(lambda l: l.move_id.move_type in SALE_DOCS)))

bad = []
for l in product.filtered(lambda l: l.move_id.move_type in BUY_DOCS):
    a = l.account_id
    if a.account_type in INCOME:
        bad.append("%s %s → %s %s  %s"
                   % (l.move_id.name, (l.name or "")[:30], a.code, a.name,
                      m(l.balance)))
report("purchase lines never post to revenue", bad,
       "%s purchase line(s), none on revenue"
       % len(product.filtered(lambda l: l.move_id.move_type in BUY_DOCS)))

tax_accounts = env["account.account"]
for tax in env["account.tax"].search([]):
    tax_accounts |= (tax.invoice_repartition_line_ids.mapped("account_id")
                     | tax.refund_repartition_line_ids.mapped("account_id"))
# A VAT settlement entry legitimately moves these balances by hand, so this is
# a warning to read, not a failure: each line listed is either the quarter's
# settlement or VAT that skipped the tax engine.
manual_tax = lines.filtered(
    lambda l: l.account_id in tax_accounts and not l.tax_line_id
    and l.move_id.move_type == "entry")
bad = ["%s %s → %s %s  %s" % (l.move_id.name, (l.name or "")[:30], l.account_id.code,
                               l.account_id.name, m(l.balance)) for l in manual_tax]
report("VAT accounts are only reached through a tax", bad,
       "every line on a VAT account came from a tax", warn=True)

control = lines.filtered(lambda l: l.account_id.account_type in
                         ("asset_receivable", "liability_payable"))
bad = ["%s → %s %s  %s" % (l.move_id.name, l.account_id.code, l.account_id.name,
                            m(l.balance))
       for l in control.filtered(lambda l: not l.partner_id)]
report("every receivable and payable line names its party", bad,
       "%s control-account line(s), all with a partner" % len(control))

# Odoo 18 renamed account.move.payment_id to origin_payment_id.
PAYMENT_FIELD = ("origin_payment_id" if "origin_payment_id" in env["account.move"]._fields
                 else "payment_id")
manual_control = control.filtered(
    lambda l: l.move_id.move_type == "entry" and not l.move_id[PAYMENT_FIELD]
    and not l.move_id.statement_line_id and not l.full_reconcile_id
    and not l.matched_debit_ids and not l.matched_credit_ids)
bad = ["%s %s → %s  %s" % (l.move_id.name, (l.move_id.ref or l.name or "")[:34],
                            l.account_id.code, m(l.balance)) for l in manual_control]
report("no hand entry left open on a receivable or payable", bad,
       "every journal entry on a control account is matched to something",
       warn=True)

cashlike = lines.filtered(lambda l: l.account_id.account_type == "asset_cash")
off_journal = cashlike.filtered(lambda l: l.journal_id.type not in ("bank", "cash"))
bad = ["%s (%s journal) → %s %s  %s" % (l.move_id.name, l.journal_id.type,
                                        l.account_id.code, l.account_id.name,
                                        m(l.balance)) for l in off_journal]
report("bank and cash accounts move through bank or cash journals", bad,
       "%s bank/cash line(s), all from bank or cash journals" % len(cashlike),
       warn=True)

# ---------------------------------------------------------------- WRONG SIDE
heading("WRONG SIDE — a balance on the side its type should never be")

balances = defaultdict(float)
for l in lines:
    balances[l.account_id] += l.balance

SIDE = {
    # account_type: (expected sign, why a contrary balance might be legitimate)
    "asset_receivable": (1, "a customer who paid in advance"),
    "asset_cash": (1, "an overdrawn bank account"),
    "asset_current": (1, ""),
    "asset_non_current": (1, ""),
    "asset_fixed": (1, "accumulated depreciation, if it lives here"),
    "asset_prepayments": (1, ""),
    "liability_payable": (-1, "a supplier paid ahead of the bill"),
    "liability_current": (-1, ""),
    "liability_non_current": (-1, ""),
    "liability_credit_card": (-1, ""),
    "equity": (-1, "drawings or accumulated losses"),
    "income": (-1, "credit notes larger than sales"),
    "income_other": (-1, ""),
    "expense": (1, "a refund larger than the cost"),
    "expense_direct_cost": (1, "a cost reclassified out"),
    "expense_depreciation": (1, ""),
}
bad = []
for a, bal in sorted(balances.items(), key=lambda kv: kv[0].code or ""):
    rule = SIDE.get(a.account_type)
    if not rule or abs(bal) < 0.01:
        continue
    sign, legit = rule
    if bal * sign < 0:
        note = (" — legitimate if: %s" % legit) if legit else ""
        bad.append("%s %s (%s) %s %s%s"
                   % (a.code, a.name, a.account_type,
                      "credit" if bal < 0 else "debit", m(abs(bal)), note))
report("every account's balance is on its natural side", bad,
       "all %s accounts with a balance sit on their natural side"
       % len([b for b in balances.values() if abs(b) >= 0.01]), warn=True,
       limit=12)

# --------------------------------------------------------------- NOT CLEARED
heading("NOT CLEARED — accounts that exist to empty again")

clearing_words = ("transfer", "suspense", "outstanding", "تحويل", "معلق",
                  "مستحقة", "وسيط")
# Contract accounts (107xxx unbilled and retention, 204xxx billings and
# advances) are reconcilable and current, but they hold real balances that
# audit_ledger.py proves against the claims; they are not waiting to empty.
clearing = env["account.account"].search([]).filtered(
    lambda a: not contract_account(a) and (
        a.reconcile and a.account_type in ("asset_current", "liability_current")
        or any(w in (a.name or "").lower() for w in clearing_words)))
bad = ["%s %s  %s" % (a.code, a.name, m(balances.get(a, 0.0)))
       for a in clearing.sorted("code") if abs(balances.get(a, 0.0)) >= 0.01]
report("transfer, suspense and outstanding accounts are empty", bad,
       "%s clearing account(s), all at zero" % len(clearing), warn=True)

# ------------------------------------------------------------------ TIDINESS
heading("TIDINESS")

used = set(lines.mapped("account_id").ids)
deprecated = env["account.account"].with_context(active_test=False).search(
    [("deprecated", "=", True)]) if "deprecated" in env["account.account"]._fields \
    else env["account.account"]
bad = ["%s %s" % (a.code, a.name) for a in deprecated if a.id in used]
report("no deprecated account is still used", bad, "none", warn=True)

direct = product.filtered(lambda l: l.account_id.account_type == "expense_direct_cost")
bad = ["%s %s → %s  %s" % (l.move_id.name, (l.name or "")[:28], l.account_id.code,
                            m(l.balance))
       for l in direct.filtered(lambda l: not l.analytic_distribution)]
report("every direct cost carries a cost centre", bad,
       "%s direct-cost line(s), all on a cost centre" % len(direct), warn=True)

heading("%s wrong-account failure(s), %s warning(s), %s clean"
        % (len(FAIL), len(WARN), len(OK)))
for label, problems in FAIL:
    print("  FAIL  %s — %s line(s)" % (label, len(problems)))
for label, problems in WARN:
    print("  WARN  %s — %s item(s)" % (label, len(problems)))
print("=" * 78)
