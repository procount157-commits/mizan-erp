# -*- coding: utf-8 -*-
"""شركة الأمانة للمقاولات — nine months of real contracting activity.

Builds a ledger that actually ties: opening balances, progress billings with
retention withheld, subcontractor and material bills, site payroll costed to
each project, overheads, depreciation, collections and payments, then revenue
recognised on percentage of completion.

Everything that touches a project carries an analytic distribution, because
that is what drives cost-to-date, and cost-to-date is what drives the revenue
figure. A cost posted without it silently understates completion.
"""
from datetime import date

company = env.company
Move = env["account.move"]
Account = env["account.account"]
Partner = env["res.partner"]
Journal = env["account.journal"]

MARKER = "ALAMANA-YTD-2026"
existing = Move.search([("ref", "=like", MARKER + "%")])
if existing:
    existing.filtered(lambda m: m.state == "posted").button_draft()
    existing.filtered(lambda m: m.state != "cancel").button_cancel()
    print("cleared %d entries from a previous run" % len(existing))


def acc(code):
    a = Account.search([("code", "=", code)], limit=1)
    if not a:
        raise ValueError("missing account %s" % code)
    return a


def journal(code):
    return Journal.search([("code", "=", code)], limit=1)


sale_j = journal("INV") or Journal.search([("type", "=", "sale")], limit=1)
bill_j = journal("BILL") or Journal.search([("type", "=", "purchase")], limit=1)
gen_j = Journal.search([("type", "=", "general")], limit=1)
bank_j = Journal.search([("type", "=", "bank")], limit=1)

tax_dubai = env["account.tax"].search(
    [("name", "=", "5% DB"), ("type_tax_use", "=", "sale")], limit=1)
tax_sharjah = env["account.tax"].search(
    [("name", "=", "5% S"), ("type_tax_use", "=", "sale")], limit=1)
tax_purchase = env["account.tax"].search(
    [("name", "=", "5%"), ("type_tax_use", "=", "purchase")], limit=1)

villa = env["project.project"].search([("name", "like", "فيلا")], limit=1)
school = env["project.project"].search([("name", "like", "مدرسة")], limit=1)
AN_VILLA = {str(villa.account_id.id): 100}
AN_SCHOOL = {str(school.account_id.id): 100}

client_villa = Partner.search([("name", "like", "الخليج للاستثمار")], limit=1)
client_school = Partner.search([("name", "like", "بلدية الشارقة")], limit=1)


def vendor(name, trn=False):
    found = Partner.search([("name", "=", name)], limit=1)
    if found:
        return found
    return Partner.create({
        "name": name, "is_company": True, "supplier_rank": 1,
        "country_id": env.ref("base.ae").id, "vat": trn,
    })


v_materials = vendor("مؤسسة الرمال لمواد البناء", "100234567800003")
v_sub_civil = vendor("شركة البنيان لمقاولات الباطن", "100345678900003")
v_sub_mep = vendor("الرواد للأعمال الكهروميكانيكية", "100456789000003")
v_plant = vendor("الخليج لتأجير المعدات", "100567890100003")
v_landlord = vendor("مجموعة الوصل العقارية")

posted = []


def entry(ref, when, lines, jrnl=None):
    """A balanced journal entry. Lines are (account_code, debit, credit, label, analytic)."""
    move = Move.create({
        "move_type": "entry",
        "journal_id": (jrnl or gen_j).id,
        "date": when,
        "ref": "%s %s" % (MARKER, ref),
        "line_ids": [(0, 0, {
            "account_id": acc(code).id,
            "debit": dr, "credit": cr, "name": label,
            "analytic_distribution": an or False,
        }) for code, dr, cr, label, an in lines],
    })
    move.action_post()
    posted.append(move)
    return move


def bill(ref, when, partner, when_lines):
    """A vendor bill: (account_code, amount, label, analytic)."""
    move = Move.create({
        "move_type": "in_invoice",
        "journal_id": bill_j.id,
        "partner_id": partner.id,
        "invoice_date": when,
        "date": when,
        "ref": "%s %s" % (MARKER, ref),
        "invoice_line_ids": [(0, 0, {
            "name": label,
            "account_id": acc(code).id,
            "quantity": 1,
            "price_unit": amount,
            "tax_ids": [(6, 0, tax_purchase.ids)],
            "analytic_distribution": an or False,
        }) for code, amount, label, an in when_lines],
    })
    move.action_post()
    posted.append(move)
    return move


def progress_invoice(ref, when, partner, label, amount, tax, analytic):
    """A progress claim (مستخلص) against a contract.

    The claim credits progress billings, NOT revenue. On a long-term contract
    the invoice is a demand for cash against work certified so far; revenue is
    earned by doing the work, and is recognised separately on percentage of
    completion. Crediting revenue here as well would count the same job twice —
    once when billed and once when earned — and the two never agree, because
    billing runs ahead of or behind the work by design.

    At any date the two accounts net to the contract's position: billings above
    revenue is a liability to the client, revenue above billings is an asset.
    """
    move = Move.create({
        "move_type": "out_invoice",
        "journal_id": sale_j.id,
        "partner_id": partner.id,
        "invoice_date": when,
        "date": when,
        "ref": "%s %s" % (MARKER, ref),
        "invoice_line_ids": [(0, 0, {
            "name": label,
            "account_id": acc("204004").id,
            "quantity": 1,
            "price_unit": amount,
            "tax_ids": [(6, 0, tax.ids)],
            "analytic_distribution": analytic,
        })],
    })
    move.action_post()
    posted.append(move)
    return move


def withhold_retention(ref, when, invoice, percent=5.0):
    """Move the client's retention out of receivables into a retention asset.

    Retention is not an ordinary receivable: it is not due until the defects
    period ends, and leaving it in trade debtors makes the ageing report claim
    money is overdue when it is not yet payable at all.
    """
    amount = round(invoice.amount_untaxed * percent / 100.0, 2)
    entry(ref, when, [
        ("107003", amount, 0.0, "محتجزات %s" % invoice.name, False),
        ("102011", 0.0, amount, "محتجزات %s" % invoice.name, False),
    ])
    return amount


# ============================================================ opening balances
entry("OPENING", date(2026, 1, 1), [
    ("101001", 850000.0, 0.0, "رصيد افتتاحي — البنك", False),
    ("106004", 320000.0, 0.0, "رصيد افتتاحي — سيارات ومركبات", False),
    ("106012", 680000.0, 0.0, "رصيد افتتاحي — آلات ومعدات إنشائية", False),
    ("106009", 0.0, 96000.0, "مجمع إهلاك السيارات", False),
    ("106013", 0.0, 204000.0, "مجمع إهلاك الآلات", False),
    ("300001", 0.0, 1000000.0, "رأس المال المدفوع", False),
    ("300004", 0.0, 550000.0, "أرباح مرحّلة", False),
])

# =================================================== project costs — الفيلا
bill("BILL-001", date(2026, 2, 10), v_materials,
     [("401001", 180000.0, "حديد تسليح وخرسانة — فيلا ند الشبا", AN_VILLA)])
b_sub1 = bill("BILL-002", date(2026, 3, 8), v_sub_civil,
     [("401003", 220000.0, "أعمال هيكلية — فيلا ند الشبا", AN_VILLA)])
bill("BILL-003", date(2026, 4, 12), v_plant,
     [("401004", 45000.0, "إيجار حفار وونش — فيلا ند الشبا", AN_VILLA)])
bill("BILL-004", date(2026, 5, 9), v_materials,
     [("401001", 120000.0, "مواد تشطيبات — فيلا ند الشبا", AN_VILLA)])
b_sub2 = bill("BILL-005", date(2026, 6, 14), v_sub_mep,
     [("401003", 150000.0, "أعمال كهروميكانيك — فيلا ند الشبا", AN_VILLA)])
bill("BILL-006", date(2026, 7, 11), v_materials,
     [("401001", 65000.0, "مواد صحية وكهربائية — فيلا ند الشبا", AN_VILLA)])

# =================================================== project costs — المدرسة
bill("BILL-007", date(2026, 3, 15), v_materials,
     [("401001", 300000.0, "مواد إنشائية — توسعة المدرسة", AN_SCHOOL)])
b_sub3 = bill("BILL-008", date(2026, 4, 20), v_sub_civil,
     [("401003", 350000.0, "أعمال خرسانية — توسعة المدرسة", AN_SCHOOL)])
bill("BILL-009", date(2026, 5, 18), v_materials,
     [("401001", 220000.0, "بلوك ومواد بناء — توسعة المدرسة", AN_SCHOOL)])
bill("BILL-010", date(2026, 6, 22), v_plant,
     [("401004", 60000.0, "إيجار معدات — توسعة المدرسة", AN_SCHOOL)])
b_sub4 = bill("BILL-011", date(2026, 7, 19), v_sub_mep,
     [("401003", 280000.0, "أعمال ميكانيكية — توسعة المدرسة", AN_SCHOOL)])
bill("BILL-012", date(2026, 8, 6), v_materials,
     [("401009", 35000.0, "رسوم تصاريح بلدية الشارقة", AN_SCHOOL)])

# ------------------------------------- retention withheld from subcontractors
# The company holds 5% back from its own subcontractors, exactly as its clients
# hold it back from the company. Netting it out of payables keeps the payment
# run from paying money that is not yet due.
for tag, b in (("SUBRET-1", b_sub1), ("SUBRET-2", b_sub2),
               ("SUBRET-3", b_sub3), ("SUBRET-4", b_sub4)):
    held = round(b.amount_untaxed * 0.05, 2)
    entry(tag, b.invoice_date, [
        ("201002", held, 0.0, "محتجزات مقاول باطن %s" % b.name, False),
        ("204001", 0.0, held, "محتجزات مقاول باطن %s" % b.name, False),
    ])

# ==================================================== site payroll, by project
# Direct site labour belongs to the job, not to overhead. Without the analytic
# distribution the wages of the people building the villa never reach the
# villa's cost, and its completion percentage reads low for the whole year.
for month in (3, 4, 5, 6, 7):
    entry("LABOUR-V-%02d" % month, date(2026, month, 28), [
        ("401002", 24000.0, 0.0, "أجور عمالة الموقع — فيلا ند الشبا", AN_VILLA),
        ("201004", 0.0, 24000.0, "رواتب مستحقة — عمالة الفيلا", False),
    ])
for month in (3, 4, 5, 6, 7, 8):
    entry("LABOUR-S-%02d" % month, date(2026, month, 28), [
        ("401002", 30000.0, 0.0, "أجور عمالة الموقع — توسعة المدرسة", AN_SCHOOL),
        ("201004", 0.0, 30000.0, "رواتب مستحقة — عمالة المدرسة", False),
    ])

# ======================================================== progress billings
inv1 = progress_invoice("CLAIM-V1", date(2026, 3, 31), client_villa,
                        "مستخلص رقم 1 — فيلا ند الشبا (عقد CT-2026-001)",
                        600000.0, tax_dubai, AN_VILLA)
withhold_retention("RET-V1", date(2026, 3, 31), inv1)

inv2 = progress_invoice("CLAIM-S1", date(2026, 5, 31), client_school,
                        "مستخلص رقم 1 — توسعة مدرسة الشارقة (عقد CT-2026-002)",
                        900000.0, tax_sharjah, AN_SCHOOL)
withhold_retention("RET-S1", date(2026, 5, 31), inv2)

inv3 = progress_invoice("CLAIM-V2", date(2026, 6, 30), client_villa,
                        "مستخلص رقم 2 — فيلا ند الشبا (عقد CT-2026-001)",
                        550000.0, tax_dubai, AN_VILLA)
withhold_retention("RET-V2", date(2026, 6, 30), inv3)

inv4 = progress_invoice("CLAIM-S2", date(2026, 8, 31), client_school,
                        "مستخلص رقم 2 — توسعة مدرسة الشارقة (عقد CT-2026-002)",
                        750000.0, tax_sharjah, AN_SCHOOL)
withhold_retention("RET-S2", date(2026, 8, 31), inv4)
print("progress billings: %.2f AED before VAT" % sum(
    i.amount_untaxed for i in (inv1, inv2, inv3, inv4)))


# ============================================================ overheads
# Deliberately carrying no analytic distribution: head office rent and the
# finance department are not a cost of either job, and loading them onto one
# would flatter the other's margin.
for month in range(1, 10):
    entry("RENT-%02d" % month, date(2026, month, 1), [
        ("400016", 9000.0, 0.0, "إيجار المكتب الرئيسي", False),
        ("201015", 0.0, 9000.0, "إيجار مستحق", False),
    ])
    # Head office payroll only. The site crews are costed to their jobs above,
    # so putting them here as well would double the wage bill and hide the
    # margin on both contracts.
    entry("ADMIN-PAY-%02d" % month, date(2026, month, 28), [
        ("400003", 17000.0, 0.0, "رواتب أساسية — الإدارة", False),
        ("400004", 6000.0, 0.0, "بدل سكن — الإدارة", False),
        ("400005", 3000.0, 0.0, "بدل مواصلات — الإدارة", False),
        ("400008", 2400.0, 0.0, "مخصص مكافأة نهاية الخدمة", False),
        ("201004", 0.0, 26000.0, "رواتب مستحقة — الإدارة", False),
        ("201006", 0.0, 2400.0, "مخصص نهاية الخدمة", False),
    ])
    entry("UTIL-%02d" % month, date(2026, month, 25), [
        ("400018", 2500.0, 0.0, "كهرباء ومياه", False),
        ("400020", 1200.0, 0.0, "هاتف وإنترنت", False),
        ("201011", 0.0, 3700.0, "مصاريف مستحقة", False),
    ])

entry("LICENSE", date(2026, 1, 15), [
    ("400032", 18000.0, 0.0, "رسوم الرخصة التجارية السنوية", False),
    ("101001", 0.0, 18000.0, "سداد رسوم الرخصة", False),
])
entry("INSURANCE", date(2026, 2, 1), [
    ("401008", 24000.0, 0.0, "تأمين المشاريع والمسؤولية المدنية", False),
    ("101001", 0.0, 24000.0, "قسط التأمين السنوي", False),
])

# ---------------------------------------------------------- depreciation
# Nine months at straight line: vehicles over five years, plant over eight.
entry("DEPN-YTD", date(2026, 9, 30), [
    ("400066", 48000.0, 0.0, "إهلاك السيارات — 9 أشهر", False),
    ("401013", 63750.0, 0.0, "إهلاك الآلات والمعدات — 9 أشهر", False),
    ("106009", 0.0, 48000.0, "مجمع إهلاك السيارات", False),
    ("106013", 0.0, 63750.0, "مجمع إهلاك الآلات", False),
])

# ================================================== collections and payments
def receipt(ref, when, partner, amount, invoices):
    """Cash in from a client, reconciled against their claims."""
    move = entry(ref, when, [
        ("101001", amount, 0.0, "تحصيل من %s" % partner.name, False),
        ("102011", 0.0, amount, "تحصيل مستخلصات — %s" % partner.name, False),
    ], jrnl=bank_j)
    debit_lines = invoices.line_ids.filtered(
        lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled)
    credit_line = move.line_ids.filtered(
        lambda l: l.account_id.account_type == "asset_receivable")
    (debit_lines | credit_line).reconcile()
    return move


def payment(ref, when, partner, amount, bills):
    move = entry(ref, when, [
        ("201002", amount, 0.0, "سداد إلى %s" % partner.name, False),
        ("101001", 0.0, amount, "سداد مستحقات %s" % partner.name, False),
    ], jrnl=bank_j)
    credit_lines = bills.line_ids.filtered(
        lambda l: l.account_id.account_type == "liability_payable" and not l.reconciled)
    debit_line = move.line_ids.filtered(
        lambda l: l.account_id.account_type == "liability_payable")
    (credit_lines | debit_line).reconcile()
    return move


receipt("RCPT-V1", date(2026, 4, 20), client_villa, 599000.0, inv1)
receipt("RCPT-S1", date(2026, 7, 5), client_school, 900000.0, inv2)
receipt("RCPT-V2", date(2026, 8, 12), client_villa, 550000.0, inv3)

all_bills = Move.search([("move_type", "=", "in_invoice"),
                         ("ref", "=like", MARKER + "%")])
payment("PAY-MAT", date(2026, 6, 30), v_materials, 630000.0,
        all_bills.filtered(lambda b: b.partner_id == v_materials))
payment("PAY-SUB", date(2026, 7, 31), v_sub_civil, 540000.0,
        all_bills.filtered(lambda b: b.partner_id == v_sub_civil))
payment("PAY-PLANT", date(2026, 8, 15), v_plant, 110000.0,
        all_bills.filtered(lambda b: b.partner_id == v_plant))

env.cr.commit()
print("posted %d journal entries and documents" % len(posted))


# ================================================= revenue on completion
# Only here does revenue enter the profit and loss account, measured by cost
# incurred against budget rather than by what has been invoiced.
rev_account = acc("501001")
wip_account = acc("107002")
for contract in env["mizan.contract"].search([]):
    contract.invalidate_recordset()
    if contract.revenue_to_recognise <= 1:
        continue
    contract.action_create_recognition()
    draft = contract.recognition_ids.filtered(lambda r: r.state == "draft")[:1]
    if not draft:
        continue
    draft.write({
        "date": date(2026, 9, 30),
        "revenue_account_id": rev_account.id,
        "wip_account_id": wip_account.id,
    })
    draft.action_post()
    print("recognised %s: %.2f (%.2f%% complete on cost of %.2f)" % (
        contract.code, draft.amount, contract.completion_percent,
        contract.cost_incurred))

env.cr.commit()
