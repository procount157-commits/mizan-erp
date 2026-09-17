# -*- coding: utf-8 -*-
"""Build a hierarchy over the flat UAE chart of accounts.

l10n_ae creates 168 accounts with no account.group records, so the Chart of
Accounts screen is one long flat list. Odoo assigns each account to the most
specific group whose prefix range covers its code, so defining the ranges here
turns the same accounts into a collapsible tree and makes the financial reports
produce group subtotals.

Prefix start and end must be the same length — Odoo enforces that with a
database constraint.

    docker compose exec -T odoo odoo shell --config=/etc/odoo/odoo.conf \
        --db_user odoo --db_password "$POSTGRES_PASSWORD" \
        -d <database> --no-http < scripts/build_account_groups.py
"""

# (key, name, prefix_start, prefix_end, parent_key)
GROUPS = [
    ('1', 'الأصول', '1', '1', None),
    ('100', 'النقد وما في حكمه', '100', '100', '1'),
    ('101', 'البنوك والصناديق', '101', '101', '1'),
    ('102', 'الذمم المدينة', '102', '102', '1'),
    ('103', 'المخزون والشحن', '103', '103', '1'),
    ('104', 'مصاريف مدفوعة مقدماً وتأمينات', '104', '104', '1'),
    ('106', 'الأصول الثابتة', '106', '106', '1'),
    ('128', 'أصول أخرى', '128', '128', '1'),

    ('2', 'الالتزامات', '2', '2', None),
    ('201', 'الالتزامات المتداولة', '201', '201', '2'),
    ('202', 'الالتزامات طويلة الأجل', '202', '202', '2'),
    ('212', 'إيرادات مؤجلة', '212', '212', '2'),

    ('3', 'حقوق الملكية', '3', '3', None),

    ('4', 'المصروفات', '4', '4', None),
    ('40000', 'تكلفة المبيعات', '400001', '400002', '4'),
    ('40001', 'تكاليف الموظفين', '400003', '400015', '4'),
    ('40002', 'الإيجارات والخدمات', '400016', '400023', '4'),
    ('40003', 'السفر والضيافة', '400024', '400028', '4'),
    ('40004', 'أتعاب مهنية', '400029', '400034', '4'),
    ('40005', 'مخصصات وإعدامات', '400035', '400039', '4'),
    ('40006', 'مصاريف تشغيلية عامة', '400040', '400050', '4'),
    ('40007', 'مصاريف بنكية وتمويلية', '400051', '400062', '4'),
    ('40008', 'الإهلاك والإطفاء', '400063', '400070', '4'),

    ('5', 'الإيرادات', '5', '5', None),
    ('50000', 'إيرادات التشغيل', '500001', '500008', '5'),
    ('50001', 'إيرادات أخرى', '500009', '500013', '5'),
]

Group = env['account.group']
company = env.company
by_key = {}

for key, name, start, end, parent in GROUPS:
    existing = Group.search([
        ('code_prefix_start', '=', start),
        ('company_id', '=', company.id),
    ], limit=1)
    values = {
        'name': name,
        'code_prefix_start': start,
        'code_prefix_end': end,
        'company_id': company.id,
        'parent_id': by_key[parent].id if parent else False,
    }
    group = existing if existing else Group.create(values)
    if existing:
        group.write(values)
    group.with_context(lang='ar_001').name = name
    by_key[key] = group

env.cr.commit()

# group_id is computed from the prefixes; recompute so the tree fills in now.
env['account.account'].search([])._compute_account_group()
env.cr.commit()

grouped = env['account.account'].search_count([('group_id', '!=', False)])
total = env['account.account'].search_count([])
print('RESULT groups=%d accounts_grouped=%d/%d' % (len(by_key), grouped, total))
