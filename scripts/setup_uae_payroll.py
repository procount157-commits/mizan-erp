# -*- coding: utf-8 -*-
"""Build a UAE salary structure on top of OCA payroll.

UAE contracts are written as a basic wage plus allowances, and that split is not
cosmetic: end-of-service gratuity is calculated on the *basic* wage only, so the
structure has to keep it separate from housing and transport. Gratuity itself
follows Federal Decree-Law 33 of 2021 — 21 days of basic pay for each of the
first five years, 30 days for each year after that.

    docker compose exec -T odoo odoo shell --config=/etc/odoo/odoo.conf \
        --db_user odoo --db_password "$POSTGRES_PASSWORD" \
        -d <database> --no-http < scripts/setup_uae_payroll.py
"""

Rule = env["hr.salary.rule"]
Structure = env["hr.payroll.structure"]
Category = env["hr.salary.rule.category"]
Account = env["account.account"]


def account(code):
    return Account.search([("code", "=", code)], limit=1)


def category(code, name):
    cat = Category.search([("code", "=", code)], limit=1)
    if not cat:
        cat = Category.create({"code": code, "name": name})
    return cat


cat_basic = category("BASIC", "Basic")
cat_alw = category("ALW", "Allowances")
cat_gross = category("GROSS", "Gross")
cat_ded = category("DED", "Deductions")
cat_net = category("NET", "Net")
cat_comp = category("COMP", "Employer Charges")

structure = Structure.search([("code", "=", "UAE_STD")], limit=1)
if not structure:
    structure = Structure.create({"name": "UAE Standard Salary", "code": "UAE_STD"})
structure.with_context(lang="ar_001").name = "هيكل الراتب الإماراتي"

# (code, en name, ar name, category, sequence, amount_select, value, debit, credit)
RULES = [
    ("BASIC", "Basic Salary", "الراتب الأساسي", cat_basic, 10,
     "code", "result = contract.wage", "400003", None),

    ("HOUSE", "Housing Allowance", "بدل السكن", cat_alw, 20,
     "code", "result = contract.wage * 0.25", "400004", None),

    ("TRANS", "Transport Allowance", "بدل المواصلات", cat_alw, 30,
     "code", "result = contract.wage * 0.10", "400005", None),

    ("OT", "Overtime", "العمل الإضافي", cat_alw, 40,
     "code", "result = inputs.OT.amount if inputs.OT else 0", "400003", None),

    ("GROSS", "Gross Salary", "إجمالي الراتب", cat_gross, 100,
     "code", "result = categories.BASIC + categories.ALW", None, None),

    ("ADV", "Advance Deduction", "خصم السلف", cat_ded, 110,
     "code", "result = -(inputs.ADV.amount if inputs.ADV else 0)", None, "107006"),

    ("ABS", "Unpaid Absence", "خصم الغياب", cat_ded, 120,
     "code", "result = -(inputs.ABS.amount if inputs.ABS else 0)", None, "400003"),

    ("NET", "Net Payable", "صافي المستحق", cat_net, 200,
     "code", "result = categories.BASIC + categories.ALW + categories.DED",
     None, "201004"),

    # Gratuity is an employer liability accrued monthly, not a deduction from pay.
    ("EOSB", "End of Service Accrual", "مخصص مكافأة نهاية الخدمة", cat_comp, 210,
     "code",
     "years = 0.0\n"
     "if contract.date_start:\n"
     "    years = (payslip.date_to - contract.date_start).days / 365.0\n"
     "days = 21.0 if years <= 5 else 30.0\n"
     "result = contract.wage / 30.0 * days / 12.0",
     "400008", "202001"),
]

created = 0
for code, en, ar, cat, seq, amount_select, value, debit, credit in RULES:
    rule = Rule.search([("code", "=", code)], limit=1)
    values = {
        "name": en,
        "code": code,
        "category_id": cat.id,
        "sequence": seq,
        "condition_select": "none",
        "amount_select": amount_select,
        "amount_python_compute": value,
        "appears_on_payslip": True,
    }
    if debit and account(debit):
        values["account_debit"] = account(debit).id
    if credit and account(credit):
        values["account_credit"] = account(credit).id
    if rule:
        rule.write(values)
    else:
        rule = Rule.create(values)
        created += 1
    rule.with_context(lang="ar_001").name = ar
    if rule not in structure.rule_ids:
        structure.write({"rule_ids": [(4, rule.id)]})

env.cr.commit()
print("RESULT structure=%s rules=%d created=%d"
      % (structure.code, len(structure.rule_ids), created))
