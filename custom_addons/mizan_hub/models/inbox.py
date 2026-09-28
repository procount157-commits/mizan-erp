# -*- coding: utf-8 -*-
"""What is waiting for me, on one screen, with the next step on each row.

The prototype answered the first half of the question — it gathered work from
eight apps into one list. The finance manager's objection to it was the second
half: having found the task, he still had to open the document, find the right
button among eleven, and know which one the process expected. So this version
carries the next action on the row itself.

It still does not reimplement anything. Pressing the button calls the real
document's own method through the next-action engine, so a claim certified from
here goes through exactly the code that certifies it from its own form: same
guards, same entries, same audit trail. What the inbox removes is the
navigation, not the control.

Rebuilt when opened, not stored. A stored inbox has to be invalidated by every
model it watches, and the first missed trigger shows a manager a task that was
done yesterday — worse than no inbox at all. Rebuilding costs a dozen queries
and cannot go stale.

Each user sees only rows built for them: the gathering is filtered by role
before it starts, and a record rule keeps one user's rows out of another's list
even though they share a table.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MizanInboxItem(models.TransientModel):
    _name = "mizan.work.item"
    _description = "Work Inbox"
    _order = "urgency, amount desc"

    name = fields.Char(string="Task", readonly=True)
    source = fields.Char(string="App", readonly=True)
    partner_name = fields.Char(string="Party", readonly=True)
    amount = fields.Monetary(readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    urgency = fields.Selection(
        [("1", "Needs a decision"),
         ("2", "Needs checking"),
         ("3", "Worth knowing")],
        string="Priority", readonly=True)
    note = fields.Char(string="Why", readonly=True)
    date_due = fields.Date(string="Due", readonly=True)
    days_late = fields.Integer(string="Days", readonly=True)

    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)

    action_label = fields.Char(string="Next Action", readonly=True)
    action_hint = fields.Char(string="What happens", readonly=True)
    can_act = fields.Boolean(readonly=True)

    # --------------------------------------------------------------- acting
    def _record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            raise UserError(_("This row is not linked to a document."))
        return self.env[self.res_model].browse(self.res_id).exists()

    def action_open(self):
        """Open the real document, where the rest of the buttons are."""
        self.ensure_one()
        record = self._record()
        if not record:
            raise UserError(_("That document no longer exists. Refresh the "
                              "inbox."))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [[False, "form"]],
            "target": "current",
        }

    def action_do_next(self):
        """Take the document's own next step, without leaving the inbox."""
        self.ensure_one()
        record = self._record()
        if not record:
            raise UserError(_("That document no longer exists. Refresh the "
                              "inbox."))
        if not hasattr(record, "action_mizan_next"):
            return self.action_open()
        result = record.action_mizan_next()
        # A method that opens a window — registering a payment, say — must be
        # allowed to; the inbox refreshes on the way back either way.
        if isinstance(result, dict) and result.get("type"):
            return result
        return self.action_refresh()

    def action_do_selected(self):
        """Take the next step on every selected row.

        Bulk, but not blind: a row whose step is blocked stops that row and
        nothing else, and the count of both is reported at the end. A bulk
        action that swallows failures is how an approval nobody made ends up
        in the ledger."""
        done, failed = 0, []
        for item in self:
            record = item._record()
            if not record or not hasattr(record, "action_mizan_next"):
                failed.append(item.name)
                continue
            try:
                # Each row in its own savepoint: one blocked document must not
                # roll back the twenty that went through before it.
                with self.env.cr.savepoint():
                    record.action_mizan_next()
                done += 1
            except Exception as error:  # noqa: BLE001
                failed.append("%s — %s" % (item.name, error))
        message = _("%s done.", done)
        if failed:
            message += "\n" + _("%s could not be completed:", len(failed))
            message += "\n• " + "\n• ".join(failed[:10])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Work Inbox"),
                "message": message,
                "type": "warning" if failed else "success",
                "sticky": bool(failed),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    # ------------------------------------------------------------ the role
    def _role(self):
        """Which slice of the work this user is responsible for.

        A project manager opening the inbox should not be handed the bank
        reconciliation, and an accountant should not be handed the guarantees.
        Showing everyone everything is the same as showing nobody anything."""
        user = self.env.user
        return {
            "finance": user.has_group("account.group_account_manager"),
            "accounts": user.has_group("account.group_account_invoice"),
            "projects": user.has_group("project.group_project_manager"),
            "hr": user.has_group("hr.group_hr_user"),
        }

    # ------------------------------------------------------------ gathering
    @api.model
    def _gather(self):
        company = self.env.company
        currency = company.currency_id
        today = fields.Date.context_today(self)
        role = self._role()
        rows = []

        def add(name, source, party, amount, urgency, note, record,
                due=False, label="", hint="", act=True):
            rows.append({
                "name": name, "source": source, "partner_name": party or "",
                "amount": amount or 0.0, "currency_id": currency.id,
                "urgency": urgency, "note": note,
                "res_model": record._name, "res_id": record.id,
                "date_due": due or False,
                "days_late": (today - due).days if due else 0,
                "action_label": label, "action_hint": hint,
                "can_act": bool(act and label),
            })

        def nxt(record):
            """The document's own next step, asked of the document."""
            if not hasattr(record, "_mizan_next_action"):
                return "", "", False
            try:
                info = record._mizan_next_action() or {}
            except Exception:  # noqa: BLE001
                return "", "", False
            return (info.get("label") or "", info.get("hint") or "",
                    not info.get("blocked"))

        # --- progress claims -------------------------------------------
        if role["finance"] or role["projects"]:
            Claim = self.env["mizan.progress.claim"]
            for claim in Claim.search([("state", "in", ("submitted", "certified"))]):
                label, hint, ok = nxt(claim)
                if claim.state == "certified":
                    add(_("Raise the tax invoice for %s", claim.name),
                        _("Contracting"), claim.partner_id.display_name,
                        claim.amount_this_period, "1",
                        _("Certified and not yet invoiced"), claim,
                        label=label, hint=hint, act=ok)
                else:
                    add(_("%s is with the consultant", claim.name),
                        _("Contracting"), claim.partner_id.display_name,
                        claim.amount_this_period, "3",
                        _("Waiting for certification"), claim,
                        label=label, hint=hint, act=ok)

        # --- variation orders waiting on the client ---------------------
        if role["finance"] or role["projects"]:
            Variation = self.env["mizan.contract.variation"]
            for vo in Variation.search([("state", "in", ("draft", "submitted"))]):
                label, hint, ok = nxt(vo)
                add(_("Variation %s: %s", vo.reference, vo.name),
                    _("Contracting"), vo.contract_id.partner_id.display_name,
                    vo.amount, "2" if vo.state == "submitted" else "1",
                    _("Not in the contract value until it is approved"), vo,
                    label=label, hint=hint, act=ok)

        # --- cheques ----------------------------------------------------
        if role["finance"]:
            Cheque = self.env["mizan.cheque"]
            for cheque in Cheque.search([("state", "=", "to_approve")]):
                label, hint, ok = nxt(cheque)
                add(_("Approve cheque %s", cheque.name), _("Banking"),
                    cheque.partner_id.display_name, cheque.amount, "1",
                    _("Second signature required") if cheque.needs_second_approval
                    else _("Waiting for approval"), cheque,
                    due=cheque.due_date, label=label, hint=hint, act=ok)
            for cheque in Cheque.search([("state", "=", "bounced")]):
                add(_("Cheque %s bounced", cheque.name), _("Banking"),
                    cheque.partner_id.display_name, cheque.amount, "1",
                    _("Raise a claim on it or write it off"), cheque,
                    due=cheque.due_date, act=False)
            for cheque in Cheque.search([("state", "=", "deposited"),
                                         ("due_date", "<", today)]):
                label, hint, ok = nxt(cheque)
                add(_("Cheque %s is past its date and not cleared", cheque.name),
                    _("Banking"), cheque.partner_id.display_name,
                    cheque.amount, "2",
                    _("Ask the bank, or record it bounced"), cheque,
                    due=cheque.due_date, label=label, hint=hint, act=ok)

        # --- expense claims ---------------------------------------------
        if role["finance"] or role["hr"]:
            Sheet = self.env["hr.expense.sheet"]
            for sheet in Sheet.search([("state", "in", ("submit", "approve"))]):
                label, hint, ok = nxt(sheet)
                add(_("%s — %s", sheet.name, sheet.employee_id.name),
                    _("Petty Cash"), sheet.employee_id.name,
                    sheet.total_amount, "1",
                    _("Submitted and waiting") if sheet.state == "submit"
                    else _("Approved and not posted"), sheet,
                    label=label, hint=hint, act=ok)

        # --- documents still in draft -----------------------------------
        if role["accounts"]:
            Move = self.env["account.move"]
            # A draft invoice has no number yet — Odoo shows "/" — so naming
            # the task after it reads as "Post /". Before it is numbered, the
            # party and the kind are what a person recognises it by.
            kinds = dict(Move._fields["move_type"]._description_selection(self.env))
            for move in Move.search([("state", "=", "draft"),
                                     ("move_type", "!=", "entry")]):
                label, hint, ok = nxt(move)
                numbered = move.name and move.name not in ("/", False)
                caption = (_("Post %s", move.name) if numbered
                           else _("Post a draft %(kind)s for %(party)s",
                                  kind=kinds.get(move.move_type, _("document")),
                                  party=move.partner_id.display_name
                                  or _("no party")))
                add(caption, _("Accounting"), move.partner_id.display_name,
                    move.amount_total, "2", _("Draft, not in the ledger"), move,
                    due=move.invoice_date_due, label=label, hint=hint, act=ok)

            # --- invoices overdue and unpaid
            overdue = Move.search([
                ("state", "=", "posted"), ("move_type", "=", "out_invoice"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("invoice_date_due", "<", today)])
            for move in overdue:
                add(_("%s is overdue", move.name), _("Accounting"),
                    move.partner_id.display_name, move.amount_residual, "2",
                    _("Chase the customer"), move,
                    due=move.invoice_date_due, act=False)

        # --- bank lines nobody has explained ----------------------------
        if role["accounts"]:
            Line = self.env["account.bank.statement.line"]
            for line in Line.search([("is_reconciled", "=", False)]):
                add(_("Reconcile: %s", (line.payment_ref or "")[:40]),
                    _("Banking"), line.partner_id.display_name or "",
                    abs(line.amount), "2",
                    _("The bank moved money nothing explains"), line,
                    due=line.date, act=False)

        # --- guarantees about to lapse ----------------------------------
        if role["finance"] or role["projects"]:
            Bond = self.env["mizan.contract.bond"]
            for bond in Bond.search([("state", "=", "active")]):
                if 0 <= bond.days_to_expiry <= 30:
                    add(_("Guarantee %(ref)s expires in %(days)s days",
                          ref=bond.name, days=bond.days_to_expiry),
                        _("Contracting"),
                        bond.contract_id.partner_id.display_name,
                        bond.amount, "1",
                        _("An expired guarantee holds up the next claim"),
                        bond, due=bond.expiry_date, act=False)

        # --- advances still being recovered -----------------------------
        if role["finance"]:
            Contract = self.env["mizan.contract"]
            for contract in Contract.search([("advance_amount", ">", 0)]):
                if contract.advance_outstanding > 0:
                    add(_("Advance outstanding on %s", contract.code),
                        _("Contracting"), contract.partner_id.display_name,
                        contract.advance_outstanding, "3",
                        _("Recovered from each claim"), contract, act=False)

        # --- contracts forecast to lose money ---------------------------
        if role["finance"] or role["projects"]:
            for contract in self.env["mizan.contract"].search(
                    [("state", "=", "running")]):
                if contract.is_loss_making and not contract.loss_provision_booked:
                    add(_("%s is forecast to lose money", contract.name),
                        _("Contracting"), contract.partner_id.display_name,
                        contract.loss_provision_required, "1",
                        _("IFRS 15 wants the whole loss provided now, not "
                          "spread over the remaining periods"), contract,
                        act=False)

        return rows

    @api.model
    def action_refresh(self):
        """Rebuild this user's list and show it."""
        self.search([("create_uid", "=", self.env.uid)]).unlink()
        rows = self._gather()
        if rows:
            self.create(rows)
        return {
            "type": "ir.actions.act_window",
            "name": _("Work Inbox"),
            "res_model": "mizan.work.item",
            "view_mode": "list,form",
            "target": "current",
            "context": {"search_default_group_urgency": 1},
        }
