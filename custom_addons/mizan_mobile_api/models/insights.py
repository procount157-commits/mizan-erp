# -*- coding: utf-8 -*-
"""Insights and a short report, written for whoever is looking.

The manager reads the company: cash, profit, what customers owe, projects,
what waits for him. The accountant reads today's desk: whom to chase first,
what to pay, what to post. The engineer reads his site: the crew, the daily
report, his cash.

The figures are always the system's. The language model (Settings → AI, the
same key as invoice reading) only reads them and writes a few plain
sentences; it is told never to compute a figure of its own. Without a key,
or when the service fails, fixed rules write the same insights from the same
figures.

Generated at most once an hour per person and role and kept, so opening the
app does not call the model each time."""
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .approvals import _is_manager

_logger = logging.getLogger(__name__)

AUDIENCE = {
    "manager": "the owner of a UAE contracting company, on his phone. Tell him how the company is doing "
               "and what needs his decision this week",
    "accountant": "the accountant of a UAE contracting company, at the start of the day. Tell her what to "
                  "do first: which customers to chase (largest and latest first), which supplier bills fall "
                  "due, receipts to post, bank lines to match",
    "engineer": "a site engineer of a UAE contracting company, on site. Tell him what is still to do today "
                "(crew, daily report, receipts) and anything about his petty cash; practical and short",
}

PROMPT = """You are the assistant of {audience}. Below are today's figures from the
accounting system, in JSON.

Write in {lang}. Use ONLY the figures given, quoted exactly as written; never
compute, estimate or invent a number. Be concrete and short; no greetings.

Return ONLY one JSON object:
{{"insights": [{{"title": str (max 6 words), "text": str (one sentence, max 25 words),
                "tone": "good" | "watch" | "bad"}}],   (3 to 6 items, most urgent first)
  "report": str (a short paragraph, 3-6 sentences, what to do next)}}

Figures:
{facts}"""


class MizanMobile(models.AbstractModel):
    _inherit = "mizan.mobile"

    # ------------------------------------------------------------- facts
    @api.model
    def _insight_facts(self):
        summary = self.env["mizan.owner"].get_summary()
        cards = {c["key"]: {"title": c["title"], "value": c["value"], "lines": c.get("lines", [])}
                 for c in summary.get("cards", [])}
        projects = []
        for c in self.env["mizan.contract"].search([("state", "=", "running")], limit=10):
            projects.append({
                "name": c.name, "percent_complete": "%.1f%%" % (c.completion_percent or 0.0),
                "contract_value": self._money(c.revised_contract_value or c.contract_value),
                "cost_to_date": self._money(c.cost_incurred), "billed": self._money(c.billed_net),
                "client_owes": self._money(c.client_balance), "retention_held": self._money(c.retention_balance),
                "forecast": next((p["line"] for p in summary.get("projects", []) if p["name"] == c.name), ""),
            })
        approvals = self.approvals()["items"]
        return {
            "company": summary.get("company"), "date": summary.get("date"),
            "headline": summary.get("headline"), "cards": cards, "projects": projects,
            "waiting_for_approval": {
                "count": len(approvals),
                "items": [{"kind": a["kind"], "what": a["title"], "who": a["who"], "amount": a["amount"]} for a in approvals[:8]],
            },
            "recent": [e["text"] for e in summary.get("events", [])],
        }

    @api.model
    def _accountant_facts(self):
        d = self.accountant_summary()
        return {
            "receipts_to_post": [{"what": r["title"], "who": r["who"], "amount": r["amount"]} for r in d["receipts"][:8]],
            "customers_past_due": [{"customer": m["who"], "invoice": m["name"], "amount": m["amount"], "late": m["late"]}
                                   for m in d["overdue"][:8]],
            "customers_past_due_total": d["overdue_total"],
            "supplier_bills_due_within_7_days": [{"supplier": m["who"], "bill": m["name"], "amount": m["amount"],
                                                  "due": m["when"], "waiting_manager": m["waiting"]} for m in d["due"][:8]],
            "supplier_bills_due_total": d["due_total"],
            "bank_lines_unmatched": d["bank_count"], "bank_in_unmatched": d["bank_in"], "bank_out_unmatched": d["bank_out"],
            "waiting_for_manager": d["waiting_manager"],
        }

    @api.model
    def _engineer_facts(self):
        d = self.engineer_home()
        return {
            "date": d["date"], "todo_today": [{"task": t["title"], "done": t["done"], "detail": t["text"]} for t in d["todo"]],
            "petty_cash": d["cash"], "projects": [{"name": p["name"], "percent_complete": "%s%%" % p["percent"],
                                                  "days_left": p["days_left"], "workers_today": p["workers_today"]}
                                                 for p in d["projects"]],
            "receipts": d["receipts"],
        }

    # ------------------------------------------------------------- rules
    @api.model
    def _rule_insights(self, facts):
        """The manager's insights without a language model."""
        items = []
        cards = facts["cards"]
        mood = "good"
        headline = facts.get("headline") or ""
        if headline:
            items.append({"title": _("The company today"), "text": headline,
                          "tone": "good" if "good shape" in headline or "وضع جيد" in headline else "watch"})
        for key, tone in (("cash", "good"), ("profit", "good"), ("owed", "watch"), ("due", "watch")):
            card = cards.get(key)
            if card:
                line = card["lines"][0] if card["lines"] else ""
                items.append({"title": card["title"], "text": "%s. %s" % (card["value"], line), "tone": tone})
        for p in facts["projects"]:
            if "Losing" in p["forecast"] or "تخسر" in p["forecast"] or "Thin" in p["forecast"] or "هامش ضعيف" in p["forecast"]:
                items.insert(1, {"title": p["name"], "text": p["forecast"], "tone": "bad"})
        waiting = facts["waiting_for_approval"]["count"]
        if waiting:
            items.insert(0, {"title": _("Waiting for you"), "text": _("%s request(s) wait for your approval.", waiting), "tone": "watch"})
            mood = "watch"
        report = " ".join(i["text"] for i in items[:4])
        return {"insights": items[:6], "report": report, "source": "rules", "mood": mood}

    @api.model
    def _rule_accountant(self, f):
        items = []
        if f["customers_past_due"]:
            top = f["customers_past_due"][0]
            items.append({"title": _("Chase first"), "tone": "bad",
                          "text": _("%(c)s owes %(a)s on %(i)s, %(l)s.", c=top["customer"], a=top["amount"],
                                    i=top["invoice"], l=top["late"])})
            items.append({"title": _("Customers past due"), "tone": "watch",
                          "text": _("%(n)s invoice(s) past due, %(t)s in all.", n=len(f["customers_past_due"]),
                                    t=f["customers_past_due_total"])})
        if f["supplier_bills_due_within_7_days"]:
            items.append({"title": _("To pay this week"), "tone": "watch",
                          "text": _("%(n)s supplier bill(s) due within 7 days, %(t)s.",
                                    n=len(f["supplier_bills_due_within_7_days"]), t=f["supplier_bills_due_total"])})
        if f["receipts_to_post"]:
            items.append({"title": _("Receipts to post"), "tone": "watch",
                          "text": _("%s approved petty-cash receipt(s) wait to be posted.", len(f["receipts_to_post"]))})
        if f["bank_lines_unmatched"]:
            items.append({"title": _("Bank to match"), "tone": "watch",
                          "text": _("%s bank line(s) are not matched yet.", f["bank_lines_unmatched"])})
        if f["waiting_for_manager"]:
            items.append({"title": _("With the manager"), "tone": "watch",
                          "text": _("%s item(s) wait for the manager's approval.", f["waiting_for_manager"])})
        if not items:
            items.append({"title": _("All clear"), "tone": "good", "text": _("Nothing is late or waiting today.")})
        return {"insights": items[:6], "report": " ".join(i["text"] for i in items[:4]), "source": "rules"}

    @api.model
    def _rule_engineer(self, f):
        items = [{"title": t["task"], "text": t["detail"], "tone": "watch"} for t in f["todo_today"] if not t["done"]]
        for p in f["projects"]:
            if p["days_left"] is not None and p["days_left"] < 0:
                items.append({"title": p["name"], "tone": "bad",
                              "text": _("Past its completion date by %s day(s).", -p["days_left"])})
            elif p["days_left"] is not None and p["days_left"] <= 14:
                items.append({"title": p["name"], "tone": "watch",
                              "text": _("%(d)s day(s) to the completion date, %(p)s complete.",
                                        d=p["days_left"], p=p["percent_complete"])})
        if not items:
            items.append({"title": _("Today is done"), "tone": "good",
                          "text": _("Crew and daily report are in. Good work.")})
        return {"insights": items[:6], "report": " ".join(i["text"] for i in items[:4]), "source": "rules"}

    # ------------------------------------------------------------- one door
    @api.model
    def _insight_kind(self, role):
        roles = self._roles()
        if role == "manager" and _is_manager(self.env):
            return self._insight_facts, self._rule_insights
        if role == "accountant" and "accountant" in roles:
            return self._accountant_facts, self._rule_accountant
        if role in ("engineer", "staff") and (set(roles) & {"engineer", "staff"}):
            return self._engineer_facts, self._rule_engineer
        raise AccessError(_("These insights are not for your role."))

    @api.model
    def role_insights(self, role="manager", refresh=False):
        facts_fn, rules_fn = self._insight_kind(role)
        params = self.env["ir.config_parameter"].sudo()
        key = "mizan_mobile.insights.%s.%s.%s" % (role, self.env.uid, self.env.company.id)
        now = fields.Datetime.now()
        # The engineer's day changes by the hour; his tips are kept 20 minutes.
        ttl = 1200 if role in ("engineer", "staff") else 3600
        if not refresh:
            try:
                cached = json.loads(params.get_param(key) or "{}")
                if cached.get("at") and (now - fields.Datetime.to_datetime(cached["at"])).total_seconds() < ttl:
                    return cached["data"]
            except (ValueError, TypeError):
                pass
        facts = facts_fn()
        data = None
        ai = self.env["mizan.ai"]
        ai_ready = bool(ai._config().get("key"))
        if ai_ready:
            lang = "Arabic" if (self.env.user.lang or "").startswith("ar") else "English"
            try:
                reply = ai._chat([{"role": "user", "content": PROMPT.format(
                    audience=AUDIENCE.get(role, AUDIENCE["manager"]), lang=lang,
                    facts=json.dumps(facts, ensure_ascii=False, indent=1))}], json_mode=True, timeout=60)
                parsed = ai._json(reply)
                insights = [i for i in parsed.get("insights", []) if i.get("title") and i.get("text")][:6]
                for i in insights:
                    if i.get("tone") not in ("good", "watch", "bad"):
                        i["tone"] = "watch"
                if insights:
                    data = {"insights": insights, "report": str(parsed.get("report") or ""), "source": "ai"}
            except Exception as error:  # noqa: BLE001 - the rules answer instead
                _logger.info("Insights (%s): AI unavailable (%s); using the rules", role, error)
        if not data:
            data = rules_fn(facts)
        data["at"] = fields.Datetime.context_timestamp(self, now).strftime("%d/%m %H:%M")
        data["ai_ready"] = ai_ready
        params.set_param(key, json.dumps({"at": fields.Datetime.to_string(now), "data": data}, ensure_ascii=False))
        return data

    @api.model
    def manager_insights(self, refresh=False):
        """Kept for app versions before role_insights."""
        return self.role_insights("manager", refresh=refresh)
