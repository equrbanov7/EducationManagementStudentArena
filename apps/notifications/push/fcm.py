"""Firebase Cloud Messaging HTTP v1 müştərisi (əlavə asılılıq YOXDUR — ``requests`` + ``cryptography``).

Axın: service account açarı ilə RS256 imzalı JWT → ``oauth2.googleapis.com/token`` → 1 saatlıq access token
(Django keşində, 5 dəq ehtiyatla) → ``POST fcm.googleapis.com/v1/projects/<id>/messages:send``.

Cavabın təsnifatı (:class:`SendResult.outcome`):

* ``ok`` — çatdırıldı;
* ``unregistered`` — token artıq yoxdur (tətbiq silinib / token yenilənib; HTTP 404 və ya ``UNREGISTERED``)
  → cihaz DEAKTİV edilir;
* ``invalid`` — token formatı yararsızdır (400 ``INVALID_ARGUMENT`` + «registration token») → deaktiv;
* ``sender_mismatch`` — token başqa Firebase layihəsinindir (403 ``SENDER_ID_MISMATCH``) → deaktiv;
* ``auth`` — access token rədd edildi (401) — bir dəfə yeni token alınıb təkrarlanır;
* ``retry`` — müvəqqəti (429 / 5xx / şəbəkə) — cihaz aktiv qalır;
* ``error`` — digər (payload xətası və s.) — cihaz aktiv qalır, loqa yazılır.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass

from django.core.cache import cache

import requests

from .config import Credentials

logger = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
_TOKEN_CACHE_KEY = "emsarena:notifications:fcm_access_token:v1:{email}"
_TOKEN_LIFETIME = 3600
_TOKEN_SAFETY = 300
_TIMEOUT = (5, 10)  # (qoşulma, oxu) saniyə — Celery işi asılı qalmasın

DEACTIVATING = frozenset({"unregistered", "invalid", "sender_mismatch"})


@dataclass(frozen=True)
class SendResult:
    outcome: str
    status: int = 0
    detail: str = ""


class AuthError(Exception):
    """Access token alınmadı (açar yararsızdır / Google rədd etdi) — bütün partiya dayanır."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _signed_assertion(creds: Credentials, now: int) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": creds.client_email,
        "scope": SCOPE,
        "aud": creds.token_uri,
        "iat": now,
        "exp": now + _TOKEN_LIFETIME,
    }
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    key = serialization.load_pem_private_key(creds.private_key.encode("utf-8"), password=None)
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def access_token(creds: Credentials, *, session=None, force_refresh: bool = False) -> str:
    """Keşlənmiş OAuth access token; yoxdursa / ``force_refresh`` → yenisi alınır. Alınmasa :class:`AuthError`."""
    cache_key = _TOKEN_CACHE_KEY.format(email=creds.client_email)
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached:
            return cached
    http = session or requests
    try:
        assertion = _signed_assertion(creds, int(time.time()))
        response = http.post(
            creds.token_uri,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            timeout=_TIMEOUT,
        )
    except (ValueError, TypeError) as exc:  # PEM açar yararsızdır
        raise AuthError(f"service account açarı oxunmadı: {type(exc).__name__}") from exc
    except requests.RequestException as exc:
        raise AuthError(f"token sorğusu alınmadı: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise AuthError(f"token sorğusu rədd edildi: HTTP {response.status_code}")
    try:
        payload = response.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in") or _TOKEN_LIFETIME)
    except (ValueError, KeyError, TypeError) as exc:
        raise AuthError("token cavabı gözlənilməz formadadır") from exc
    cache.set(cache_key, token, max(60, expires_in - _TOKEN_SAFETY))
    return token


def _error_code(body) -> tuple[str, str]:
    """``(FCM errorCode və ya status, message)`` — cavab gövdəsindən."""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return "", ""
    code = ""
    for detail in error.get("details") or []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            code = str(detail["errorCode"])
            break
    return code or str(error.get("status") or ""), str(error.get("message") or "")[:300]


def classify(status: int, body) -> SendResult:
    if status == 200:
        return SendResult("ok", status)
    code, message = _error_code(body)
    if status == 404 or code == "UNREGISTERED":
        return SendResult("unregistered", status, code)
    if code == "SENDER_ID_MISMATCH":
        return SendResult("sender_mismatch", status, code)
    if status == 400 and code == "INVALID_ARGUMENT" and "registration token" in message.lower():
        return SendResult("invalid", status, code)
    if status == 401:
        return SendResult("auth", status, code)
    if status == 429 or status >= 500 or code in {"UNAVAILABLE", "INTERNAL", "QUOTA_EXCEEDED"}:
        return SendResult("retry", status, code)
    return SendResult("error", status, f"{code}: {message}" if code else message)


class FCMClient:
    """Bir partiya üçün müştəri: bir HTTP sessiyası (keep-alive) + bir access token."""

    def __init__(self, creds: Credentials, *, session=None):
        self.creds = creds
        self.session = session or requests.Session()
        self.url = SEND_URL.format(project=creds.project_id)
        self._token = None

    def _headers(self) -> dict:
        if self._token is None:
            self._token = access_token(self.creds, session=self.session)
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json; charset=UTF-8"}

    def _post(self, message: dict) -> SendResult:
        try:
            response = self.session.post(self.url, json={"message": message}, headers=self._headers(), timeout=_TIMEOUT)
        except requests.RequestException as exc:
            return SendResult("retry", 0, type(exc).__name__)
        try:
            body = response.json()
        except ValueError:
            body = {}
        return classify(response.status_code, body)

    def send(self, message: dict) -> SendResult:
        result = self._post(message)
        if result.outcome == "auth":
            # Keşdəki token vaxtından əvvəl ləğv olunub (açar dəyişib) — bir dəfə yenisi.
            self._token = access_token(self.creds, session=self.session, force_refresh=True)
            result = self._post(message)
        return result

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["DEACTIVATING", "AuthError", "FCMClient", "SendResult", "access_token", "classify"]
