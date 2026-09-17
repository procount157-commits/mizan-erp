# -*- coding: utf-8 -*-
"""Load one complete contracting job, end to end.

This doubles as the integration test: every cost below is booked to the same
analytic account, so if any link between purchasing, payroll, petty cash and
the contract is broken, the percentage of completion at the end comes out wrong
rather than merely missing.

The job: a 12-storey tower, AED 5m contract, AED 4m budgeted cost, with
materials bought, an electrical subcontractor engaged, staff paid, temporary
labour hired and a site float held by the foreman.

    docker compose exec -T odoo odoo shell --config=/etc/odoo/odoo.conf \
        --db_user odoo --db_password "$POSTGRES_PASSWORD" \
        -d <database> --no-http < scripts/demo_contracting.py
"""

from datetime import date

company = env.company
Partner = env["res.partner"]
Account = env["account.account"]


def account(code):
    return Account.search([("code", "=", code)], limit=1)


def partner(name, **vals):
    rec = Partner.search([("name", "=", name)], limit=1)
    return rec if rec else Partner.create(dict(vals, name=name))


# --- parties ---------------------------------------------------------------
client = partner("شركة الخليج للتطوير العقاري", is_company=True,
                 customer_rank=1, city="دبي", vat="100200300400500")
sub_electrical = partner("مؤسسة النور للأعمال الكهربائية", is_company=True,
                         supplier_rank=1, city="الشارقة")
supplier_steel = partner("مصنع الاتحاد للحديد", is_company=True,
                         supplier_rank=1, city="أبوظبي")
manpower = partner("وكالة الإمارات لتوريد العمالة", is_company=True,
                   supplier_rank=1, city="دبي")

# --- the job ---------------------------------------------------------------
plan = env["account.analytic.plan"].search([], limit=1)
cost_center = env["account.analytic.account"].search(
    [("name", "=", "برج الخليج — عقد 2026/014")], limit=1)
if not cost_center:
    cost_center = env["account.analytic.account"].create({
        "name": "برج الخليج — عقد 2026/014",
        "plan_id": plan.id,
        "partner_id": client.id,
        "company_id": company.id,
    })

project = env["project.project"].search([("name", "=", "برج الخليج السكني")], limit=1)
if not project:
    project = env["project.project"].create({
        "name": "برج الخليج السكني",
        "partner_id": client.id,
        "company_id": company.id,
    })

contract = env["mizan.contract"].search([("code", "=", "CT-2026-014")], limit=1)
if not contract:
    contract = env["mizan.contract"].create({
        "name": "إنشاء برج الخليج السكني — 12 طابقاً",
        "code": "CT-2026-014",
        "partner_id": client.id,
        "project_id": project.id,
        "analytic_account_id": cost_center.id,
        "contract_value": 5_000_000.0,
        "budget_cost": 4_000_000.0,
        "retention_percent": 5.0,
        "date_start": date(2026, 1, 15),
        "date_end": date(2027, 6, 30),
    })
if contract.state == "draft":
    contract.action_start()

dist = {str(cost_center.id): 100}
purchase_journal = env["account.journal"].search([("type", "=", "purchase")], limit=1)


def vendor_bill(vendor, label, amount, expense_code, bill_date):
    """A supplier cost charged to the job."""
    existing = env["account.move"].search([("ref", "=", label)], limit=1)
    if existing:
        return existing
    bill = env["account.move"].create({
        "move_type": "in_invoice",
        "partner_id": vendor.id,
        "invoice_date": bill_date,
        "date": bill_date,
        "ref": label,
        "journal_id": purchase_journal.id,
        "invoice_line_ids": [(0, 0, {
            "name": label,
            "quantity": 1,
            "price_unit": amount,
            "account_id": account(expense_code).id,
            "analytic_distribution": dist,
        })],
    })
    bill.action_post()
    return bill


# --- costs on the job ------------------------------------------------------
vendor_bill(supplier_steel, "حديد تسليح — دفعة أولى", 420_000, "401001", date(2026, 3, 10))
vendor_bill(supplier_steel, "خرسانة جاهزة — الأساسات", 260_000, "401001", date(2026, 4, 5))
vendor_bill(sub_electrical, "مستخلص كهرباء رقم 1", 180_000, "401003", date(2026, 5, 20))
vendor_bill(manpower, "عمالة مؤقتة — مايو ويونيو", 95_000, "401002", date(2026, 6, 30))
vendor_bill(supplier_steel, "إيجار رافعة برجية", 70_000, "401004", date(2026, 7, 1))

# --- people ----------------------------------------------------------------
Employee = env["hr.employee"]


def employee(name, job, wage, start, identification):
    rec = Employee.search([("name", "=", name)], limit=1)
    if not rec:
        rec = Employee.create({
            "name": name,
            "job_title": job,
            "company_id": company.id,
            "identification_id": identification,
        })
    struct = env["hr.payroll.structure"].search([("code", "=", "UAE_STD")], limit=1)
    contract_rec = env["hr.contract"].search([("employee_id", "=", rec.id)], limit=1)
    if not contract_rec:
        env["hr.contract"].create({
            "name": "عقد عمل — %s" % name,
            "employee_id": rec.id,
            "date_start": start,
            "wage": wage,
            "struct_id": struct.id,
            "state": "open",
            "company_id": company.id,
        })
    return rec


engineer = employee("م. خالد الحوسني", "مهندس موقع", 14_000, date(2021, 2, 1), "784198512345671")
foreman = employee("سعيد الظاهري", "مشرف موقع (فورمان)", 7_500, date(2019, 6, 15), "784198812345672")
storekeeper = employee("أنور حسن", "أمين مخزن", 4_500, date(2023, 9, 1), "784199012345673")

# --- petty cash held on site ----------------------------------------------
# The foreman carries a float and spends it in small amounts; each expense is
# charged to the job so it reaches the progress calculation like any other cost.
expense_product = env["product.product"].search([("can_be_expensed", "=", True)], limit=1)
cash_journal = env["account.journal"].search([("type", "=", "cash")], limit=1)

if not env["hr.expense.sheet"].search_count([("name", "=", "عهدة الموقع — يوليو 2026")]):
    lines = [
        ("وقود ومواصلات للموقع", 2_400),
        ("أدوات ومستهلكات صغيرة", 3_100),
        ("ضيافة اجتماع استشاري المشروع", 850),
        ("رسوم تصاريح بلدية", 1_650),
    ]
    expenses = env["hr.expense"]
    for label, amount in lines:
        expenses |= env["hr.expense"].create({
            "name": label,
            "employee_id": foreman.id,
            "product_id": expense_product.id,
            "total_amount_currency": amount,
            "payment_mode": "company_account",
            "analytic_distribution": dist,
            "company_id": company.id,
            "date": date(2026, 7, 20),
        })
    sheet = env["hr.expense.sheet"].create({
        "name": "عهدة الموقع — يوليو 2026",
        "employee_id": foreman.id,
        "expense_line_ids": [(6, 0, expenses.ids)],
        "journal_id": cash_journal.id,
        "company_id": company.id,
    })
    sheet.action_submit_sheet()

# --- a client progress claim, settled by post-dated cheque -----------------
sale_journal = env["account.journal"].search([("type", "=", "sale")], limit=1)
claim = env["account.move"].search([("ref", "=", "مستخلص رقم 1 — برج الخليج")], limit=1)
if not claim:
    claim = env["account.move"].create({
        "move_type": "out_invoice",
        "partner_id": client.id,
        "invoice_date": date(2026, 8, 1),
        "date": date(2026, 8, 1),
        "ref": "مستخلص رقم 1 — برج الخليج",
        "journal_id": sale_journal.id,
        "invoice_line_ids": [(0, 0, {
            "name": "أعمال منفذة حتى 31 يوليو 2026",
            "quantity": 1,
            "price_unit": 1_200_000,
            "account_id": account("501001").id,
            "analytic_distribution": dist,
        })],
    })
    claim.action_post()

bank_journal = env["account.journal"].search([("type", "=", "bank")], limit=1)
if not env["mizan.cheque"].search_count([("name", "=", "CHQ-552001")]):
    env["mizan.cheque"].create({
        "name": "CHQ-552001",
        "cheque_type": "received",
        "partner_id": client.id,
        "bank_id": env["res.bank"].search([("name", "ilike", "EMIRATES")], limit=1).id
                   or env["res.bank"].search([], limit=1).id,
        "amount": 1_140_000,
        "issue_date": date(2026, 8, 5),
        "due_date": date(2026, 11, 5),
        "journal_id": bank_journal.id,
        "cheque_account_id": account("102013").id,
        "counterpart_account_id": account("102011").id,
        "invoice_ids": [(6, 0, claim.ids)],
    }).action_register()

env.cr.commit()
contract.invalidate_recordset()

print("RESULT contract=%s" % contract.name)
print("RESULT value=%.0f budget=%.0f" % (contract.contract_value, contract.budget_cost))
print("RESULT cost_to_date=%.0f" % contract.cost_incurred)
print("RESULT percent=%.1f" % contract.completion_percent)
print("RESULT revenue_earned=%.0f" % contract.revenue_earned)
print("RESULT to_recognise=%.0f" % contract.revenue_to_recognise)
