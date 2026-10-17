# -*- coding: utf-8 -*-
"""Clear the demonstration data, by the administrator's own hand.

The administrator types the company name; a full backup is written first and
nothing is deleted if it fails. Then documents and test records go, and the
set-up stays. Optionally the role test users are archived and one
full-access test account is created, whose password the administrator sets
in Odoo's own Change Password screen."""
import logging
import os
from datetime import datetime

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BACKUP_DIR = "/var/lib/odoo/backups"
TESTER_LOGIN = "test@alamana.ae"

# Documents and test records, in the order they can go: what points at a
# record goes before the record. Repeated passes catch the rest.
PURGE = [
    "mail.activity", "mail.mail",
    "account.partial.reconcile", "account.full.reconcile",
    "mizan.contract.recognition", "mizan.plant.charge", "mizan.overhead.allocation",
    "mizan.progress.claim.line", "mizan.progress.claim",
    "mizan.subcontract.backcharge", "mizan.subcontract.variation", "mizan.subcontract",
    "mizan.contract.variation.line", "mizan.contract.variation",
    "mizan.contract.bond", "mizan.contract.boq.line", "mizan.contract.budget.line",
    "mizan.contract.forecast", "mizan.contract",
    "mizan.plant", "mizan.cheque", "mizan.employee.advance",
    "mizan.petty.cash.receipt", "mizan.petty.cash",
    "mizan.site.report", "mizan.site.capture",
    "mizan.workflow.case", "mizan.wps.line", "mizan.wps.file",
    "mizan.month.close.check", "mizan.month.close",
    "mizan.alert.log", "mizan.dashboard.tile", "mizan.work.item", "mizan.data.quality",
    "mizan.project.health", "mizan.quick.tile", "mizan.find.result",
    "account.bank.statement.line", "account.bank.statement",
    "account.payment", "account.move", "account.analytic.line",
    "hr.expense.sheet", "hr.expense", "hr.payslip", "hr.payslip.run",
    "hr.leave", "hr.leave.allocation", "hr.attendance",
    "purchase.order", "sale.order",
    "stock.move.line", "stock.move", "stock.picking", "stock.quant",
    "crm.lead", "calendar.event", "maintenance.request", "maintenance.equipment",
    "account.asset",
]
# Master data: everything goes except what a module or the set-up relies on.
MASTER = ["project.task", "project.project", "hr.employee", "product.product",
          "product.template", "account.analytic.account", "res.partner"]
KEEP_LOGINS = ["admin", "admin@alamana.ae", "support@proaccount.ae", TESTER_LOGIN, "__system__"]


class MizanResetData(models.TransientModel):
    _name = "mizan.reset.data"
    _description = "Clean test data"

    company_name = fields.Char(default=lambda self: self.env.company.name, readonly=True)
    confirm = fields.Char(string="Type the company name to confirm")
    archive_role_users = fields.Boolean(string="Archive the test users (engineers, accountant, manager…)", default=True)
    create_tester = fields.Boolean(string="Create the full-access test account (%s)" % TESTER_LOGIN, default=True)
    result = fields.Text(readonly=True)

    # ------------------------------------------------------------ the action
    def action_reset(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an administrator can clean the data."))
        if (self.confirm or "").strip() != (self.company_name or "").strip():
            raise UserError(_("Type the company name exactly as shown to confirm."))
        env = api.Environment(self.env.cr, SUPERUSER_ID, {"active_test": False})
        backup = self._backup(env)
        before = self._counts(env)
        self._wipe(env)
        tester = False
        if self.archive_role_users:
            self._archive_roles(env)
        if self.create_tester:
            tester = self._tester(env)
        after = self._counts(env)
        lines = [_("Backup: %s", backup), ""]
        lines += ["%s: %s → %s" % (label, before[label], after[label]) for label in before]
        self.result = "\n".join(lines)
        _logger.info("reset by %s:\n%s", self.env.user.login, self.result)
        if tester:
            return {
                "type": "ir.actions.act_window", "name": _("Set the test account's password"),
                "res_model": "change.password.wizard", "view_mode": "form", "target": "new",
                "context": {"active_model": "res.users", "active_ids": tester.ids, "active_id": tester.id},
            }
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new"}

    # ------------------------------------------------------------- the parts
    def _counts(self, env):
        labels = {"Journal entries and invoices": "account.move", "Contacts": "res.partner",
                  "Products": "product.template", "Employees": "hr.employee",
                  "Projects": "project.project", "Contracts": "mizan.contract",
                  "Accounts (kept)": "account.account"}
        return {label: env[model].with_context(active_test=False).search_count([]) if model in env else 0
                for label, model in labels.items()}

    def _backup(self, env):
        """Odoo's own backup format (dump.sql + filestore + manifest.json),
        restorable from the database manager. Built here rather than through
        the database manager, which is switched off on the server."""
        import json
        import shutil
        import subprocess
        import tempfile

        from odoo import release
        from odoo.tools import config, osutil
        from odoo.tools.misc import exec_pg_environ, find_pg_tool

        os.makedirs(BACKUP_DIR, exist_ok=True)
        db_name = env.cr.dbname
        path = os.path.join(BACKUP_DIR, "%s-before-reset-%s.zip" % (
            db_name, datetime.now().strftime("%Y%m%d-%H%M%S")))
        try:
            with tempfile.TemporaryDirectory() as dump_dir:
                filestore = config.filestore(db_name)
                if os.path.exists(filestore):
                    shutil.copytree(filestore, os.path.join(dump_dir, "filestore"))
                with open(os.path.join(dump_dir, "manifest.json"), "w") as fh:
                    env.cr.execute("SELECT name, latest_version FROM ir_module_module WHERE state = 'installed'")
                    modules = dict(env.cr.fetchall())
                    env.cr.execute("SHOW server_version")
                    json.dump({"odoo_dump": "1", "db_name": db_name, "version": release.version,
                               "version_info": release.version_info, "major_version": release.major_version,
                               "pg_version": env.cr.fetchone()[0], "modules": modules}, fh, indent=4)
                subprocess.run([find_pg_tool("pg_dump"), "--no-owner",
                                "--file=" + os.path.join(dump_dir, "dump.sql"), db_name],
                               env=exec_pg_environ(), check=True, capture_output=True)
                with open(path, "wb") as stream:
                    osutil.zip_dir(dump_dir, stream, include_dir=False,
                                   fnct_sort=lambda names: sorted(names, key=lambda n: n != "dump.sql"))
        except Exception as error:  # noqa: BLE001 - reported, nothing deleted
            if os.path.exists(path):
                os.remove(path)
            raise UserError(_("The backup failed, so nothing was deleted: %s", error)) from None
        if os.path.getsize(path) < 100_000:
            raise UserError(_("The backup came out empty, so nothing was deleted."))
        return path

    def _protected(self, env, model):
        ids = set(env["ir.model.data"].search([("model", "=", model)]).mapped("res_id"))
        users = env["res.users"].with_context(active_test=False).search([])
        if model == "res.partner":
            ids |= set(env["res.company"].search([]).partner_id.ids) | set(users.partner_id.ids)
        if model == "hr.employee":
            kept = users.filtered(lambda u: u.login in KEEP_LOGINS)
            ids |= set(env["hr.employee"].with_context(active_test=False).search([("user_id", "in", kept.ids)]).ids)
        return ids

    def _delete(self, env, model, records):
        """ORM first, so files and messages go with the record; directly when
        a document's own rules refuse. Each in a savepoint."""
        Model = env[model].with_context(force_delete=True, active_test=False,
                                        tracking_disable=True, mail_notrack=True)
        records = Model.browse(records.ids).exists()
        if not records:
            return
        try:
            with env.cr.savepoint():
                if model == "account.move":
                    records.filtered(lambda m: m.state == "posted").button_draft()
                records.unlink()
            return
        except Exception as error:  # noqa: BLE001 - then directly
            _logger.info("reset: ORM refused %s (%s)", model, str(error)[:150])
        env.invalidate_all()
        for rid in records.ids:
            try:
                with env.cr.savepoint():
                    env.cr.execute('DELETE FROM "%s" WHERE id = %%s' % Model._table, (rid,))
            except Exception:  # noqa: BLE001 - kept for the next pass
                pass
        env.invalidate_all()

    def _wipe(self, env):
        for field in ("fiscalyear_lock_date", "tax_lock_date", "sale_lock_date",
                      "purchase_lock_date", "hard_lock_date", "period_lock_date"):
            fld = env["res.company"]._fields.get(field)
            if fld and fld.store:
                env.cr.execute('UPDATE res_company SET "%s" = NULL' % field)
        env.invalidate_all()
        for _pass in range(4):
            for model in PURGE:
                if model in env and env[model]._auto:
                    self._delete(env, model, env[model].with_context(active_test=False).search([]))
            for model in MASTER:
                if model in env:
                    keep = self._protected(env, model)
                    self._delete(env, model, env[model].with_context(active_test=False).search(
                        [("id", "not in", list(keep))]))
        for journal in env["account.journal"].search([("bank_account_id", "!=", False)]):
            if (journal.bank_account_id.acc_number or "").replace(" ", "").startswith("AE070331"):
                bank = journal.bank_account_id
                journal.bank_account_id = False
                self._delete(env, "res.partner.bank", bank)
        self._orphans(env)
        for seq in env["ir.sequence"].search([]):
            if (seq.code or "").startswith(("mizan.", "purchase.order", "sale.order", "hr.expense")):
                seq.number_next = 1
                seq.date_range_ids.write({"number_next": 1})

    def _orphans(self, env):
        Attachment = env["ir.attachment"]
        for name in set(Attachment.search([("res_model", "!=", False), ("res_field", "=", False)]).mapped("res_model")):
            if name not in env or not env[name]._auto:
                continue
            atts = Attachment.search([("res_model", "=", name), ("res_field", "=", False)])
            alive = set(env[name].with_context(active_test=False).browse(atts.mapped("res_id")).exists().ids)
            self._delete(env, "ir.attachment", atts.filtered(lambda a: a.res_id and a.res_id not in alive))
        Message = env["mail.message"]
        for name in set(Message.search([("model", "!=", False)]).mapped("model")):
            if name not in env or not env[name]._auto:
                continue
            msgs = Message.search([("model", "=", name)])
            alive = set(env[name].with_context(active_test=False).browse(msgs.mapped("res_id")).exists().ids)
            orphans = msgs.filtered(lambda m: m.res_id and m.res_id not in alive)
            if orphans:
                env.cr.execute("DELETE FROM mail_message WHERE id IN %s", (tuple(orphans.ids),))
        env.invalidate_all()

    def _archive_roles(self, env):
        Users = env["res.users"].with_context(active_test=False)
        Users.search([("share", "=", False), ("login", "not in", KEEP_LOGINS),
                      ("id", "!=", SUPERUSER_ID), ("id", "!=", self.env.uid)]).write({"active": False})

    def _tester(self, env):
        Users = env["res.users"].with_context(active_test=False, no_reset_password=True)
        groups = env["res.groups"].search([("share", "=", False)])
        groups -= env.ref("base.group_portal") | env.ref("base.group_public")
        values = {"name": "حساب الاختبار", "login": TESTER_LOGIN, "email": TESTER_LOGIN,
                  "groups_id": [(6, 0, groups.ids)], "lang": "ar_001", "tz": "Asia/Dubai",
                  "company_ids": [(6, 0, env["res.company"].search([]).ids)],
                  "company_id": self.env.company.id, "active": True}
        tester = Users.search([("login", "=", TESTER_LOGIN)], limit=1)
        if tester:
            tester.write(values)
        else:
            tester = Users.create(values)
        # The self-service screens (my advances, my petty cash) need the
        # person to be an employee too.
        if "hr.employee" in env and not env["hr.employee"].with_context(active_test=False).search(
                [("user_id", "=", tester.id)], limit=1):
            env["hr.employee"].create({"name": tester.name, "user_id": tester.id,
                                       "work_email": TESTER_LOGIN, "company_id": values["company_id"]})
        return tester
