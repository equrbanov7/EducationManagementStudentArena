"""25% / alt qrup — HEYƏT növbəsi (Mühasibatlıq + dekanlıq / tədris şöbəsi) və iz görünüşü.

Tab-lar açardan asılıdır (rol adı yox):

* «Ödəniş yoxlaması» — ``retake.payment_verify``: qəbz yoxlanılan müraciətlər, orijinal fayl adı + yükləmə
  vaxtı (YALNIZ mühasibə), eyni qəbzin başqa müraciətdə yüklənməsi xəbərdarlığı;
* «Qəbul və qərar» — ``retake.manage``: ödənişi təsdiqlənmiş 25% müraciətləri, alt qrup müraciətləri,
  nəticə / yerləşdirmə gözləyənlər;
* «Hamısı» + «Tələbə izi» — hər üç açardan biri (``student.records_view`` daxil — koordinator, dekanlıq,
  rəhbərlik izi görür).

Əhatə ``retake_access.scoped_applications`` ilədir; KPI-lər tək aqreqat sorğu, səhifədəki qəbzlərin
dublikat yoxlaması tək sorğu.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Count
from django.utils.translation import pgettext_lazy

from core.search_text import tolerant_q

from . import retake_access, retake_closure, retake_fees, retake_queries, retake_rules
from .models import RetakeApplication, RetakeKind, RetakeStatus
from .retake_services import duplicate_receipt_map

_CTX = "registrar.retake"

PAGE_SIZE = 25
SECTION = "retake-desk"

TAB_PAYMENTS = "payments"
TAB_ADMISSION = "admission"
TAB_ALL = "all"
TAB_FEES = "fees"

_ADMISSION_STATUSES = (
    RetakeStatus.SUBMITTED,
    RetakeStatus.PAYMENT_VERIFIED,
    RetakeStatus.ADMITTED,
    RetakeStatus.EXAM_GRANTED,
)


def _params(request) -> dict:
    get = request.GET
    return {
        "tab": (get.get("rt_tab") or "").strip(),
        "status": (get.get("rt_status") or "").strip(),
        "kind": (get.get("rt_kind") or "").strip(),
        "q": (get.get("rt_q") or "").strip()[:100],
        "page": (get.get("rt_page") or "1").strip(),
        "student": (get.get("rt_student") or "").strip(),
        "app": (get.get("rt_app") or "").strip()[:40],
    }


def _tabs(keys) -> list:
    tabs = []
    if keys["verify"]:
        tabs.append((TAB_PAYMENTS, pgettext_lazy(_CTX, "Ödəniş yoxlaması")))
    if keys["manage"] or keys["record"]:
        tabs.append((TAB_ADMISSION, pgettext_lazy(_CTX, "Qəbul və qərar")))
    if keys["trail"]:  # mühasib «Hamısı»nı və tələbə izini GÖRMÜR (ballar / tarixçə — sahibin qaydası)
        tabs.append((TAB_ALL, pgettext_lazy(_CTX, "Hamısı")))
    if keys.get("fees"):  # 2026-10-19: təhsil haqqı cədvəli (Mühasibatlıq)
        tabs.append((TAB_FEES, pgettext_lazy(_CTX, "Təhsil haqqı cədvəli")))
    return tabs


def _keys_for_tab(tab) -> tuple:
    if tab == TAB_PAYMENTS:
        return (retake_rules.PERM_PAYMENT_VERIFY,)
    if tab == TAB_ADMISSION:
        return (retake_rules.PERM_MANAGE, retake_rules.PERM_SCORE_ENTRY)
    return retake_access.TRAIL_KEYS


def _tab_filter(queryset, tab):
    if tab == TAB_PAYMENTS:
        return queryset.filter(kind=RetakeKind.RETAKE_25).exclude(status=RetakeStatus.SUBMITTED)
    if tab == TAB_ADMISSION:
        return queryset.filter(status__in=_ADMISSION_STATUSES).exclude(
            kind=RetakeKind.RETAKE_25, status=RetakeStatus.SUBMITTED
        )
    return queryset


def _default_status(tab) -> str:
    return RetakeStatus.PAYMENT_PENDING_REVIEW if tab == TAB_PAYMENTS else ""


_PAYMENT_KPIS = (RetakeStatus.PAYMENT_PENDING_REVIEW, RetakeStatus.PAYMENT_REJECTED, RetakeStatus.PAYMENT_VERIFIED)
_ALL_KPIS = (
    RetakeStatus.PAYMENT_PENDING_REVIEW,
    RetakeStatus.PAYMENT_VERIFIED,
    RetakeStatus.SUBMITTED,
    RetakeStatus.ADMITTED,
    RetakeStatus.EXAM_GRANTED,
    RetakeStatus.COMPLETED,
)

#: «Ödəniş yoxlaması» sətrində görünən addımlar — bal / nəticə hadisələri mühasibə GÖSTƏRİLMİR.
_PAYMENT_EVENTS = frozenset({"submitted", "receipt_uploaded", "payment_verified", "payment_rejected", "withdrawn"})


def _kpis(queryset, order=_ALL_KPIS) -> list:
    counts = dict(queryset.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
    tiles = []
    for status in order:
        tone = retake_rules.tone_for(status)
        tiles.append(
            {
                "label": RetakeStatus(status).label,
                "value": counts.get(status, 0),
                "tone": f"accent-{tone}" if tone in ("primary", "success", "warning", "danger") else "",
                "status": status,
            }
        )
    return tiles


def _search(queryset, text):
    q = tolerant_q(
        text,
        ("student__first_name", "student__last_name", "student__username", "subject__name"),
        compact_fields=("subject__code", "student_group__name"),
    )
    return queryset.filter(q) if q is not None else queryset


def _payment_row(row, application) -> dict:
    """Mühasibat görünüşü — yalnız ödəniş yoxlamasına lazım olan sahələr (bal, nəticə, başqa fənlər YOX)."""
    profile = getattr(application.student, "profile", None)
    keep = [
        entry for entry, event in zip(row["timeline"], application.ordered_events) if event.action in _PAYMENT_EVENTS
    ]
    if keep:
        keep[-1] = {**keep[-1], "current": True}
    expected = row.get("expected_fee")
    paid = application.paid_amount
    return {
        **{key: row[key] for key in ("app", "id", "kind_label", "receipt", "receipt_url", "duplicates", "can_verify")},
        "student_number": (getattr(profile, "institutional_identifier", "") or "") if profile else "",
        "timeline": keep,
        "expected_fee": expected,
        "fee_year": (application.fee_inputs or {}).get("academic_year") or "",
        "paid_amount": paid,
        "amount_mismatch": expected is not None and paid is not None and paid != expected,
    }


def _rows(page, keys, *, payment_view=False) -> list:
    applications = list(page.object_list)
    receipts = [a.current_receipt for a in applications if a.current_receipt_id]
    duplicates = duplicate_receipt_map(receipts) if keys["verify"] else {}
    expected = retake_fees.expected_map(applications) if payment_view else {}
    rows = []
    for application in applications:
        row = retake_queries.decorate(application)
        receipt = application.current_receipt
        row["duplicates"] = duplicates.get(getattr(receipt, "id", None), [])
        row["can_verify"] = keys["verify"] and application.status == RetakeStatus.PAYMENT_PENDING_REVIEW
        row["can_admit"] = (
            keys["manage"]
            and application.kind == RetakeKind.RETAKE_25
            and application.status == RetakeStatus.PAYMENT_VERIFIED
        )
        row["can_decide_subgroup"] = (
            keys["manage"] and application.kind == RetakeKind.SUBGROUP and application.status == RetakeStatus.SUBMITTED
        )
        row["can_place"] = (
            keys["manage"] and application.kind == RetakeKind.SUBGROUP and application.status == RetakeStatus.ADMITTED
        )
        row["can_record"] = (
            keys["record"]
            and application.kind == RetakeKind.RETAKE_25
            and application.status in retake_rules.RESULT_RECORDABLE
        )
        is_25 = application.kind == RetakeKind.RETAKE_25
        # 2026-10-19 (sahib): ödənişdən sonra bağlanış — yalnız qərarla (``retake_closure``).
        row["can_close"] = keys["manage"] and is_25 and application.status in retake_closure.AFTER_PAYMENT
        row["can_no_show"] = keys["manage"] and is_25 and application.status in retake_closure.ACTIONS["no_show"][2]
        row["expected_fee"] = expected.get(application.pk)
        rows.append(_payment_row(row, application) if payment_view else row)
    return rows


def build(request, organization) -> dict:
    user = request.user
    keys = retake_access.desk_keys(user, organization)
    keys["fees"] = retake_fees.can_manage(user, organization)
    if not (keys["trail"] or keys["record"] or keys["verify"] or keys["fees"]):
        return {"has_access": False}
    params = _params(request)
    tabs = _tabs(keys)
    tab_keys = [key for key, _label in tabs]
    tab = params["tab"] if params["tab"] in tab_keys else tab_keys[0]
    if tab == TAB_FEES:
        return _fees_tab(organization, keys, tabs, params)
    base = retake_access.scoped_applications(RetakeApplication.objects.all(), user, organization, _keys_for_tab(tab))
    tab_qs = _tab_filter(base, tab)
    status = params["status"] if params["status"] in RetakeStatus.values else ""
    if not params["status"] and "rt_status" not in request.GET:
        status = _default_status(tab)
    filtered = tab_qs
    if status:
        filtered = filtered.filter(status=status)
    if params["kind"] in RetakeKind.values:
        filtered = filtered.filter(kind=params["kind"])
    filtered = _search(filtered, params["q"])
    if params["app"]:
        filtered = filtered.filter(pk__in=[params["app"]] if _is_uuid(params["app"]) else [])
    payment_view = tab == TAB_PAYMENTS
    filtered = filtered.select_related(
        "student",
        "student__profile",
        "subject",
        "period",
        "student_group",
        "current_receipt",
        "enrollment__offering__group",
        "target_offering",
    ).prefetch_related(retake_queries.events_prefetch())
    paginator = Paginator(filtered.order_by("created_at" if tab != TAB_ALL else "-created_at"), PAGE_SIZE)
    page = paginator.get_page(params["page"])
    trail = _trail(request, organization, params["student"], keys)
    return {
        "has_access": True,
        "keys": keys,
        "tabs": [{"key": key, "label": label, "current": key == tab} for key, label in tabs],
        "tab": tab,
        "params": {**params, "status": status, "tab": tab},
        "kpis": _kpis(tab_qs, _PAYMENT_KPIS if payment_view else _ALL_KPIS),
        "rows": _rows(page, keys, payment_view=payment_view),
        "payment_view": payment_view,
        "page": page,
        "total": paginator.count,
        "status_choices": (
            [(s, RetakeStatus(s).label) for s in _PAYMENT_KPIS] if payment_view else RetakeStatus.choices
        ),
        "kind_choices": RetakeKind.choices,
        "trail": trail,
        "reason_min": retake_rules.REASON_MIN,
    }


def _fees_tab(organization, keys, tabs, params) -> dict:
    years = retake_fees.known_years(organization)
    return {
        "has_access": True,
        "keys": keys,
        "tabs": [{"key": key, "label": label, "current": key == TAB_FEES} for key, label in tabs],
        "tab": TAB_FEES,
        "params": {**params, "tab": TAB_FEES},
        "fees": {
            "rows": retake_fees.table(organization),
            "programs": retake_fees.program_choices(organization),
            "years": years,
            "settings": retake_fees.settings_snapshot(),
        },
        "kpis": [],
        "rows": [],
        "trail": None,
        "reason_min": retake_rules.REASON_MIN,
    }


def _is_uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _trail(request, organization, raw_student, keys):
    if not raw_student or not raw_student.isdigit() or not keys["trail"]:
        return None
    from django.contrib.auth import get_user_model

    student = get_user_model().objects.filter(pk=int(raw_student)).first()
    if student is None or not retake_access.student_in_scope(
        request.user, organization, student.pk, retake_access.TRAIL_KEYS
    ):
        return {"missing": True}
    return retake_queries.student_trail(student=student, organization=organization)


__all__ = ["PAGE_SIZE", "SECTION", "TAB_ADMISSION", "TAB_ALL", "TAB_FEES", "TAB_PAYMENTS", "build"]
