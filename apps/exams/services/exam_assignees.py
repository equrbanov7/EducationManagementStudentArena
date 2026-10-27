"""«Tapşırıq təyin olunmuşlar» — imtahanı verə bilən tələbələrin siyahısı (sahib 2026-10-27).

Sahib: «keçid olsun baxmağa — hansı qrup var, filterləmək, search eləmək, tələbələrə baxmaq, əlifba sırasına
görə düzmək». Bu modul YALNIZ oxuyur (siyahı + süzgəc + sıra); təyinatın dəyişdirilməsi view qatındadır
(``views/teacher/exams/assignee_edit.py`` — sehrbazın saxlama qapıları ilə).

Üzvlük məntiqi BURADA YENİDƏN YAZILMIR:

* imtahanı verə bilənlər — ``student_pins._assigned_student_ids`` (PIN provizionunun və bildirişlərin
  kanonik çoxluğu: fərdi + köhnə kohort + reyestr qrupu (alt qruplar və fənnin cari jurnalı daxil) + kurs
  − istisnalar; giriş siyasəti ``user_in_allowed_units`` ilə eyni şərt);
* «qrupla» mənbəyi — ``unit_assignment.unit_assigned_student_ids`` + köhnə kohort üzvləri;
* istisna edilənlər (``excluded_users``) siyahıda bayraqla görünür, amma imtahanı verə bilmir.

Sorğu sayı tələbə sayından asılı deyil (sabit ≈ 15; bal yalnız görünən səhifə üçün hesablanır).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.auth import get_user_model

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.domain.unit_assignment import unit_assigned_student_ids
from core.person_names import user_display_name_with_patronymic
from core.search_text import tolerant_match

SOURCE_GROUP = "group"
SOURCE_INDIVIDUAL = "individual"
SOURCE_COURSE = "course"
SOURCES = (SOURCE_GROUP, SOURCE_INDIVIDUAL, SOURCE_COURSE)

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_FINISHED = "finished"
#: Süzgəc dəyəri (cəhd statusu deyil): istisna edilmiş tələbələr.
STATUS_EXCLUDED = "excluded"
STATUSES = (STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_FINISHED, STATUS_EXCLUDED)

SORT_KEYS = ("name", "group", "code", "status")
_STATUS_ORDER = {STATUS_IN_PROGRESS: 0, STATUS_FINISHED: 1, STATUS_NOT_STARTED: 2}
_OPEN_STATUSES = ("draft", "in_progress")


@dataclass
class AssigneeRow:
    """Siyahının bir sətri (tələbə)."""

    user: object
    name: str
    group_name: str
    code: str
    is_individual: bool
    is_group: bool
    is_course: bool
    is_excluded: bool
    has_pin: bool | None
    status: str
    attempts_count: int = 0
    last_finished: object = None
    sources: tuple = field(default_factory=tuple)

    @property
    def user_id(self):
        return self.user.pk


def eligible_student_ids(exam) -> set:
    """İmtahanı verə bilən tələbələr — kanonik çoxluq (PIN provizionu ilə EYNİ funksiya)."""
    from apps.exams.services.student_pins import _assigned_student_ids

    return _assigned_student_ids(exam)


def assignee_count(exam) -> int:
    """Detal səhifəsindəki «Tapşırıq təyin olunmuşlar» kartının sayı."""
    return len(eligible_student_ids(exam))


def _group_member_ids(exam) -> set:
    ids = set(unit_assigned_student_ids(exam))
    ids.update(pk for pk in exam.allowed_groups.values_list("students__id", flat=True) if pk)
    return ids


def _course_member_ids(exam) -> set:
    if not exam.course_id:
        return set()
    return set(exam.course.memberships.filter(role="student").values_list("user_id", flat=True))


def _pin_map(exam, ids) -> dict | None:
    from apps.exams.models import ExamStudentPin
    from apps.exams.services.student_pins import exam_requires_student_pins

    if not exam_requires_student_pins(exam):
        return None
    pins = ExamStudentPin.objects.filter(exam=exam, student_id__in=list(ids)).only(
        "student_id", "pin_cipher", "revoked_at", "expires_at"
    )
    return {pin.student_id: bool(pin.pin_cipher) and pin.is_usable() for pin in pins}


def _attempt_map(exam) -> dict:
    """``{user_id: (status, cəhd sayı, son bitmiş cəhd)}`` — sınaq cəhdləri sayılmır (BİR sorğu)."""
    from apps.exams.models import ExamAttempt

    out: dict = {}
    attempts = (
        ExamAttempt.objects.filter(exam=exam, is_trial=False)
        .only(
            "id",
            "user_id",
            "exam_id",
            "status",
            "started_at",
            "finished_at",
            "teacher_score",
            "correct_count",
            "wrong_count",
        )
        .order_by("started_at", "id")
    )
    for attempt in attempts:
        status, count, last = out.get(attempt.user_id, (STATUS_NOT_STARTED, 0, None))
        count += 1
        if attempt.status in _OPEN_STATUSES:
            status = STATUS_IN_PROGRESS
        elif attempt.status in ATTEMPT_FINISHED_STATUSES:
            last = attempt
            if status != STATUS_IN_PROGRESS:
                status = STATUS_FINISHED
        out[attempt.user_id] = (status, count, last)
    return out


def build_roster(exam) -> list:
    """Bütün təyin olunmuşlar (istisnalar bayraqla) → :class:`AssigneeRow` siyahısı, ad sırası ilə."""
    eligible = eligible_student_ids(exam)
    excluded = set(exam.excluded_users.values_list("id", flat=True))
    individual = set(exam.allowed_users.values_list("id", flat=True))
    group_members = _group_member_ids(exam)
    course_members = _course_member_ids(exam)
    shown = eligible | (excluded & (individual | group_members | course_members))
    if not shown:
        return []

    from apps.registrar.public import student_group_names

    users = get_user_model().objects.filter(pk__in=list(shown)).select_related("profile")
    groups = student_group_names.current_group_names(shown)
    pins = _pin_map(exam, shown)
    attempts = _attempt_map(exam)
    rows = []
    for user in users:
        status, count, last = attempts.get(user.pk, (STATUS_NOT_STARTED, 0, None))
        profile = getattr(user, "profile", None)
        is_individual = user.pk in individual
        is_group = user.pk in group_members
        is_course = user.pk in course_members
        sources = tuple(
            source
            for source, flag in (
                (SOURCE_GROUP, is_group),
                (SOURCE_INDIVIDUAL, is_individual),
                (SOURCE_COURSE, is_course),
            )
            if flag
        )
        rows.append(
            AssigneeRow(
                user=user,
                name=user_display_name_with_patronymic(user) or user.username,
                group_name=groups.get(user.pk, ""),
                code=(getattr(profile, "institutional_identifier", "") or "") if profile is not None else "",
                is_individual=is_individual,
                is_group=is_group,
                is_course=is_course,
                is_excluded=user.pk in excluded,
                has_pin=None if pins is None else pins.get(user.pk, False),
                status=status,
                attempts_count=count,
                last_finished=last,
                sources=sources,
            )
        )
    return sort_rows(rows, "name", "asc")


#: Azərbaycan əlifbası (sahib: «əlifba sırasına görə») — kod nöqtəsi sırası «Ə», «Ş», «İ»-ni sona atırdı.
_AZ_ALPHABET = "abcçdeəfgğhxıijkqlmnoöprsştuüvwyz"
_AZ_RANK = {letter: index for index, letter in enumerate(_AZ_ALPHABET)}
_AZ_LOWER = {"I": "ı", "İ": "i"}


def az_sort_key(text) -> tuple:
    """Mətnin Azərbaycan əlifbası sırası ilə müqayisə açarı (registrdən asılı deyil; tanınmayan simvol sonda)."""
    out = []
    for char in str(text or "").replace("\u0307", ""):
        lower = _AZ_LOWER.get(char) or char.lower()
        rank = _AZ_RANK.get(lower)
        out.append((0, rank) if rank is not None else (1, ord(lower)))
    return tuple(out)


def _sort_name(row):
    user = row.user
    return (
        az_sort_key(user.last_name),
        az_sort_key(user.first_name),
        az_sort_key(row.name),
        user.username.casefold(),
    )


def sort_rows(rows, sort_by, sort_dir) -> list:
    """Sıra: ``name`` (soyad, ad — əlifba), ``group``, ``code``, ``status``; ``sort_dir`` = asc / desc."""
    reverse = sort_dir == "desc"
    if sort_by == "group":
        key = lambda row: (not row.group_name, az_sort_key(row.group_name), _sort_name(row))  # noqa: E731
    elif sort_by == "code":
        key = lambda row: (not row.code, row.code, _sort_name(row))  # noqa: E731
    elif sort_by == "status":
        key = lambda row: (row.is_excluded, _STATUS_ORDER.get(row.status, 9), _sort_name(row))  # noqa: E731
    else:
        key = _sort_name
    return sorted(rows, key=key, reverse=reverse)


def filter_rows(rows, *, query="", group="", source="", status="") -> list:
    """Süzgəclər: mətn (ad / ata adı / istifadəçi adı / kod — hərf-dözümlü), qrup adı, mənbə, status."""
    out = []
    for row in rows:
        if group and row.group_name != group:
            continue
        if source in SOURCES and source not in row.sources:
            continue
        if status == STATUS_EXCLUDED:
            if not row.is_excluded:
                continue
        elif status in STATUSES and (row.is_excluded or row.status != status):
            continue
        if query and not tolerant_match(query, row.name, row.user.username, row.code, row.user.email):
            continue
        out.append(row)
    return out


def group_summary(rows) -> list:
    """Qrup çipləri: ``[(qrup adı, say)]`` — yalnız imtahanı verə bilənlər (istisnasız), ada görə."""
    counts: dict = {}
    for row in rows:
        if row.is_excluded:
            continue
        counts[row.group_name] = counts.get(row.group_name, 0) + 1
    return sorted(counts.items(), key=lambda item: (item[0] == "", az_sort_key(item[0])))


def roster_stats(rows) -> dict:
    active = [row for row in rows if not row.is_excluded]
    return {
        "eligible": len(active),
        "group": sum(1 for row in active if row.is_group),
        "individual": sum(1 for row in active if row.is_individual),
        "excluded": len(rows) - len(active),
        "finished": sum(1 for row in active if row.status == STATUS_FINISHED),
        "in_progress": sum(1 for row in active if row.status == STATUS_IN_PROGRESS),
    }


def attach_scores(exam, rows) -> None:
    """Görünən səhifənin bitmiş cəhdlərinə bal mətni (``row.score_text``) — test: effektiv bal / maks."""
    finished = [row.last_finished for row in rows if row.last_finished is not None]
    for row in rows:
        row.score_text = ""
    if not finished:
        return
    for attempt in finished:
        attempt.exam = exam
    if exam.exam_type == "test":
        from apps.exams.services.result_calculation import attach_test_result_summaries

        attach_test_result_summaries(finished)
    for row in rows:
        attempt = row.last_finished
        if attempt is None:
            continue
        result = getattr(attempt, "test_result", None)
        if result is not None:
            row.score_text = f"{result.score_display} / {result.max_score_display}"
        elif attempt.teacher_score is not None:
            row.score_text = str(attempt.teacher_score)


__all__ = [
    "AssigneeRow",
    "SORT_KEYS",
    "SOURCES",
    "STATUSES",
    "assignee_count",
    "attach_scores",
    "az_sort_key",
    "build_roster",
    "eligible_student_ids",
    "filter_rows",
    "group_summary",
    "roster_stats",
    "sort_rows",
]
