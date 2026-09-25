"""«Tapşırıq yoxlaması» (müəllim) — göndəriş siyahısı və çekməcə (detal) konteksti.

Siyahı ``public.list_submissions`` üzərindədir: görünürlük queryset səviyyəsində
(qrupun canlı müəllimi / inzibatçı / əhatəli əməkdaş — yalnız oxu), qaralamalar
heç vaxt düşmür. Defolt süzgəc «Yoxlanılır» (baxış növbəsi); sayğaclar status
süzgəcindən ƏVVƏLKİ dəst üzrə tək GROUP BY sorğusudur.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.translation import pgettext

from .. import public
from ..constants import SECTION_REVIEW, MatchMethod, SubmissionStatus, TaskKind
from ..models import SubjectFolder
from ..services import lookups
from . import common

_CTX = "subject_folder.ui"

_STATUS_FILTERS = ("submitted", "returned", "accepted", "checked", "rejected")
_KIND_FILTERS = ("selfwork", "homework")
_ORDERS = ("-submitted_at", "submitted_at", "student", "-similarity")


def review_panel(context) -> dict:
    request, organization, user, base = common.resolve(context)
    if organization is None or not lookups.is_authenticated(user):
        return {"state": "no_org"}
    status = common.param(request, "status") or "submitted"
    status = status if status in _STATUS_FILTERS + ("all",) else "submitted"
    kind = common.param(request, "kind")
    kind = kind if kind in _KIND_FILTERS else ""
    flagged = common.param(request, "flagged") == "1"
    late = common.param(request, "late") == "1"
    search = common.param(request, "q", limit=120)
    order = common.param(request, "order")
    order = order if order in _ORDERS else "-submitted_at"
    folders = _reviewable_folders(organization, user)
    folder_id = common.uuid_param(request, "folder")
    folder = next((row for row in folders if row.pk == folder_id), None)

    base_rows = public.list_submissions(
        organization=organization,
        actor=user,
        folder=folder,
        kind=kind or None,
        flagged=True if flagged else None,
        late=True if late else None,
        student_query=search,
        order=order,
    )
    counts = public.status_counts(base_rows)
    rows = base_rows if status == "all" else base_rows.filter(status=status)
    page = Paginator(rows, common.PAGE_SIZE).get_page(common.param(request, "page") or 1)
    items = [_row(submission) for submission in page.object_list]
    everything = [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
    query = {
        "section": SECTION_REVIEW,
        "sf_status": status,
        "sf_kind": kind,
        "sf_folder": str(folder.pk) if folder else "",
        "sf_flagged": "1" if flagged else "",
        "sf_late": "1" if late else "",
        "sf_q": search,
        "sf_order": order if order != "-submitted_at" else "",
    }
    return {
        "state": "ready",
        "urls": common.endpoint_urls(),
        "items": items,
        "page_obj": page,
        "pagination_query": urlencode({key: value for key, value in query.items() if value}),
        "is_filtered": bool(folder or kind or flagged or late or search or status != "submitted"),
        "filter_fields": [
            {
                "name": "sf_status",
                "label": pgettext(_CTX, "Status"),
                "kind": "select",
                "options": [{"value": "all", "label": pgettext(_CTX, "Hamısı")}]
                + [{"value": key, "label": str(SubmissionStatus(key).label)} for key in _STATUS_FILTERS],
                "value": status,
                "default": "submitted",
            },
            {
                "name": "sf_folder",
                "label": pgettext(_CTX, "Qovluq"),
                "kind": "select",
                "options": everything + [{"value": str(row.pk), "label": _folder_label(row)} for row in folders],
                "value": str(folder.pk) if folder else "",
                "searchable": len(folders) > 8,
            },
            {
                "name": "sf_kind",
                "label": pgettext(_CTX, "Növ"),
                "kind": "select",
                "options": everything + [{"value": key, "label": str(TaskKind(key).label)} for key in _KIND_FILTERS],
                "value": kind,
            },
            {
                "name": "sf_flagged",
                "label": pgettext(_CTX, "Oxşarlıq"),
                "kind": "select",
                "options": everything + [{"value": "1", "label": pgettext(_CTX, "Yalnız bayraqlananlar")}],
                "value": "1" if flagged else "",
            },
            {
                "name": "sf_late",
                "label": pgettext(_CTX, "Gecikmə"),
                "kind": "select",
                "options": everything + [{"value": "1", "label": pgettext(_CTX, "Yalnız gecikənlər")}],
                "value": "1" if late else "",
            },
            {
                "name": "sf_q",
                "label": pgettext(_CTX, "Tələbə"),
                "kind": "search",
                "value": search,
                "placeholder": pgettext(_CTX, "Ad, soyad və ya istifadəçi adı…"),
                "wide": True,
            },
        ],
        "filter_count_label": pgettext(_CTX, "Nəticə: %(count)d göndəriş") % {"count": page.paginator.count},
        "kpi_tiles": _kpis(counts),
        "can_bulk": any(item["can_bulk"] for item in items),
        "bulk_limit": 100,
        "reject_reasons": [{"value": value, "label": str(label)} for value, label in public.RejectReason.choices],
        "empty_title": (
            pgettext(_CTX, "Yoxlama növbəsi boşdur")
            if status == "submitted" and not folder
            else pgettext(_CTX, "Süzgəcə uyğun göndəriş yoxdur")
        ),
    }


def _reviewable_folders(organization, user) -> list:
    """Süzgəc üçün qovluqlar: aktorun sahib olduğu və ya qrupunu tədris etdiyi (1 sorğu)."""
    rows = SubjectFolder.objects.filter(organization=organization)
    if not lookups.is_org_admin(user, organization):
        taught = lookups.taught_offerings_q(user, prefix="assignments__offering__")
        rows = rows.filter(Q(owner_id=user.pk) | taught)
    return list(
        rows.select_related("subject", "period").distinct().order_by("-period__start_date", "subject__name")[:200]
    )


def _folder_label(folder) -> str:
    period = getattr(folder.period, "name", "")
    return f"{folder.title} · {period}" if period else folder.title


def _kpis(counts) -> list:
    return [
        {
            "label": pgettext(_CTX, "YOXLANILIR"),
            "value": counts.get("submitted", 0),
            "tone": "warning" if counts.get("submitted") else None,
            "note": pgettext(_CTX, "baxış gözləyən iş"),
        },
        {"label": pgettext(_CTX, "QAYTARILIB"), "value": counts.get("returned", 0)},
        {
            "label": pgettext(_CTX, "QƏBUL / YOXLANILIB"),
            "value": counts.get("accepted", 0) + counts.get("checked", 0),
        },
        {"label": pgettext(_CTX, "RƏDD EDİLİB"), "value": counts.get("rejected", 0)},
    ]


def _row(submission) -> dict:
    offering = submission.assignment.offering
    return {
        "submission": submission,
        "student_name": common.user_name(submission.student),
        "group": getattr(getattr(offering, "group", None), "name", ""),
        "task_title": submission.task.title,
        "kind_label": str(TaskKind(submission.kind).label),
        "folder_title": submission.task.folder.title,
        "chip": common.status_chip(submission.status),
        "sync": common.sync_chip(submission.journal_sync_status),
        "similarity": (
            round(float(submission.similarity_max) * 100) if submission.similarity_max is not None else None
        ),
        "points": common.points_text(submission.points),
        "points_max": common.points_text(submission.points_max or submission.task.max_points),
        "can_bulk": submission.status == SubmissionStatus.SUBMITTED,
    }


# ── Çekməcə ─────────────────────────────────────────────────────────────────


def detail_context(submission, user) -> dict:
    """Göndərişin çekməcə gövdəsi — ``submission_detail`` görmə hüququnu yoxlayır (``FolderError``)."""
    detail = public.submission_detail(submission, actor=user)
    offering = submission.assignment.offering
    group = getattr(getattr(offering, "group", None), "name", "")
    attempts = [
        {
            "attempt": attempt,
            "chip": common.status_chip(attempt.status),
            "files": [
                {"file": row, "url": common.submission_file_url(row), "size": common.human_size(row.size)}
                for row in attempt.files.all()
            ],
            "points": common.points_text(attempt.points),
            "is_current": attempt.pk == submission.pk,
        }
        for attempt in detail["attempts"]
        if attempt.status != SubmissionStatus.DRAFT or attempt.pk == submission.pk
    ]
    preview = None
    if "accept" in detail["actions"]:
        preview = public.journal_preview(submission)
    return {
        "title": common.user_name(submission.student),
        "subtitle": " · ".join(part for part in (submission.task.title, group) if part),
        "submission": submission,
        "chip": common.status_chip(submission.status),
        "sync": common.sync_chip(submission.journal_sync_status),
        "kind_label": str(TaskKind(submission.kind).label),
        "is_selfwork": submission.kind == TaskKind.SELFWORK,
        "attempts": attempts,
        "events": [{"event": event, "label": str(public.EventKind(event.kind).label)} for event in detail["events"]],
        "matches": [_match_row(match, submission) for match in detail["matches"]],
        "actions": detail["actions"],
        "can_review": detail["can_review"],
        "preview": preview,
        "max_points": common.points_text(submission.task.max_points),
        "reject_reasons": [{"value": value, "label": str(label)} for value, label in public.RejectReason.choices],
        "urls": common.endpoint_urls(),
    }


def _match_row(match, submission) -> dict:
    other = match.submission_b if match.submission_a_id == submission.pk else match.submission_a
    offering = getattr(getattr(other, "assignment", None), "offering", None)
    return {
        "match": match,
        "other_name": common.user_name(getattr(other, "student", None)),
        "other_group": getattr(getattr(offering, "group", None), "name", ""),
        "score": round(float(match.score) * 100),
        "method": str(MatchMethod(match.method).label),
        "is_dismissed": match.dismissed_at is not None,
    }


__all__ = ["detail_context", "review_panel"]
