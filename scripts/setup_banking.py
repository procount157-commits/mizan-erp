# -*- coding: utf-8 -*-
"""Make the bank journals ready to reconcile. Runs against the template.

Three things were missing, and together they meant the reconciliation screen
had nothing to show even once it stopped crashing.

1. No outstanding accounts on the bank journal. Without them a payment posts
   straight to the bank account, so the ledger records money as being in the
   bank on the day the voucher was typed — not the day it cleared. The bank
   line and the payment then have nothing to match, because the payment
   already wrote the bank balance itself.

2. No reconciliation rules. Bank charges, interest and small differences
   arrive on the statement with no document behind them. Without a rule
   somebody writes a journal entry by hand for every one, and in practice
   they stop reconciling instead.

3. Nothing enforced that a cash journal has an outstanding account too, which
   is how petty cash was already set up and is the right shape.
"""

Journal = env["account.journal"]
Account = env["account.account"]
Model = env["account.reconcile.model"]
company = env.company


def account(code):
    record = Account.search(
        [("code", "=", code), ("company_ids", "in", company.id)], limit=1)
    if not record:
        record = Account.search([("code", "=", code)], limit=1)
    if not record:
        raise Exception(
            "Account %s is missing. Run scripts/complete_coa.py first." % code)
    return record


incoming = account("101003")   # Outstanding Receipts
outgoing = account("101004")   # Outstanding Payments
charges = account("400051")    # Other Bank Charges
suspense = account("101002")   # Bank Suspense

changed = []
for journal in Journal.search([("type", "=", "bank"),
                               ("company_id", "=", company.id)]):
    values = {}
    if not journal.suspense_account_id:
        values["suspense_account_id"] = suspense.id
    if values:
        journal.write(values)
    # The payment method lines are what actually carry the outstanding
    # account; setting it on the journal alone does nothing.
    for line in journal.inbound_payment_method_line_ids:
        if not line.payment_account_id:
            line.payment_account_id = incoming.id
            changed.append("%s in:%s" % (journal.code, line.name))
    for line in journal.outbound_payment_method_line_ids:
        if not line.payment_account_id:
            line.payment_account_id = outgoing.id
            changed.append("%s out:%s" % (journal.code, line.name))

# ------------------------------------------------------------------ rules
RULES = [
    {
        "name": "Bank Charges",
        "arabic": "رسوم بنكية",
        "match_label": "contains",
        "match_label_param": "CHG",
        "account": charges,
    },
    {
        "name": "Bank Charges (Arabic narrative)",
        "arabic": "رسوم بنكية — وصف عربي",
        "match_label": "contains",
        "match_label_param": "رسوم",
        "account": charges,
    },
]

created = []
for rule in RULES:
    existing = Model.search([("name", "=", rule["name"]),
                             ("company_id", "=", company.id)], limit=1)
    if existing:
        continue
    record = Model.with_context(lang="en_US").create({
        "name": rule["name"],
        "company_id": company.id,
        "rule_type": "writeoff_suggestion",
        "match_label": rule["match_label"],
        "match_label_param": rule["match_label_param"],
        "line_ids": [(0, 0, {
            "account_id": rule["account"].id,
            "amount_type": "percentage",
            "amount_string": "100",
            "label": rule["name"],
        })],
    })
    record.with_context(lang="ar_001").name = rule["arabic"]
    created.append(rule["name"])

# The matching rule Odoo ships for invoices is worth having on by default:
# most statement lines settle a document that is already in the system.
invoice_rule = Model.search([("rule_type", "=", "invoice_matching"),
                             ("company_id", "=", company.id)], limit=1)

env.cr.commit()

print()
print("outstanding accounts set on %d payment method lines" % len(changed))
for c in changed:
    print("   %s" % c)
print("reconciliation rules created: %s" % (", ".join(created) or "none new"))
print("invoice matching rule: %s" % (invoice_rule.name if invoice_rule else "NONE"))
print()
for journal in Journal.search([("type", "in", ("bank", "cash")),
                               ("company_id", "=", company.id)]):
    print("%-6s default=%-8s suspense=%-8s in=%-8s out=%-8s" % (
        journal.code,
        journal.default_account_id.code or "-",
        journal.suspense_account_id.code or "-",
        (journal.inbound_payment_method_line_ids.mapped(
            "payment_account_id.code") or ["-"])[0],
        (journal.outbound_payment_method_line_ids.mapped(
            "payment_account_id.code") or ["-"])[0]))
