"""Jurnalın «Dəyişiklik tarixçəsi» paneli — JSON səhifələri (UNEC müqayisəsi P1-3, 2026-09-25).

``grade_audit`` hər saxlamanı BİR aqreqat ``AuditLog`` sətri kimi yazır
(``resource_type = registrar.grade.<kind>``, ``resource_id`` = açılış). Əvvəl
``journal_detail`` son 20 qeydi hər grid/yekun açılışında hesablayırdı, amma heç
bir şablon onu göstərmirdi — boşuna sorğu idi. İndi panel
(``_jd_history_drawer.html`` + ``journal_history.js``) AÇILANDA bu endpoint-dən
20-lik səhifələrlə oxuyur: kim, nə vaxt, nə (dərs tarixi / element), köhnə → yeni.

Süzgəclər:

* ``?date=YYYY-MM-DD`` — SERVERDƏ: yalnız həmin dərs tarixinə toxunan qeydlər
  (tarix audit sətrinin mətnindədir — ``"2026-09-25 · Seminar"``). Beləcə köhnə
  dərsin tarixçəsi də «daha çox» basmadan tam gəlir.
* tələbə adı və qeyd növü — MÜŞTƏRİ TƏRƏFİNDƏ (yüklənmiş qeydlər üzərində,
  diakritikaya dözümlü axtarış — ``ə/e``, ``ı/i`` fərqi axtarışı pozmur).

Giriş qapısı jurnal SƏHİFƏSİ ilə eynidir (redaktor / korrektor / siyahı idarəçisi /
yalnız-oxu müşahidəçi); TƏLƏBƏ heç vaxt görmür (404). Sorğu sayı səhifədəki
qeyd sayından ASILI DEYİL: açılış + icazə + bir səhifə sorğusu (+ ilk səhifədə
ümumi say və dərs tarixləri, + ``enrollment:<id>`` etiketləri üçün bir həll sorğusu).
"""

from __future__ import annotations

import datetime as _dt
import re

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_GET

from core.http_ids import parse_uuid

from .journal_access import can_edit_journal, can_observe_journal, offering_or_404

_CTX = "registrar.journal_history"

#: Bir səhifədəki qeyd (saxlama əməliyyatı) sayı — brif: «> 20 olsa daha çox».
PAGE_SIZE = 20
MAX_PAGE = 50
#: Bir qeydin daşıdığı sətir tavanı — 555 nəfərlik mühazirənin toplu saxlaması
#: tək qeyddə 555 sətirdir; panelə hamısı lazım deyil (``rows_total`` tam sayı verir).
ROW_CAP = 300

#: ``grade_audit`` resource_type prefiksi (``_RESOURCE_PREFIX`` ilə eyni).
_PREFIX = "registrar.grade"

_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

#: Audit «kind» → UI qrupu (müştəri tərəfindəki növ çipləri bununla süzür).
_GROUPS = {"mark": "mark", "component": "component", "final": "final", "resit": "final"}

_KIND_LABELS = {
    "mark": pgettext_lazy(_CTX, "Davamiyyət / bal"),
    "component": pgettext_lazy(_CTX, "Komponent balı"),
    "final": pgettext_lazy(_CTX, "Yekun imtahan"),
    "resit": pgettext_lazy(_CTX, "Təkrar imtahan"),
    "correction": pgettext_lazy(_CTX, "Sənədli düzəliş — bal / davamiyyət"),
    "lesson-correction": pgettext_lazy(_CTX, "Sənədli düzəliş — dərs"),
    "lesson-deletion": pgettext_lazy(_CTX, "Sənədli düzəliş — dərs silindi"),
    "selfwork-correction": pgettext_lazy(_CTX, "Sənədli düzəliş — sərbəst iş"),
    "coursework-correction": pgettext_lazy(_CTX, "Sənədli düzəliş — kurs işi"),
    "component-correction": pgettext_lazy(_CTX, "Sənədli düzəliş — komponent"),
}
_REVERT_LABEL = pgettext_lazy(_CTX, "Düzəlişin geri alınması")


def kind_group(kind: str) -> str:
    """``mark`` / ``component`` / ``final`` / ``correction`` (qalan hamısı sənədli axındır)."""
    return _GROUPS.get(kind, "correction")


def kind_label(kind: str) -> str:
    if kind in _KIND_LABELS:
        return str(_KIND_LABELS[kind])
    if kind.endswith("-revert"):
        return str(_REVERT_LABEL)
    return kind


def _offering_for_history(request, offering_id):
    """Jurnal səhifəsi ilə EYNİ qapı + tələbə ailəsi üçün açıq qadağa (brif: «tələbə görmür»)."""
    offering = offering_or_404(request, offering_id)
    from . import corrections as corrections_service
    from . import guest_roster, page_contexts

    if page_contexts.is_student_family_user(offering.organization, request.user):
        raise Http404
    allowed = (
        can_edit_journal(request.user, offering)
        or corrections_service.can_correct_journal(request)
        or guest_roster.can_manage_offering_roster(request.user, offering)
        or can_observe_journal(request.user, offering)
    )
    if not allowed:
        raise Http404
    return offering


def _bounds(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", PAGE_SIZE))
    except (TypeError, ValueError):
        limit = PAGE_SIZE
    return offset, max(1, min(limit, MAX_PAGE))


def parse_filter_date(raw):
    """``?date=`` — yalnız düzgün ISO tarix; qalan hər şey süzgəcsiz (səssiz)."""
    try:
        return _dt.date.fromisoformat((raw or "").strip()[:10])
    except ValueError:
        return None


def row_date(*texts) -> str:
    """Sətrin dərs tarixi — ``item`` («2026-09-25 · Seminar») və ya dərs düzəlişində ``student``."""
    for text in texts:
        match = _DATE_RE.match(str(text or ""))
        if match:
            return match.group(1)
    return ""


def _user_label(user) -> str:
    if user is None:
        return pgettext(_CTX, "Sistem")
    return (user.get_full_name() or "").strip() or user.username


def _enrollment_names(offering, changes_lists) -> dict:
    """``enrollment:<uuid>`` etiketlərini (düzəlişin geri alınması) tələbə adına çevirir — TƏK sorğu."""
    wanted = {}
    for changes in changes_lists:
        for change in changes:
            label = str(change.get("student") or "") if isinstance(change, dict) else ""
            if label.startswith("enrollment:"):
                parsed = parse_uuid(label.split(":", 1)[1])
                if parsed is not None:
                    wanted[label] = parsed
    if not wanted:
        return {}
    from . import grade_audit

    enrollments = offering.enrollments.filter(pk__in=set(wanted.values())).select_related("student")
    by_id = {enrollment.pk: grade_audit.student_label(enrollment) for enrollment in enrollments}
    return {label: by_id[pk] for label, pk in wanted.items() if pk in by_id}


def _serialize_entry(row, names, impersonation_key) -> dict:
    kind = (row.resource_type or "").rsplit(".", 1)[-1]
    real_rows = []
    impersonated_by = ""
    for change in row.changes or []:
        if not isinstance(change, dict):
            continue
        if impersonation_key in change and "student" not in change:
            impersonated_by = str((change.get(impersonation_key) or {}).get("username") or "")
            continue
        real_rows.append(change)
    rows = []
    for change in real_rows[:ROW_CAP]:
        student = str(change.get("student") or "")
        item = str(change.get("item") or "")
        lesson_level = student in ("", "—") or bool(_DATE_RE.match(student))
        if student == "academic-record":
            student, lesson_level = pgettext(_CTX, "Akademik qeyd"), True
        rows.append(
            {
                "student": names.get(student, student),
                "item": item,
                "old": str(change.get("old") if change.get("old") is not None else "—"),
                "new": str(change.get("new") if change.get("new") is not None else "—"),
                "date": row_date(item, student),
                "lesson_level": lesson_level,
            }
        )
    local = timezone.localtime(row.created_at) if timezone.is_aware(row.created_at) else row.created_at
    return {
        "id": str(row.pk),
        "when": local.isoformat(),
        "day": local.date().isoformat(),
        "time": local.strftime("%H:%M"),
        "user": _user_label(row.user),
        "kind": kind,
        "group": kind_group(kind),
        "kind_label": kind_label(kind),
        "count": len(real_rows),
        "rows_total": len(real_rows),
        "rows": rows,
        "impersonated_by": impersonated_by,
    }


def _lesson_dates(offering) -> list:
    """Süzgəc seçimləri — açılışın dərs tarixləri (yenidən köhnəyə), növləri ilə birlikdə. TƏK sorğu."""
    from .models import LessonKind

    labels = dict(LessonKind.choices)
    by_date: dict = {}
    for date, kind in offering.lessons.order_by("-date").values_list("date", "kind"):
        kinds = by_date.setdefault(date.isoformat(), [])
        label = str(labels.get(kind, kind))
        if label not in kinds:
            kinds.append(label)
    return [{"value": value, "kinds": kinds} for value, kinds in by_date.items()]


def history_page(*, offering, offset=0, limit=PAGE_SIZE, date=None) -> dict:
    """Bir səhifə tarixçə (yenidən köhnəyə). ``date`` verilibsə yalnız o dərs tarixinə toxunanlar."""
    from core.audit import IMPERSONATION_KEY

    audit_log = django_apps.get_model("audit", "AuditLog")
    queryset = audit_log.objects.filter(
        organization=offering.organization,
        resource_type__startswith=_PREFIX,
        resource_id=str(offering.pk),
    )
    if date is not None:
        # Tarix audit sətrinin MƏTNİNDƏDİR (JSON → mətn üzərində LIKE; açılış üzrə dəst kiçikdir).
        queryset = queryset.filter(changes__icontains=date.isoformat())
    window = list(queryset.select_related("user").order_by("-created_at", "-pk")[offset : offset + limit + 1])
    has_more = len(window) > limit
    window = window[:limit]
    names = _enrollment_names(offering, [row.changes or [] for row in window])
    payload = {
        "ok": True,
        "entries": [_serialize_entry(row, names, IMPERSONATION_KEY) for row in window],
        "offset": offset,
        "next_offset": offset + len(window),
        "has_more": has_more,
        "date": date.isoformat() if date else "",
    }
    if offset == 0:
        payload["total"] = len(window) if not has_more else queryset.count()
        if date is None:
            payload["dates"] = _lesson_dates(offering)
    return payload


@login_required
@require_GET
def history_json(request, offering_id):
    """``GET /jurnal/<offering>/tarixce/?offset=&limit=&date=`` — panelin səhifələri."""
    offering = _offering_for_history(request, offering_id)
    offset, limit = _bounds(request)
    date = parse_filter_date(request.GET.get("date"))
    return JsonResponse(history_page(offering=offering, offset=offset, limit=limit, date=date))


__all__ = [
    "MAX_PAGE",
    "PAGE_SIZE",
    "ROW_CAP",
    "history_json",
    "history_page",
    "kind_group",
    "kind_label",
    "parse_filter_date",
    "row_date",
]
