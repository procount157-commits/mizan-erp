# -*- coding: utf-8 -*-
"""The engineer's day on the phone.

His home: what is still to do today (crew, daily report, receipts), his
petty cash, and his jobs — progress and days to the completion date, never
the contract's money. The daily site report filed from the phone, with the
crew he already recorded counted in by trade. And the receipt read by the AI
from its photograph, so he checks figures rather than types them."""
import base64
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

RECEIPT_PROMPT = """You read a shop receipt or a small supplier invoice photographed on a
UAE building site. Return ONLY one JSON object, no prose:
{"vendor_name": str or null, "date": "YYYY-MM-DD" or null,
 "subtotal": number or null (before VAT), "vat_amount": number or null,
 "total": number or null (the amount paid, VAT included),
 "description": str (what was bought, max 8 words, in {lang}),
 "kind": one of {kinds} or null}
Copy numbers exactly as printed, without thousands separators. Never invent a
value: use null when it is not on the receipt. UAE receipts write day/month/year."""


class MizanMobile(models.AbstractModel):
    _inherit = "mizan.mobile"

    # ------------------------------------------------------------ helpers
    @api.model
    def _forget_insights(self, *roles):
        params = self.env["ir.config_parameter"].sudo()
        for role in roles:
            params.set_param("mizan_mobile.insights.%s.%s.%s" % (role, self.env.uid, self.env.company.id), False)

    @api.model
    def _engineer_contracts(self):
        """The running jobs this engineer is on: the project is his, he
        follows it, or he recorded crew or a report on it this month. When
        none can be told, every running job."""
        Contract = self.env["mizan.contract"].sudo()
        running = Contract.search([("state", "=", "running")], order="name")
        user = self.env.user
        since = fields.Date.subtract(fields.Date.context_today(self), days=30)
        crew = self.env["mizan.labour.day"].sudo().search(
            [("create_uid", "=", user.id), ("date", ">=", since)]).mapped("contract_id")
        reports = self.env["mizan.site.report"].sudo().search(
            [("author_id", "=", user.id), ("date", ">=", since)]).mapped("project_id")
        mine = running.filtered(lambda c: c in crew or (c.project_id and (
            c.project_id in reports or c.project_id.user_id == user
            or user.partner_id in c.project_id.message_partner_ids)))
        return mine or running

    # ------------------------------------------------------------ home
    @api.model
    def engineer_home(self):
        roles = self._roles()
        if not set(roles) & {"engineer", "staff"}:
            raise AccessError(_("This screen is for site staff."))
        today = fields.Date.context_today(self)
        user = self.env.user
        contracts = self._engineer_contracts() if "engineer" in roles else self.env["mizan.contract"]
        Day = self.env["mizan.labour.day"].sudo()
        days_today = Day.search([("date", "=", today), ("contract_id", "in", contracts.ids)])
        Report = self.env["mizan.site.report"].sudo()
        reports_today = Report.search([("author_id", "=", user.id), ("date", "=", today)])
        filed = reports_today.filtered(lambda r: r.state != "draft")

        employee = self._employee()
        cash = {"available": self._money(0), "held": self._money(0), "waiting": self._money(0), "low": False}
        receipts = {"waiting": 0, "approved_month": 0, "refused_month": 0}
        if employee:
            pc = self.env["mizan.employee.advance"]._petty_cash(employee)
            cash = {"available": self._money(pc["available"]), "held": self._money(pc["held"]),
                    "waiting": self._money(pc["waiting"]),
                    "low": pc["held"] > 0 and pc["available"] < 0.2 * pc["held"]}
            Sheet = self.env["hr.expense.sheet"].sudo()
            month = today.replace(day=1)
            base = [("employee_id", "=", employee.id), ("mizan_advance_id", "!=", False)]
            receipts = {
                "waiting": Sheet.search_count(base + [("state", "=", "submit")]),
                "approved_month": Sheet.search_count(base + [("state", "in", ("approve", "post", "done")),
                                                             ("approval_date", ">=", month)]),
                "refused_month": Sheet.search_count(base + [("state", "=", "cancel"), ("write_date", ">=", month)]),
            }

        todo = []
        if "engineer" in roles:
            workers = len(days_today.mapped("card_id"))
            todo.append({"key": "crew", "done": bool(days_today), "title": _("Today's crew"),
                         "text": _("%s worker(s) recorded today.", workers) if days_today
                         else _("Nobody is recorded on site today yet.")})
            todo.append({"key": "report", "done": bool(filed), "title": _("Daily site report"),
                         "text": _("Filed: %s.", ", ".join(filed.mapped("project_id.name"))) if filed
                         else _("Not filed yet for today.")})
        if employee:
            todo.append({"key": "cash", "done": not cash["low"], "title": _("Petty cash"),
                         "text": _("%s left. Ask for a top-up before it runs out.", cash["available"]) if cash["low"]
                         else _("%s available.", cash["available"])})
        if receipts["refused_month"]:
            todo.append({"key": "refused", "done": False, "title": _("Refused receipts"),
                         "text": _("%s receipt(s) refused this month — see why in Petty cash.", receipts["refused_month"])})

        projects = []
        for c in contracts:
            projects.append({
                "id": c.id, "project_id": c.project_id.id, "name": c.name, "code": c.code or "",
                "client": c.partner_id.name or "",
                "percent": round(c.completion_percent or 0.0, 1),
                "days_left": (c.date_end - today).days if c.date_end else None,
                "workers_today": len(days_today.filtered(lambda d, c=c: d.contract_id == c)),
                "report_today": bool(filed.filtered(lambda r, c=c: r.project_id == c.project_id)),
            })
        return {
            "name": user.name, "first_name": (user.name or "").split(" ")[0],
            "date": today.strftime("%d/%m/%Y"), "todo": todo, "cash": cash,
            "receipts": receipts, "projects": projects,
            "done": sum(1 for t in todo if t["done"]), "total": len(todo),
        }

    # ------------------------------------------------------------ daily report
    @api.model
    def site_report_form(self):
        if "engineer" not in self._roles():
            raise AccessError(_("The daily report is for site engineers."))
        Report = self.env["mizan.site.report"]
        today = fields.Date.context_today(self)
        contracts = self._engineer_contracts().filtered("project_id")
        Day = self.env["mizan.labour.day"].sudo()
        projects = []
        for c in contracts:
            days = Day.search([("date", "=", today), ("contract_id", "=", c.id)])
            filed = Report.sudo().search([("author_id", "=", self.env.uid), ("date", "=", today),
                                          ("project_id", "=", c.project_id.id)], limit=1)
            projects.append({"id": c.project_id.id, "name": c.name, "workers": len(days),
                             "filed": bool(filed and filed.state != "draft")})
        sel = lambda f: [{"key": k, "label": l} for k, l in Report._fields[f]._description_selection(self.env)]
        recent = Report.search([("author_id", "=", self.env.uid)], order="date desc, id desc", limit=10)
        state_label = dict(Report._fields["state"]._description_selection(self.env))
        return {
            "date": today.strftime("%d/%m/%Y"), "projects": projects,
            "weather": sel("weather"), "reasons": sel("stop_reason"),
            "recent": [{"id": r.id, "name": r.name, "project": r.project_id.name, "date": r.date.strftime("%d/%m"),
                        "men": r.headcount, "state": r.state, "state_label": state_label.get(r.state, ""),
                        "stopped": r.work_stopped} for r in recent],
        }

    @api.model
    def _crew_manpower(self, project, day):
        """The crew recorded for the day, as manpower lines by trade."""
        contract = self.env["mizan.contract"].sudo().search([("project_id", "=", project.id)], limit=1)
        if not contract:
            return []
        Job = self.env["hr.job"].sudo()
        groups = defaultdict(int)
        for d in self.env["mizan.labour.day"].sudo().search([("date", "=", day), ("contract_id", "=", contract.id)]):
            trade = (d.card_id.trade or d.employee_id.job_id.name or _("Labourer")).strip()
            groups[(trade, d.fraction)] += 1
        lines = []
        for (trade, fraction), count in groups.items():
            job = Job.search([("name", "=ilike", trade)], limit=1) or Job.create({"name": trade})
            lines.append((0, 0, {"trade_id": job.id, "headcount": count, "hours": 8.0 * float(fraction or 1)}))
        return lines

    @api.model
    def submit_site_report(self, project_id, work_done, weather="clear", issues=None, work_stopped=False,
                           stop_reason=None, stop_hours=0, photo=None):
        if "engineer" not in self._roles():
            raise AccessError(_("The daily report is for site engineers."))
        if not (work_done or "").strip():
            raise UserError(_("Write what was built today."))
        if work_stopped and not stop_reason:
            raise UserError(_("Say why work stopped."))
        if photo:
            try:
                base64.b64decode(photo, validate=True)
            except Exception:
                raise UserError(_("The photograph could not be read.")) from None
        today = fields.Date.context_today(self)
        project = self.env["project.project"].browse(int(project_id)).exists()
        if not project:
            raise UserError(_("Choose the project."))
        Report = self.env["mizan.site.report"]
        report = Report.search([("author_id", "=", self.env.uid), ("date", "=", today),
                                ("project_id", "=", project.id)], limit=1)
        if report and report.state != "draft":
            raise UserError(_("Today's report for %s is already filed.", project.name))
        values = {"weather": weather or "clear", "work_done": work_done.strip(), "issues": issues or False,
                  "work_stopped": bool(work_stopped), "stop_reason": stop_reason if work_stopped else False,
                  "stop_hours": float(stop_hours or 0) if work_stopped else 0}
        if photo:
            values["photo"] = photo
        manpower = self._crew_manpower(project, today)
        if report:
            report.manpower_ids.unlink()
            report.write(dict(values, manpower_ids=manpower))
        else:
            report = Report.create(dict(values, project_id=project.id, date=today, manpower_ids=manpower))
        report.action_submit()
        self._forget_insights("engineer")
        return {"ok": True, "name": report.name, "men": report.headcount, "form": self.site_report_form()}

    # ------------------------------------------------------------ AI receipt
    @api.model
    def read_receipt(self, photo, mimetype="image/jpeg"):
        """What the AI reads on a receipt photo, checked by the system:
        subtotal + VAT must make the total, and VAT must be 5% or none."""
        ai = self.env["mizan.ai"]
        if not ai._config().get("key"):
            return {"ok": False, "reason": "no_ai"}
        kinds = [k for k, _l in self.env["mizan.site.capture"]._fields["spend_kind"]._description_selection(self.env)] \
            if "spend_kind" in self.env["mizan.site.capture"]._fields else []
        lang = "Arabic" if (self.env.user.lang or "").startswith("ar") else "English"
        prompt = RECEIPT_PROMPT.replace("{lang}", lang).replace("{kinds}", ", ".join(kinds) or "null")
        message = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mimetype or "image/jpeg", photo)}},
        ]}]
        try:
            data = ai._json(ai._chat(message, json_mode=True, timeout=60))
        except UserError as error:
            return {"ok": False, "reason": "failed", "message": str(error.args[0] if error.args else error)}

        def num(v):
            try:
                return round(float(str(v).replace(",", "")), 2) if v not in (None, "") else None
            except ValueError:
                return None

        total, sub, vat = num(data.get("total")), num(data.get("subtotal")), num(data.get("vat_amount"))
        notes, checked = [], True
        if total is None and sub is not None:
            total = round(sub + (vat or 0), 2)
        if total is None:
            checked = False
            notes.append(_("The total could not be read; type it."))
        if sub is not None and vat is not None and total is not None and abs(sub + vat - total) > 0.05:
            checked = False
            notes.append(_("Subtotal and VAT do not make the total; check the amount."))
        if sub and vat and abs(vat - sub * 0.05) > max(0.05, sub * 0.002):
            notes.append(_("The VAT is not 5% of the subtotal."))
        kind = data.get("kind") if data.get("kind") in kinds else None
        return {
            "ok": True, "checked": checked, "notes": notes,
            "amount": total, "vat": bool(vat), "vat_amount": vat,
            "vendor": (data.get("vendor_name") or "")[:80], "date": data.get("date") or "",
            "description": (data.get("description") or "")[:120], "kind": kind,
        }
