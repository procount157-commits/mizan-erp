# -*- coding: utf-8 -*-
"""Tag the existing costs with their cost code, and budget each contract by code.

Back-filling rather than re-seeding: the ledger is correct and posted, and the
cost code is an analysis dimension on the line, not part of the double entry.
Rewriting it on posted lines changes nothing a trial balance would notice.
"""
Code = env["mizan.cost.code"]
Line = env["account.move.line"]


def code(reference):
    found = Code.search([("code", "=", reference)], limit=1)
    if not found:
        raise ValueError("missing cost code %s" % reference)
    return found


# What each posted cost actually was, matched on the description it carries.
MATCH = [
    ("حديد تسليح وخرسانة", "03-300"),
    ("مواد تشطيبات", "09-300"),
    ("مواد صحية وكهربائية", "15-100"),
    ("مواد إنشائية", "03-200"),
    ("بلوك ومواد بناء", "04-100"),
    ("أعمال هيكلية", "03-200"),
    ("أعمال خرسانية", "03-100"),
    ("أعمال كهروميكانيك", "16-100"),
    ("أعمال ميكانيكية", "15-200"),
    ("إيجار حفار وونش", "30-100"),
    ("إيجار معدات", "30-100"),
    ("رسوم تصاريح", "40-100"),
    ("رسوم تصريح", "40-100"),
    ("أجور عمالة الموقع", "20-100"),
    ("إهلاك الآلات", "30-200"),
    ("تأمين المشاريع", "40-200"),
    ("وقود مركبة", "30-300"),
    ("أدوات ومواد موقع", "03-400"),
]

tagged = 0
costs = Line.search([
    ("parent_state", "=", "posted"),
    ("account_id.account_type", "in",
     ("expense_direct_cost", "expense", "expense_depreciation")),
    ("mizan_cost_code_id", "=", False),
])
for line in costs:
    label = (line.name or "") + " " + (line.move_id.ref or "")
    for needle, reference in MATCH:
        if needle in label:
            line.mizan_cost_code_id = code(reference).id
            tagged += 1
            break
env.cr.commit()
print("cost lines tagged: %d of %d" % (tagged, len(costs)))

# ---------------------------------------------------------------- budgets
# Split each contract's budget across the trades it is actually built from.
BUDGETS = {
    "CT-2026-001": [          # villa, budget 1,850,000
        ("01-100", 60000), ("02-100", 90000), ("03-100", 180000),
        ("03-200", 320000), ("03-300", 240000), ("03-400", 70000),
        ("04-100", 110000), ("09-200", 120000), ("09-300", 130000),
        ("15-100", 95000), ("16-100", 180000), ("20-100", 140000),
        ("30-100", 60000), ("40-100", 25000), ("40-200", 30000),
    ],
    "CT-2026-002": [          # school extension, budget 4,400,000
        ("01-100", 150000), ("01-200", 120000), ("02-100", 260000),
        ("03-100", 420000), ("03-200", 760000), ("03-300", 540000),
        ("03-400", 180000), ("04-100", 300000), ("05-100", 240000),
        ("09-200", 200000), ("09-300", 180000), ("15-100", 160000),
        ("15-200", 290000), ("16-100", 340000), ("20-100", 180000),
        ("30-100", 60000), ("40-100", 20000),
    ],
}

BudgetLine = env["mizan.contract.budget.line"]
for reference, rows in BUDGETS.items():
    contract = env["mizan.contract"].search([("code", "=", reference)], limit=1)
    if not contract:
        continue
    contract.budget_line_ids.unlink()
    for sequence, (cost_code, amount) in enumerate(rows, start=1):
        BudgetLine.create({
            "contract_id": contract.id,
            "sequence": sequence * 10,
            "cost_code_id": code(cost_code).id,
            "budget_amount": amount,
        })
    contract.invalidate_recordset()
    print("%s: %d cost codes, budget %.2f (contract budget %.2f)%s" % (
        reference, len(rows), contract.budget_line_total, contract.budget_cost,
        "  <-- MISMATCH" if contract.budget_line_mismatch else ""))
env.cr.commit()
