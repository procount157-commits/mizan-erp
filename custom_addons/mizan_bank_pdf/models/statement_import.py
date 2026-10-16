# -*- coding: utf-8 -*-
import hashlib

from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.addons.base.models.res_bank import sanitize_account_number

from .pdf_statement import StatementError, parse_statement


class AccountStatementImport(models.TransientModel):
    _inherit = "account.statement.import"

    def _parse_file(self, data_file):
        if not data_file[:5] == b"%PDF-":
            return super()._parse_file(data_file)
        try:
            parsed = parse_statement(data_file)
        except StatementError as error:
            raise UserError(_("This bank statement could not be imported.\n\n%s", str(error)))
        except Exception as error:
            raise UserError(_("This PDF could not be read as a bank statement: %s", error))

        account = parsed["account_number"]
        if account and not self._mizan_journal_for(account):
            # The statement names an account no journal carries yet. Started
            # from a bank journal, that journal is meant; the account number is
            # then recorded on it so the next import finds it by itself.
            journal_id = self.env.context.get("journal_id")
            if journal_id:
                self._mizan_attach_account(self.env["account.journal"].browse(journal_id), account)
            else:
                only = self.env["account.journal"].search(
                    [("type", "=", "bank"), ("company_id", "=", self.env.company.id)])
                if len(only) == 1 and not only.bank_account_id:
                    self._mizan_attach_account(only, account)
                else:
                    account = None

        first, last = parsed["transactions"][0]["date"], parsed["transactions"][-1]["date"]
        fingerprint = hashlib.sha1((account or "") .encode()).hexdigest()[:8]
        transactions = []
        for index, line in enumerate(parsed["transactions"]):
            transactions.append({
                "date": line["date"],
                "payment_ref": line["payment_ref"],
                "amount": line["amount"],
                # stable across re-imports of the same statement, so a second
                # upload of the same PDF is recognised and skipped
                "unique_import_id": "pdf-%s-%s-%d-%.2f-%.2f" % (
                    fingerprint, line["date"].isoformat(), index, line["amount"], line["balance"]),
            })
        statement = {
            "name": _("Statement %(start)s – %(end)s", start=first.strftime("%d/%m/%Y"),
                      end=last.strftime("%d/%m/%Y")),
            "date": last,
            "balance_start": parsed["balance_start"],
            "balance_end_real": parsed["balance_end"],
            "transactions": transactions,
        }
        return parsed["currency"], account, [statement]

    def _mizan_journal_for(self, account):
        number = sanitize_account_number(account)
        return self.env["account.journal"].search([
            ("type", "=", "bank"), ("company_id", "=", self.env.company.id),
            ("bank_account_id.sanitized_acc_number", "=", number)], limit=1)

    def _mizan_attach_account(self, journal, account):
        if journal.bank_account_id:
            return
        Bank = self.env["res.partner.bank"].sudo()
        number = sanitize_account_number(account)
        bank_account = Bank.search([("sanitized_acc_number", "=", number),
                                    ("partner_id", "=", journal.company_id.partner_id.id)], limit=1) \
            or Bank.create({"acc_number": account, "partner_id": journal.company_id.partner_id.id})
        journal.sudo().bank_account_id = bank_account

    def import_file_button(self):
        """Import, reconcile, and say what happened in one sentence."""
        Line = self.env["account.bank.statement.line"]
        before = set(Line.search([]).ids)
        result = super().import_file_button()
        fresh = Line.search([("id", "not in", list(before))])
        if not fresh:
            return result
        done = fresh.filtered("is_reconciled")
        waiting = fresh - done
        message = _("%(n)s line(s) imported: %(done)s reconciled automatically, %(left)s waiting for review.",
                    n=len(fresh), done=len(done), left=len(waiting))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": _("Bank statement imported"), "message": message,
                "type": "success" if not waiting else "warning", "sticky": True,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Bank lines to review") if waiting else _("Imported bank lines"),
                    "res_model": "account.bank.statement.line",
                    "views": [[False, "list"], [False, "form"]],
                    "domain": [("id", "in", (waiting or fresh).ids)],
                    "target": "current",
                },
            },
        }


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def _mizan_setup_bank_fee_rules(self):
        """Run on install and every upgrade; safe to repeat."""
        from ..hooks import setup_bank_fee_rules
        for company in self.search([]):
            setup_bank_fee_rules(self.with_company(company).env)
