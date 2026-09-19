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


def ensure(code, name, account_type, reconcile=False):
    """Relabel a known account, or create it if the code is free."""
    account = by_code(code)
    if account:
        account.write({"name": name, "account_type": account_type})
        return account, False
    values = {
        "code": code,
        "name": name,
        "account_type": account_type,
        "reconcile": reconcile,
    }
    if "company_ids" in Account._fields:
        values["company_ids"] = [(6, 0, [company.id])]
    else:
        values["company_id"] = company.id
    return Account.create(values), True


# ------------------------------------------------------------------- equity
# A UAE LLC must transfer 10% of annual profit to a statutory reserve until it
# reaches half the capital, so the reserve is a real account here, not decoration.
EQUITY = [
    ("300001", "رأس المال المدفوع", "equity"),
    ("300002", "حساب الشركاء الجاري", "equity"),
    ("300003", "الاحتياطي القانوني", "equity"),
    ("300004", "أرباح مُرحّلة من سنوات سابقة", "equity"),
    ("300005", "توزيعات أرباح", "equity"),
]

# -------------------------------------------------------------- fixed assets
# Reclassified, not renamed only: an accumulated depreciation account sitting in
# current assets understates the fixed asset base and overstates liquidity.
FIXED = [
    ("106001", "تحسينات على عقار مستأجر", "asset_fixed"),
    ("106002", "أثاث وتجهيزات مكتبية", "asset_fixed"),
    ("106003", "أجهزة حاسب وبرمجيات", "asset_fixed"),
    ("106004", "سيارات ومركبات", "asset_fixed"),
    ("106005", "أعمال رأسمالية تحت التنفيذ", "asset_fixed"),
    ("106006", "مجمع إطفاء تحسينات العقار المستأجر", "asset_fixed"),
    ("106007", "مجمع إهلاك الأثاث والتجهيزات", "asset_fixed"),
    ("106008", "مجمع إهلاك أجهزة الحاسب والبرمجيات", "asset_fixed"),
    ("106009", "مجمع إهلاك السيارات والمركبات", "asset_fixed"),
    ("106010", "علامات تجارية مسجلة", "asset_fixed"),
    ("106012", "آلات ومعدات إنشائية", "asset_fixed"),
    ("106013", "مجمع إهلاك الآلات والمعدات الإنشائية", "asset_fixed"),
    ("106014", "سقالات وقوالب ومعدات صغيرة", "asset_fixed"),
    ("106015", "مجمع إهلاك السقالات والقوالب", "asset_fixed"),
]

# --------------------------------------------- contracting accounts in Arabic
# Added in English by an earlier script; an Arabic-facing ledger should not have
# half its contracting accounts in English.
CONTRACTING = [
    ("107001", "تكاليف عقود تحت التنفيذ", "asset_current"),
    ("107002", "إيراد مستحق غير مفوتر", "asset_current"),
    ("107003", "محتجزات مدينة لدى العملاء", "asset_current"),
    ("107004", "مستخلصات مدينة", "asset_current"),
    ("107005", "دفعات مقدمة لمقاولي الباطن", "asset_current"),
    ("107006", "عهد نقدية بالمواقع", "asset_current"),
    ("107007", "مواد بالموقع", "asset_current"),
    ("107008", "تأمينات حسن الأداء", "asset_current"),
    ("204001", "محتجزات دائنة لمقاولي الباطن", "liability_current"),
    ("204002", "دفعات مقدمة من العملاء", "liability_current"),
    ("204003", "مطالبات مقاولي الباطن", "liability_current"),
    ("204004", "فواتير تتجاوز الأعمال المنفذة", "liability_current"),
    ("204005", "مخصص خسائر العقود", "liability_current"),
    ("204006", "مخصص الضمان وإصلاح العيوب", "liability_current"),
    ("401001", "مواد إنشائية", "expense_direct_cost"),
    ("401002", "عمالة مباشرة بالموقع", "expense_direct_cost"),
    ("401003", "تكاليف مقاولي الباطن", "expense_direct_cost"),
    ("401004", "إيجار آليات ومعدات", "expense_direct_cost"),
    ("401005", "وقود وتشغيل الآليات", "expense_direct_cost"),
    ("401006", "نقل ومناولة بالموقع", "expense_direct_cost"),
    ("401007", "مصاريف موقع غير مباشرة", "expense_direct_cost"),
    ("401008", "تأمين المشاريع", "expense_direct_cost"),
    ("401009", "رسوم تصاريح وبلدية", "expense_direct_cost"),
    ("401010", "أتعاب هندسية وتصميم", "expense_direct_cost"),
    ("401011", "أعمال إعادة وإصلاح", "expense_direct_cost"),
    ("401012", "غرامات تأخير", "expense"),
    # Depreciation of owned plant is a cost of doing the work, not an office
    # overhead — a contractor that hires a crane charges it to the job, and one
    # that owns the crane should be no different.
    # Plant depreciation only. The chart already carries depreciation accounts
    # for vehicles, furniture and computers (400063-400066); what it lacks is
    # one for construction plant, because the standard UAE chart is not written
    # for contractors.
    ("401013", "إهلاك الآلات والمعدات الإنشائية", "expense_direct_cost"),
    ("501001", "إيرادات عقود طويلة الأجل", "income"),
    ("501002", "إيرادات أوامر تغييرية", "income"),
    ("501003", "إيرادات مطالبات", "income"),
    ("501004", "إيرادات عقود صيانة", "income"),
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
    for code, name, account_type in group:
        account, is_new = ensure(code, name, account_type)
        created += int(is_new)
        renamed += int(not is_new)

env.cr.commit()
print("accounts created: %d, corrected: %d" % (created, renamed))

from collections import Counter
counts = Counter(Account.search([]).mapped("account_type"))
print("equity accounts now: %d" % counts.get("equity", 0))
print("fixed asset accounts now: %d" % counts.get("asset_fixed", 0))
print("total accounts: %d" % Account.search_count([]))
