"""Möhür buraxılışı və ləğvi — ``DocumentSeal``-ın YEGANƏ yazıçısı.

Buraxılış (``issue_sealed_document``)
------------------------------------
Sənədi quran modul (məs. registrar transkripti) faktları və ``render(mark) -> bytes`` funksiyasını verir;
servis:

1. publik ``payload``-ın kanonik JSON həşini hesablayır;
2. **təkrar istifadə**: eyni təşkilat + növ + sahib + dil + ``payload`` həşi ilə BU GÜN verilmiş, ləğv
   edilməmiş möhür varsa, sənəd həmin möhürün kodu və verilmə anı ilə yenidən qurulur — baytlar
   saxlanmış ``file_sha256`` ilə üst-üstə düşürsə eyni möhür qaytarılır (gündə bir tələbəyə onlarla
   yükləmə = bir sətir). Baytlar fərqlidirsə (məzmun və ya şablon dəyişib) YENİ möhür verilir;
3. yeni möhür: 80 bitlik kod → ``render`` → faylın DƏQİQ baytlarının həşi → sətir (append-only).

Renderer DETERMİNİSTİK olmalıdır (eyni ``mark`` → eyni baytlar): transkriptdə ``no_new_id=True`` və sabit
verilmə anı bunu təmin edir.

Ləğv (``revoke_seal``)
----------------------
Birdəfəlik, səbəb məcburi (≥ ``MIN_REVOKE_REASON``). Şərti UPDATE (``revoked_at IS NULL``) paralel iki
klikdən yalnız birini keçirir; DB trigger-i qalan sütunların dəyişməzliyini ayrıca yoxlayır.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language, pgettext

from . import codes
from .models import DocumentSeal

logger = logging.getLogger("verification")

#: Ləğv səbəbinin minimum uzunluğu (layihənin «səbəb dialoqu» qaydası; DB trigger-i ≥ 10 tələb edir).
MIN_REVOKE_REASON = 20
MAX_REVOKE_REASON = 1000
AUDIT_SEAL = "verification.seal"


class SealError(ValueError):
    """Ləğv qaydası pozuntusu — ``code`` maşın açarı, ``str(exc)`` istifadəçi mətni."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return str(self.message)


@dataclass(frozen=True)
class SealMark:
    """Sənədin üzərinə çap olunan rekvizitlər: kod, tam yoxlama URL-i, qısa ünvan, verilmə anı."""

    code: str
    url: str
    short_url: str
    issued_at: dt.datetime


def verification_base_url() -> str:
    """Çap olunan URL-in kökü — ``DOCUMENT_VERIFY_BASE_URL`` (prod: publik domen), yoxdursa ``SITE_URL``."""
    base = getattr(settings, "DOCUMENT_VERIFY_BASE_URL", "") or getattr(settings, "SITE_URL", "") or ""
    return str(base).strip().rstrip("/")


def verification_url(code: str) -> str:
    return f"{verification_base_url()}{reverse('verification:detail', args=[code])}"


def _short_url() -> str:
    base = verification_base_url().split("://", 1)[-1]
    return f"{base}{reverse('verification:home')}".rstrip("/")


def mark_for(code: str, issued_at) -> SealMark:
    return SealMark(code=code, url=verification_url(code), short_url=_short_url(), issued_at=issued_at)


def mask_holder_name(user) -> str:
    """«Elvin Qurbanov» → «Elvin Q.» — publik səhifədə sahibin adı YALNIZ belə görünür."""
    first = " ".join(str(getattr(user, "first_name", "") or "").split())
    last = " ".join(str(getattr(user, "last_name", "") or "").split())
    if first and last:
        return f"{first} {last[0]}."
    if first or last:
        return first or f"{last[0]}."
    username = str(getattr(user, "username", "") or "")
    return f"{username[:2]}***" if username else "—"


def canonical_json(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _start_of_today():
    today = timezone.localdate()
    return timezone.make_aware(dt.datetime.combine(today, dt.time.min))


def _reusable(*, organization, doc_type, subject_user, language, payload_hash):
    return (
        DocumentSeal.objects.filter(
            organization=organization,
            doc_type=doc_type,
            subject_user=subject_user,
            language=language,
            payload_sha256=payload_hash,
            revoked_at__isnull=True,
            issued_at__gte=_start_of_today(),
        )
        .exclude(file_sha256="")
        .order_by("-issued_at")
        .first()
    )


def _audit(action, *, seal, user, request, reason, new_values=None, old_values=None):
    """Best-effort audit (SAVEPOINT): xəta sorğu tranzaksiyasını zəhərləmir, sənəd buraxılışını dayandırmır."""
    from core.audit import log_action

    try:
        with transaction.atomic():
            log_action(
                action,
                user=user if getattr(user, "pk", None) else None,
                organization=seal.organization,
                request=request,
                resource_type=AUDIT_SEAL,
                resource_id=seal.code,
                resource_repr=f"{seal.title} — {seal.code}"[:200],
                reason=reason,
                new_values=new_values,
                old_values=old_values,
            )
    except Exception:  # noqa: BLE001 — audit heç vaxt əsas əməli sındırmasın
        logger.exception("verification: audit yazılmadı (%s)", seal.code)


def issue_sealed_document(
    *, organization, doc_type, subject_user, title, payload, issued_by, render, scope_path="", request=None
):
    """Möhürlənmiş sənəd → ``(bytes, DocumentSeal)``. Çağıran əvvəlcə SƏLAHİYYƏTİ yoxlamalıdır."""
    from core.constants import AuditAction

    language = (get_language() or "")[:8]
    payload = dict(payload or {})
    payload_hash = sha256_hex(canonical_json(payload))

    candidate = _reusable(
        organization=organization,
        doc_type=doc_type,
        subject_user=subject_user,
        language=language,
        payload_hash=payload_hash,
    )
    if candidate is not None:
        data = render(mark_for(candidate.code, timezone.localtime(candidate.issued_at)))
        if sha256_hex(data) == candidate.file_sha256:
            return data, candidate

    issued_at = timezone.now()
    code = codes.generate(getattr(organization, "slug", ""))
    data = render(mark_for(code, timezone.localtime(issued_at)))
    seal = DocumentSeal(
        organization=organization,
        code=code,
        doc_type=doc_type,
        subject_user=subject_user,
        title=str(title)[:200],
        issued_at=issued_at,
        issued_by=issued_by if getattr(issued_by, "pk", None) else None,
        scope_path=str(scope_path or "")[:1000],
        language=language,
        payload=payload,
        payload_sha256=payload_hash,
        file_sha256=sha256_hex(data),
    )
    with transaction.atomic():
        seal.save(force_insert=True)
    _audit(
        AuditAction.CREATE,
        seal=seal,
        user=issued_by,
        request=request,
        reason=pgettext("verification.audit", "Rəsmi sənəd möhürləndi (QR yoxlama kodu verildi)."),
        new_values={"doc_type": doc_type, "code": code, "file_sha256": seal.file_sha256},
    )
    return data, seal


def revoke_seal(*, seal, actor, reason, request=None) -> DocumentSeal:
    """Möhürü ləğv edir (birdəfəlik). Səlahiyyət/əhatə çağıranda YOXLANILIB."""
    from core.constants import AuditAction

    text = " ".join(str(reason or "").split())
    if len(text) < MIN_REVOKE_REASON:
        raise SealError(
            "reason_short",
            pgettext("verification.staff", "Səbəb ən azı %(n)s simvol olmalıdır.") % {"n": MIN_REVOKE_REASON},
        )
    text = text[:MAX_REVOKE_REASON]
    if seal.revoked_at is not None:
        raise SealError("already_revoked", pgettext("verification.staff", "Bu sənəd artıq ləğv edilib."))
    now = timezone.now()
    updated = DocumentSeal.objects.filter(pk=seal.pk, revoked_at__isnull=True).update(
        revoked_at=now, revoked_by=actor if getattr(actor, "pk", None) else None, revoke_reason=text
    )
    if not updated:
        raise SealError("already_revoked", pgettext("verification.staff", "Bu sənəd artıq ləğv edilib."))
    seal.revoked_at, seal.revoked_by, seal.revoke_reason = now, actor, text
    _audit(
        AuditAction.UPDATE,
        seal=seal,
        user=actor,
        request=request,
        reason=text,
        old_values={"status": "valid"},
        new_values={"status": "revoked", "revoked_at": now.isoformat()},
    )
    return seal


__all__ = [
    "MIN_REVOKE_REASON",
    "SealError",
    "SealMark",
    "canonical_json",
    "issue_sealed_document",
    "mark_for",
    "mask_holder_name",
    "revoke_seal",
    "sha256_hex",
    "verification_url",
]
