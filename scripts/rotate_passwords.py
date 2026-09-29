# -*- coding: utf-8 -*-
"""Issue fresh passwords for the human logins in one database.

    docker exec -i -e MIZAN_CREDENTIALS_OUT=/tmp/alamana-users.txt \
        mizan-odoo odoo shell -d alamana --no-http \
        --db_user odoo --db_password "$PW" < scripts/rotate_passwords.py

Written because six passwords were committed to this repository in plain text.
Removing them from the file does not rotate them: anyone who cloned the
repository before, or who reads the history afterwards, still holds them. The
file and the logins have to be fixed separately, and this is the second half.

NAME THE LOGINS. Rotating more than leaked is its own harm: every person on
the list is locked out until somebody hands them a new password, and an
administrator locked out of their own database at the wrong moment is a worse
morning than the exposure was. So the logins are given explicitly, and the
script refuses to guess:

    MIZAN_ROTATE_LOGINS=manager@x.ae,finance@x.ae

Service logins are refused even when named. The platform's own support account
is the operator's way back into a client database, and rotating it from inside
that database is how you lock yourself out of the thing you support.

The new passwords go to a file, never to the terminal. A scrollback is not a
place to leave six people's credentials, and the operator has to move them
into a password manager and delete the file regardless.
"""
import os
import secrets
from datetime import date

SYSTEM_LOGINS = {"__system__", "default", "public", "portaltemplate"}
# The operator's own way back into the client database.
SERVICE_PREFIXES = ("support@",)

wanted = [login.strip() for login
          in os.environ.get("MIZAN_ROTATE_LOGINS", "").split(",")
          if login.strip()]
if not wanted:
    raise SystemExit(
        "Name the logins to rotate:\n"
        "    MIZAN_ROTATE_LOGINS=manager@x.ae,finance@x.ae\n"
        "Rotating everything locks out people whose password never leaked.")

rotated, skipped = [], []
for login in wanted:
    user = env["res.users"].with_context(active_test=False).search(
        [("login", "=", login)], limit=1)
    if not user:
        skipped.append("%s (no such login)" % login)
        continue
    if login in SYSTEM_LOGINS or login.startswith(SERVICE_PREFIXES):
        skipped.append("%s (service login — refused)" % login)
        continue
    if user.share:
        skipped.append("%s (portal user — the client's business)" % login)
        continue
    password = secrets.token_urlsafe(15)
    user.sudo().write({"password": password})
    rotated.append((user.login, user.name, password))

out = os.environ.get("MIZAN_CREDENTIALS_OUT",
                     "/tmp/%s-users.txt" % env.cr.dbname)
with open(out, "w", encoding="utf-8") as handle:
    handle.write("%s — passwords rotated %s\n\n"
                 % (env.company.name, date.today().isoformat()))
    for login, name, password in rotated:
        handle.write("%-28s %-24s %s\n" % (login, name, password))
    handle.write("\nHand these over, then delete this file.\n")
os.chmod(out, 0o600)

print("=" * 72)
print("rotated (%d):" % len(rotated))
for login, name, _password in rotated:
    print("  %-28s %s" % (login, name))
print("\nleft alone (%d):" % len(skipped))
for note in skipped:
    print("  %s" % note)
print("\npasswords written to %s" % out)
print("Hand them over, then delete that file.")
print("=" * 72)

env.cr.commit()
