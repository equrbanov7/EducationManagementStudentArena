"""Təsdiq NÖVBƏSİNİN sətir view-modeli və RİSK çipləri (dizayn təhvili §3.3).

Burada domen sorğusu YOXDUR — :mod:`apps.syllabus.services` hazır versiyaları
verir, bu modul isə onları şablonun birbaşa dövr edə biləcəyi dict-lərə çevirir.

Risk çipləri dizayndakı dörd açarın BİRBAŞA qarşılığıdır və hər biri REAL
sahədən hesablanır (uydurma göstərici yoxdur):

===========  ==========================================================
``late``     ``submitted_at``-dən bəri ≥ 10 gün keçib (SLA pozuntusu)
``miss``     ``completion_percent < 100`` — bölmə çatışmır
``diff``     versiya BÖYÜKDÜR (``major``) və dosyenin təsdiqlənmişi var
``policy``   sərbəst iş strukturu universitet siyasətində YOXDUR (məs. 3×5)
===========  ==========================================================

Heç biri yoxdursa «risk yoxdur» yaşıl çipi göstərilir — dizayndakı davranış.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import ChangeKind

from .labels import STATUS_TONES
from .rows import DETAIL_LABEL, detail_urls

_CTX = "accounts.syllabus"

_DASH = "—"

#: Gözləmə müddəti eşikləri (dizayn §3.3: 10 gündən çox → qırmızı).
LATE_DAYS = 10
WARN_DAYS = 5

RISK_LABELS = {
    "late": (pgettext_lazy(_CTX, "10 gündən çox gözləyir"), "danger"),
    "miss": (pgettext_lazy(_CTX, "çatışmayan bölmə var"), "warning"),
    "policy": (pgettext_lazy(_CTX, "siyasət yoxlaması"), "warning"),
    "diff": (pgettext_lazy(_CTX, "böyük dəyişiklik"), "primary"),
    "none": (pgettext_lazy(_CTX, "risk yoxdur"), "success"),
}

_TODAY = pgettext_lazy(_CTX, "bugün gəlib")
_WAITING = pgettext_lazy(_CTX, "%(days)s gündür gözləyir")
_ACTIVE_VERSION = pgettext_lazy(_CTX, "%(version)s aktivdir")
_UNKNOWN_PERSON = pgettext_lazy(_CTX, "Müəllif göstərilməyib")
_NO_PROGRAM = pgettext_lazy(_CTX, "Proqram təyin edilməyib")
_NO_CHAIR = pgettext_lazy(_CTX, "Kafedra təyin edilməyib")


def person(user) -> str:
    """İnsanın göstəriş adı — boş qalmır (audit sətri «—» ilə oxunmur)."""
    if user is None:
        return str(_UNKNOWN_PERSON)
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "") or str(_UNKNOWN_PERSON)


def waiting_days(version, *, now) -> int:
    moment = version.submitted_at
    if moment is None or now is None:
        return 0
    return max((now - moment).days, 0)


def wait_text(days: int) -> str:
    """«bugün gəlib» / «N gündür gözləyir» — cədvəl və panel üçün EYNİ mətn."""
    return str(_TODAY) if days == 0 else str(_WAITING) % {"days": days}


def wait_tone(days: int) -> str:
    if days >= LATE_DAYS:
        return "danger"
    if days >= WARN_DAYS:
        return "warning"
    return "muted"


def percent_tone(percent: int) -> str:
    """Dizayn: ≥90 % yaşıl, ≥70 % mavi, qalan sarı (növbə cədvəlinin eşikləri)."""
    if percent >= 90:
        return "success"
    if percent >= 70:
        return "primary"
    return "warning"


def risk_keys(version, *, days: int, policy_breach: bool) -> list:
    keys = []
    if days >= LATE_DAYS:
        keys.append("late")
    if (version.completion_percent or 0) < 100:
        keys.append("miss")
    if policy_breach:
        keys.append("policy")
    if version.change_kind == ChangeKind.MAJOR and version.syllabus.approved_version_id:
        keys.append("diff")
    return keys or ["none"]


def build_risks(version, *, days: int, policy_breach: bool) -> list:
    rows = []
    for key in risk_keys(version, days=days, policy_breach=policy_breach):
        label, tone = RISK_LABELS[key]
        rows.append({"key": key, "label": label, "tone": tone})
    return rows


def build_queue_row(version, *, now, policy_breach: bool = False) -> dict:
    """Bir təsdiq növbəsi sətri (dizayn §3.3 cədvəlinin 7 sütunu)."""
    syllabus = version.syllabus
    days = waiting_days(version, now=now)
    percent = version.completion_percent or 0
    approved = syllabus.approved_version
    urls = detail_urls(syllabus.pk)
    return {
        "version_id": str(version.pk),
        "syllabus_id": str(syllabus.pk),
        # «Baxışa keç» qərar panelini AÇIR (profil qabığında qalır); «Detallı
        # bax» isə sənədi AYRICA TABDA açır — ikisi fərqli səthlərdir.
        "detail_url": f"{urls['detail']}?version={version.pk}",
        "detail_label": DETAIL_LABEL,
        "code": syllabus.subject.code,
        "name": syllabus.subject.name,
        "program": syllabus.program.display_label if syllabus.program_id else str(_NO_PROGRAM),
        "teacher": person(syllabus.author or version.submitted_by),
        "chair": syllabus.chair_unit.name if syllabus.chair_unit_id else str(_NO_CHAIR),
        "sent": version.submitted_at,
        "wait_days": days,
        "wait_text": wait_text(days),
        "wait_tone": wait_tone(days),
        "percent": percent,
        "percent_tone": percent_tone(percent),
        "version_label": version.label,
        "active_version": (str(_ACTIVE_VERSION) % {"version": approved.label} if approved is not None else _DASH),
        "risks": build_risks(version, days=days, policy_breach=policy_breach),
        "status_key": version.status,
        "status_label": SyllabusStatus(version.status).label,
        "status_tone": STATUS_TONES.get(version.status, "neutral"),
    }


__all__ = [
    "LATE_DAYS",
    "RISK_LABELS",
    "WARN_DAYS",
    "build_queue_row",
    "build_risks",
    "percent_tone",
    "person",
    "risk_keys",
    "wait_text",
    "wait_tone",
    "waiting_days",
]
