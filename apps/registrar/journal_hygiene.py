"""«Jurnal təmizliyi» — AŞKARLAMA qatı (yalnız oxu; sahib 2026-10-10).

Sahib: «jurnalda çıxarılmış, yəni oxumayan çıxmış amma jurnalda adı qalan tələbələri tapmaq; qrupdakı
tələbələrə keçmədiyi dərs düşüb sistemdən nəticələrinə — onu ordan təyin edib çıxarmaq, balda yoxdu heç
nə boş görünür».

Üç kateqoriya, hər biri TƏK querysetdir (``Exists`` alt-sorğuları, N+1 yoxdur):

(a) **Ayrılmış tələbə** (``left_student``) — ``enrolled`` qeydiyyat, aktiv açılış, cari və ya gələcək dövr,
    jurnal bağlı DEYİL; tələbə isə oxumur: hesab arxivdədir, akademik status xaric / akademik məzuniyyət /
    məzun, qeyd passivdir, oxu müddəti bitib (``study_state`` qaydası) və ya akademik qeydi ümumiyyətlə yoxdur.
    Tələbənin HƏR HANSI qeydi hələ «oxuyur»sa sətir düşmür. Ayrıca «köçürülüb» statusu kodda YOXDUR — qrupu
    dəyişmiş tələbənin öz-qrup sətri ``group_changed`` etiketi ilə işarələnir (tək başına meyar deyil:
    alt-qrup bölgüsündə ana qrupun sətirləri qanunidir).
(b) **Boş fənn** (``empty_subject``) — ``dropped`` olmayan, alt-qrup əlavəsi olmayan (``source_group`` boş),
    qayıb saatı 0 və heç bir sübutu olmayan qeydiyyat (:func:`evidence_sources`). Gedən semestrdə hər sətir
    hələ boşdur, ona görə sətir yalnız dövr bitibsə / jurnal bağlıdırsa və ya «sərt» mənbə varsa düşür:
    açılış ləğv olunub və ya qrup seçmə fənni dəyişib. Mənbə etiketləri: ``cancelled_offering``,
    ``replaced_elective``, ``not_in_curriculum``, ``legacy_no_result``; heç biri yoxdursa ``unexplained``.
    Güc: açılışda heç bir dərs yoxdur VƏ qrupda heç kimin datası yoxdur → ``strong``; qalan hamısı
    ``review`` (yalnız yoxlama üçün — məs. sinif yoldaşlarının datası var).
(c) **Keçirilməyən fənn** (``not_held``, sahib 2026-10-11) — açılış səviyyəli: dövr bitib, ≥2 tələbə, heç
    kimin imtahan («çıxış») balı yoxdur, yalnız giriş balı və ya heç nə. Qayda və güc:
    :mod:`apps.registrar.journal_hygiene_not_held`.

Qeydiyyat SİLİNMİR: qərarlar :mod:`apps.registrar.journal_hygiene_actions`-dadır.
"""

from __future__ import annotations

import uuid

from django.apps import apps as django_apps
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from . import journal_hygiene_not_held as not_held
from .models import (
    AcademicStatus,
    ComponentScore,
    ComponentScoreCorrection,
    CourseWork,
    CourseWorkCorrection,
    CriterionScore,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    ExamScoreEntry,
    FinalGrade,
    GroupElectiveChoice,
    GuestRosterDocument,
    HygieneCategory,
    JournalCorrection,
    LegacyGradeFact,
    Lesson,
    LessonMark,
    ResitRecord,
    SelfWorkCorrection,
    SelfWorkMark,
    StudentAcademicRecord,
)

_CTX = "registrar.journal_hygiene"

LEFT = HygieneCategory.LEFT_STUDENT.value
EMPTY = HygieneCategory.EMPTY_SUBJECT.value
#: (c) Keçirilməyən fənn — açılış səviyyəli qayda :mod:`apps.registrar.journal_hygiene_not_held`-dədir.
NOT_HELD = not_held.NOT_HELD
CATEGORIES = (LEFT, EMPTY, NOT_HELD)

# ── (a) səbəblər — güclüdən zəifə ────────────────────────────────────────────
REASON_ARCHIVED = "archived"
REASON_EXPELLED = "expelled"
REASON_ACADEMIC_LEAVE = "academic_leave"
REASON_GRADUATED = "graduated"
REASON_INACTIVE = "inactive_record"
REASON_PERIOD_ENDED = "period_ended"
REASON_NO_RECORD = "no_record"
LEFT_REASONS = (
    REASON_ARCHIVED,
    REASON_EXPELLED,
    REASON_ACADEMIC_LEAVE,
    REASON_GRADUATED,
    REASON_INACTIVE,
    REASON_PERIOD_ENDED,
    REASON_NO_RECORD,
)
#: Rəsmi/qəti sübutlu səbəblər; «oxu müddəti bitib» və «qeyd yoxdur» yalnız yoxlama siqnalıdır.
STRONG_LEFT_REASONS = frozenset(LEFT_REASONS[:5])
TAG_GROUP_CHANGED = "group_changed"

# ── (b) mənbə etiketləri ─────────────────────────────────────────────────────
SOURCE_CANCELLED = "cancelled_offering"
SOURCE_REPLACED = "replaced_elective"
SOURCE_NOT_IN_CURRICULUM = "not_in_curriculum"
SOURCE_LEGACY = "legacy_no_result"
SOURCE_UNEXPLAINED = "unexplained"
EMPTY_SOURCES = (SOURCE_CANCELLED, SOURCE_REPLACED, SOURCE_NOT_IN_CURRICULUM, SOURCE_LEGACY, SOURCE_UNEXPLAINED)
STRENGTH_STRONG = "strong"
STRENGTH_REVIEW = "review"

#: Köçürmənin «qəbul ili bilinmir» sentineli — ``accounts.services.people.study_state`` ilə EYNİ
#: (registrar → accounts importu modul-sərhəd dövrü yaradardı, ona görə dəyər təkrarlanır).
UNKNOWN_ADMISSION_YEAR = 1950

LABELS = {
    REASON_ARCHIVED: pgettext_lazy(_CTX, "Hesab arxivdədir"),
    REASON_EXPELLED: pgettext_lazy(_CTX, "Xaric olunub"),
    REASON_ACADEMIC_LEAVE: pgettext_lazy(_CTX, "Akademik məzuniyyətdədir"),
    REASON_GRADUATED: pgettext_lazy(_CTX, "Məzun olub"),
    REASON_INACTIVE: pgettext_lazy(_CTX, "Akademik qeyd passivdir"),
    REASON_PERIOD_ENDED: pgettext_lazy(_CTX, "Oxu müddəti bitib"),
    REASON_NO_RECORD: pgettext_lazy(_CTX, "Akademik qeydi yoxdur"),
    TAG_GROUP_CHANGED: pgettext_lazy(_CTX, "Qrupu dəyişib"),
    SOURCE_CANCELLED: pgettext_lazy(_CTX, "Açılış ləğv olunub"),
    SOURCE_REPLACED: pgettext_lazy(_CTX, "Seçmə fənn dəyişdirilib"),
    SOURCE_NOT_IN_CURRICULUM: pgettext_lazy(_CTX, "Tədris planında yoxdur"),
    SOURCE_LEGACY: pgettext_lazy(_CTX, "Köhnə sistemdə nəticə yoxdur"),
    SOURCE_UNEXPLAINED: pgettext_lazy(_CTX, "Mənbəsi bəlli deyil"),
    not_held.REASON_NOT_HELD: pgettext_lazy(_CTX, "Fənn keçirilməyib — qrupda heç kimin imtahan balı yoxdur"),
    not_held.TAG_ENTRY_ONLY: pgettext_lazy(_CTX, "Yalnız giriş balı"),
    not_held.TAG_NO_SCORES: pgettext_lazy(_CTX, "Heç bir bal yoxdur"),
    not_held.TAG_TAUGHT: pgettext_lazy(_CTX, "Dərs / kollokvium izi var"),
    STRENGTH_STRONG: pgettext_lazy(_CTX, "Güclü siqnal"),
    STRENGTH_REVIEW: pgettext_lazy(_CTX, "Yoxlanmalı"),
}

#: Filtr açarları — allow-list (naməlum açar səssizcə nəzərə alınmır).
FILTER_KEYS = ("period", "faculty", "group", "category", "q")


def label(code) -> str:
    return str(LABELS.get(code, code or ""))


def current_academic_year_start(now=None) -> int:
    """Tədris ili sentyabrda başlayır (``study_state.current_academic_year_start`` ilə eyni)."""
    now = now or timezone.localtime()
    return now.year if now.month >= 9 else now.year - 1


def parse_uuid(value):
    """Etibarlı UUID mətni və ya ``None`` (yanlış id 500 əvəzinə boş nəticə verir)."""
    try:
        return uuid.UUID(str(value or "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


# ── Sübut mənbələri — boşluq meyarının TƏK siyahısı ──────────────────────────


def _real_final_grade() -> Q:
    """Boş ``FinalGrade`` sətri (yalnız yaradılıb) sübut deyil; bal / bonus / rəy / dərc sübutdur."""
    return Q(exam_score__isnull=False) | ~Q(bonus=0) | ~Q(comment="") | Q(is_published=True)


def evidence_sources() -> list:
    """``(açar, model, qeydiyyat sahəsi, əlavə süzgəc)`` — aşkarlama, önizləmə və tətbiq EYNİ siyahını işlədir.

    Fənn qovluğu təhvili (``subject_folder.Submission``) app registry ilə alınır — registrar o modulu
    statik import etmir (modul-sərhəd qapısı); quraşdırılmayıbsa sadəcə atlanır.
    """
    sources = [
        ("marks", LessonMark, "enrollment_id", None),
        ("components", ComponentScore, "enrollment_id", None),
        ("criteria", CriterionScore, "enrollment_id", None),
        ("selfwork", SelfWorkMark, "enrollment_id", None),
        ("coursework", CourseWork, "enrollment_id", None),
        ("resits", ResitRecord, "enrollment_id", None),
        ("exam_entries", ExamScoreEntry, "enrollment_id", None),
        ("legacy_facts", LegacyGradeFact, "enrollment_id", None),
        ("finals", FinalGrade, "enrollment_id", _real_final_grade()),
        ("journal_corrections", JournalCorrection, "enrollment_ref", None),
        ("selfwork_corrections", SelfWorkCorrection, "enrollment_id", None),
        ("coursework_corrections", CourseWorkCorrection, "enrollment_id", None),
        ("component_corrections", ComponentScoreCorrection, "enrollment_id", None),
        ("guest_documents", GuestRosterDocument, "enrollment_id", None),
        # Köçürmə xələfi: datası sələf qeydiyyatdadır, xələf «boş» görünsə də fantom deyil.
        ("predecessors", Enrollment, "superseded_by_id", None),
    ]
    try:
        submission = django_apps.get_model("subject_folder", "Submission")
    except LookupError:  # pragma: no cover — fənn qovluğu quraşdırılmayıb
        submission = None
    if submission is not None:
        sources.append(("folder_submissions", submission, "enrollment_id", None))
    return sources


def _source_queryset(model, field, extra, value):
    queryset = model.objects.filter(**{field: value})
    return queryset.filter(extra) if extra is not None else queryset


def evidence_q(ref: str = "pk") -> Q:
    """Qeydiyyatın (``OuterRef(ref)``) HƏR HANSI sübutu varmı — ``Exists`` alt-sorğularının OR-u.

    SELECT siyahısı üçündür (kiçik dəstlər). Böyük dəsti süzmək üçün :func:`no_evidence_filters`
    işlədilir: ayrı-ayrı ``NOT EXISTS`` şərtlərini PostgreSQL anti-join-ə çevirir (OR-un inkarını yox).
    """
    condition = Q()
    for _key, model, field, extra in evidence_sources():
        condition |= Q(Exists(_source_queryset(model, field, extra, OuterRef(ref))))
    return condition


def no_evidence_filters(ref: str = "pk") -> list:
    """``filter(*no_evidence_filters())`` — hər mənbə üçün ayrıca ``NOT EXISTS`` (anti-join)."""
    return [
        ~Exists(_source_queryset(model, field, extra, OuterRef(ref))) for _k, model, field, extra in evidence_sources()
    ]


def offering_data_q(ref: str = "offering_id") -> Q:
    """Açılışda HƏR HANSI qeydiyyatın datası varmı (güc qiyməti üçün; FK-lı mənbələr + qayıb saatı)."""
    condition = Q(Exists(Enrollment.objects.filter(offering_id=OuterRef(ref), absence_hours__gt=0)))
    for _key, model, field, extra in evidence_sources():
        if field != "enrollment_id":
            continue
        queryset = model.objects.filter(enrollment__offering_id=OuterRef(ref))
        condition |= Q(Exists(queryset.filter(extra) if extra is not None else queryset))
    return condition


# ── (a) Ayrılmış tələbələr ───────────────────────────────────────────────────


def _profile_model():
    return django_apps.get_model("accounts", "UserProfile")


def _records():
    return StudentAcademicRecord.objects.filter(
        organization_id=OuterRef("organization_id"), student_id=OuterRef("student_id")
    )


def _studying_records(year_start: int):
    """«Həqiqətən oxuyur» qeydləri — ``study_state`` qaydası: rəsmi status + müddət bitməyib."""
    ects = Case(When(program__ects_total__gt=0, then=F("program__ects_total")), default=Value(240))
    return (
        _records()
        .filter(status=AcademicStatus.ENROLLED, is_active=True)
        .annotate(jh_end=ExpressionWrapper(F("admission_year") + (ects + 59) / 60, output_field=IntegerField()))
        .filter(Q(admission_year=UNKNOWN_ADMISSION_YEAR) | Q(jh_end__gt=year_start))
    )


def left_reason_expression(*, now=None):
    """Hər ``enrolled`` sətir üçün səbəb kodu; tələbə oxuyursa ``""`` (sətir düşmür)."""
    records = _records()
    archived = _profile_model().objects.filter(user_id=OuterRef("student_id"), access_state="archived")
    return Case(
        When(Exists(archived), then=Value(REASON_ARCHIVED)),
        When(Exists(_studying_records(current_academic_year_start(now))), then=Value("")),
        When(Exists(records.filter(status=AcademicStatus.EXPELLED)), then=Value(REASON_EXPELLED)),
        When(Exists(records.filter(status=AcademicStatus.ACADEMIC_LEAVE)), then=Value(REASON_ACADEMIC_LEAVE)),
        When(Exists(records.filter(status=AcademicStatus.GRADUATED)), then=Value(REASON_GRADUATED)),
        When(Exists(records.filter(status=AcademicStatus.ENROLLED, is_active=False)), then=Value(REASON_INACTIVE)),
        When(Exists(records), then=Value(REASON_PERIOD_ENDED)),
        default=Value(REASON_NO_RECORD),
        output_field=CharField(),
    )


def open_period_q(*, today=None) -> Q:
    """Cari və ya gələcək (aktiv) dövr — gedən/gələn semestrin jurnalı."""
    today = today or timezone.localdate()
    return Q(offering__period__is_active=True) & (
        Q(offering__period__is_current=True) | Q(offering__period__start_date__gt=today)
    )


def left_candidates(organization, *, today=None, now=None):
    """(a) — annotasiyalı queryset: ``jh_reason``, ``jh_strong``, ``jh_has_evidence``, ``jh_group_changed``."""
    group_member = _records().filter(group_id=OuterRef("offering__group_id"))
    queryset = (
        Enrollment.objects.filter(
            organization=organization, status=Enrollment.Status.ENROLLED, offering__is_active=True
        )
        .filter(open_period_q(today=today))
        .exclude(offering__assessment_scheme__is_published=True)
        .annotate(jh_reason=left_reason_expression(now=now))
        .exclude(jh_reason="")
    )
    return queryset.annotate(
        jh_strong=Case(When(jh_reason__in=STRONG_LEFT_REASONS, then=True), default=False, output_field=BooleanField()),
        jh_has_evidence=ExpressionWrapper(Q(absence_hours__gt=0) | evidence_q(), output_field=BooleanField()),
        # Qeydi olan, amma heç biri açılışın qrupunda olmayan öz-qrup sətri (qeydsiz tələbə etiketlənmir).
        jh_group_changed=ExpressionWrapper(
            Q(source_group__isnull=True, offering__group__isnull=False) & Q(Exists(_records())) & ~Exists(group_member),
            output_field=BooleanField(),
        ),
    )


# ── (b) Boş fənlər ───────────────────────────────────────────────────────────


def _replaced_elective_q() -> Q:
    """Qrupun həmin blok üçün CARİ seçimi BAŞQA fənndir (sətir köhnə seçimdən qalıb)."""
    blocks = CurriculumSubject.objects.filter(
        organization_id=OuterRef(OuterRef("organization_id")),
        subject_id=OuterRef(OuterRef("offering__subject_id")),
        is_elective=True,
    ).values("elective_group")
    choice = GroupElectiveChoice.objects.filter(
        organization_id=OuterRef("organization_id"),
        group_id=OuterRef("offering__group_id"),
        period_id=OuterRef("offering__period_id"),
        elective_group__in=Subquery(blocks),
    ).exclude(chosen_subject_id=OuterRef("offering__subject_id"))
    return Q(kind=EnrollmentKind.ELECTIVE) & Q(Exists(choice))


def _in_curriculum_q() -> Q:
    return Q(
        Exists(
            CurriculumSubject.objects.filter(
                subject_id=OuterRef("offering__subject_id"),
                curriculum__student_records__student_id=OuterRef("student_id"),
                curriculum__student_records__organization_id=OuterRef("organization_id"),
            )
        )
    )


def legacy_offering_q() -> Q:
    """Köçürmə möhürü (``exam_eligibility._migrated_offering_ids`` ilə eyni açarlar)."""
    try:
        entity_map = django_apps.get_model("legacy_import", "LegacyEntityMap")
    except LookupError:  # pragma: no cover — legacy_import quraşdırılmayıb
        return Q(pk__in=[])
    return Q(
        Exists(
            entity_map.objects.filter(
                entity_type="course_offering",
                state="migrated",
                target_pk=Cast(OuterRef("offering_id"), output_field=CharField()),
            )
        )
    )


def closed_period_q(*, today=None) -> Q:
    """Dövr bitib və ya jurnal bağlanıb — boşluq artıq «hələ başlamayıb» demək deyil."""
    today = today or timezone.localdate()
    return Q(offering__period__end_date__lt=today) | Q(offering__assessment_scheme__is_published=True)


def _flag(condition) -> ExpressionWrapper:
    return ExpressionWrapper(condition, output_field=BooleanField())


def empty_candidates(organization, *, today=None):
    """(b) — annotasiyalı queryset: mənbə bayraqları (``jh_<etiket>``), ``jh_closed``, ``jh_strong``."""
    base = (
        Enrollment.objects.filter(organization=organization, source_group__isnull=True, absence_hours=0)
        .exclude(status=Enrollment.Status.DROPPED)
        .filter(*no_evidence_filters())
        .annotate(
            jh_cancelled=_flag(Q(offering__is_active=False)),
            jh_replaced=_flag(_replaced_elective_q()),
            jh_closed=_flag(closed_period_q(today=today)),
        )
        .filter(Q(jh_closed=True) | Q(jh_cancelled=True) | Q(jh_replaced=True))
    )
    lessons = Lesson.objects.filter(offering_id=OuterRef("offering_id"))
    return base.annotate(
        jh_not_in_curriculum=_flag(~_in_curriculum_q()),
        jh_legacy=_flag(legacy_offering_q()),
        jh_strong=Case(
            When(Exists(lessons), then=False),
            When(offering_data_q(), then=False),
            default=True,
            output_field=BooleanField(),
        ),
    )


#: Mənbə etiketi → annotasiya adı (``unexplained`` = heç biri).
SOURCE_FLAGS = {
    SOURCE_CANCELLED: "jh_cancelled",
    SOURCE_REPLACED: "jh_replaced",
    SOURCE_NOT_IN_CURRICULUM: "jh_not_in_curriculum",
    SOURCE_LEGACY: "jh_legacy",
}


def _unexplained_q() -> Q:
    return Q(**{flag: False for flag in SOURCE_FLAGS.values()})


# ── Süzgəclər, sıralama, saylar ──────────────────────────────────────────────


def _faculty_q(organization, faculty_id) -> Q:
    org_unit = django_apps.get_model("organizations", "OrgUnit")
    faculty = org_unit.objects.filter(organization=organization, pk=faculty_id).only("id", "path").first()
    if faculty is None:
        return Q(pk__in=[])
    prefix = f"{faculty.path or faculty.pk}/"
    return Q(offering__group_id=faculty.pk) | Q(offering__group__path__startswith=prefix)


def _category_q(category: str, code: str):
    if category == NOT_HELD:
        condition = not_held.category_q(code)
        if condition is not None:
            return condition
    elif category == LEFT:
        if code in LEFT_REASONS:
            return Q(jh_reason=code)
        if code == TAG_GROUP_CHANGED:
            return Q(jh_group_changed=True)
    else:
        if code in SOURCE_FLAGS:
            return Q(**{SOURCE_FLAGS[code]: True})
        if code == SOURCE_UNEXPLAINED:
            return _unexplained_q()
    if code in (STRENGTH_STRONG, STRENGTH_REVIEW):
        return Q(jh_strong=code == STRENGTH_STRONG)
    return None


def apply_filters(queryset, organization, category: str, filters: dict):
    """Allow-list süzgəcləri; yanlış id səssizcə nəzərə alınmır (heç vaxt 500 vermir)."""
    from core.search_text import tolerant_q

    filters = filters or {}
    period = parse_uuid(filters.get("period"))
    if period:
        queryset = queryset.filter(offering__period_id=period)
    faculty = parse_uuid(filters.get("faculty"))
    if faculty:
        queryset = queryset.filter(_faculty_q(organization, faculty))
    group = parse_uuid(filters.get("group"))
    if group:
        queryset = queryset.filter(offering__group_id=group)
    condition = _category_q(category, str(filters.get("category") or "").strip())
    if condition is not None:
        queryset = queryset.filter(condition)
    search = tolerant_q(
        str(filters.get("q") or "")[:100],
        fields=(
            "student__first_name",
            "student__last_name",
            "student__username",
            "offering__subject__name",
            "offering__subject__code",
        ),
    )
    if search is not None:
        queryset = queryset.filter(search)
    return queryset


def candidates(organization, category: str, filters=None, *, today=None):
    """Süzgəclənmiş, sıralanmış kateqoriya querysetı (güclü siqnal əvvəl)."""
    if category == LEFT:
        queryset = left_candidates(organization, today=today)
        order = ("-jh_strong", "offering__group__name", "offering__subject__code")
    elif category == EMPTY:
        queryset = empty_candidates(organization, today=today)
        order = ("-jh_strong", "-offering__period__start_date", "offering__group__name", "offering__subject__code")
    elif category == NOT_HELD:
        queryset = not_held.candidates(organization, today=today)
        # Açılışın sətirləri yan-yana (``offering_id``): «hamısını seç» TAM açılışları götürür.
        order = ("-jh_strong", "-offering__period__start_date", "offering__group__name", "offering__subject__code")
        order = (*order, "offering_id")
    else:
        return Enrollment.objects.none()
    queryset = apply_filters(queryset, organization, category, filters)
    return queryset.order_by(*order, "student__last_name", "student__first_name", "pk")


def counts(queryset, category: str) -> dict:
    """BİR aqreqat sorğusu: cəm, güclü siqnal və hər səbəb/etiket üzrə say."""
    if category == NOT_HELD:
        return not_held.counts(queryset)
    aggregates = {"total": Count("pk"), "strong": Count("pk", filter=Q(jh_strong=True))}
    if category == LEFT:
        for code in LEFT_REASONS:
            aggregates[code] = Count("pk", filter=Q(jh_reason=code))
        aggregates[TAG_GROUP_CHANGED] = Count("pk", filter=Q(jh_group_changed=True))
        aggregates["empty"] = Count("pk", filter=Q(jh_has_evidence=False))
    else:
        for code, flag in SOURCE_FLAGS.items():
            aggregates[code] = Count("pk", filter=Q(**{flag: True}))
        aggregates[SOURCE_UNEXPLAINED] = Count("pk", filter=_unexplained_q())
    totals = queryset.order_by().aggregate(**aggregates)
    return {key: int(value or 0) for key, value in totals.items()}


def category_options(category: str) -> list:
    """Kateqoriya süzgəcinin seçimləri (dəyər + etiket)."""
    if category == NOT_HELD:
        codes = not_held.NOT_HELD_TAGS
    else:
        codes = (*LEFT_REASONS, TAG_GROUP_CHANGED) if category == LEFT else EMPTY_SOURCES
    return [{"value": code, "label": label(code)} for code in (*codes, STRENGTH_STRONG, STRENGTH_REVIEW)]


__all__ = [
    "CATEGORIES",
    "EMPTY",
    "EMPTY_SOURCES",
    "FILTER_KEYS",
    "LEFT",
    "LEFT_REASONS",
    "NOT_HELD",
    "SOURCE_FLAGS",
    "STRENGTH_REVIEW",
    "STRENGTH_STRONG",
    "STRONG_LEFT_REASONS",
    "TAG_GROUP_CHANGED",
    "apply_filters",
    "candidates",
    "category_options",
    "closed_period_q",
    "counts",
    "current_academic_year_start",
    "empty_candidates",
    "evidence_q",
    "evidence_sources",
    "label",
    "left_candidates",
    "left_reason_expression",
    "legacy_offering_q",
    "no_evidence_filters",
    "offering_data_q",
    "open_period_q",
    "parse_uuid",
]
