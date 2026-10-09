# -*- coding: utf-8 -*-
"""Switch on petty cash, and open everybody on their own first screen.

    docker exec -i mizan-odoo odoo shell -d <db> --no-http \
        --db_user odoo --db_password "$PW" < scripts/setup_pettycash.py

Optional: MIZAN_SITE_MANAGERS="eng.omar@x.ae,..." makes those logins the
engineers' managers — they approve their team's receipts. Nobody is promoted
unless named: who manages whom is the client's decision, not a guess.

1. The advance account, journal and ceiling (what setup_advances.py does), if
   not set already. Petty cash cannot be paid out without them.
2. Every internal user's home becomes the dashboard. An engineer opens the
   app on his cash, his reports and a camera button; a manager on what is
   waiting for him and the jobs — not on a grid of twenty apps.
"""
import os

company = env.company
if not company.mizan_advance_account_id:
    account = env["account.account"].search([("code", "=", "102600")], limit=1) \
        or env["account.account"].create({"code": "102600", "name": "سُلف الموظفين",
                                          "account_type": "asset_current", "reconcile": True})
    journal = env["account.journal"].search(
        [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
    company.write({"mizan_advance_account_id": account.id,
                   "mizan_advance_journal_id": journal.id or False,
                   "mizan_advance_limit": company.mizan_advance_limit or 20000.0})
print("advances account: %s" % company.mizan_advance_account_id.display_name)
print("paid from       : %s" % (company.mizan_advance_journal_id.display_name or "NOT SET"))
print("limit           : %s" % company.mizan_advance_limit)

manager_group = env.ref("mizan_site.group_site_manager")
for login in filter(None, (os.environ.get("MIZAN_SITE_MANAGERS") or "").split(",")):
    user = env["res.users"].search([("login", "=", login.strip())])
    if user:
        user.write({"groups_id": [(4, manager_group.id)]})
        print("site manager    : %s" % login)
    else:
        print("NOT FOUND       : %s" % login)

home = env.ref("mizan_hub.action_dashboard")
users = env["res.users"].search([("share", "=", False), ("active", "=", True)])
# action_id points at ir.actions.actions, the parent of a server action, so
# it takes the id rather than the server action record itself.
users.filtered(lambda u: u.action_id.id != home.id).write({"action_id": home.id})
print("home screen     : dashboard for %d user(s)" % len(users))

env.cr.commit()
print("saved.")
