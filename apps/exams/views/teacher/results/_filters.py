"""results paketi — nəticələr cədvəlinin süzgəc / sıralama məntiqi (səhifə + Excel ixracı + ixrac işi).

2026-10-25 (sahib: «qrupa görə filtrdə gəlmirdi … əlavə filtr, sort, günə görə, tarix»):
* qrup — çoxlu seçim, ana qrup alt qruplarını da əhatə edir, «Qrupsuz» (bax `_group_index`);
* gün (imtahan bir neçə gündə keçibsə), zal, apellyasiya, bal aralığı;
* axtarış: ad / soyad / ata adı / istifadəçi adı / e-poçt + FİN (yalnız TAM 7 simvol);
* sıralama: qrup və test balı da (test balı DB-də saxlanmır — `_test_scores`).
Bütün dəyərlər URL-də saxlanılır; tanınmayan dəyər səssizcə atılır (əvvəlki davranış).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.search_text import tolerant_q

from ._group_index import build_group_index, resolve_group_options

FIN_RE = re.compile(r"^[A-Za-z0-9]{7}$")
STATUS_VALUES = ("all", "draft", "in_progress", "submitted", "expired")
APPEAL_VALUES = ("open", "closed", "any", "none")
NO_ROOM_VALUE = "none"
FILTER_KEYS = (
    "q",
    "group",
    "status",
    "checked",
    "appeal",
    "room",
    "day",
    "date_from",
    "date_to",
    "score_min",
    "score_max",
    "sort_by",
    "sort_dir",
)
SORT_FIELDS = {
    "user": ("user__first_name", "user__last_name"),
    "username": ("user__username",),
    "email": ("user__email",),
    "status": ("status",),
    "correct": ("correct_count",),
    "wrong": ("wrong_count",),
    "score": ("teacher_score",),
    "start": ("started_at",),
    "end": ("finished_at",),
    "duration": ("duration_seconds",),
    "group": ("_group_sort",),
}


def param_list(params, key) -> list[str]:
    """QueryDict (`getlist`) və ya düz mapping (ixrac işi: CSV/list) — boşsuz dəyərlər."""
    if hasattr(params, "getlist"):
        raw = params.getlist(key)
    else:
        value = params.get(key)
        raw = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for item in raw:
        out += [part.strip() for part in str(item or "").split(",") if part.strip()]
    return out


def _single(params, key) -> str:
    values = param_list(params, key)
    return values[0] if values else ""


def parse_score(raw) -> Decimal | None:
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() and Decimal("0") <= value <= Decimal("100000") else None


def _search_q(search_query: str):
    query = tolerant_q(
        search_query,
        ("user__username", "user__first_name", "user__last_name", "user__email", "user__profile__patronymic"),
    )
    if FIN_RE.match(search_query):
        fin_q = Q(user__profile__fin__iexact=search_query)
        query = fin_q if query is None else (query | fin_q)
    return query


def _group_sort_subquery():
    """Sətirdə göstərilən qrupun adı (`_group_index` ilə eyni «ən uyğun qeyd» qaydası)."""
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    best = (
        record_model.objects.filter(student_id=OuterRef("user_id"), group__isnull=False)
        .annotate(
            _rank=Case(
                When(is_active=True, status="enrolled", then=Value(2)),
                When(is_active=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("-_rank", "-created_at")
        .values("group__name")[:1]
    )
    return Subquery(best)


def day_options(exam) -> list[dict]:
    """Cəhdlərin başladığı yerli günlər + say (1 sorğu) — «Gün» seçicisi."""
    tz = timezone.get_current_timezone()
    rows = (
        exam.attempts.exclude(is_trial=True)
        .annotate(day=TruncDate("started_at", tzinfo=tz))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("day")
    )
    return [{"value": row["day"].strftime("%d.%m.%Y"), "count": row["n"]} for row in rows if row["day"]]


def room_options(exam) -> list[dict]:
    """Cəhdlərin qeydə alındığı zallar + say (1 sorğu); heç biri zalda deyilsə boş."""
    rows = list(
        exam.attempts.exclude(is_trial=True)
        .values("room_id", "room__name")
        .annotate(n=Count("id"))
        .order_by("room__name")
    )
    if not any(row["room_id"] for row in rows):
        return []
    options = [
        {"value": str(row["room_id"]), "name": row["room__name"], "count": row["n"]} for row in rows if row["room_id"]
    ]
    without = sum(row["n"] for row in rows if not row["room_id"])
    if without:
        options.append({"value": NO_ROOM_VALUE, "name": "", "count": without, "is_none": True})
    return options


def _apply_appeal(exam, attempts, appeal_filter):
    from apps.exams import score_adjustments

    attempt_ids = list(exam.attempts.exclude(is_trial=True).values_list("id", flat=True))
    status_map = score_adjustments.status_by_attempt(attempt_ids)
    if appeal_filter == "none":
        return attempts.exclude(id__in=list(status_map))
    if appeal_filter == "open":
        ids = [pk for pk, row in status_map.items() if not row["is_final"]]
    elif appeal_filter == "closed":
        ids = [pk for pk, row in status_map.items() if row["is_final"]]
    else:
        ids = list(status_map)
    return attempts.filter(id__in=ids)


def apply_results_filters_from_params(exam, params, *, parse_date):
    """Süzgəclər + sıralama → (attempts_qs, state). `parse_date` — `_helpers._parse_filter_date`."""
    from ._helpers import _expire_overdue_attempts

    # Lazy expire: vaxtı keçmiş "davam edir" cəhdləri siyahıdan ƏVVƏL expired-ə çevir.
    _expire_overdue_attempts(exam)

    # ``exam`` select_related-də YOXDUR: ``exam.attempts`` hər sətrə eyni ``exam`` instansını qoyur.
    attempts = (
        exam.attempts.exclude(is_trial=True).select_related("user", "room")
        # `answers__selected_options` QƏSDƏN yoxdur — bax `_test_scores.attach_legacy_selected_options`.
        .prefetch_related("answers__question__options")
    )
    is_test = exam.exam_type == "test"

    search_query = (params.get("q") or "").strip()[:120]
    student_q = _search_q(search_query)
    if student_q is not None:
        attempts = attempts.filter(student_q)

    status_filter = (_single(params, "status") or "all").lower()
    if status_filter not in STATUS_VALUES:
        status_filter = "all"
    if status_filter != "all":
        attempts = attempts.filter(status=status_filter)

    checked_filter = (_single(params, "checked") or "all").lower()
    if is_test or checked_filter not in ("checked", "unchecked"):
        checked_filter = "all"  # test imtahanında hamısı «yoxlanılıb» sayılır — süzgəc mənasızdır
    elif checked_filter == "checked":
        attempts = attempts.filter(checked_by_teacher=True)
    else:
        attempts = attempts.filter(checked_by_teacher=False)

    appeal_filter = _single(params, "appeal").lower()
    if appeal_filter not in APPEAL_VALUES:
        appeal_filter = ""
    if appeal_filter:
        attempts = _apply_appeal(exam, attempts, appeal_filter)

    room_filter = _single(params, "room")
    if room_filter == NO_ROOM_VALUE:
        attempts = attempts.filter(room__isnull=True)
    elif room_filter.isdigit():
        attempts = attempts.filter(room_id=int(room_filter))
    else:
        room_filter = ""

    day_raw, day = parse_date(_single(params, "day"))
    date_from_raw, date_from = parse_date(params.get("date_from"))
    date_to_raw, date_to = parse_date(params.get("date_to"))
    tz = timezone.get_current_timezone()
    if day or date_from or date_to:
        attempts = attempts.annotate(_start_day=TruncDate("started_at", tzinfo=tz))
    if day:
        attempts = attempts.filter(_start_day=day)
    if date_from:
        attempts = attempts.filter(_start_day__gte=date_from)
    if date_to:
        attempts = attempts.filter(_start_day__lte=date_to)

    # Qrup — `_group_index` (ana qrup → alt qruplar, «Qrupsuz», kohort); çoxlu seçim = «və ya».
    group_index = build_group_index(exam)
    groups = resolve_group_options(group_index, param_list(params, "group"))
    if groups:
        user_ids: set = set()
        for option in groups:
            user_ids |= group_index.user_ids_for(option)
        attempts = attempts.filter(user_id__in=sorted(user_ids))

    score_min = parse_score(params.get("score_min"))
    score_max = parse_score(params.get("score_max"))
    sort_by = _single(params, "sort_by")
    sort_dir = _single(params, "sort_dir")
    if sort_by not in SORT_FIELDS or sort_dir not in ("asc", "desc"):
        sort_by, sort_dir = "", ""

    test_scores = None
    if is_test and (score_min is not None or score_max is not None or sort_by == "score"):
        from ._test_scores import test_score_map

        test_scores = test_score_map(attempts)
    if score_min is not None or score_max is not None:
        if test_scores is not None:
            keep = [
                pk
                for pk, value in test_scores.items()
                if (score_min is None or value >= score_min) and (score_max is None or value <= score_max)
            ]
            attempts = attempts.filter(id__in=keep)
        else:
            if score_min is not None:
                attempts = attempts.filter(teacher_score__gte=score_min)
            if score_max is not None:
                attempts = attempts.filter(teacher_score__lte=score_max)

    if sort_by:
        if sort_by == "group":
            attempts = attempts.annotate(_group_sort=_group_sort_subquery())
        if sort_by == "score" and test_scores is not None:
            ranked = sorted(test_scores, key=lambda pk: (test_scores[pk], pk))
            attempts = attempts.annotate(
                _score_rank=Case(
                    *[When(id=pk, then=Value(rank)) for rank, pk in enumerate(ranked)],
                    default=Value(-1),
                    output_field=IntegerField(),
                )
            )
            fields = ("_score_rank",)
        else:
            fields = SORT_FIELDS[sort_by]
        expressions = [f"-{name}" if sort_dir == "desc" else name for name in fields]
        attempts = attempts.order_by(*expressions, "-started_at", "-id")
    else:
        attempts = attempts.order_by("-started_at", "-id")

    return attempts, {
        "search_query": search_query,
        "status_filter": status_filter,
        "checked_filter": checked_filter,
        "appeal_filter": appeal_filter,
        "room_filter": room_filter,
        "day_raw": day_raw,
        "date_from_raw": date_from_raw,
        "date_to_raw": date_to_raw,
        "group_values": [option.id for option in groups],
        "group_id": ",".join(option.id for option in groups) or None,
        "group_index": group_index,
        "score_min": "" if score_min is None else format(score_min.normalize(), "f"),
        "score_max": "" if score_max is None else format(score_max.normalize(), "f"),
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }


def filter_query_items(state, *, include_sort=True) -> list[tuple[str, str]]:
    """Cari süzgəc vəziyyəti → URL parametrləri (sıralama, səhifələmə, ixrac linkləri üçün)."""
    items = [
        ("q", state["search_query"]),
        ("status", "" if state["status_filter"] == "all" else state["status_filter"]),
        ("checked", "" if state["checked_filter"] == "all" else state["checked_filter"]),
        ("appeal", state["appeal_filter"]),
        ("room", state["room_filter"]),
        ("day", state["day_raw"]),
        ("date_from", state["date_from_raw"]),
        ("date_to", state["date_to_raw"]),
        ("score_min", state["score_min"]),
        ("score_max", state["score_max"]),
    ]
    items += [("group", value) for value in state["group_values"]]
    if include_sort:
        items += [("sort_by", state["sort_by"]), ("sort_dir", state["sort_dir"])]
    return [(key, value) for key, value in items if value not in ("", None)]


def filters_active(state) -> bool:
    return bool(filter_query_items(state, include_sort=False))


__all__ = [
    "FILTER_KEYS",
    "apply_results_filters_from_params",
    "day_options",
    "filter_query_items",
    "filters_active",
    "param_list",
    "parse_score",
    "room_options",
]
