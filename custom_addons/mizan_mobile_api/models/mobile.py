# -*- coding: utf-8 -*-
"""What the phone app shows, computed here so the app only draws.

Every method runs as the signed-in person, with their rights: an engineer
asking for the manager's figures gets an access error, not the figures."""
import base64
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .approvals import _is_manager


class MizanMobile(models.AbstractModel):
    _name = "mizan.mobile"
    _description = "Phone app data"

    # ------------------------------------------------------------ helpers
    @api.model
    def _money(self, amount):
        currency = self.env.company.currency_id
        lang = self.env.context.get("lang") or self.env.user.lang or ""
        unit = "د.إ" if lang.startswith("ar") and currency.name == "AED" else currency.name
        return "%s %s" % ("{:,.0f}".format(amount or 0.0), unit)

    @api.model
    def _employee(self):
        return self.env["hr.employee"].search([("user_id", "=", self.env.uid)], limit=1)

    @api.model
    def _roles(self):
        user = self.env.user
        roles = []
        if _is_manager(self.env):
            roles.append("manager")
        if user.has_group("hr_expense.group_hr_expense_team_approver") or _is_manager(self.env):
            roles.append("approver")
        if user.has_group("mizan_site.group_site_engineer"):
            roles.append("engineer")
        if user.has_group("account.group_account_invoice"):
            roles.append("accountant")
        if self._employee() and "engineer" not in roles:
            roles.append("staff")  # anyone with petty cash of their own
        return roles

    # ------------------------------------------------------------ who
    @api.model
    def me(self):
        user = self.env.user
        roles = self._roles()
        return {
            "uid": user.id, "name": user.name, "first_name": (user.name or "").split(" ")[0],
            "lang": user.lang, "company": self.env.company.name, "roles": roles,
            "currency": self.env.company.currency_id.name,
            "counts": self.counts() if ("manager" in roles or "approver" in roles) else {},
        }

    @api.model
    def counts(self):
        out = {"approvals": len(self.approvals()["items"])}
        out["alerts"] = self.env["mail.notification"].sudo().search_count([
            ("res_partner_id", "=", self.env.user.partner_id.id), ("is_read", "=", False)])
        return out

    # ------------------------------------------------------------ manager
    @api.model
    def manager_summary(self):
        if not _is_manager(self.env):
            raise AccessError(_("The manager's summary is for managers."))
        summary = self.env["mizan.owner"].get_summary()
        for card in summary.get("cards", []):
            card.pop("action", None)
        for project in summary.get("projects", []):
            project.pop("action", None)
        summary["approvals"] = len(self.approvals()["items"])
        return summary

    @api.model
    def projects(self):
        if not _is_manager(self.env) and not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("Projects are for managers and accounts."))
        rows = []
        for c in self.env["mizan.contract"].search([("state", "in", ("running", "done"))], order="code"):
            rows.append({
                "id": c.id, "name": c.name, "code": c.code, "client": c.partner_id.name or "",
                "percent": round(c.completion_percent or 0.0, 1),
                "value": self._money(c.revised_contract_value or c.contract_value),
                "billed": self._money(c.billed_net), "cost": self._money(c.cost_incurred),
                "owed": self._money(c.client_balance), "retention": self._money(c.retention_balance),
                "margin": self._money(c.margin_to_date) if c.has_project_accounts else "",
                "sources": [
                    {"label": _("Supplier bills"), "value": self._money(c.cost_bills)},
                    {"label": _("Subcontractors"), "value": self._money(c.cost_subcontract)},
                    {"label": _("Petty cash"), "value": self._money(c.cost_petty)},
                    {"label": _("Labour"), "value": self._money(c.cost_labour)},
                    {"label": _("Stock"), "value": self._money(c.cost_stock)},
                    {"label": _("Entries"), "value": self._money(c.cost_other)},
                ] if c.has_project_accounts else [],
            })
        return {"projects": rows}

    @api.model
    def alerts(self, limit=40):
        notifications = self.env["mail.notification"].sudo().search(
            [("res_partner_id", "=", self.env.user.partner_id.id)], order="id desc", limit=limit)
        items = []
        for n in notifications:
            msg = n.mail_message_id
            body = (msg.body or "")
            import re
            text = re.sub(r"<br\s*/?>", "\n", body)
            text = re.sub(r"<[^>]+>", "", text).strip()
            items.append({"id": n.id, "title": msg.subject or msg.record_name or _("Notification"),
                          "text": text[:400], "date": fields.Datetime.context_timestamp(self, msg.date).strftime("%d/%m %H:%M") if msg.date else "",
                          "unread": not n.is_read})
        return {"items": items}

    @api.model
    def alerts_read(self):
        self.env["mail.notification"].sudo().search([
            ("res_partner_id", "=", self.env.user.partner_id.id), ("is_read", "=", False)]).write({"is_read": True})
        return True

    # ------------------------------------------------------------ approvals
    @api.model
    def approvals(self):
        items = []
        user = self.env.user
        Sheet = self.env["hr.expense.sheet"]
        if user.has_group("hr_expense.group_hr_expense_team_approver") or _is_manager(self.env):
            for s in Sheet.search([("state", "=", "submit"), ("mizan_advance_id", "!=", False)], order="id desc", limit=50):
                items.append({"kind": "receipt", "id": s.id, "title": s.name, "who": s.employee_id.name,
                              "amount": self._money(s.total_amount), "date": s.mizan_date and s.mizan_date.strftime("%d/%m/%Y") or "",
                              "project": s.expense_line_ids[:1].analytic_distribution and self._project_name(s.expense_line_ids[:1]) or "",
                              "photo": "/web/image/hr.expense.sheet/%d/mizan_photo" % s.id if s.mizan_photo else ""})
            for a in self.env["mizan.employee.advance"].search([("state", "=", "submitted")], order="id desc", limit=50):
                items.append({"kind": "topup", "id": a.id, "title": a.purpose or _("Top-up request"), "who": a.employee_id.name,
                              "amount": self._money(a.amount), "date": a.date and a.date.strftime("%d/%m/%Y") or "",
                              "project": a.project_id.name if "project_id" in a._fields and a.project_id else ""})
        if _is_manager(self.env):
            for b in self.env["account.move"].search([("mizan_approval_state", "=", "to_approve")], order="id desc", limit=50):
                items.append({"kind": "bill", "id": b.id, "title": b.name, "who": b.partner_id.name or "",
                              "amount": self._money(b.amount_total), "date": b.invoice_date and b.invoice_date.strftime("%d/%m/%Y") or "",
                              "project": b.mizan_contract_id.name or ""})
            for r in self.env["mizan.payment.request"].search([("state", "=", "to_approve")], order="id desc", limit=50):
                items.append({"kind": "sc_payment", "id": r.id, "title": r.subcontract_id.code or "", "who": r.partner_id.name or "",
                              "amount": self._money(r.amount), "date": r.date and r.date.strftime("%d/%m/%Y") or "",
                              "project": r.contract_id.name or "",
                              "note": _("Retention withheld: %s", self._money(r.retention_amount)) if r.retention_amount else ""})
        return {"items": items}

    def _project_name(self, line):
        ids = [int(k) for key in (line.analytic_distribution or {}) for k in str(key).split(",") if k.strip().isdigit()]
        account = self.env["account.analytic.account"].sudo().browse(ids[:1])
        return account.name or ""

    @api.model
    def decide(self, kind, record_id, approve):
        if kind == "receipt":
            sheet = self.env["hr.expense.sheet"].browse(int(record_id))
            if approve:
                sheet.action_mizan_approve()
            else:
                sheet._do_refuse(_("Refused from the phone app")) if hasattr(sheet, "_do_refuse") else sheet.write({"state": "cancel"})
        elif kind == "topup":
            advance = self.env["mizan.employee.advance"].browse(int(record_id))
            advance.action_approve() if approve else advance.action_refuse()
        elif kind == "bill":
            bill = self.env["account.move"].browse(int(record_id))
            bill.action_mizan_approve_bill() if approve else bill.action_mizan_refuse_bill()
        elif kind == "sc_payment":
            req = self.env["mizan.payment.request"].browse(int(record_id))
            req.action_approve() if approve else req.action_refuse()
        else:
            raise UserError(_("Unknown approval."))
        return {"ok": True, "counts": self.counts()}

    # ------------------------------------------------------------ engineer
    @api.model
    def my_cash(self):
        employee = self._employee()
        if not employee:
            return {"linked": False}
        cash = self.env["mizan.employee.advance"]._petty_cash(employee)
        sheets = self.env["hr.expense.sheet"].search(
            [("employee_id", "=", employee.id), ("mizan_advance_id", "!=", False)], order="id desc", limit=30)
        state_label = dict(self.env["hr.expense.sheet"]._fields["state"]._description_selection(self.env))
        requests = self.env["mizan.employee.advance"].search(
            [("employee_id", "=", employee.id)], order="id desc", limit=10)
        adv_label = dict(self.env["mizan.employee.advance"]._fields["state"]._description_selection(self.env))
        return {
            "linked": True,
            "held": self._money(cash["held"]), "waiting": self._money(cash["waiting"]),
            "available": self._money(cash["available"]), "available_raw": cash["available"],
            "receipts": [{"id": s.id, "title": s.name, "amount": self._money(s.total_amount),
                          "date": s.mizan_date and s.mizan_date.strftime("%d/%m/%Y") or "",
                          "state": s.state, "state_label": state_label.get(s.state, ""),
                          "photo": "/web/image/hr.expense.sheet/%d/mizan_photo" % s.id if s.mizan_photo else ""}
                         for s in sheets],
            "requests": [{"id": a.id, "title": a.purpose or "", "amount": self._money(a.amount),
                          "state": a.state, "state_label": adv_label.get(a.state, "")} for a in requests],
            "kinds": [{"key": k, "label": l} for k, l in
                      self.env["mizan.site.capture"]._fields["spend_kind"]._description_selection(self.env)],
            "projects": self._my_projects(),
        }

    @api.model
    def _my_projects(self):
        projects = self.env["project.project"].search([("account_id", "!=", False)], order="name")
        return [{"id": p.id, "name": p.name} for p in projects]

    @api.model
    def submit_receipt(self, photo, amount, project_id, kind=None, description=None, vat=True):
        if not photo:
            raise UserError(_("Take a photograph of the receipt."))
        try:
            base64.b64decode(photo, validate=True)
        except Exception:
            raise UserError(_("The photograph could not be read.")) from None
        values = {"photo": photo, "amount": float(amount or 0), "project_id": int(project_id),
                  "paid_by": "cash", "description": description or "", "vat_on_receipt": bool(vat)}
        if kind:
            values["spend_kind"] = kind
        capture = self.env["mizan.site.capture"].create(values)
        capture.action_save()
        return {"ok": True, "cash": self.my_cash()}

    @api.model
    def request_topup(self, amount, purpose=None, project_id=None):
        employee = self._employee()
        if not employee:
            raise UserError(_("Your login is not linked to an employee record."))
        values = {"employee_id": employee.id, "amount": float(amount or 0), "mizan_topup": True,
                  "purpose": purpose or _("Petty cash top-up")}
        if project_id and "project_id" in self.env["mizan.employee.advance"]._fields:
            values["project_id"] = int(project_id)
        advance = self.env["mizan.employee.advance"].create(values)
        advance.action_send_topup()
        return {"ok": True, "cash": self.my_cash()}

    # ------------------------------------------------------------ crew
    @api.model
    def crew(self, contract_id=None, date=None):
        day = fields.Date.to_date(date) if date else fields.Date.context_today(self)
        Contract = self.env["mizan.contract"].sudo()
        contracts = Contract.search([("state", "=", "running"), ("wip_account_id", "!=", False)], order="name")
        contract = Contract.browse(int(contract_id)) if contract_id else contracts[:1]
        cards = self.env["mizan.labour.card"].search([("active", "=", True)], order="employee_id")
        days = self.env["mizan.labour.day"].search([("date", "=", day), ("contract_id", "=", contract.id)]) if contract else []
        by_card = {d.card_id.id: d for d in days}
        return {
            "date": day.strftime("%Y-%m-%d"), "date_label": day.strftime("%d/%m/%Y"),
            "projects": [{"id": c.id, "name": c.name} for c in contracts],
            "project_id": contract.id if contract else False,
            "workers": [{"card_id": card.id, "name": card.employee_id.name, "trade": card.trade or "",
                         "wage": self._money(card.daily_wage),
                         "fraction": by_card[card.id].fraction if card.id in by_card else "",
                         "posted": by_card[card.id].state == "posted" if card.id in by_card else False}
                        for card in cards],
            "total": self._money(sum(d.cost for d in days)),
        }

    @api.model
    def save_crew(self, contract_id, date, entries):
        """entries: [{card_id, fraction}] with fraction '' to remove."""
        day = fields.Date.to_date(date)
        Day = self.env["mizan.labour.day"]
        for entry in entries or []:
            card_id, fraction = int(entry["card_id"]), entry.get("fraction") or ""
            existing = Day.search([("card_id", "=", card_id), ("date", "=", day), ("contract_id", "=", int(contract_id))], limit=1)
            if existing and existing.state == "posted":
                continue
            if not fraction:
                existing.unlink()
            elif existing:
                existing.fraction = fraction
            else:
                Day.create({"card_id": card_id, "date": day, "contract_id": int(contract_id), "fraction": fraction})
        return self.crew(contract_id, date)
