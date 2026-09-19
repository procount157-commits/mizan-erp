# -*- coding: utf-8 -*-
import logging
import os
import re
import secrets
from contextlib import closing
from datetime import timedelta

import psycopg2

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import config
from odoo.modules.registry import Registry
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

BACKUP_NAME = re.compile(
    # Both formats count: .zip from this module, .dump from scripts/backup.sh.
    r"^(?P<db>.+)-(?P<day>\d{8})-(?P<time>\d{6})\.(dump|zip)$")


class MizanTenant(models.Model):
    """One client deployment.

    Every client runs in its own PostgreSQL database, so no access-rule mistake
    can ever show one client's ledger to another. That isolation costs one
    thing: nothing inside Odoo can see across databases, and an operator running
    ten of them cannot answer "whose backup is stale" or "who is about to
    outgrow the disk" without opening each one by hand.

    This model is that missing view. The figures are read live from the cluster
    on every display rather than cached, because a stale number on an operations
    screen is worse than no number at all.
    """

    _name = "mizan.tenant"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Client Deployment"
    _order = "state, name"
    _rec_name = "name"

    name = fields.Char(string="Client", required=True, tracking=True)
    database = fields.Char(
        required=True, copy=False,
        help="PostgreSQL database backing this client.")
    url = fields.Char(
        string="URL",
        help="Where this client reaches their system, e.g. "
             "https://alrayan.proaccount.ae. Leave empty to use the database "
             "selector on the main host.")
    partner_id = fields.Many2one("res.partner", string="Billing Contact")

    sector = fields.Selection(
        [("contracting", "Contracting"), ("restaurant", "Restaurant"),
         ("retail", "Retail"), ("services", "Services"), ("general", "General")],
        default="general", required=True)

    plan = fields.Selection(
        [("trial", "Trial"), ("standard", "Standard"), ("plus", "Plus")],
        default="trial", required=True, tracking=True)
    monthly_fee = fields.Monetary(tracking=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id)
    user_limit = fields.Integer(
        default=0, help="Contracted number of users. 0 means no limit.")
    storage_limit_mb = fields.Integer(
        string="Storage Limit (MB)", default=0,
        help="Contracted storage. 0 means no limit.")

    state = fields.Selection(
        [("onboarding", "Onboarding"), ("live", "Live"),
         ("suspended", "Suspended"), ("closed", "Closed")],
        default="onboarding", required=True, copy=False, tracking=True)

    go_live_date = fields.Date(copy=False)
    renewal_date = fields.Date(help="When the current subscription period ends.")
    days_to_renewal = fields.Integer(compute="_compute_renewal")
    renewal_warning = fields.Boolean(compute="_compute_renewal")

    # --- live figures, read from the cluster on every display --------------
    db_exists = fields.Boolean(string="Database Found", compute="_compute_live")
    db_size_mb = fields.Float(string="Size (MB)", compute="_compute_live")
    user_count = fields.Integer(compute="_compute_live")
    invoice_count = fields.Integer(compute="_compute_live")
    last_activity = fields.Datetime(compute="_compute_live")
    over_user_limit = fields.Boolean(compute="_compute_live")
    over_storage_limit = fields.Boolean(compute="_compute_live")

    backup_state = fields.Selection(
        [("fresh", "Fresh"), ("stale", "Stale"), ("missing", "Missing")],
        compute="_compute_backup")
    last_backup = fields.Datetime(compute="_compute_backup")

    health = fields.Selection(
        [("ok", "Healthy"), ("attention", "Needs Attention"),
         ("down", "Unreachable")],
        compute="_compute_health", search="_search_health")
    health_reason = fields.Char(compute="_compute_health")

    suspended_user_ids = fields.Char(
        copy=False, readonly=True,
        help="Users deactivated by suspension, restored on reactivation.")

    metric_ids = fields.One2many("mizan.tenant.metric", "tenant_id")
    backup_ids = fields.One2many("mizan.tenant.backup", "tenant_id")
    note = fields.Text()

    _sql_constraints = [
        ("database_uniq", "unique(database)",
         "That database is already registered to another client."),
    ]

    # ------------------------------------------------------------------ live
    def _connect(self, database):
        """Open a short-lived connection to a client database.

        Wrapped by the caller in contextlib.closing: psycopg2's own context
        manager ends the transaction but leaves the socket open, which on a
        list view refreshed every few minutes exhausts max_connections.
        """
        return psycopg2.connect(
            dbname=database,
            user=config["db_user"],
            password=config["db_password"] or None,
            host=config["db_host"] or "localhost",
            port=config["db_port"] or 5432,
            connect_timeout=4,
        )

    def _compute_live(self):
        for tenant in self:
            tenant.db_exists = False
            tenant.db_size_mb = 0.0
            tenant.user_count = 0
            tenant.invoice_count = 0
            tenant.last_activity = False
            tenant.over_user_limit = False
            tenant.over_storage_limit = False
            if not tenant.database:
                continue
            try:
                with closing(self._connect(tenant.database)) as conn:
                    conn.set_session(readonly=True, autocommit=True)
                    with conn.cursor() as cr:
                        tenant._read_metrics(cr)
                tenant.db_exists = True
            except psycopg2.Error as exc:
                # One unreachable client must not blank out the other nine.
                _logger.warning("tenant %s unreachable: %s", tenant.database, exc)
            tenant.over_user_limit = bool(
                tenant.user_limit and tenant.user_count > tenant.user_limit)
            tenant.over_storage_limit = bool(
                tenant.storage_limit_mb
                and tenant.db_size_mb > tenant.storage_limit_mb)

    def _read_metrics(self, cr):
        """Fill the live fields from an open cursor on the client database."""
        self.ensure_one()
        cr.execute("SELECT pg_database_size(current_database());")
        self.db_size_mb = round(cr.fetchone()[0] / 1048576.0, 1)

        # OdooBot and our own support login are not the client's users and
        # must not appear on their seat count.
        cr.execute("""
            SELECT value FROM ir_config_parameter
             WHERE key = 'mizan_saas.support_uid';
        """)
        row = cr.fetchone()
        spare = [1] + ([int(row[0])] if row and row[0].isdigit() else [])
        cr.execute("""
            SELECT count(*) FROM res_users
             WHERE active AND share IS NOT TRUE AND id <> ALL(%s);
        """, (spare,))
        self.user_count = cr.fetchone()[0]

        cr.execute("""
            SELECT count(*), max(write_date) FROM account_move
             WHERE move_type IN ('out_invoice', 'out_refund');
        """)
        count, last = cr.fetchone()
        self.invoice_count = count or 0
        self.last_activity = last

    def _backup_dir(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "mizan_saas.backup_dir", "/var/lib/odoo/backups")

    def _compute_backup(self):
        backup_dir = self._backup_dir()
        newest = {}
        if os.path.isdir(backup_dir):
            for entry in os.listdir(backup_dir):
                match = BACKUP_NAME.match(entry)
                if not match:
                    continue
                day, clock = match.group("day"), match.group("time")
                stamp = fields.Datetime.to_datetime("%s-%s-%s %s:%s:%s" % (
                    day[:4], day[4:6], day[6:],
                    clock[:2], clock[2:4], clock[4:]))
                db = match.group("db")
                if db not in newest or stamp > newest[db]:
                    newest[db] = stamp
        now = fields.Datetime.now()
        for tenant in self:
            stamp = newest.get(tenant.database)
            tenant.last_backup = stamp or False
            if not stamp:
                tenant.backup_state = "missing"
            elif now - stamp < timedelta(days=2):
                tenant.backup_state = "fresh"
            else:
                tenant.backup_state = "stale"

    @api.depends("renewal_date")
    def _compute_renewal(self):
        today = fields.Date.context_today(self)
        for tenant in self:
            if tenant.renewal_date:
                tenant.days_to_renewal = (tenant.renewal_date - today).days
                tenant.renewal_warning = tenant.days_to_renewal <= 30
            else:
                tenant.days_to_renewal = 0
                tenant.renewal_warning = False

    def _compute_health(self):
        for tenant in self:
            reasons = []
            if tenant.state in ("closed", "onboarding"):
                tenant.health = "ok"
                tenant.health_reason = ""
                continue
            if not tenant.db_exists:
                tenant.health = "down"
                tenant.health_reason = _("Database not reachable")
                continue
            if tenant.backup_state == "missing":
                reasons.append(_("no backup"))
            elif tenant.backup_state == "stale":
                reasons.append(_("backup over 2 days old"))
            if tenant.over_user_limit:
                reasons.append(_("%(used)s users over a limit of %(limit)s",
                                 used=tenant.user_count, limit=tenant.user_limit))
            if tenant.over_storage_limit:
                reasons.append(_("storage over plan"))
            if tenant.renewal_warning:
                reasons.append(_("renews in %s days", tenant.days_to_renewal))
            tenant.health = "attention" if reasons else "ok"
            tenant.health_reason = ", ".join(reasons)

    def _search_health(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            raise UserError(_("Health can only be filtered by equality."))
        wanted = value if isinstance(value, (list, tuple)) else [value]
        matching = self.search([]).filtered(lambda t: t.health in wanted)
        negate = operator in ("!=", "not in")
        return [("id", "not in" if negate else "in", matching.ids)]

    # --------------------------------------------------------------- actions
    def action_open_tenant(self):
        """Open the client's own system in a new tab."""
        self.ensure_one()
        if self.url:
            url = self.url
        else:
            base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            url = "%s/web/database/selector" % base
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    def action_go_live(self):
        for tenant in self:
            if not tenant.db_exists:
                raise UserError(_(
                    "Database '%s' does not exist yet — provision it first.",
                    tenant.database))
        self.write({
            "state": "live",
            "go_live_date": fields.Date.context_today(self),
        })

    def action_suspend(self):
        """Suspend a client by blocking logins in their own database.

        Suspension has to bite inside the client's database, not just on this
        screen: a client whose record here says "suspended" but who can still
        log in and invoice is not suspended.
        """
        for tenant in self:
            if tenant.db_exists:
                tenant._set_tenant_logins(active=False)
        self.write({"state": "suspended"})

    def action_reactivate(self):
        for tenant in self:
            if tenant.db_exists:
                tenant._set_tenant_logins(active=True)
        self.write({"state": "live"})

    def action_close(self):
        for tenant in self:
            if tenant.db_exists:
                tenant._set_tenant_logins(active=False)
        self.write({"state": "closed"})

    def _tenant_env(self):
        """An Environment on the client's database.

        Suspension writes users and groups, which is not work to do with hand
        written SQL: password hashing, group inheritance and the user cache all
        live in the ORM. Loading the client's registry costs memory, but
        suspending is rare and getting it wrong locks someone out.
        """
        self.ensure_one()
        return Registry(self.database).cursor()

    def _support_user(self, env):
        """The operator's own login inside a client database, created if absent.

        Every suspension has to leave one door open, or the operator cannot
        reopen the database to lift the suspension, take a final backup, or
        hand the data back. That door is a login of ours, never the client's
        administrator — sparing the client's admin would mean the client simply
        carries on working, which is not a suspension at all.
        """
        params = env["ir.config_parameter"].sudo()
        login = self.env["ir.config_parameter"].sudo().get_param(
            "mizan_saas.support_login", "support@proaccount.ae")
        user = env["res.users"].sudo().with_context(active_test=False).search(
            [("login", "=", login)], limit=1)
        if not user:
            user = env["res.users"].sudo().create({
                "name": "ProAccount Support",
                "login": login,
                "password": secrets.token_urlsafe(18),
                "groups_id": [(6, 0, [env.ref("base.group_system").id])],
            })
        user.active = True
        params.set_param("mizan_saas.support_uid", str(user.id))
        return user

    def _set_tenant_logins(self, active):
        """Deactivate the client's users, or restore exactly the ones we took.

        Reactivation restores the users suspension switched off and nobody
        else: a client who had two staff deactivated before we suspended them
        should not find those two logged back in afterwards. So suspension
        records the ids it touched and reactivation reads them back.
        """
        self.ensure_one()
        with self._tenant_env() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            support = self._support_user(env)
            Users = env["res.users"].sudo().with_context(active_test=False)
            if active:
                ids = [int(x) for x in (self.suspended_user_ids or "").split(",") if x]
                Users.browse(ids).exists().write({"active": True})
                self.suspended_user_ids = False
            else:
                victims = Users.search([
                    ("active", "=", True),
                    ("id", "not in", [SUPERUSER_ID, support.id]),
                ])
                self.suspended_user_ids = ",".join(str(i) for i in victims.ids)
                victims.write({"active": False})

    def action_backup_now(self):
        self.ensure_one()
        return self.env["mizan.tenant.backup"].run_backup(self)

    def action_view_metrics(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Growth of %s", self.name),
            "res_model": "mizan.tenant.metric",
            "view_mode": "graph,list",
            "domain": [("tenant_id", "=", self.id)],
            "context": {"default_tenant_id": self.id},
        }

    # ------------------------------------------------------------------ cron
    @api.model
    def cron_snapshot_metrics(self):
        """Record today's size and usage for every live client.

        Capacity questions are about slope, not level: one number tells you
        nothing about when a client will outgrow the server, a year of them
        tells you the month.
        """
        today = fields.Date.context_today(self)
        Metric = self.env["mizan.tenant.metric"]
        for tenant in self.search([("state", "in", ("live", "onboarding"))]):
            if not tenant.db_exists:
                continue
            existing = Metric.search(
                [("tenant_id", "=", tenant.id), ("date", "=", today)], limit=1)
            values = {
                "tenant_id": tenant.id,
                "date": today,
                "db_size_mb": tenant.db_size_mb,
                "user_count": tenant.user_count,
                "invoice_count": tenant.invoice_count,
            }
            if existing:
                existing.write(values)
            else:
                Metric.create(values)
        return True


class MizanTenantMetric(models.Model):
    _name = "mizan.tenant.metric"
    _description = "Client Usage Snapshot"
    _order = "date desc, tenant_id"

    tenant_id = fields.Many2one(
        "mizan.tenant", required=True, ondelete="cascade", index=True)
    date = fields.Date(required=True, index=True)
    db_size_mb = fields.Float(string="Size (MB)")
    user_count = fields.Integer()
    invoice_count = fields.Integer()

    _sql_constraints = [
        ("tenant_date_uniq", "unique(tenant_id, date)",
         "One snapshot per client per day."),
    ]
