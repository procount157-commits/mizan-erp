# -*- coding: utf-8 -*-
import logging
import os
import re
import shutil
import secrets
import string
import uuid

from markupsafe import Markup
from contextlib import closing

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
from odoo.service import db as db_service
from odoo.sql_db import db_connect, close_db
from odoo.tools import SQL, config as odoo_config
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

DB_NAME = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


class MizanTenantProvision(models.TransientModel):
    """Create a client database by copying the golden template.

    Copying beats installing: a fresh install of the full module set takes
    about eight minutes and its result depends on whichever module versions are
    on disk that day, while a copy takes seconds and is byte-identical to every
    other client. When a bug turns up at one client, it reproduces at all of
    them — which is what makes supporting ten deployments possible at all.
    """

    _name = "mizan.tenant.provision"
    _description = "Provision a Client"

    name = fields.Char(string="Client", required=True)
    database = fields.Char(required=True)
    sector = fields.Selection(
        [("contracting", "Contracting"), ("restaurant", "Restaurant"),
         ("retail", "Retail"), ("services", "Services"), ("general", "General")],
        default="contracting", required=True)
    plan = fields.Selection(
        [("trial", "Trial"), ("standard", "Standard"), ("plus", "Plus")],
        default="trial", required=True)
    admin_login = fields.Char(
        string="Client Administrator Email", required=True,
        help="The login handed to the client. A one-time password is generated "
             "and shown once when provisioning finishes.")
    template_db = fields.Char(
        required=True,
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param(
            "mizan_saas.template_db", "mizan_template"))
    url = fields.Char(string="Client URL")

    @api.onchange("name")
    def _onchange_name(self):
        """Suggest a database name, since the rules for one are not obvious."""
        if self.name and not self.database:
            slug = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")
            self.database = (slug or "client")[:40]

    def action_provision(self):
        self.ensure_one()
        if not DB_NAME.match(self.database or ""):
            raise UserError(_(
                "'%s' is not a usable database name. Use lowercase letters, "
                "digits and underscores, starting with a letter.", self.database))

        existing = self._existing_databases()
        if self.database in existing:
            raise UserError(_("Database '%s' already exists.", self.database))
        if self.template_db not in existing:
            raise UserError(_(
                "Template '%s' does not exist. Build it once with:\n\n"
                "    scripts/provision_tenant.sh --build-template",
                self.template_db))

        _logger.info("provisioning %s from %s", self.database, self.template_db)
        # Copies the database and the filestore, and regenerates dbuuid — which
        # matters: two databases sharing a uuid confuse anything that identifies
        # a deployment by it, including Odoo's own cron locking.
        self._duplicate_database(self.template_db, self.database)

        password, stray_banks = self._reset_tenant_identity()

        tenant = self.env["mizan.tenant"].create({
            "name": self.name,
            "database": self.database,
            "sector": self.sector,
            "plan": self.plan,
            "url": self.url,
            "state": "onboarding",
        })

        # Markup, not a plain string: message_post escapes anything that is not
        # marked safe, and an escaped body shows the client "&lt;b&gt;" instead
        # of their password.
        tenant.message_post(body=Markup(
            "%s<br/>%s <b>%s</b><br/>%s <b>%s</b><br/><i>%s</i>") % (
            _("Provisioned from template %s.", self.template_db),
            _("Administrator:"), self.admin_login,
            _("One-time password:"), password,
            _("Shown here only — the client must change it at first sign-in.")))

        if stray_banks:
            # Loud, because a client issuing invoices that carry someone else's
            # IBAN is the kind of mistake that is only noticed by the payer.
            tenant.message_post(body=Markup("<b>%s</b> %s") % (
                _("Check the template."),
                _("These bank accounts came from %(template)s and could not be "
                  "removed, because posted documents in the copy refer to them: "
                  "%(accounts)s. They are archived, not deleted — a golden "
                  "template should carry no bank account at all.",
                  template=self.template_db,
                  accounts=", ".join(stray_banks))))
            tenant.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Remove bank details inherited from the template"),
                user_id=self.env.user.id)

        return {
            "type": "ir.actions.act_window",
            "res_model": "mizan.tenant",
            "res_id": tenant.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def _existing_databases(self):
        """Every database on the cluster.

        Not odoo.service.db.list_dbs: with a --database argument and no
        dbfilter — which is how this deployment runs — it reports only the
        database Odoo was started with, so it would happily let us overwrite a
        client or refuse a template that is right there.
        """
        with closing(db_connect("postgres").cursor()) as cr:
            cr.execute("""
                SELECT datname FROM pg_database
                 WHERE datistemplate = false AND datallowconn = true;
            """)
            return {row[0] for row in cr.fetchall()}

    def _duplicate_database(self, source, target):
        """Copy a database and its filestore, the way Odoo copies one.

        Odoo's own exp_duplicate_database does exactly this, but it is gated
        behind `list_db`, which is deliberately off here so that no visitor can
        reach the database manager over HTTP. Turning that gate off for a
        moment would open the manager to the whole internet for that moment, so
        the steps are done directly instead — including regenerating dbuuid,
        without which two clients would share an identity that Odoo uses for
        cron locking and for anything that asks which deployment it is.
        """
        close_db(source)
        with closing(db_connect("postgres").cursor()) as cr:
            # CREATE DATABASE cannot run inside a transaction.
            cr._cnx.autocommit = True
            db_service._drop_conn(cr, source)
            cr.execute(SQL(
                "CREATE DATABASE %s ENCODING 'unicode' TEMPLATE %s",
                db_service.database_identifier(cr, target),
                db_service.database_identifier(cr, source),
            ))

        # Copy the filestore before the registry is loaded. Loading it reads
        # attachments, and every one of them is a "file not found" in the log
        # until the files are actually there.
        from_fs = odoo_config.filestore(source)
        to_fs = odoo_config.filestore(target)
        if os.path.exists(from_fs) and not os.path.exists(to_fs):
            shutil.copytree(from_fs, to_fs)

        registry = Registry.new(target)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            params = env["ir.config_parameter"]
            params.init(force=True)
            # init() is documented to regenerate these, and on a duplicated
            # database it does not always: checked afterwards rather than
            # trusted, because two clients sharing a dbuuid share Odoo's cron
            # locking and anything else that asks which deployment this is.
            if params.get_param("database.uuid") == self._source_uuid(source):
                params.set_param("database.uuid", str(uuid.uuid4()))
        _logger.info("duplicated %s to %s", source, target)

    def _source_uuid(self, source):
        with closing(db_connect(source).cursor()) as cr:
            cr.execute(
                "SELECT value FROM ir_config_parameter WHERE key = 'database.uuid';")
            row = cr.fetchone()
            return row[0] if row else None

    def _reset_tenant_identity(self):
        """Strip the template's identity out of the fresh copy.

        A copied database inherits whatever the template carried: its company
        name, its TRN, its bank accounts, its admin login. Left alone, a new
        client would start life issuing tax invoices under someone else's tax
        number — so every identifying field is cleared here, before anyone can
        log in.
        """
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(14))

        registry = Registry(self.database)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            company = env["res.company"].browse(1)
            company.write({
                "name": self.name,
                "vat": False,
                "company_registry": False,
                "street": False, "street2": False, "city": False,
                "zip": False, "phone": False, "email": False, "website": False,
            })
            # unlink() on a bank account that any posted document refers to
            # archives it instead of deleting it, so the template's IBAN would
            # stay in the client's database, invisible but present. Search with
            # archived records included, delete what can be deleted, and report
            # whatever survives rather than shipping it silently.
            banks = env["res.partner.bank"].with_context(
                active_test=False).search([("partner_id", "=", company.partner_id.id)])
            banks.unlink()
            survivors = banks.exists().mapped("acc_number")

            admin = env.ref("base.user_admin", raise_if_not_found=False)
            if admin:
                admin.write({
                    "login": self.admin_login,
                    "password": password,
                    "name": self.name,
                })
                # The client's administrator runs their company, not the
                # platform. Leaving system rights here would let them install
                # modules into a database we have to upgrade and support.
                for xmlid in ("base.group_system", "mizan_core.group_platform_admin"):
                    group = env.ref(xmlid, raise_if_not_found=False)
                    if group:
                        admin.write({"groups_id": [(3, group.id)]})
                admin.partner_id.write({"email": self.admin_login})

            # A support login of our own, so suspending this client later does
            # not also lock us out of their database.
            support_login = self.env["ir.config_parameter"].sudo().get_param(
                "mizan_saas.support_login", "support@proaccount.ae")
            support = env["res.users"].with_context(active_test=False).search(
                [("login", "=", support_login)], limit=1)
            if not support:
                groups = [env.ref("base.group_system").id]
                # Platform administration — installing modules, adding companies,
                # managing users — is held by this login alone. The client's own
                # administrator never gets it, so there is no account inside the
                # client company that can reach those screens.
                platform = env.ref("mizan_core.group_platform_admin",
                                   raise_if_not_found=False)
                if platform:
                    groups.append(platform.id)
                support = env["res.users"].create({
                    "name": "ProAccount Support",
                    "login": support_login,
                    "password": secrets.token_urlsafe(18),
                    "groups_id": [(6, 0, groups)],
                })
            env["ir.config_parameter"].set_param(
                "mizan_saas.support_uid", str(support.id))

            # The copy carries the template's base URL; left pointing at the
            # template host, every emailed invoice link would go to the wrong
            # place.
            if self.url:
                env["ir.config_parameter"].set_param("web.base.url", self.url)
                env["ir.config_parameter"].set_param("web.base.url.freeze", "True")
        return password, survivors
