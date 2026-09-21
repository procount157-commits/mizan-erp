# -*- coding: utf-8 -*-
"""September's bank statement for الأمانة, and the reconciliation of it.

Every receipt and payment seeded so far was written straight into the bank
account as a journal entry. That is valid accounting and it balances, but it
leaves nothing to reconcile: the ledger wrote the bank balance itself, so there
is no independent record to agree with. The reconciliation screen was empty for
that reason as much as for the crash.

This is the bank's own record of the account for September, entered as the bank
sent it, and then worked: four lines matched to the documents they settle, one
left open because nobody knows yet what it is. The open line is the point — a
reconciliation screen that is always empty is not reconciling anything.
"""
from datetime import date

from odoo.exceptions import UserError

Statement = env["account.bank.statement"]
Line = env["account.bank.statement.line"]
Move = env["account.move"]
MoveLine = env["account.move.line"]
Journal = env["account.journal"]
Account = env["account.account"]

MARKER = "ALAMANA-STMT-2026-09"
# Each step below checks for its own work, so the script can be re-run: it
# picks up where it stopped rather than recording the same movements twice.
existing_statement = Statement.search([("name", "=", MARKER)], limit=1)

journal = Journal.search([("type", "=", "bank"), ("code", "=", "BNK1")], limit=1)
if not journal:
    raise UserError("No bank journal BNK1.")
bank_account = journal.default_account_id

# The balance the bank would have carried forward at the end of August.
opening = sum(MoveLine.search([
    ("parent_state", "=", "posted"),
    ("account_id", "=", bank_account.id),
    ("date", "<=", date(2026, 8, 31)),
]).mapped("balance"))


def invoice(name):
    move = Move.search([("name", "=", name), ("state", "=", "posted")], limit=1)
    if not move:
        raise UserError("Document %s not found." % name)
    return move


# (date, narrative as the bank writes it, amount, document to match or None)
LINES = [
    (date(2026, 9, 3), "تحويل وارد — بلدية الشارقة / INV/2026/00004",
     400000.00, "INV/2026/00004"),
    (date(2026, 9, 8), "تحويل صادر — مؤسسة الرمال / BILL/2026/05/0001",
     -126000.00, "BILL/2026/05/0001"),
    (date(2026, 9, 10), "CHG - MONTHLY ACCOUNT MAINTENANCE FEE",
     -450.00, "rule"),
    (date(2026, 9, 15), "تحويل وارد — شركة الخليج للاستثمار العقاري",
     1000.00, "INV/2026/00001"),
    (date(2026, 9, 18), "إيداع غير محدد المصدر — TRF884412",
     12500.00, None),
]

created = []
if existing_statement:
    statement = existing_statement
else:
    statement = Statement.create({
        "name": MARKER,
        "journal_id": journal.id,
        "date": date(2026, 9, 20),
        "balance_start": opening,
        "balance_end_real": opening + sum(a for _d, _n, a, _m in LINES),
    })
    for when, narrative, amount, match in LINES:
        created.append((Line.create({
            "statement_id": statement.id,
            "journal_id": journal.id,
            "date": when,
            "payment_ref": narrative,
            "amount": amount,
        }), match))
    env.cr.commit()

# ------------------------------------------------------------ reconciling
report = []
for line, match in created:
    if match is None:
        report.append((line, "left open", ""))
        continue
    if match == "rule":
        # The bank-charges rule should recognise the narrative on its own.
        line.clean_reconcile()
        if not line.can_reconcile:
            report.append((line, "RULE DID NOT FIRE", ""))
            continue
        line.reconcile_bank_line()
        report.append((line, "posted by rule", "400051"))
        continue

    document = invoice(match)
    control = document.line_ids.filtered(
        lambda l: l.account_id.account_type in
        ("asset_receivable", "liability_payable") and not l.reconciled)
    if not control:
        report.append((line, "NOTHING OPEN ON %s" % match, ""))
        continue
    # The widget's own API rather than a Form on its view: the same two calls
    # the screen makes, without pulling the test framework into a setup script.
    line.clean_reconcile()
    line._add_account_move_line(control[:1])
    line.can_reconcile = line.reconcile_data_info.get("can_reconcile", False)
    if not line.can_reconcile:
        report.append((line, "COULD NOT MATCH %s" % match, ""))
        continue
    line.reconcile_bank_line()
    report.append((line, "matched", match))

env.cr.commit()

# ---------------------------------------------------------------- evidence
print()
print("=" * 86)
print("BANK STATEMENT — %s" % MARKER)
print("=" * 86)
print("opening balance   %18s" % "{:,.2f}".format(statement.balance_start))
print("closing per bank  %18s" % "{:,.2f}".format(statement.balance_end_real))
print()
print("%-11s %-46s %13s  %-12s %s" % (
    "date", "narrative", "amount", "state", "settles"))
for line in statement.line_ids.sorted(key=lambda l: (l.date, l.id)):
    _liq, suspense_lines, other_lines = line._seek_for_lines()
    settles = ", ".join(sorted(set(other_lines.mapped("account_id.code")))) or "-"
    if suspense_lines:
        settles = "still in suspense"
    print("%-11s %-46s %13s  %-12s %s" % (
        line.date, (line.payment_ref or "")[:46],
        "{:,.2f}".format(line.amount),
        "reconciled" if line.is_reconciled else "open", settles))

print()
open_lines = Line.search([("statement_id", "=", statement.id),
                          ("is_reconciled", "=", False)])
print("lines still to reconcile: %d" % len(open_lines))
for line in open_lines:
    print("   %s  %s  %s" % (line.date, "{:,.2f}".format(line.amount),
                             line.payment_ref))

print()
env.cr.execute("""
    select sum(debit), sum(credit) from account_move_line l
    join account_move m on m.id = l.move_id where m.state = 'posted'
""")
dr, cr_ = env.cr.fetchone()
print("trial balance   %s / %s   %s" % (
    "{:,.2f}".format(dr), "{:,.2f}".format(cr_),
    "balanced" if abs(dr - cr_) < 0.01 else "OUT BY %.2f" % (dr - cr_)))

ledger_bank = sum(MoveLine.search([
    ("parent_state", "=", "posted"),
    ("account_id", "=", bank_account.id)]).mapped("balance"))
print("bank per ledger %18s" % "{:,.2f}".format(ledger_bank))
print("bank per statement %15s" % "{:,.2f}".format(statement.balance_end_real))
print("difference      %18s   (the unidentified deposit is included in both;"
      % "{:,.2f}".format(ledger_bank - statement.balance_end_real))
print("                                       it sits in suspense until someone names it)")

suspense = sum(MoveLine.search([
    ("parent_state", "=", "posted"),
    ("account_id", "=", journal.suspense_account_id.id)]).mapped("balance"))
print("bank suspense   %18s" % "{:,.2f}".format(suspense))

for name in ("INV/2026/00004", "INV/2026/00001", "BILL/2026/05/0001"):
    doc = invoice(name)
    print("%-20s residual %14s   %s" % (
        name, "{:,.2f}".format(doc.amount_residual), doc.payment_state))


# ======================================================== what reconciling found
# Reconciling the statement turned up a 5,000 gap between the ledger's bank
# balance and the bank's own. The cause: the petty cash float was drawn from
# the bank on 1 September through a GENERAL journal entry that credited the
# bank account directly, instead of going through the bank journal. The money
# genuinely left the bank, so it belongs on the statement — but the direct
# entry already wrote the bank balance, so simply adding the statement line
# would take the 5,000 out twice.
#
# The correction is to reverse the entry that bypassed the bank and let the
# statement record the withdrawal, which is where it always belonged. The net
# effect on both accounts is nil; what changes is that the bank account is now
# written only by the bank journal, and the statement ties.
#
# This is the whole point of the screen. Nobody was going to find this by
# reading the ledger: both sides of that entry were correct accounts and the
# trial balance balanced throughout.

CORRECTION = "ALAMANA-STMT-2026-09 CORRECTION"
if not Line.search([("payment_ref", "=", "سحب نقدي "
                                          "لتغذية "
                                          "العهدة "
                                          "النثرية")]):
    bypass = Move.search([
        ("journal_id.type", "=", "general"),
        ("state", "=", "posted"),
        ("date", ">", date(2026, 8, 31)),
        ("line_ids.account_id", "=", bank_account.id),
    ])
    petty = Account.search([("code", "=", "101020")], limit=1)
    if bypass and petty:
        reversal = bypass._reverse_moves(default_values_list=[{
            "date": m.date,
            "ref": "%s — %s" % (CORRECTION, m.ref or m.name),
        } for m in bypass])
        reversal.action_post()

        correction_line = Line.create({
            "statement_id": statement.id,
            "journal_id": journal.id,
            "date": date(2026, 9, 1),
            "payment_ref": "سحب نقدي "
                           "لتغذية "
                           "العهدة "
                           "النثرية",
            "amount": -5000.00,
        })
        _liq, suspense_lines, _other = correction_line._seek_for_lines()
        suspense_lines.with_context(
            skip_account_move_synchronization=True,
            skip_readonly_check=True,
        ).account_id = petty.id

        statement.balance_end_real = (
            statement.balance_start
            + sum(statement.line_ids.mapped("amount")))
        env.cr.commit()

        print()
        print("=" * 86)
        print("CORRECTION")
        print("=" * 86)
        print("reversed entries that wrote the bank outside the bank journal:")
        for m in bypass:
            print("   %s  %s  %s" % (m.name, m.date, m.ref or ""))
        print("statement line added: %s  %s" % (
            correction_line.date, "{:,.2f}".format(correction_line.amount)))

ledger_bank = sum(MoveLine.search([
    ("parent_state", "=", "posted"),
    ("account_id", "=", bank_account.id)]).mapped("balance"))
statement.invalidate_recordset()
print()
print("bank per ledger        %18s" % "{:,.2f}".format(ledger_bank))
print("statement closing      %18s" % "{:,.2f}".format(statement.balance_end_real))
print("difference             %18s" % "{:,.2f}".format(
    ledger_bank - statement.balance_end_real))
env.cr.execute("""
    select sum(debit), sum(credit) from account_move_line l
    join account_move m on m.id = l.move_id where m.state = 'posted'
""")
dr, cr_ = env.cr.fetchone()
print("trial balance          %s / %s  %s" % (
    "{:,.2f}".format(dr), "{:,.2f}".format(cr_),
    "balanced" if abs(dr - cr_) < 0.01 else "OUT BY %.2f" % (dr - cr_)))
