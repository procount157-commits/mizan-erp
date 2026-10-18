# -*- coding: utf-8 -*-
"""Set new passwords on the server, typed by the administrator.

Run on the server (Hostinger → VPS → Browser terminal):

    cd /root/mihwar/miqyas && docker compose exec odoo python3 /mnt/custom_addons/mizan_reset/tools/set_passwords.py

It asks for the admin's new password (typed twice, never shown), then
whether every other active user should get the same password. Nothing is
printed or stored except Odoo's own password hash.
"""
import getpass
import os
import sys

import odoo
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

DB = sys.argv[1] if len(sys.argv) > 1 else "alamana"
ADMIN = sys.argv[2] if len(sys.argv) > 2 else "admin@alamana.ae"


def ask(prompt):
    while True:
        first = getpass.getpass(prompt)
        if len(first) < 8:
            print("At least 8 characters, please.")
            continue
        if getpass.getpass("Type it again: ") != first:
            print("The two did not match. Again.")
            continue
        return first


def main():
    # The image's entrypoint passes the database login from HOST/USER/PASSWORD
    # (POSTGRES_* locally); run directly, this script has to do the same.
    args = ["--config=/etc/odoo/odoo.conf"]
    for flag, names in (("--db_host", ("HOST",)), ("--db_user", ("USER", "POSTGRES_USER")),
                        ("--db_password", ("PASSWORD", "POSTGRES_PASSWORD"))):
        value = next((os.environ[n] for n in names if os.environ.get(n)), None)
        if value and not (flag == "--db_user" and value == "root"):
            args.append("%s=%s" % (flag, value))
    odoo.tools.config.parse_config(args)
    with Registry(DB).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
        Users = env["res.users"]
        admin = Users.search([("login", "=", ADMIN)], limit=1)
        if not admin:
            print("No user %s in %s." % (ADMIN, DB))
            return 1
        password = ask("New password for %s: " % ADMIN)
        admin.write({"password": password, "active": True})
        others = Users.search([("share", "=", False), ("active", "=", True),
                               ("id", "not in", [admin.id, SUPERUSER_ID])])
        if others:
            print("\nOther users: " + ", ".join(others.mapped("login")))
            if input("Give them all this same password? [y/N] ").strip().lower() in ("y", "yes", "ن", "نعم"):
                others.write({"password": password})
                print("Done for %s other user(s)." % len(others))
        cr.commit()
        print("\nDone. Sign in at the login page as %s with the password you typed." % ADMIN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
