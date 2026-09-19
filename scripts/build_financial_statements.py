# -*- coding: utf-8 -*-
"""Balance sheet and profit & loss, which Odoo Community does not ship.

account_financial_report gives ledgers, the trial balance and ageing, and stops
there. The two statements every owner, bank and auditor actually asks for are
absent from Community entirely, so they are built here on OCA mis_builder.

The bracketed domain filters ACCOUNTS, not journal items, so the fields are
account.account fields (account_type, code) with no account_id prefix.

Lines are selected by account TYPE, not by code prefix. This chart mixes them —
400001 is a direct cost while 400003 is an overhead, both in the 400 range — so
a prefix rule would quietly file cost of sales under administrative expenses.
"""

Report = env["mis.report"]
KPI = env["mis.report.kpi"]
Instance = env["mis.report.instance"]


def build(name, rows, description):
    report = Report.search([("name", "=", name)], limit=1)
    if report:
        report.kpi_ids.unlink()
    else:
        report = Report.create({"name": name, "description": description})
    for seq, (kpi_name, label, expression, style) in enumerate(rows, start=1):
        KPI.create({
            "report_id": report.id,
            "sequence": seq * 10,
            "name": kpi_name,
            "description": label,
            "expression": expression,
            "type": "num",
            "compare_method": "none",
            "accumulation_method": "sum" if expression else "sum",
            "style_id": style.id if style else False,
        })
    return report


Style = env["mis.report.style"]
bold = Style.search([("name", "=", "Mizan Total")], limit=1) or Style.create({
    "name": "Mizan Total", "font_weight": "bold", "font_weight_inherit": False,
})

# ------------------------------------------------------------ balance sheet
# bale = ending balance. Debits are positive, so liabilities, equity and income
# are negated to present them the way a reader expects.
BALANCE_SHEET = [
    # Selected by code alone. The bank sits in asset_cash and the petty cash box
    # in asset_current, so adding "type is cash" to "code starts 101" counts the
    # bank twice and pushes the error into whatever line absorbs the remainder.
    ("cash", "النقد وما في حكمه",
     "bale[('code','=like','101%')] + bale[('code','=like','105%')]", None),
    ("receivables", "ذمم مدينة — عملاء",
     "bale[('account_type','=','asset_receivable')]", None),
    ("contract_assets", "أصول العقود (إيراد مستحق ومحتجزات)",
     "bale[('code','=like','107%')]", None),
    ("other_current", "أصول متداولة أخرى ومصاريف مقدمة",
     "bale[('account_type','in',('asset_current','asset_cash'))] "
     "- bale[('code','=like','101%')] "
     "- bale[('code','=like','105%')] "
     "- bale[('code','=like','107%')]", None),
    ("total_current_assets", "إجمالي الأصول المتداولة",
     "cash + receivables + contract_assets + other_current", bold),
    ("fixed_assets", "الأصول الثابتة (بالصافي)",
     "bale[('account_type','in',('asset_fixed','asset_non_current'))]", None),
    ("total_assets", "إجمالي الأصول", "total_current_assets + fixed_assets", bold),

    ("payables", "ذمم دائنة — موردون",
     "-bale[('account_type','=','liability_payable')]", None),
    ("contract_liabilities", "التزامات العقود (فوترة زائدة ومحتجزات)",
     "-bale[('code','=like','204%')]", None),
    ("other_liabilities", "التزامات متداولة أخرى ومستحقات",
     "-bale[('account_type','in',('liability_current','liability_non_current'))] "
     "+ bale[('code','=like','204%')]", None),
    ("total_liabilities", "إجمالي الالتزامات",
     "payables + contract_liabilities + other_liabilities", bold),

    ("capital", "رأس المال والاحتياطيات",
     "-bale[('account_type','in',('equity','equity_unaffected'))]", None),
    ("result", "نتيجة الفترة",
     "-balp[('account_type','in',"
     "('income','income_other','expense','expense_direct_cost','expense_depreciation'))]", None),
    ("total_equity", "إجمالي حقوق الملكية", "capital + result", bold),
    ("check", "إجمالي الالتزامات وحقوق الملكية",
     "total_liabilities + total_equity", bold),
]

# --------------------------------------------------------- profit and loss
PROFIT_LOSS = [
    ("revenue", "إيرادات العقود المعترف بها",
     "-balp[('account_type','in',('income','income_other'))]", None),
    ("direct_cost", "تكلفة تنفيذ العقود",
     "balp[('account_type','=','expense_direct_cost')]", None),
    ("gross_profit", "مجمل الربح", "revenue - direct_cost", bold),
    ("gross_margin", "هامش مجمل الربح %",
     "gross_profit / revenue * 100 if revenue else AccountingNone", None),
    ("opex", "مصاريف عمومية وإدارية",
     "balp[('account_type','in',('expense','expense_depreciation'))]", None),
    ("net_profit", "صافي الربح", "gross_profit - opex", bold),
    ("net_margin", "هامش صافي الربح %",
     "net_profit / revenue * 100 if revenue else AccountingNone", None),
]

bs = build("الميزانية العمومية", BALANCE_SHEET,
           "المركز المالي — الأصول والالتزامات وحقوق الملكية")
pl = build("قائمة الدخل", PROFIT_LOSS,
           "الإيرادات والتكاليف ونتيجة الفترة")
env.cr.commit()
print("templates: %s / %s" % (bs.name, pl.name))


def instance(report, name, mode="fix"):
    inst = Instance.search([("name", "=", name)], limit=1)
    if inst:
        inst.period_ids.unlink()
    else:
        inst = Instance.create({"name": name, "report_id": report.id})
    inst.write({"report_id": report.id, "comparison_mode": False,
                "date_from": "2026-01-01", "date_to": "2026-12-31",
                "target_move": "posted"})
    return inst


i_bs = instance(bs, "الميزانية العمومية — 2026")
i_pl = instance(pl, "قائمة الدخل — 2026")
env.cr.commit()
print("instances ready: %s | %s" % (i_bs.name, i_pl.name))
