# -*- coding: utf-8 -*-
"""Make notifications reach people when there is no outgoing mail server.

    docker exec -i mizan-odoo odoo shell -d <db> --no-http \
        --db_user odoo --db_password "$PW" < scripts/setup_notifications.py

Odoo gives every user a choice of where notifications go: by email, or inside
Odoo. Every user here was on email — and this database has no outgoing mail
server. So every approval, every assignment, every reminder addressed to them
was handed to a mail queue that could not send it, and nobody saw anything.

Inside Odoo is the only setting that works today, and it is also what drives
phone notifications: Odoo pushes to a phone only what lands in the person's
inbox. So while no mail server exists, everybody is moved to it.

The day a mail server is configured, this script changes nothing — it checks
for one first — and anybody who prefers email can switch back on their own
preferences. It is a default for a broken situation, not a policy.
"""

servers = env["ir.mail_server"].sudo().search_count([("active", "=", True)])
print("=" * 72)
print("NOTIFICATIONS")
print("=" * 72)
if servers:
    print("An outgoing mail server is configured (%d). Email notifications" % servers)
    print("can be delivered, so nobody's preference is changed.")
else:
    users = env["res.users"].sudo().search([
        ("share", "=", False), ("active", "=", True),
        ("login", "not in", ["__system__", "default", "public",
                             "portaltemplate"]),
        ("notification_type", "=", "email"),
    ])
    users.write({"notification_type": "inbox"})
    print("No outgoing mail server. Moved to notifications inside Odoo (%d):"
          % len(users))
    for user in users:
        print("  %s" % user.login)
    print("\nOn a phone, each person turns notifications on once from the chat")
    print("icon at the top of the app; after that, what reaches their inbox")
    print("reaches their phone.")
env.cr.commit()
print("\nsaved.")
