# -*- coding: utf-8 -*-
"""Put the site engineers into the Site Engineer role, and say who was missed.

    docker exec -i mizan-odoo odoo shell -d <db> --no-http \
        --db_user odoo --db_password "$PW" < scripts/setup_site.py

Who counts as a site engineer is a judgement, so this does not guess widely.
It takes users who already have project access and are not accountants, which
is what an engineer looks like in every database built from the template, and
prints everyone it touched and everyone it deliberately did not.

It also drops Technical Features from them. That group grants no data access,
but it puts developer-only fields on every form — which on a phone, for
somebody filling in a daily report while standing on a slab, is noise in the
only place there is no room for any.
"""

engineer = env.ref("mizan_site.group_site_engineer")
project_user = env.ref("project.group_project_user")
accountant = env.ref("account.group_account_invoice")
no_one = env.ref("base.group_no_one")

candidates = env["res.users"].search([
    ("share", "=", False),
    ("groups_id", "in", project_user.id),
])

added, skipped, cleaned = [], [], []
for user in candidates:
    if user.has_group("account.group_account_invoice") \
            or user.has_group("account.group_account_manager"):
        skipped.append("%s (works in the ledger)" % user.login)
        continue
    if user._is_admin():
        skipped.append("%s (administrator)" % user.login)
        continue
    if engineer in user.groups_id:
        skipped.append("%s (already)" % user.login)
        continue
    user.write({"groups_id": [(4, engineer.id)]})
    added.append(user.login)
    if no_one in user.groups_id:
        user.write({"groups_id": [(3, no_one.id)]})
        cleaned.append(user.login)

print("=" * 72)
print("SITE ENGINEER ROLE")
print("=" * 72)
print("\nadded (%d):" % len(added))
for login in added:
    print("  %s" % login)
print("\ntechnical features removed (%d):" % len(cleaned))
for login in cleaned:
    print("  %s" % login)
print("\nnot touched (%d):" % len(skipped))
for note in skipped:
    print("  %s" % note)

print("\nA site manager — somebody who reads every project's reports — is a")
print("separate role and is not granted here. Add mizan_site.group_site_manager")
print("by hand to whoever that is, deliberately.")

env.cr.commit()
print("\nsaved.")
