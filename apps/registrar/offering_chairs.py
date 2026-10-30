"""Açılışın (``CourseOffering``) KAFEDRASI — «Kafedra» süzgəclərinin TƏK tərifi (sahib, 2026-10-25).

İstifadə edənlər: «Keçilmiş dərslər» (``lessons_log_units.kafedra_lesson_q`` / ``kafedra_slot_q`` və
kafedra seçim siyahısı), elektron jurnal siyahısı ``/jurnal/`` (``journal_list_query.apply_unit_filters``)
və kafedra kökü olan ``journal.view`` əhatəsi (``journal_scope``). Hamısı bu modulu çağırır — tərif
bir yerdədir.

TƏRİF — açılış o kafedraya aiddir ki, FƏNNİN TƏDRİS YÜKÜ ona aiddir (müəllimin ştatı yox):

1. **Dərs yükü sətri** — açılışı əhatə edən tapşırıq sətri (eyni fənn + semestr + sətrin qrupları
   arasında açılışın qrupu; ləğv edilmiş sənəd xaric) → ``TeachingTask.chair``.
2. Yoxdursa **fənnin aparıcı kafedrası** (``Subject.chair_unit``).
3. Yoxdursa **fənnin yükü** başqa semestrlərdə (köçürülmüş açılışlar): fənnin tapşırıq sətirlərinin
   kafedraları; bir neçədirsə, açılışın müəllimi tədris üzvü olduğu kafedraya daralır (yoxsa hamısı).
4. Heç biri yoxdursa (yükdə izi olmayan köhnə fənn): qrup kafedranın alt-ağacındadırsa həmin kafedra
   (seed quruluşu), yoxsa müəllimin ŞTAT kafedrası — aktiv, TƏDRİS rollu kafedra üzvlüyü; əsas
   (``is_primary``) üzvlük varsa yalnız o.

NİYƏ (prod, 2026-10-25): əvvəlki tərif «müəllim kafedranın İSTƏNİLƏN aktiv üzvüdür VƏ YA fənn
kafedranındır» idi. Yer kadastrı kafedrasının ştat müəllimi «Mülki müdafiə» aparır; dərs yükü
faylı yüklənəndə (2026-10-23) o, Proqramlaşdırma kafedrasının yükündə də saat aldığı üçün həmin
kafedraya da (əlavə) üzv yazıldı — və onun BÜTÜN «Mülki müdafiə» dərsləri Proqramlaşdırma
süzgəcinə düşdü. Eyni səbəblə müəllimin rol fərqi olmadan istənilən bölmə üzvlüyü (məs. «Beynəlxalq
şöbə») də «kafedra» seçimi kimi çıxırdı.

Sorğu sayı sətir sayından asılı deyil (4–5 toplu SELECT); həll Python-da, tək keçidlə.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Q

from core.constants import OrgUnitType

CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
#: Kafedra üzvlüyündə «tədris rolu» (ştat müəllimi) — inzibati üzvlüklər (``member``, ``hr``…) sayılmır.
TEACHING_ROLE_NAMES = (
    "teacher",
    "assistant",
    "assistant_teacher",
    "lab_assistant",
    "instructor",
    "professor",
    "associate_professor",
    "senior_instructor",
    "chair_head",
)
#: ``workload.constants.TaskStatus.CANCELLED`` — registrar → workload Python import kənarı yaranmasın.
CANCELLED_TASK = "cancelled"


def _model(app_label, name):
    return django_apps.get_model(app_label, name)


def _nearest(path, known) -> str | None:
    """``path``-in (özü daxil) ``known``-dakı ən yaxın əcdadı."""
    for segment in reversed((path or "").split("/")):
        if segment in known:
            return segment
    return None


def _chair_units(organization_id) -> dict:
    """Təşkilatın kafedra tipli bölmələri: ``{id: path}``."""
    from apps.organizations.public import narrow_kafedra_rows

    rows = (
        _model("organizations", "OrgUnit")
        .objects.filter(organization_id=organization_id, unit_type__in=CHAIR_TYPES)
        .values_list("id", "path", "unit_type")
    )
    # İnzibati şöbə (``department``) kafedra deyil — təşkilatda ``chair`` varsa (bax ``organizations.kafedra_units``).
    return {str(uid): path or "" for uid, path, _type in narrow_kafedra_rows(rows, lambda row: row[2])}


def _load_index(organization_id, offerings):
    """``({(fənn, semestr, qrup): {kafedra}}, {fənn: {kafedra}})`` — iki toplu sorğu."""
    row_model = _model("workload", "TeachingTaskRow")
    through = row_model.groups.through
    subjects = offerings.order_by().values("subject_id")
    exact: dict = defaultdict(set)
    by_subject: dict = defaultdict(set)
    for subject_id, chair_id in (
        row_model.objects.filter(organization_id=organization_id, subject_id__in=subjects)
        .exclude(task__status=CANCELLED_TASK)
        .values_list("subject_id", "task__chair_id")
        .distinct()
    ):
        by_subject[subject_id].add(str(chair_id))
    for subject_id, period_id, group_id, chair_id in (
        through.objects.filter(
            teachingtaskrow__organization_id=organization_id, teachingtaskrow__subject_id__in=subjects
        )
        .exclude(teachingtaskrow__task__status=CANCELLED_TASK)
        .values_list(
            "teachingtaskrow__subject_id", "teachingtaskrow__period_id", "orgunit_id", "teachingtaskrow__task__chair_id"
        )
        .distinct()
    ):
        exact[(subject_id, period_id, group_id)].add(str(chair_id))
    return exact, by_subject


def _staff_index(organization_id, offerings, chairs) -> tuple[dict, dict]:
    """``({müəllim: bütün tədris kafedraları}, {müəllim: ştat kafedraları})`` — bir sorğu.

    Üzvlüyün bölməsi kafedranın alt-bölməsidirsə ən yaxın kafedra götürülür. Ştat = ``is_primary``
    tədris üzvlüyünün kafedrası; belə üzvlük yoxdursa bütün tədris kafedraları."""
    every: dict = defaultdict(set)
    primary: dict = defaultdict(set)
    for user_id, path, is_primary in (
        _model("organizations", "Membership")
        .objects.filter(
            organization_id=organization_id,
            is_active=True,
            role__is_active=True,
            role__name__in=TEACHING_ROLE_NAMES,
            scope_unit__isnull=False,
            user_id__in=offerings.order_by().exclude(instructor_id=None).values("instructor_id"),
        )
        .values_list("user_id", "scope_unit__path", "is_primary")
    ):
        chair = _nearest(path, chairs)
        if chair is None:
            continue
        every[user_id].add(chair)
        if is_primary:
            primary[user_id].add(chair)
    staff = {user_id: frozenset(primary.get(user_id) or found) for user_id, found in every.items()}
    return every, staff


def offering_chairs(offerings, organization_id) -> dict:
    """``{açılış_pk: frozenset(kafedra_id)}`` — ``offerings`` queryset-indəki hər açılış üçün (tərif: modul başlığı).

    Kafedrası təyin oluna bilməyən açılış nəticədə boş çoxluqla qalır (heç bir kafedra süzgəcinə düşmür)."""
    offerings = offerings.order_by()
    chairs = _chair_units(organization_id)
    exact, by_subject = _load_index(organization_id, offerings)
    every, staff = _staff_index(organization_id, offerings, chairs)
    result = {}
    for pk, subject_id, period_id, group_id, group_path, instructor_id, subject_chair in offerings.values_list(
        "pk", "subject_id", "period_id", "group_id", "group__path", "instructor_id", "subject__chair_unit_id"
    ):
        found = exact.get((subject_id, period_id, group_id))
        if not found and subject_chair:
            found = {str(subject_chair)}
        if not found and subject_id in by_subject:
            candidates = by_subject[subject_id]
            found = (candidates & every.get(instructor_id, set())) or candidates
        if not found:
            group_chair = _nearest(group_path, chairs)
            found = {group_chair} if group_chair else staff.get(instructor_id, frozenset())
        result[pk] = frozenset(found)
    return result


def official_offering_chairs(offerings, organization_id) -> dict:
    """Exact workload or explicit subject chair only; no employment/student-group inference.

    For appeal PII access an unknown owner fails closed. Historical workload in
    another period, staff membership and the student's faculty are not evidence.
    """
    offerings = offerings.filter(organization_id=organization_id).order_by()
    row_model = _model("workload", "TeachingTaskRow")
    released = Q(teachingtaskrow__task__status__in=("approved", "distributed", "amended")) | Q(
        teachingtaskrow__task__status="distributing", teachingtaskrow__task__submitted_at__isnull=False
    )
    exact = defaultdict(set)
    for subject_id, period_id, group_id, chair_id in (
        row_model.groups.through.objects.filter(
            teachingtaskrow__organization_id=organization_id,
            teachingtaskrow__task__organization_id=organization_id,
            teachingtaskrow__subject_id__in=offerings.values("subject_id"),
        )
        .filter(released)
        .values_list(
            "teachingtaskrow__subject_id", "teachingtaskrow__period_id", "orgunit_id", "teachingtaskrow__task__chair_id"
        )
    ):
        exact[(subject_id, period_id, group_id)].add(str(chair_id))
    return {
        pk: frozenset(exact.get((subject_id, period_id, group_id)) or ({str(chair)} if chair else set()))
        for pk, subject_id, period_id, group_id, chair in offerings.values_list(
            "pk", "subject_id", "period_id", "group_id", "subject__chair_unit_id"
        )
    }


def chair_paths(organization_id, chair_ids) -> dict:
    """``{kafedra_id: (ad, path)}`` — seçim siyahısı və alt-ağac yoxlaması üçün (bir sorğu)."""
    if not chair_ids:
        return {}
    rows = (
        _model("organizations", "OrgUnit")
        .objects.filter(organization_id=organization_id, pk__in=list(chair_ids))
        .values_list("id", "name", "path")
    )
    return {str(uid): (name, path or "") for uid, name, path in rows}


def _within(chair_id, path, unit) -> bool:
    return chair_id == str(unit.pk) or path.startswith(f"{unit.path}/")


def offering_ids_in_unit(unit, offerings) -> list:
    """``offerings``-dən kafedrası ``unit``-in özü və ya alt-bölməsi olan açılışların pk-ları."""
    mapping = offering_chairs(offerings, unit.organization_id)
    known = chair_paths(unit.organization_id, set().union(*mapping.values()) if mapping else set())
    inside = {chair_id for chair_id, (_name, path) in known.items() if _within(chair_id, path, unit)}
    return [pk for pk, found in mapping.items() if found & inside]


def _offerings_for(unit, within, offering):
    """Həll olunacaq açılışlar: ``within`` (açılış / dərs / slot queryset-i) daraldır, yoxsa təşkilatın hamısı."""
    model = _model("registrar", "CourseOffering")
    base = model.objects.filter(organization_id=unit.organization_id)
    if within is None:
        return base
    if offering:
        return base.filter(pk__in=within.order_by().values(f"{offering}id"))
    return base.filter(pk__in=within.order_by().values("pk"))


def kafedra_q(unit, *, offering="", within=None) -> Q:
    """Kafedra süzgəci ``Q``-su: ``offering=""`` — ``CourseOffering`` queryset-i, ``"offering__"`` — dərs / slot.

    ``within`` — süzüləcək queryset (həll yalnız onun açılışları üçün aparılır; ``None`` → təşkilat)."""
    ids = offering_ids_in_unit(unit, _offerings_for(unit, within, offering))
    if not ids:
        # Boş ``IN ()`` SQL vermir (EmptyResultSet) — keş açarları sorğu mətnindən qurulur.
        return Q(pk__isnull=True)
    return Q(**{"pk__in" if not offering else f"{offering}id__in": ids})


def chair_candidates(offerings, organization_id) -> dict:
    """Seçim siyahısı: ``offerings``-in kafedraları ``{id: (ad, path)}``."""
    mapping = offering_chairs(offerings, organization_id)
    return chair_paths(organization_id, set().union(*mapping.values()) if mapping else set())


__all__ = [
    "CHAIR_TYPES",
    "TEACHING_ROLE_NAMES",
    "chair_candidates",
    "chair_paths",
    "kafedra_q",
    "offering_chairs",
    "official_offering_chairs",
    "offering_ids_in_unit",
]
