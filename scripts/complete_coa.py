# -*- coding: utf-8 -*-
"""Complete the chart of accounts: equity, fixed assets, Arabic names.

l10n_ae's UAE chart ships without a single equity account — the group
"3 حقوق الملكية" exists and is empty — so a balance sheet has nowhere to put
capital or retained earnings and cannot be presented at all. It also files
vehicles, plant and their accumulated depreciation under current assets, which
makes working capital look far healthier than it is.

Both are wrong for every client, not just one, so this runs against the
template as well.

    docker compose exec -T odoo odoo shell --config=/etc/odoo/odoo.conf \
        --db_user odoo --db_password "$PW" -d <database> --no-http \
        < scripts/complete_coa.py
"""

Account = env["account.account"]
company = env.company


def by_code(code):
    return Account.search([("code", "=", code)], limit=1)


def ensure(code, english, arabic, account_type, reconcile=False):
    """Relabel a known account, or create it if the code is free.

    The English name is the stored source and the Arabic one is its
    translation, the same way l10n_ae and arabize_coa.py do it. Writing Arabic
    into the source instead leaves the account reading Arabic for a user who
    picked English — the chart then speaks both languages at once and neither
    properly.
    """
    account = by_code(code)
    if account:
        account.with_context(lang="en_US").write(
            {"name": english, "account_type": account_type})
        account.with_context(lang="ar_001").write({"name": arabic})
        return account, False
    values = {
        "code": code,
        "name": english,
        "account_type": account_type,
        "reconcile": reconcile,
    }
    if "company_ids" in Account._fields:
        values["company_ids"] = [(6, 0, [company.id])]
    else:
        values["company_id"] = company.id
    account = Account.create(values)
    account.with_context(lang="ar_001").write({"name": arabic})
    return account, True


# ------------------------------------------------------------------- equity
# A UAE LLC must transfer 10% of annual profit to a statutory reserve until it
# reaches half the capital, so the reserve is a real account here, not decoration.
EQUITY = [
    ("300001", "Paid-up Share Capital", "رأس المال المدفوع", "equity"),
    ("300002", "Partners' Current Account", "حساب الشركاء الجاري", "equity"),
    ("300003", "Statutory Reserve", "الاحتياطي القانوني", "equity"),
    ("300004", "Retained Earnings", "أرباح مُرحّلة من سنوات سابقة", "equity"),
    ("300005", "Dividends Declared", "توزيعات أرباح", "equity"),
]

# -------------------------------------------------------------- fixed assets
# Reclassified, not renamed only: an accumulated depreciation account sitting in
# current assets understates the fixed asset base and overstates liquidity.
FIXED = [
    ("106001", "Leasehold Improvements", "تحسينات على عقار مستأجر", "asset_fixed"),
    ("106002", "Furniture & Office Equipment", "أثاث وتجهيزات مكتبية", "asset_fixed"),
    ("106003", "Computer Hardware & Software", "أجهزة حاسب وبرمجيات", "asset_fixed"),
    ("106004", "Motor Vehicles", "سيارات ومركبات", "asset_fixed"),
    ("106005", "Capital Work in Progress", "أعمال رأسمالية تحت التنفيذ", "asset_fixed"),
    ("106006", "Accumulated Amortisation - Leasehold Improvements", "مجمع إطفاء تحسينات العقار المستأجر", "asset_fixed"),
    ("106007", "Accumulated Depreciation - Furniture & Equipment", "مجمع إهلاك الأثاث والتجهيزات", "asset_fixed"),
    ("106008", "Accumulated Depreciation - Computer Hardware & Software", "مجمع إهلاك أجهزة الحاسب والبرمجيات", "asset_fixed"),
    ("106009", "Accumulated Depreciation - Motor Vehicles", "مجمع إهلاك السيارات والمركبات", "asset_fixed"),
    ("106010", "Registered Trademarks", "علامات تجارية مسجلة", "asset_fixed"),
    ("106012", "Construction Plant & Machinery", "آلات ومعدات إنشائية", "asset_fixed"),
    ("106013", "Accumulated Depreciation - Construction Plant", "مجمع إهلاك الآلات والمعدات الإنشائية", "asset_fixed"),
    ("106014", "Scaffolding, Formwork & Small Tools", "سقالات وقوالب ومعدات صغيرة", "asset_fixed"),
    ("106015", "Accumulated Depreciation - Scaffolding & Formwork", "مجمع إهلاك السقالات والقوالب", "asset_fixed"),
]

# --------------------------------------------- contracting accounts in Arabic
# Added in English by an earlier script; an Arabic-facing ledger should not have
# half its contracting accounts in English.
CONTRACTING = [
    ("107001", "Contract Work in Progress - Costs", "تكاليف عقود تحت التنفيذ", "asset_current"),
    ("107002", "Accrued Unbilled Revenue", "إيراد مستحق غير مفوتر", "asset_current"),
    ("107003", "Retention Receivable from Clients", "محتجزات مدينة لدى العملاء", "asset_current"),
    ("107004", "Progress Claims Receivable", "مستخلصات مدينة", "asset_current"),
    ("107005", "Advances to Subcontractors", "دفعات مقدمة لمقاولي الباطن", "asset_current"),
    ("107006", "Site Petty Cash Advances", "عهد نقدية بالمواقع", "asset_current"),
    ("107007", "Materials on Site", "مواد بالموقع", "asset_current"),
    ("107008", "Performance Bond Deposits", "تأمينات حسن الأداء", "asset_current"),
    ("204001", "Retention Payable to Subcontractors", "محتجزات دائنة لمقاولي الباطن", "liability_current"),
    ("204002", "Advances from Clients", "دفعات مقدمة من العملاء", "liability_current"),
    ("204003", "Subcontractor Claims Payable", "مطالبات مقاولي الباطن", "liability_current"),
    ("204004", "Billings in Excess of Work Done", "فواتير تتجاوز الأعمال المنفذة", "liability_current"),
    ("204005", "Provision for Contract Losses", "مخصص خسائر العقود", "liability_current"),
    ("204006", "Warranty & Defects Provision", "مخصص الضمان وإصلاح العيوب", "liability_current"),
    ("401001", "Construction Materials", "مواد إنشائية", "expense_direct_cost"),
    ("401002", "Direct Site Labour", "عمالة مباشرة بالموقع", "expense_direct_cost"),
    ("401003", "Subcontractor Costs", "تكاليف مقاولي الباطن", "expense_direct_cost"),
    ("401004", "Plant & Equipment Hire", "إيجار آليات ومعدات", "expense_direct_cost"),
    ("401005", "Plant Fuel & Running Costs", "وقود وتشغيل الآليات", "expense_direct_cost"),
    ("401006", "Site Transport & Handling", "نقل ومناولة بالموقع", "expense_direct_cost"),
    ("401007", "Site Overheads", "مصاريف موقع غير مباشرة", "expense_direct_cost"),
    ("401008", "Project Insurance", "تأمين المشاريع", "expense_direct_cost"),
    ("401009", "Permits & Municipality Fees", "رسوم تصاريح وبلدية", "expense_direct_cost"),
    ("401010", "Engineering & Design Fees", "أتعاب هندسية وتصميم", "expense_direct_cost"),
    ("401011", "Rework & Remedial Costs", "أعمال إعادة وإصلاح", "expense_direct_cost"),
    ("401012", "Liquidated Damages", "غرامات تأخير", "expense"),
    # Depreciation of owned plant is a cost of doing the work, not an office
    # overhead — a contractor that hires a crane charges it to the job, and one
    # that owns the crane should be no different.
    # Plant depreciation only. The chart already carries depreciation accounts
    # for vehicles, furniture and computers (400063-400066); what it lacks is
    # one for construction plant, because the standard UAE chart is not written
    # for contractors.
    ("401013", "Depreciation - Construction Plant", "إهلاك الآلات والمعدات الإنشائية", "expense_direct_cost"),
    ("501001", "Long-term Contract Revenue", "إيرادات عقود طويلة الأجل", "income"),
    ("501002", "Variation Order Revenue", "إيرادات أوامر تغييرية", "income"),
    ("501003", "Claims Revenue", "إيرادات مطالبات", "income"),
    ("501004", "Maintenance Contract Revenue", "إيرادات عقود صيانة", "income"),
]

# Repair: an earlier version of this script took 400070 and 400071 — which
# l10n_ae ships as the IFRS 16 right-of-use depreciation and cash discount loss
# accounts — and relabelled them as depreciation accounts that the chart
# already had elsewhere. Renaming a localisation account does not create a new
# one, it destroys the meaning of the old one.
RESTORE = [
    ("400070", "Depreciation on right of use asset (IFRS 16)", "expense"),
    ("400071", "Cash Discount Loss", "expense"),
]
for code, name, account_type in RESTORE:
    account = by_code(code)
    if account and account.name != name:
        account.write({"name": name, "account_type": account_type})
        print("restored %s to '%s'" % (code, name))

created = renamed = 0
for group in (EQUITY, FIXED, CONTRACTING):
    for code, english, arabic, account_type in group:
        account, is_new = ensure(code, english, arabic, account_type)
        created += int(is_new)
        renamed += int(not is_new)

env.cr.commit()
print("accounts created: %d, corrected: %d" % (created, renamed))

from collections import Counter
counts = Counter(Account.search([]).mapped("account_type"))
print("equity accounts now: %d" % counts.get("equity", 0))
print("fixed asset accounts now: %d" % counts.get("asset_fixed", 0))
print("total accounts: %d" % Account.search_count([]))
