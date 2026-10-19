# -*- coding: utf-8 -*-
"""Firebase Cloud Messaging (HTTP v1), for the Android app.

Google takes a short-lived OAuth token signed with the Firebase project's
service-account key (RS256). The key is uploaded once in Settings; it is
kept server-side and never shown again. Like APNs, a failure is logged and
never fails the action that caused the notification."""
import base64
import json
import logging
import threading
import time

import requests

_logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
DEAD = {"UNREGISTERED", "INVALID_ARGUMENT"}

_cache = {}
_lock = threading.Lock()


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def access_token(account):
    """Exchange a signed JWT for an access token, kept for 50 minutes."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    email = account["client_email"]
    with _lock:
        cached = _cache.get(email)
        if cached and cached[1] > time.time():
            return cached[0]
        now = int(time.time())
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": email, "scope": SCOPE, "aud": TOKEN_URL,
                                  "iat": now, "exp": now + 3600}).encode())
        signing_input = ("%s.%s" % (header, claims)).encode()
        key = serialization.load_pem_private_key(account["private_key"].encode(), password=None)
        signature = _b64(key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256()))
        response = requests.post(TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": "%s.%s" % (signing_input.decode(), signature)}, timeout=20)
        response.raise_for_status()
        token = response.json()["access_token"]
        _cache[email] = (token, time.time() + 50 * 60)
        return token


def send(account, tokens, title, body, data=None):
    """Send to each device; return the tokens Google says are gone."""
    dead = []
    try:
        auth = access_token(account)
    except Exception:  # noqa: BLE001 - logged, never raised
        _logger.exception("Firebase: could not get an access token")
        return dead
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % account["project_id"]
    for token in tokens:
        message = {"message": {
            "token": token,
            "notification": {"title": title[:120], "body": body[:400]},
            "data": {k: str(v) for k, v in (data or {}).items()},
            "android": {"priority": "high", "notification": {"channel_id": "miqyas", "sound": "default"}},
        }}
        try:
            r = requests.post(url, json=message, headers={"Authorization": "Bearer %s" % auth}, timeout=20)
            if r.status_code in (400, 404):
                status = (r.json().get("error", {}).get("details") or [{}])[0].get("errorCode") \
                    or r.json().get("error", {}).get("status")
                if status in DEAD:
                    dead.append(token)
            elif r.status_code >= 300:
                _logger.warning("Firebase: %s %s", r.status_code, r.text[:200])
        except Exception:  # noqa: BLE001
            _logger.exception("Firebase: send failed")
    return dead
