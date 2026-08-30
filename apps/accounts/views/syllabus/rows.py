"""Siyahı ekranının SƏTİR və KPI view-modelləri (dizayn təhvili §3.1).

Burada yalnız GÖSTƏRİŞ məntiqi var: domen sorğuları
:mod:`apps.syllabus.services`-dədir, mətnlər :mod:`.labels`-dədir. Bu fayl
ikisini birləşdirib şablonun birbaşa dövr edə biləcəyi sadə dict-lər qaytarır
(şablonda `{% if %}` zənciri qalmasın deyə).

⚠️ «Sillabussuz fənn» sətirləri: müəllimin açılışı (``CourseOffering``) var,
sillabusu YOXDUR. Onlar dizaynda ayrıca sətir kimi görünür (`v —`, 0 %,
«Sillabus yarat») və «Sillabussuz fənn» KPI-nin mənbəyidir. Bu sətirlərin `id`-si
sillabusun deyil, AÇILIŞIN id-sidir — ona görə `kind` sahəsi ilə ayrılır.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import STATUS_NEXT_STEP, SyllabusStatus

from .labels import NEXT_STEP_TONES, STATUS_TONES

_CTX = "accounts.syllabus"

_DASH = "—"

_NOT_CREATED = pgettext_lazy(_CTX, "yaradılmayıb")
_QUEUED = pgettext_lazy(_CTX, "Növbədə")
_REVIEWING = pgettext_lazy(_CTX, "Baxır: %(who)s")
_REVISION_BY = pgettext_lazy(_CTX, "Düzəliş: %(who)s")
_REJECTED_BY = pgettext_lazy(_CTX, "Rədd: %(who)s")
_WAITING_DAYS = pgettext_lazy(_CTX, "%(days)s gündür gözləyir")
_ACTIVE_VERSION = pgettext_lazy(_CTX, "%(version)s aktivdir")
_MIGRATED_APPROVER = pgettext_lazy(_CTX, "Sistem / köçürmə")

#: Əməl açarı → (etiket, düymə növü). JS açara görə davranır (`data-action`).
ACTION_LABELS = {
    "create": (pgettext_lazy(_CTX, "Sillabus yarat"), "primary"),
    "resume": (pgettext_lazy(_CTX, "Davam et"), "primary"),
    "fix": (pgettext_lazy(_CTX, "Düzəlişə davam et"), "primary"),
    "copy": (pgettext_lazy(_CTX, "Keçən ildən köçür"), "secondary"),
    "new_version": (pgettext_lazy(_CTX, "Yeni versiya yarat"), "primary"),
    "view": (pgettext_lazy(_CTX, "Bax"), "secondary"),
    "notes": (pgettext_lazy(_CTX, "Qeydlərə bax"), "secondary"),
    "reason": (pgettext_lazy(_CTX, "Səbəbə bax"), "secondary"),
    "submitted_view": (pgettext_lazy(_CTX, "Göndərilmiş variantı gör"), "secondary"),
    "withdraw": (pgettext_lazy(_CTX, "Geri çağır"), "secondary"),
    "pdf": (pgettext_lazy(_CTX, "PDF yüklə"), "secondary"),
    "history": (pgettext_lazy(_CTX, "Versiya tarixçəsi"), "secondary"),
}

#: Statusa görə əməl dəsti. ⚠️ TƏSDİQLƏNMİŞ sillabusda «redaktə» YOXDUR —
#: dizayn qaydası: yalnız bax / PDF / tarixçə / yeni versiya.
ACTIONS_BY_STATUS = {
    SyllabusStatus.DRAFT.value: ("resume", "copy"),
    SyllabusStatus.REVISION.value: ("notes", "fix"),
    SyllabusStatus.SUBMITTED.value: ("submitted_view", "withdraw"),
    SyllabusStatus.REVIEW.value: ("submitted_view", "withdraw"),
    SyllabusStatus.APPROVED.value: ("view", "pdf", "history", "new_version"),
    SyllabusStatus.REJECTED.value: ("reason", "new_version"),
    SyllabusStatus.ARCHIVED.value: ("view", "pdf"),
}


def _person(user) -> str:
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "") or ""


def _days_since(moment, now) -> int:
    if moment is None or now is None:
        return 0
    return max((now - moment).days, 0)


def percent_tone(percent: int) -> str:
    """Tamamlanma zolağının tonu (dizayn: 100 % yaşıl, ≥50 % mavi, qalan sarı)."""
    if percent >= 100:
        return "success"
    if percent >= 50:
        return "primary"
    return "warning"


def approver_text(syllabus, version, *, now=None) -> str:
    """«Status və təsdiqləyən» sütununun ikinci sətri."""
    if version is None:
        return _DASH
    status = version.status
    if status == SyllabusStatus.APPROVED.value:
        who = _person(version.approved_by) or str(_MIGRATED_APPROVER)
        return f"{who}, {version.approved_at:%d.%m.%Y}" if version.approved_at else who
    if status == SyllabusStatus.ARCHIVED.value:
        who = _person(version.approved_by) or str(_MIGRATED_APPROVER)
        return who or _DASH
    if status == SyllabusStatus.REVISION.value:
        return str(_REVISION_BY) % {"who": _person(version.reviewer) or _DASH}
    if status == SyllabusStatus.REJECTED.value:
        return str(_REJECTED_BY) % {"who": _person(version.reviewer) or _DASH}
    if status == SyllabusStatus.REVIEW.value:
        waited = str(_WAITING_DAYS) % {"days": _days_since(version.submitted_at, now)}
        return f"{str(_REVIEWING) % {'who': _person(version.reviewer) or _DASH}} · {waited}"
    if status == SyllabusStatus.SUBMITTED.value:
        return f"{_QUEUED} · {str(_WAITING_DAYS) % {'days': _days_since(version.submitted_at, now)}}"
    approved = getattr(syllabus, "approved_version", None)
    if approved is not None:
        return str(_ACTIVE_VERSION) % {"version": approved.label}
    return _DASH


def _actions(keys):
    rows = []
    for key in keys:
        label, kind = ACTION_LABELS[key]
        rows.append({"key": key, "label": label, "kind": kind})
    return rows


#: Sətirdən AYRICA TAM SƏHİFƏYƏ («Detallı bax», `target="_blank"`) keçid.
DETAIL_LABEL = pgettext_lazy(_CTX, "Detallı bax")


def detail_urls(syllabus_id) -> dict:
    """``{"detail", "pdf"}`` — sənəd səhifəsi və onun PDF nüsxəsi.

    Sətir view-modelində saxlanılır ki, şablonda hər dövr üçün ``{% url %}``
    çağırışı olmasın və eyni keçid həm cədvəldə, həm kartda, həm də təsdiq
    növbəsində EYNİ yerdən gəlsin.
    """
    kwargs = {"syllabus_id": str(syllabus_id)}
    return {
        "detail": reverse("accounts:syllabus_detail", kwargs=kwargs),
        "pdf": reverse("accounts:syllabus_detail_pdf", kwargs=kwargs),
    }


def _period_labels(period):
    if period is None:
        return "", ""
    return period.year_display, period.name


def build_row(syllabus, *, now=None, can_copy: bool = False) -> dict:
    """Mövcud sillabus dosyesindən cədvəl sətri."""
    version = syllabus.current_version
    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    percent = version.completion_percent if version is not None else 0
    year, semester = _period_labels(syllabus.period)
    keys = list(ACTIONS_BY_STATUS.get(status, ()))
    if status == SyllabusStatus.DRAFT.value and not can_copy:
        keys = [key for key in keys if key != "copy"]
    urls = detail_urls(syllabus.pk)
    return {
        "kind": "syllabus",
        "id": str(syllabus.pk),
        "detail_url": urls["detail"],
        "pdf_url": urls["pdf"],
        "detail_label": DETAIL_LABEL,
        "version_id": str(version.pk) if version is not None else "",
        "code": syllabus.subject.code,
        "name": syllabus.subject.name,
        "program": syllabus.program.name if syllabus.program_id else "",
        "year": year,
        "semester": semester,
        "version_label": version.label if version is not None else _DASH,
        "percent": percent,
        "percent_tone": percent_tone(percent),
        "status_key": status,
        "status_label": SyllabusStatus(status).label,
        "status_tone": STATUS_TONES.get(status, "neutral"),
        "approver": approver_text(syllabus, version, now=now),
        "next_step": STATUS_NEXT_STEP.get(status, ""),
        "next_tone": NEXT_STEP_TONES.get(status, "default"),
        "touched": version.updated_at if version is not None else syllabus.updated_at,
        "actions": _actions(keys),
    }


def build_missing_row(offering, *, can_copy: bool = False) -> dict:
    """Sillabusu OLMAYAN açılış — «Sillabus yarat» sətri (0 %, versiya yoxdur)."""
    year, semester = _period_labels(offering.period)
    keys = ["create"] + (["copy"] if can_copy else [])
    return {
        "kind": "missing",
        "id": str(offering.pk),
        # Sillabus dosyesi hələ yoxdur → detal səhifəsi də yoxdur (link gizlənir).
        "detail_url": "",
        "pdf_url": "",
        "detail_label": DETAIL_LABEL,
        "version_id": "",
        "code": offering.subject.code,
        "name": offering.subject.name,
        "program": "",
        "year": year,
        "semester": semester,
        "version_label": _DASH,
        "percent": 0,
        "percent_tone": "warning",
        "status_key": "missing",
        "status_label": pgettext_lazy(_CTX, "Sillabus yoxdur"),
        "status_tone": "danger",
        "approver": _DASH,
        "next_step": pgettext_lazy(_CTX, "Semestr başlayana qədər sillabus yaradılmalıdır"),
        "next_tone": "warning",
        "touched": None,
        "touched_text": _NOT_CREATED,
        "actions": _actions(keys),
    }


__all__ = [
    "ACTIONS_BY_STATUS",
    "ACTION_LABELS",
    "DETAIL_LABEL",
    "detail_urls",
    "approver_text",
    "build_missing_row",
    "build_row",
    "percent_tone",
]
