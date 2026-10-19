# -*- coding: utf-8 -*-
"""The manager's insights and short report.

The figures are the system's: cash, profit, what customers owe, what is due,
each project's progress and margin, what waits for approval. The language
model (Settings → AI, the same key as invoice reading) only reads those
figures and writes a few plain sentences about them; it is told never to
compute a figure of its own. Without a key, or when the service fails, the
same insights are written by fixed rules from the same figures.

Generated at most once an hour per person and kept, so opening the app
does not call the model each time."""
import json
import logging

from odoo import _, api, fields, models

from .approvals import _is_manager

_logger = logging.getLogger(__name__)

PROMPT = """You are the finance assistant of a UAE contracting company, writing for the
owner on his phone. Below are today's figures from the accounting system, in JSON.

Write in {lang}. Use ONLY the figures given, quoted exactly as written; never
compute, estimate or invent a number. Be concrete and short; no greetings.

Return ONLY one JSON object:
{{"insights": [{{"title": str (max 6 words), "text": str (one sentence, max 25 words),
                "tone": "good" | "watch" | "bad"}}],   (4 to 6 items, worst first)
  "report": str (a short paragraph, 4-6 sentences, what to do this week)}}

Figures:
{facts}"""


class MizanMobile(models.AbstractModel):
    _inherit = "mizan.mobile"

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
    def _rule_insights(self, facts):
        """The same insights without a language model."""
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
    def manager_insights(self, refresh=False):
        if not _is_manager(self.env):
            from odoo.exceptions import AccessError
            raise AccessError(_("The manager's summary is for managers."))
        params = self.env["ir.config_parameter"].sudo()
        key = "mizan_mobile.insights.%s.%s" % (self.env.uid, self.env.company.id)
        now = fields.Datetime.now()
        if not refresh:
            try:
                cached = json.loads(params.get_param(key) or "{}")
                if cached.get("at") and (now - fields.Datetime.to_datetime(cached["at"])).total_seconds() < 3600:
                    return cached["data"]
            except (ValueError, TypeError):
                pass
        facts = self._insight_facts()
        data = None
        ai = self.env["mizan.ai"]
        if ai._config().get("key"):
            lang = "Arabic" if (self.env.user.lang or "").startswith("ar") else "English"
            try:
                reply = ai._chat([{"role": "user", "content": PROMPT.format(
                    lang=lang, facts=json.dumps(facts, ensure_ascii=False, indent=1))}], json_mode=True, timeout=60)
                parsed = ai._json(reply)
                insights = [i for i in parsed.get("insights", []) if i.get("title") and i.get("text")][:6]
                for i in insights:
                    if i.get("tone") not in ("good", "watch", "bad"):
                        i["tone"] = "watch"
                if insights:
                    data = {"insights": insights, "report": str(parsed.get("report") or ""), "source": "ai"}
            except Exception as error:  # noqa: BLE001 - the rules answer instead
                _logger.info("Insights: AI unavailable (%s); using the rules", error)
        if not data:
            data = self._rule_insights(facts)
        data["at"] = fields.Datetime.context_timestamp(self, now).strftime("%d/%m %H:%M")
        params.set_param(key, json.dumps({"at": fields.Datetime.to_string(now), "data": data}, ensure_ascii=False))
        return data
