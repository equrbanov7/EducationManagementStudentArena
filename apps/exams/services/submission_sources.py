"""Sual göndərişi formasının qrup/fənn mənbəyi — müəllimin DƏRS YÜKÜ (müəllim rəyi S2, 2026-10-08).

KÖK SƏBƏB
---------
«Yeni göndəriş» formasında fənn siyahısı YALNIZ köhnə imtahan kohortlarından
(``exams.StudentGroup.subjects``) qurulurdu. Həmin cədvəl köhnəlib və real bazada
BOŞDUR (bax ``apps/registrar/course_groups.py``) — müəllimin «Dərs yüküm»də 3 fənni
olsa da forma «Sizə hələ fənn təyin olunmayıb» deyirdi. Fənn qovluğu, imtahan dili
və ya semestr süzgəci səbəb deyildi (dil fənləri süzmür; qovluq tələbi yoxdur).

İNDİ — CARİ semestr üzrə üç mənbənin birləşməsi
------------------------------------------------
1. ``registrar.CourseOffering`` — müəllimin açılışları (jurnal; ``instructor`` və ya
   dərs səviyyəsində ``Lesson.instructor``), qrup = reyestr ``OrgUnit``;
2. ``workload.TeacherAssignment`` — kafedranın TƏSDİQLƏDİYİ bölgü
   (``distributed`` / ``amended``), sətrin qrupları;
3. köhnə kohortlar (geriyə uyğunluq; boş ola bilər).

Qrup açarı: köhnə kohort → ``"<id>"`` (rəqəm), reyestr qrupu → ``"u:<uuid>"``.
Fənn seçilə bilmirsə (bölgü təsdiqlənməyib, sətir kataloq fənninə bağlanmayıb,
cari semestrdə yük yoxdur) ``notices`` NİYƏ olduğunu izah edir — boş siyahı əvəzinə.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils.translation import pgettext

from apps.exams.services.subject_labels import subject_label

UNIT_PREFIX = "u:"
APPROVED_TASK_STATUSES = ("distributed", "amended")
_CTX = "exams.service.submission_sources"


@dataclass(frozen=True)
class SubmissionGroup:
    """Formadakı qrup çipi: köhnə kohort və ya reyestr qrupu."""

    key: str
    name: str
    cohort: object | None = None
    unit: object | None = None

    @property
    def id(self) -> str:  # şablon/JS üçün açar (``g.id``)
        return self.key

    @property
    def org_unit(self):
        """Kafedra həlli üçün akademik vahid (``resolve_submission_chair_unit``)."""
        return self.unit if self.unit is not None else getattr(self.cohort, "org_unit", None)


@dataclass
class SubmissionSources:
    groups: list = field(default_factory=list)
    subjects: list = field(default_factory=list)
    group_subjects: dict = field(default_factory=dict)
    period: object | None = None
    notices: list = field(default_factory=list)

    def split(self, chosen):
        """Seçilmiş çipləri (köhnə kohortlar, reyestr qrupları) cütünə ayırır."""
        cohorts = [group.cohort for group in chosen if group.cohort is not None]
        units = [group.unit for group in chosen if group.unit is not None]
        return cohorts, units


def _legacy_cohorts(user, organization):
    StudentGroup = django_apps.get_model("exams", "StudentGroup")
    return list(
        StudentGroup.objects.filter(organization=organization)
        .filter(Q(teacher=user) | Q(teachers=user))
        .select_related("org_unit")
        .prefetch_related("subjects")
        .distinct()
        .order_by("name")
    )


def _offering_pairs(user, organization, period):
    """(subject, unit) cütləri — müəllimin cari semestr açılışları."""
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    Lesson = django_apps.get_model("registrar", "Lesson")
    lesson_offerings = Lesson.objects.filter(instructor=user, offering__period=period).values("offering_id")
    offerings = (
        CourseOffering.objects.filter(organization=organization, period=period, is_active=True)
        .filter(Q(instructor=user) | Q(pk__in=lesson_offerings))
        .select_related("subject", "group")
    )
    return [(offering.subject, offering.group) for offering in offerings]


def _assignment_queryset(user, organization):
    try:
        TeacherAssignment = django_apps.get_model("workload", "TeacherAssignment")
    except LookupError:  # pragma: no cover — workload tətbiqi söndürülübsə
        return None
    return TeacherAssignment.objects.filter(organization=organization, teacher=user)


def _workload_rows(assignments, period):
    """Cari semestrin təsdiqlənmiş bölgü sətirləri (sətrin semestri yoxdursa — tədris ili)."""
    scoped = assignments.filter(row__task__status__in=APPROVED_TASK_STATUSES).filter(
        Q(row__period=period) | Q(row__period__isnull=True, row__task__academic_year=period.academic_year)
    )
    rows = {}
    for assignment in scoped.select_related("row", "row__subject").prefetch_related("row__groups"):
        rows[assignment.row_id] = assignment.row
    return list(rows.values())


def _period_label(period) -> str:
    year = getattr(period, "year_display", "") or getattr(period, "academic_year", "")
    return f"{period.name} {year}".strip()


def teacher_submission_sources(user, organization, *, period=None) -> SubmissionSources:
    """Müəllimin göndəriş formasında seçə biləcəyi qruplar və fənlər (+ «niyə» izahları)."""
    sources = SubmissionSources()
    if user is None or organization is None:
        return sources

    groups: dict[str, SubmissionGroup] = {}
    subjects: dict[str, object] = {}
    by_group: dict[str, dict[str, object]] = {}

    def link(group: SubmissionGroup, subject):
        groups.setdefault(group.key, group)
        bucket = by_group.setdefault(group.key, {})
        if subject is not None:
            subjects.setdefault(str(subject.pk), subject)
            bucket.setdefault(str(subject.pk), subject)

    def unit_group(unit):
        return SubmissionGroup(key=f"{UNIT_PREFIX}{unit.pk}", name=unit.name, unit=unit)

    from apps.registrar.public import dashboard_data

    period = period or dashboard_data.current_period(organization)
    sources.period = period
    assignments = _assignment_queryset(user, organization)
    unlinked: list[str] = []
    if period is not None:
        for subject, unit in _offering_pairs(user, organization, period):
            if unit is not None:
                link(unit_group(unit), subject)
            elif subject is not None:
                subjects.setdefault(str(subject.pk), subject)
        if assignments is not None:
            for row in _workload_rows(assignments, period):
                row_groups = list(row.groups.all())
                if row.subject_id is None:
                    label = (row.subject_label or "").strip()
                    if label and label not in unlinked:
                        unlinked.append(label)
                    continue
                for unit in row_groups:
                    link(unit_group(unit), row.subject)
                if not row_groups:
                    subjects.setdefault(str(row.subject_id), row.subject)

    for cohort in _legacy_cohorts(user, organization):
        group = SubmissionGroup(key=str(cohort.pk), name=cohort.name, cohort=cohort)
        groups.setdefault(group.key, group)
        for subject in cohort.subjects.all():
            link(group, subject)

    sources.groups = sorted(groups.values(), key=lambda g: g.name.casefold())
    sources.subjects = sorted(subjects.values(), key=lambda s: (s.name or s.code or "").casefold())
    sources.group_subjects = {
        key: sorted(bucket.values(), key=lambda s: (s.name or s.code or "").casefold())
        for key, bucket in by_group.items()
    }
    sources.notices = _notices(sources, assignments, period, unlinked)
    return sources


def _notices(sources, assignments, period, unlinked) -> list[str]:
    """Fənn/qrup seçilə bilməyəndə AYDIN səbəb (müəllim nə etməli olduğunu bilsin)."""
    notices = []
    if period is None:
        notices.append(
            pgettext(_CTX, "Təşkilatda cari semestr təyin olunmayıb — fənlər dərs yükünüzdən göstərilə bilmir.")
        )
        return notices
    if unlinked:
        notices.append(
            pgettext(
                _CTX,
                "Bu fənlər dərs yükünüzdə var, amma fənn kataloquna bağlanmayıb: {names}. Kafedraya müraciət edin.",
            ).format(names=", ".join(unlinked[:5]))
        )
    if sources.subjects:
        return notices
    if assignments is not None:
        pending = (
            assignments.exclude(row__task__status__in=APPROVED_TASK_STATUSES)
            .filter(Q(row__period=period) | Q(row__task__academic_year=period.academic_year))
            .exists()
        )
        if pending:
            notices.append(
                pgettext(
                    _CTX,
                    "Dərs yükünüz kafedra tərəfindən hələ təsdiqlənməyib — təsdiqdən sonra fənləriniz burada görünəcək.",
                )
            )
            return notices
        if assignments.filter(row__task__status__in=APPROVED_TASK_STATUSES).exists():
            notices.append(
                pgettext(
                    _CTX,
                    "Cari semestrdə ({period}) dərs yükünüz yoxdur. Fənlər yalnız cari semestr üzrə göstərilir.",
                ).format(period=_period_label(period))
            )
            return notices
    notices.append(
        pgettext(
            _CTX,
            "Cari semestrdə ({period}) sizin adınıza təsdiqlənmiş dərs yükü və ya jurnal tapılmadı. "
            "Fənlər dərs yükündən gəlir — fənn qovluğu yaratmaq lazım deyil; kafedra müdirinə müraciət edin.",
        ).format(period=_period_label(period))
    )
    return notices


def resolve_unit_ids(raw_values) -> list[str]:
    """Formadan gələn ``u:<uuid>`` açarlarından UUID-ləri ayırır (yalnız formatca keçərlilər)."""
    import uuid

    out = []
    for value in raw_values or ():
        text = str(value or "").strip()
        if not text.startswith(UNIT_PREFIX):
            continue
        try:
            out.append(str(uuid.UUID(text[len(UNIT_PREFIX) :])))
        except ValueError:
            continue
    return out


__all__ = [
    "SubmissionGroup",
    "SubmissionSources",
    "UNIT_PREFIX",
    "resolve_unit_ids",
    "subject_label",
    "teacher_submission_sources",
]
