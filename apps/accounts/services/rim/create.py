"""RİM «yeni hesab» — TƏK-TƏK hesab yaratma (tələbə / müəllim).

NİYƏ RİM-DƏ? Mərkəz hesabın bütün həyat dövrünü idarə edir (parol, blok,
soft-delete, bərpa, şəxsi məlumat) — YARATMAQ isə yeganə eksik həlqə idi:
tək bir müəllim və ya sonradan gələn bir tələbə üçün operator ya 1 sətirlik
Excel faylı düzəldirdi, ya da server aləti tələb edirdi.

İCAZƏ QAPISI — ``user.import``
------------------------------
Yeni kimlik yaratmaq toplu idxalla EYNİ səlahiyyətdir, ona görə EYNİ açardan
keçir (``intake.policy.PERM_IMPORT``). Ayrıca `user.create` açarı QƏSDƏN
YARADILMIR: iki açar olsaydı, bir universitet birini verib digərini unudardı və
«RİM-dən yarada bilirəm, fayldan yox» kimi izahsız fərq çıxardı.

Qapı İKİ şərtdən keçir (fail-closed):

1. RİM aktoru həll olunmalıdır (AKTİV təşkilat konteksti + AKTİV üzvlük) —
   bax `policy.resolve_actor`;
2. Aktorun ``user.import`` açarı olmalıdır — bax `intake.policy.can_import`
   (superadmin və təşkilat sahibi istisnadır).

⚠️ ``rim_staff`` (RİM ƏMƏKDAŞI, səviyyə 60) bu açarı DAŞIMIR və burada ona
səssiz güzəşt EDİLMİR — yeni kimlik yaratmaq mərkəzin RƏHBƏRİNİN
(`ikt_rehber`) və HR-in səlahiyyətidir (bax `default_roles_rim.py`).

PAROL: ``intake.create_account`` birdəfəlik parol qaytarır; o, YALNIZ bu
əməliyyatın cavabında görünür — nə DB-də, nə audit-də, nə log-da saxlanılır.
Hesab ``password_change_required=True`` ilə gəlir → ilk girişdə OTP + öz parolu.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils.translation import pgettext

from core.rate_limit import is_rate_limited, record_rate_limit_hit

from ..intake import create as intake_create
from ..intake.policy import PERM_IMPORT, can_import
from .create_form import build_draft
from .policy import RimAccessError, RimActor

logger = logging.getLogger(__name__)

_CTX = "profile.rim"

#: Yaratma səlahiyyətinin açarı — toplu idxalla EYNİ (yuxarıdakı izaha bax).
PERM_CREATE = PERM_IMPORT

#: Rate-limit: bir aktor saatda neçə hesab yarada bilər (tək-tək səth üçün).
#: Toplu idxal bundan KƏNARDIR — o, öz faylını bir əməliyyatda tətbiq edir.
DEFAULT_CREATE_RATE = "60/h"
RATE_LIMIT_SCOPE = "rim_create_account"

#: Audit qeydinin (opsional) yuxarı həddi.
MAX_NOTE_LENGTH = 300


class RimCreateError(RimAccessError):
    """Yaratma əməliyyatı sahə validasiyasından və ya ön şərtdən keçmədi.

    ``fields`` — ``{sahə adı: mesaj}``; UI onu sahələrin ALTINDA göstərir.

    ⚠️ Öz ``__init__``-i QƏSDƏN yoxdur (flake8-bugbear B042: istisna sinfi
    əlavə kwarg qəbul etməməlidir, əks halda `pickle`/`copy.copy()` bərpası
    sınır). Sahə xətaları konstruksiyadan SONRA `field_error()` köməkçisi ilə
    yazılır — sinif `args` müqaviləsini valideyndən olduğu kimi saxlayır.
    """

    #: Sinif səviyyəsində boş dəst — nüsxədə YALNIZ əvəz olunur, dəyişdirilmir.
    fields: dict = {}


def field_error(message: str, fields: dict, *, code: str = "validation_failed", status: int = 400):
    """Sahə xətaları daşıyan ``RimCreateError`` qurur (B042-yə uyğun yol)."""

    error = RimCreateError(code, message, status=status)
    error.fields = dict(fields or {})
    return error


def can_create(actor: RimActor) -> bool:
    """Aktor bu təşkilatda yeni hesab yarada bilərmi (fail-closed)."""

    if actor is None or getattr(actor, "user", None) is None:
        return False
    if getattr(actor, "organization", None) is None:
        return False
    return bool(actor.has(PERM_CREATE) and can_import(actor.user, actor.organization))


def require_create(actor: RimActor) -> None:
    """İcazə yoxdursa ``RimAccessError`` (403)."""

    if getattr(actor, "user", None) is None or getattr(actor, "organization", None) is None:
        raise RimAccessError(
            "no_organization_context",
            pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."),
        )
    if not can_create(actor):
        raise RimAccessError(
            "permission_denied",
            pgettext(_CTX, "Yeni hesab yaratmaq üçün icazəniz yoxdur."),
        )


def _check_rate_limit(actor: RimActor):
    rate = getattr(settings, "RIM_ACCOUNT_CREATE_RATE_LIMIT", DEFAULT_CREATE_RATE)
    key_parts = (getattr(actor.user, "pk", "anonymous"),)
    limited, _retry_after = is_rate_limited(RATE_LIMIT_SCOPE, rate, *key_parts)
    if limited:
        raise RimCreateError(
            "rate_limited",
            pgettext(_CTX, "Çox sayda hesab yaradıldı. Bir az sonra yenidən cəhd edin."),
            status=429,
        )
    return rate, key_parts


def _audit_reason(kind: str, note: str) -> str:
    return "RİM: yeni hesab yaradıldı (%s). Qeyd: %s" % (kind, str(note or "-")[:MAX_NOTE_LENGTH])


def create_account(actor: RimActor, *, kind: str, data: dict, request=None, note: str = "") -> dict:
    """Bir hesab yaradır və birdəfəlik parolu **bir dəfə** qaytarır.

    Returns:
        dict — ``user_id`` / ``username`` / ``password`` / ``full_name`` /
        ``email`` / ``kind`` / ``warnings``. Parolu çağıran YALNIZ cavabda
        göstərməli, heç yerdə saxlamamalıdır.

    Raises:
        RimAccessError — icazə qapısı; ``RimCreateError`` — sahə validasiyası,
        rate-limit və ya rol kataloqunun natamamlığı.
    """

    require_create(actor)
    kind = str(kind or "").strip()
    if kind not in intake_create.ACCOUNT_KINDS:
        raise field_error(
            pgettext(_CTX, "Naməlum hesab növü."),
            {"kind": pgettext(_CTX, "Naməlum hesab növü.")},
            code="account_kind_unknown",
        )

    rate, key_parts = _check_rate_limit(actor)
    organization = actor.organization

    draft = build_draft(organization, kind, data)
    if not draft.ok:
        raise field_error(pgettext(_CTX, "Formda düzəliş tələb olunan sahələr var."), draft.errors)

    try:
        role = intake_create.account_role(organization, kind)
    except intake_create.IntakeApplyError as exc:
        # Rol kataloqu natamamdır — bu, sahə xətası deyil, KONFİQURASİYA xətasıdır.
        raise RimCreateError(exc.code, exc.message, status=409) from exc

    with transaction.atomic():
        user, password = intake_create.create_account(
            organization=organization,
            kind=kind,
            values=draft.values,
            role=role,
            actor=actor.user,
            request=request,
            student_targets=draft.targets or None,
            group_name=draft.group_name,
            specialization=draft.specialization,
            scope_unit=draft.scope_unit,
            audit_reason=_audit_reason(kind, note),
        )

    record_rate_limit_hit(RATE_LIMIT_SCOPE, rate, *key_parts)
    logger.info(
        "RİM: account created by actor=%s kind=%s target=%s",
        getattr(actor.user, "pk", None),
        kind,
        user.pk,
    )
    return {
        "user_id": user.pk,
        "username": user.username,
        # DİQQƏT: parol YALNIZ burada qayıdır — saxlanılmır.
        "password": password,
        "full_name": (user.get_full_name() or user.username).strip(),
        "email": user.email,
        "kind": kind,
        "group": draft.group_name,
        "warnings": list(draft.warnings),
    }


__all__ = [
    "DEFAULT_CREATE_RATE",
    "MAX_NOTE_LENGTH",
    "PERM_CREATE",
    "RATE_LIMIT_SCOPE",
    "RimCreateError",
    "can_create",
    "create_account",
    "field_error",
    "require_create",
]
