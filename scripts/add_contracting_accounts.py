# -*- coding: utf-8 -*-
"""Extend the UAE chart of accounts with the accounts a contractor needs.

The stock l10n_ae chart is written for a trading company: it has no work in
progress, no retention, no subcontractor ledger and no way to separate revenue
recognised on progress from revenue invoiced. Those are the accounts every
construction audit in the UAE asks for, so they are added here in code ranges
that do not collide with the existing chart:

    107xxx  contract assets        204xxx  contract liabilities
    401xxx  contract direct costs  501xxx  contract revenue

Re-runnable: accounts are matched by code, so running it twice changes nothing.

    docker compose exec -T odoo odoo shell --config=/etc/odoo/odoo.conf \
        --db_user odoo --db_password "$POSTGRES_PASSWORD" \
        -d <database> --no-http < scripts/add_contracting_accounts.py
"""

# (code, arabic name, english name, account_type, reconcile)
ACCOUNTS = [
    # --- contract assets -------------------------------------------------
    ('107001', 'أعمال تحت التنفيذ — تكاليف العقود', 'Contract WIP - Costs',
     'asset_current', False),
    ('107002', 'إيرادات مستحقة غير مفوترة', 'Accrued Unbilled Revenue',
     'asset_current', True),
    ('107003', 'محتجزات مدينة لدى العملاء', 'Retention Receivable',
     'asset_current', True),
    ('107004', 'مستخلصات تحت التحصيل', 'Progress Claims Receivable',
     'asset_current', True),
    ('107005', 'دفعات مقدمة لمقاولي الباطن', 'Advances to Subcontractors',
     'asset_current', True),
    ('107006', 'عهد مواقع العمل', 'Site Petty Cash Advances',
     'asset_current', True),
    ('107007', 'مواد بالمواقع', 'Materials on Site',
     'asset_current', False),
    ('107008', 'ضمانات بنكية — حسن التنفيذ', 'Performance Bond Deposits',
     'asset_current', False),

    # --- contract liabilities --------------------------------------------
    ('204001', 'محتجزات دائنة لمقاولي الباطن', 'Retention Payable - Subcontractors',
     'liability_current', True),
    ('204002', 'دفعات مقدمة من العملاء', 'Advances from Clients',
     'liability_current', True),
    ('204003', 'مستخلصات مقاولي الباطن المستحقة', 'Subcontractor Claims Payable',
     'liability_current', True),
    ('204004', 'فوترة زائدة عن الإنجاز', 'Billings in Excess of Work Done',
     'liability_current', False),
    ('204005', 'مخصص خسائر العقود المتوقعة', 'Provision for Contract Losses',
     'liability_current', False),
    ('204006', 'مخصص أعمال الصيانة وفترة الضمان', 'Warranty & Defects Provision',
     'liability_current', False),

    # --- contract direct costs -------------------------------------------
    ('401001', 'تكلفة المواد الإنشائية', 'Construction Materials',
     'expense_direct_cost', False),
    ('401002', 'أجور العمالة المباشرة', 'Direct Site Labour',
     'expense_direct_cost', False),
    ('401003', 'تكاليف مقاولي الباطن', 'Subcontractor Costs',
     'expense_direct_cost', False),
    ('401004', 'إيجار المعدات والآليات', 'Plant & Equipment Hire',
     'expense_direct_cost', False),
    ('401005', 'وقود وتشغيل المعدات', 'Plant Fuel & Running Costs',
     'expense_direct_cost', False),
    ('401006', 'نقل ومناولة بالموقع', 'Site Transport & Handling',
     'expense_direct_cost', False),
    ('401007', 'مصاريف الموقع غير المباشرة', 'Site Overheads',
     'expense_direct_cost', False),
    ('401008', 'تأمينات المشاريع', 'Project Insurance',
     'expense_direct_cost', False),
    ('401009', 'رسوم التصاريح والبلدية', 'Permits & Municipality Fees',
     'expense_direct_cost', False),
    ('401010', 'استشارات هندسية وتصميم', 'Engineering & Design Fees',
     'expense_direct_cost', False),
    ('401011', 'أعمال إعادة التنفيذ والإصلاح', 'Rework & Remedial Costs',
     'expense_direct_cost', False),
    ('401012', 'غرامات التأخير', 'Liquidated Damages',
     'expense', False),

    # --- contract revenue -------------------------------------------------
    ('501001', 'إيرادات العقود طويلة الأجل', 'Long-term Contract Revenue',
     'income', False),
    ('501002', 'إيرادات أوامر التغيير', 'Variation Order Revenue',
     'income', False),
    ('501003', 'إيرادات المطالبات', 'Claims Revenue',
     'income', False),
    ('501004', 'إيرادات أعمال الصيانة', 'Maintenance Contract Revenue',
     'income', False),
]

# (name, prefix_start, prefix_end, parent prefix)
GROUPS = [
    ('أصول العقود', '107', '107', '1'),
    ('التزامات العقود', '204', '204', '2'),
    ('تكاليف العقود المباشرة', '401', '401', '4'),
    ('إيرادات العقود', '501', '501', '5'),
]

Account = env['account.account']
Group = env['account.group']
company = env.company

created = updated = 0
for code, ar_name, en_name, acc_type, reconcile in ACCOUNTS:
    account = Account.search([('code', '=', code)], limit=1)
    values = {
        'code': code,
        'name': en_name,
        'account_type': acc_type,
        'reconcile': reconcile,
    }
    if account:
        account.write(values)
        updated += 1
    else:
        account = Account.create(values)
        created += 1
    account.with_context(lang='ar_001').name = ar_name

env.cr.commit()

for name, start, end, parent_prefix in GROUPS:
    parent = Group.search([
        ('code_prefix_start', '=', parent_prefix),
        ('company_id', '=', company.id),
    ], limit=1)
    group = Group.search([
        ('code_prefix_start', '=', start),
        ('company_id', '=', company.id),
    ], limit=1)
    values = {
        'name': name,
        'code_prefix_start': start,
        'code_prefix_end': end,
        'company_id': company.id,
        'parent_id': parent.id if parent else False,
    }
    if group:
        group.write(values)
    else:
        group = Group.create(values)
    group.with_context(lang='ar_001').name = name

env.cr.commit()
Account.search([])._compute_account_group()
env.cr.commit()

total = Account.search_count([])
print('RESULT created=%d updated=%d total_accounts=%d' % (created, updated, total))
