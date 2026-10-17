# -*- coding: utf-8 -*-
"""One door to the language model, whichever service is behind it.

OpenRouter, Groq and most others speak the same chat-completions API, so the
provider is a base URL, a model name and a key — all in Settings. The key is
read with sudo and never leaves the server except in the request itself."""
import json
import logging
import re

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PROVIDERS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}
DEFAULT_MODELS = {
    "openrouter": "google/gemma-4-31b-it:free",
    "groq": "llama-3.3-70b-versatile",
}
P = "mizan_ai."


class MizanAI(models.AbstractModel):
    _name = "mizan.ai"
    _description = "Language model access"

    @api.model
    def _config(self):
        params = self.env["ir.config_parameter"].sudo()
        provider = params.get_param(P + "provider") or "openrouter"
        base = params.get_param(P + "base_url") or PROVIDERS.get(provider, "")
        return {
            "provider": provider,
            "base_url": base.rstrip("/"),
            "model": params.get_param(P + "invoice_model") or DEFAULT_MODELS.get(provider, ""),
            "key": params.get_param(P + "api_key") or "",
        }

    @api.model
    def _chat(self, messages, json_mode=False, timeout=120):
        """Send a chat; return the reply text. Errors become a sentence the
        accountant can act on, never a traceback."""
        cfg = self._config()
        if not cfg["key"]:
            raise UserError(_("No AI key yet. An administrator types it in Settings → AI."))
        if not cfg["base_url"] or not cfg["model"]:
            raise UserError(_("Choose the AI service and model in Settings → AI."))
        body = {"model": cfg["model"], "messages": messages, "temperature": 0}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": "Bearer %s" % cfg["key"], "Content-Type": "application/json"}
        if cfg["provider"] == "openrouter":
            headers.update({"HTTP-Referer": "https://getmihwar.com/miqyas/", "X-Title": "Miqyas"})
        try:
            response = requests.post(cfg["base_url"] + "/chat/completions", json=body,
                                     headers=headers, timeout=timeout)
        except requests.RequestException as error:
            raise UserError(_("The AI service could not be reached: %s", error)) from None
        if response.status_code == 400 and json_mode:
            # Some free models refuse response_format; ask again without it.
            body.pop("response_format", None)
            response = requests.post(cfg["base_url"] + "/chat/completions", json=body,
                                     headers=headers, timeout=timeout)
        if response.status_code == 401:
            raise UserError(_("The AI service refused the key. Check it in Settings → AI."))
        if response.status_code == 429:
            raise UserError(_("The AI service's limit is reached for now (free models allow only so many requests). Try again in a minute."))
        if response.status_code >= 400:
            raise UserError(_("The AI service answered with an error (%(code)s): %(text)s",
                              code=response.status_code, text=response.text[:300]))
        try:
            return response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError):
            raise UserError(_("The AI service sent an answer that could not be read.")) from None

    @api.model
    def _json(self, text):
        """The first JSON object in a reply — models wrap it in prose or ``` fences."""
        text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise UserError(_("The AI did not return the invoice details. Try again, or another model."))
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            raise UserError(_("The AI did not return the invoice details. Try again, or another model.")) from None

    @api.model
    def action_test(self):
        reply = self._chat([{"role": "user", "content": "Reply with the single word: OK"}], timeout=60)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("AI connected"), "type": "success",
                           "message": _("The model answered: %s", reply.strip()[:80])}}
