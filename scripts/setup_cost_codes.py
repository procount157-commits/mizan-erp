# -*- coding: utf-8 -*-
"""A cost-code structure a UAE building contractor can start from.

Modelled on the trade breakdown a bill of quantities already uses, so the codes
match how the estimator priced the job and how the consultant certifies it.
Runs against the template, so every client inherits it.
"""

CODES = [
    ("01-100", "Preliminaries & Site Setup", "الأعمال التمهيدية وتجهيز الموقع", "site", "401007"),
    ("01-200", "Site Management & Supervision", "الإدارة والإشراف بالموقع", "site", "401007"),
    ("01-300", "Temporary Works & Facilities", "الأعمال المؤقتة والمرافق", "site", "401007"),
    ("02-100", "Excavation & Earthworks", "الحفر والأعمال الترابية", "subcontract", "401003"),
    ("02-200", "Shoring & Dewatering", "التدعيم ونزح المياه", "subcontract", "401003"),
    ("03-100", "Concrete — Substructure", "الخرسانة — الأساسات", "material", "401001"),
    ("03-200", "Concrete — Superstructure", "الخرسانة — الهيكل", "material", "401001"),
    ("03-300", "Reinforcement Steel", "حديد التسليح", "material", "401001"),
    ("03-400", "Formwork & Scaffolding", "الشدة والسقالات", "material", "401001"),
    ("04-100", "Blockwork & Masonry", "أعمال البلوك والبناء", "subcontract", "401003"),
    ("05-100", "Structural Steel", "الإنشاءات المعدنية", "subcontract", "401003"),
    ("07-100", "Waterproofing & Insulation", "العزل المائي والحراري", "subcontract", "401003"),
    ("08-100", "Doors, Windows & Glazing", "الأبواب والنوافذ والزجاج", "subcontract", "401003"),
    ("09-100", "Plastering & Rendering", "أعمال اللياسة", "subcontract", "401003"),
    ("09-200", "Tiling & Flooring", "البلاط والأرضيات", "subcontract", "401003"),
    ("09-300", "Painting & Finishes", "الدهانات والتشطيبات", "subcontract", "401003"),
    ("15-100", "Plumbing & Drainage", "السباكة والصرف", "subcontract", "401003"),
    ("15-200", "HVAC", "التكييف والتهوية", "subcontract", "401003"),
    ("15-300", "Fire Fighting & Protection", "مكافحة الحريق", "subcontract", "401003"),
    ("16-100", "Electrical Installation", "الأعمال الكهربائية", "subcontract", "401003"),
    ("16-200", "Low Current & ELV", "التيار الخفيف والأنظمة", "subcontract", "401003"),
    ("20-100", "Direct Site Labour", "العمالة المباشرة بالموقع", "labour", "401002"),
    ("20-200", "Skilled Trades Labour", "عمالة الحرف المتخصصة", "labour", "401002"),
    ("30-100", "Plant Hire — External", "إيجار آليات من الخارج", "plant", "401004"),
    ("30-200", "Plant — Owned, Internal Hire", "آليات مملوكة — تحميل داخلي", "plant", "401013"),
    ("30-300", "Plant Fuel & Running", "وقود وتشغيل الآليات", "plant", "401005"),
    ("40-100", "Permits & Authority Fees", "التصاريح والرسوم الحكومية", "other", "401009"),
    ("40-200", "Project Insurance & Bonds", "تأمين المشروع والضمانات", "other", "401008"),
    ("40-300", "Design & Engineering Fees", "أتعاب التصميم والهندسة", "other", "401010"),
    ("50-100", "Rework & Remedial", "أعمال الإصلاح وإعادة التنفيذ", "other", "401011"),
]

Code = env["mizan.cost.code"]
Account = env["account.account"]
created = updated = 0
for code, english, arabic, category, account_code in CODES:
    account = Account.search([("code", "=", account_code)], limit=1)
    values = {
        "code": code,
        "name": english,
        "category": category,
        "account_id": account.id if account else False,
        "company_id": env.company.id,
    }
    record = Code.search(
        [("code", "=", code), ("company_id", "=", env.company.id)], limit=1)
    if record:
        record.with_context(lang="en_US").write(values)
        updated += 1
    else:
        record = Code.with_context(lang="en_US").create(values)
        created += 1
    record.with_context(lang="ar_001").write({"name": arabic})

env.cr.commit()
print("cost codes created: %d, updated: %d, total: %d"
      % (created, updated, Code.search_count([])))
