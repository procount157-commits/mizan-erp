# -*- coding: utf-8 -*-
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo import release
from odoo.sql_db import db_connect
from odoo.tools import config as odoo_config
from odoo.tools.misc import exec_pg_environ, find_pg_tool
from odoo.tools.osutil import zip_dir

_logger = logging.getLogger(__name__)


class MizanTenantBackup(models.Model):
    """A backup that was actually taken, with its size and where it landed.

    The point of recording these is not bookkeeping — it is that "the backup
    job is configured" and "a restorable file exists on disk this morning" are
    different claims, and only the second one is worth anything.
    """

    _name = "mizan.tenant.backup"
    _description = "Client Backup"
    _order = "create_date desc"

    tenant_id = fields.Many2one(
        "mizan.tenant", required=True, ondelete="cascade", index=True)
    database = fields.Char(related="tenant_id.database", store=True)
    filename = fields.Char(readonly=True)
    path = fields.Char(readonly=True)
    size_mb = fields.Float(string="Size (MB)", readonly=True)
    duration = fields.Float(string="Seconds", readonly=True)
    state = fields.Selection(
        [("done", "Done"), ("failed", "Failed")], readonly=True)
    error = fields.Text(readonly=True)
    origin = fields.Selection(
        [("manual", "Manual"), ("scheduled", "Scheduled")], default="manual",
        readonly=True)

    def _backup_dir(self):
        directory = self.env["ir.config_parameter"].sudo().get_param(
            "mizan_saas.backup_dir", "/var/lib/odoo/backups")
        os.makedirs(directory, exist_ok=True)
        return directory

    @api.model
    def run_backup(self, tenants, origin="manual"):
        """Dump each client database, with its filestore, to the backup directory."""
        directory = self._backup_dir()
        created = self.browse()
        for tenant in tenants:
            if not tenant.db_exists:
                raise UserError(_(
                    "Database '%s' is not reachable — nothing to back up.",
                    tenant.database))
            stamp = fields.Datetime.now()
            filename = "%s-%s.zip" % (
                tenant.database, stamp.strftime("%Y%m%d-%H%M%S"))
            path = os.path.join(directory, filename)
            started = fields.Datetime.now()
            try:
                with open(path, "wb") as stream:
                    self._dump(tenant.database, stream)
                record = self.create({
                    "tenant_id": tenant.id,
                    "filename": filename,
                    "path": path,
                    "size_mb": round(os.path.getsize(path) / 1048576.0, 1),
                    "duration": (fields.Datetime.now() - started).total_seconds(),
                    "state": "done",
                    "origin": origin,
                })
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                _logger.exception("backup of %s failed", tenant.database)
                if os.path.exists(path):
                    os.remove(path)  # a truncated dump is worse than none
                record = self.create({
                    "tenant_id": tenant.id,
                    "filename": filename,
                    "state": "failed",
                    "error": str(exc),
                    "origin": origin,
                })
            created |= record
        return {
            "type": "ir.actions.act_window",
            "name": _("Backups"),
            "res_model": "mizan.tenant.backup",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
        }

    def _manifest(self, cr):
        """The manifest Odoo's restore expects: version and installed modules."""
        cr.execute("""
            SELECT name, latest_version FROM ir_module_module
             WHERE state = 'installed';
        """)
        server = cr._obj.connection.server_version
        return {
            "odoo_dump": "1",
            "db_name": cr.dbname,
            "version": release.version,
            "version_info": release.version_info,
            "major_version": release.major_version,
            "pg_version": "%d.%d" % divmod(server / 100, 100),
            "modules": dict(cr.fetchall()),
        }

    def _dump(self, database, stream):
        """Write an Odoo-format backup: pg_dump, the filestore and a manifest.

        Odoo's own dump_db produces exactly this, but it is gated behind
        `list_db`, which is off here so the database manager is not exposed
        over HTTP. The format is reproduced rather than the gate opened, so
        these files stay restorable with Odoo's ordinary restore — a backup in
        a private format is a backup you cannot use under pressure.
        """
        with tempfile.TemporaryDirectory() as workdir:
            filestore = odoo_config.filestore(database)
            if os.path.exists(filestore):
                shutil.copytree(filestore, os.path.join(workdir, "filestore"))

            with open(os.path.join(workdir, "manifest.json"), "w") as fh:
                with db_connect(database).cursor() as cr:
                    json.dump(self._manifest(cr), fh, indent=4)

            subprocess.run(
                [find_pg_tool("pg_dump"), "--no-owner",
                 "--file=" + os.path.join(workdir, "dump.sql"), database],
                env=exec_pg_environ(),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

            zip_dir(workdir, stream, include_dir=False,
                    fnct_sort=lambda name: name != "dump.sql")

    @api.model
    def cron_backup_all(self):
        tenants = self.env["mizan.tenant"].search(
            [("state", "in", ("live", "onboarding"))])
        reachable = tenants.filtered("db_exists")
        for tenant in tenants - reachable:
            _logger.error(
                "scheduled backup skipped: %s unreachable", tenant.database)
        if reachable:
            self.run_backup(reachable, origin="scheduled")
        self._rotate()
        return True

    @api.model
    def _rotate(self):
        """Delete dumps older than the retention window.

        Unbounded backups fill the disk, and a full disk stops every client at
        once — the retention policy is an availability control, not housekeeping.
        """
        days = int(self.env["ir.config_parameter"].sudo().get_param(
            "mizan_saas.backup_retention_days", 14))
        cutoff = fields.Datetime.now() - timedelta(days=days)
        stale = self.search([
            ("create_date", "<", cutoff), ("state", "=", "done")])
        for backup in stale:
            if backup.path and os.path.exists(backup.path):
                try:
                    os.remove(backup.path)
                except OSError as exc:
                    _logger.warning("could not remove %s: %s", backup.path, exc)
        stale.unlink()
        return True
