# -*- coding: utf-8 -*-
"""Repair Arabic report labels that OCA ships as question marks.

OCA's account_financial_report carries an Arabic translation file in which some
entries are runs of "?" rather than Arabic. Odoo loads them like any other
translation, so the trial balance prints its own title and two column headings
as "???????? ????????". Removing the file stops new databases inheriting it;
this repairs the terms already loaded.

Idempotent — run it on the template and on every existing client.
"""
import re

REPLACEMENTS = {
    "Trial Balance -": "ميزان المراجعة -",
    "Period balance": "حركة الفترة",
    "Ending balance": "الرصيد الختامي",
    "Initial balance": "الرصيد الافتتاحي",
}

View = env["ir.ui.view"]
QUESTION_RUN = re.compile(r"\?{3,}")


def arch(view, lang):
    """The arch as stored for one language. Through the ORM arch_db is a plain
    string for the active language, never the jsonb dict SQL shows."""
    return view.with_context(lang=lang).arch_db or ""


broken = View.search([]).filtered(
    lambda v: QUESTION_RUN.search(arch(v, "ar_001")))
print("views carrying question-mark translations: %d" % len(broken))

repaired = 0
for view in broken:
    english = arch(view, "en_US")
    fixed = english
    for source, target in REPLACEMENTS.items():
        fixed = fixed.replace(source, target)
    view.with_context(lang="ar_001").write({"arch_db": fixed})
    repaired += 1
    print("  repaired %s" % view.key)

env.cr.commit()
still = View.search([]).filtered(
    lambda v: QUESTION_RUN.search(arch(v, "ar_001")))
print("repaired %d view(s); remaining with question marks: %d" % (repaired, len(still)))
