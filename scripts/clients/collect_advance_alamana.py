# -*- coding: utf-8 -*-
"""Record the school advance actually arriving.

The advance on CT-2026-002 was certified in June and has been recovered from
every claim since — which can only happen if the client paid it. The receipt
itself was never recorded, so the 840,000 receivable the certificate raised sat
open, and the receivables ledger stood 840,000 above the sum of the invoices
behind it. Nothing was double-counted; the money was simply missing from the
bank.

Worth naming the design point this exposes: an advance certificate posts a
receivable through a journal entry, so there is no document for the client to
pay against and no line on a statement they can match. It reconciles, it ages,
and it is invisible to anyone reading the invoice list. Raising the advance as a
customer invoice instead would be better, and is a change to make deliberately
rather than in passing.
"""
from datetime import date

from odoo.exceptions import UserError

Contract = env["mizan.contract"]
Move = env["account.move"]
Line = env["account.move.line"]

school = Contract.search([("code", "=", "CT-2026-002")], limit=1)
if not school or not school.advance_move_id:
    raise UserError("The school advance has not been certified.")

MARKER = "ALAMANA-YTD-2026 RCPT-ADV-S"
if Move.search([("ref", "=", MARKER)]):
    raise UserError("The advance receipt is already recorded.")

open_line = school.advance_move_id.line_ids.filtered(
    lambda l: l.account_id.account_type == "asset_receivable"
    and l.amount_residual > 0.01)
if not open_line:
    raise UserError("The advance receivable is already settled.")
amount = open_line.amount_residual

bank_journal = env["account.journal"].search(
    [("type", "=", "bank"), ("company_id", "=", school.company_id.id)], limit=1)
bank_account = bank_journal.default_account_id
if not bank_account:
    raise UserError("The bank journal has no account set.")

receipt = Move.create({
    "move_type": "entry",
    "journal_id": bank_journal.id,
    "date": date(2026, 6, 28),
    "ref": MARKER,
    "line_ids": [
        (0, 0, {"account_id": bank_account.id,
                "partner_id": school.partner_id.id,
                "name": "تحصيل الدفعة المقدمة — %s" % school.code,
                "debit": amount, "credit": 0.0}),
        (0, 0, {"account_id": open_line.account_id.id,
                "partner_id": school.partner_id.id,
                "name": "تحصيل الدفعة المقدمة — %s" % school.code,
                "debit": 0.0, "credit": amount}),
    ],
})
receipt.action_post()
offset = receipt.line_ids.filtered(
    lambda l: l.account_id == open_line.account_id)
(open_line | offset).reconcile()
env.cr.commit()

env.cr.execute("""
    select sum(debit), sum(credit) from account_move_line l
    join account_move m on m.id = l.move_id where m.state = 'posted'
""")
dr, cr_ = env.cr.fetchone()

ledger = sum(Line.search([
    ("parent_state", "=", "posted"),
    ("account_id.account_type", "=", "asset_receivable")]).mapped("balance"))
docs = sum(Move.search([
    ("state", "=", "posted"),
    ("move_type", "in", ("out_invoice", "out_refund"))
]).mapped("amount_residual_signed"))

print()
print("receipt posted      %s   %s" % (receipt.name, "{:,.2f}".format(amount)))
print("advance receivable  %s" % (
    "settled" if open_line.amount_residual < 0.01
    else "still open by %.2f" % open_line.amount_residual))
print("trial balance       %s / %s   %s" % (
    "{:,.2f}".format(dr), "{:,.2f}".format(cr_),
    "balanced" if abs(dr - cr_) < 0.01 else "OUT BY %.2f" % (dr - cr_)))
print("receivables ledger  %16s" % "{:,.2f}".format(ledger))
print("open invoices       %16s" % "{:,.2f}".format(docs))
print("difference          %16s" % "{:,.2f}".format(ledger - docs))
