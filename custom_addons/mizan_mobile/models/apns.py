# -*- coding: utf-8 -*-
"""Apple's push service, spoken directly.

APNs takes HTTP/2 only, with a short-lived token signed by the developer
account's .p8 key (ES256). The signing is done here with `cryptography`,
which Odoo already carries; HTTP/2 needs `httpx[http2]`, installed in the
image. Without it the server logs once and carries on: a missing notification
must never fail the action that caused it.
"""
import base64
import json
import logging
import threading
import time

_logger = logging.getLogger(__name__)

HOSTS = {"production": "https://api.push.apple.com",
         "sandbox": "https://api.sandbox.push.apple.com"}
DEAD = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}

_cache = {}
_lock = threading.Lock()


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def provider_token(team_id, key_id, p8):
    """A token is good for an hour; Apple refuses one refreshed too often, so
    it is kept for fifty minutes per key."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    with _lock:
        cached = _cache.get(key_id)
        if cached and cached[1] > time.time():
            return cached[0]
        header = _b64(json.dumps({"alg": "ES256", "kid": key_id}).encode())
        claims = _b64(json.dumps({"iss": team_id, "iat": int(time.time())}).encode())
        signing_input = ("%s.%s" % (header, claims)).encode()
        key = serialization.load_pem_private_key(p8.strip().encode(), password=None)
        r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
        signature = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        token = "%s.%s" % (signing_input.decode(), signature)
        _cache[key_id] = (token, time.time() + 50 * 60)
        return token


def send(config, tokens, title, body, url):
    """Send one notification to several devices. Returns the tokens Apple
    says are gone, so the caller can forget them."""
    try:
        import httpx
    except ImportError:
        _logger.warning("iPhone notifications skipped: httpx[http2] is not installed")
        return []
    jwt = provider_token(config["team_id"], config["key_id"], config["key"])
    payload = json.dumps({
        "aps": {"alert": {"title": title[:120], "body": body[:600]},
                "sound": "default", "badge": 1},
        "url": url,
    }).encode()
    dead = []
    host = HOSTS.get(config.get("environment") or "production", HOSTS["production"])
    with httpx.Client(http2=True, timeout=8.0) as client:
        for token in tokens:
            try:
                response = client.post(
                    "%s/3/device/%s" % (host, token), content=payload,
                    headers={"authorization": "bearer " + jwt,
                             "apns-topic": config["bundle_id"],
                             "apns-push-type": "alert", "apns-priority": "10"})
            except Exception as error:  # network: try again next message
                _logger.warning("APNs unreachable: %s", error)
                break
            if response.status_code == 200:
                continue
            reason = ""
            try:
                reason = response.json().get("reason", "")
            except ValueError:
                pass
            if response.status_code == 410 or reason in DEAD:
                dead.append(token)
            else:
                _logger.warning("APNs refused a notification: %s %s",
                                response.status_code, reason)
    return dead
