"""``legacy_repair_journal_enrollments`` — plan sətirlərinin HƏR FK sahəsinin canlı yoxlaması.

Niyə (production insidenti, 2026-09-25, run 36140119817)
--------------------------------------------------------
Plan production-un 2026-09-19/20 nüsxəsindən qurulub, canlı baza isə o vaxtdan dəyişib:
qonaq yazılışın mənbə qrupu (``Enrollment.source_group``) canlıda eyni təşkilatda tapılmadı və
PG ``registrar_same_org_source_group_guard`` (``registrar_guard_same_org_fk``: sətir YOXDURSA da,
BAŞQA təşkilatdadırsa da eyni xəta) INSERT-i ``CheckViolation`` ilə yıxdı.  İndi hər FK-ya bənzər
sahə ``decide()`` mərhələsində — dry-run-da da — canlıya qarşı yoxlanılır; nəticə həmişə AÇIQ
qərardır, heç vaxt DB xətası deyil:

* **plan daxili FK** (açılış, dərs, yazılış, komponent, mövzu) — plan pk → canlı pk; plandan kənar
  hədəf canlıda EYNİ təşkilatda yoxdursa sətir ``skip_parent`` (``repair_enrollments_apply``);
* **istinad FK** (fənn, dövr, qrup, kurs, rubrika, əvəzlənmə) — canlıda eyni təşkilatda yoxdursa
  sətir ``skip_missing_<sahə>`` (uşaqları ``skip_parent``);
* **``Enrollment.source_group``** — yoxdursa NULL (``null_source_group_id``).  Seçim səbəbi: modelin
  öz semantikası ``on_delete=SET_NULL``-dur — qrup silinəndə MÖVCUD qonaq yazılış da məhz bu
  vəziyyətə düşür (``added_by``/``added_at`` qalır).  Yazılış, xanalar, yekun və ÜOMG qalır, yalnız
  jurnaldakı «alt qrupdan əlavə» çipi görünmür.  Atlamaq isə bərpa olunan balı gizlədərdi;
* **``Lesson.room``** — yoxdursa NULL (``null_room_id``);
* **müəllim** (``instructor_id``) — ``grade.input``-lu aktiv üzvlük yoxdursa NULL
  (``null_instructor_id``; PG ``registrar_active_member_instructor_guard`` ilə eyni qayda);
* **tələbə** — aktiv üzvlük yoxdursa ``skip_student_inactive`` (PG ``registrar_active_member_student_guard``);
* **aktor sahələri** — tətbiq aktoru (``added_by``); qalan istifadəçi sahələri NULL.

Hər modelin HƏR konkret FK-sının bu siniflərdən birinə düşdüyünü ``classify_fk`` yoxlayır və test
bunu bütün spesifikasiya modelləri üçün təsdiqləyir — miqrasiya yeni FK əlavə etsə CI qırılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from .repair_enrollments_specs import ACTOR_FIELDS, CO, ENR, LESSON, NULL_USER_FIELDS, SPECS
from .repair_lesson_recovery_apply import grade_input_users
from .repair_plan_file import RepairPlanError

SKIP = "skip"
NULL = "null"
ORGANIZATION_FIELD = "organization_id"
#: Plandan kənar istinadlar: canlıda (eyni təşkilatda) yoxdursa nə edilir.
REFERENCE_POLICY = {
    (CO, "subject_id"): SKIP,
    (CO, "period_id"): SKIP,
    (CO, "group_id"): SKIP,
    (CO, "course_id"): SKIP,
    ("registrar.assessmentcomponent", "rubric_id"): SKIP,
    (ENR, "source_group_id"): NULL,
    (ENR, "superseded_by_id"): SKIP,
    (LESSON, "room_id"): NULL,
}
#: İstifadəçi FK-ları: tələbə (aktiv üzvlük) və müəllim (``grade.input``).
USER_CHECKS = {
    (ENR, "student_id"): "student",
    (CO, "instructor_id"): "instructor",
    (LESSON, "instructor_id"): "instructor",
}
_CHUNK = 1_000


def fk_attnames(model) -> list[str]:
    return sorted(field.attname for field in model._meta.concrete_fields if field.is_relation)


def classify_fk(kind: str, attname: str) -> str:
    """FK sahəsinin sinfi; tanınmayan FK plan tətbiqini dayandırır (təxmin edilmir)."""

    spec = SPECS[kind]
    if attname == ORGANIZATION_FIELD:
        return "organization"
    if attname in spec.fks:
        return "plan"
    if attname in ACTOR_FIELDS:
        return "actor"
    if attname in NULL_USER_FIELDS:
        return "null_user"
    if (kind, attname) in USER_CHECKS:
        return USER_CHECKS[(kind, attname)]
    if (kind, attname) in REFERENCE_POLICY:
        return "reference"
    raise RepairPlanError(f"legacy_repair_plan_fk_unclassified:{kind}.{attname}")


def check_fk_coverage() -> None:
    for kind, spec in SPECS.items():
        for attname in fk_attnames(spec.model):
            classify_fk(kind, attname)


def _field_by_attname(model, attname):
    for field in model._meta.concrete_fields:
        if field.attname == attname:
            return field
    raise RepairPlanError(f"legacy_repair_plan_field_unknown:{model._meta.label_lower}.{attname}")


def _present(organization, model, attname, values) -> set[str]:
    """Hədəf cədvəldə EYNİ təşkilatda olan dəyərlər (``registrar_guard_same_org_fk`` güzgüsü)."""

    target = _field_by_attname(model, attname).related_model
    scoped = any(field.attname == ORGANIZATION_FIELD for field in target._meta.concrete_fields)
    found: set[str] = set()
    ordered = sorted(values)
    for start in range(0, len(ordered), _CHUNK):
        queryset = target._base_manager.filter(pk__in=ordered[start : start + _CHUNK])
        if scoped:
            queryset = queryset.filter(organization=organization)
        found.update(str(pk) for pk in queryset.values_list("pk", flat=True))
    return found


class LiveReferences:
    """Plandakı istinad və istifadəçi dəyərlərinin canlı vəziyyəti — toplu, bir dəfə oxunur."""

    def __init__(self, organization, plan) -> None:
        check_fk_coverage()
        self.present: dict[tuple[str, str], set[str]] = {}
        for (kind, attname), _policy in REFERENCE_POLICY.items():
            values = {str(r["fields"][attname]) for r in plan.of(kind) if r["fields"].get(attname) is not None}
            self.present[(kind, attname)] = (
                _present(organization, SPECS[kind].model, attname, values) if values else set()
            )
        students = sorted({r["fields"]["student_id"] for r in plan.of(ENR) if r["fields"].get("student_id")})
        self.students = set(
            django_apps.get_model("organizations", "Membership")
            .objects.filter(
                organization=organization,
                user_id__in=students,
                is_active=True,
                role__is_active=True,
                user__is_active=True,
            )
            .values_list("user_id", flat=True)
        )
        instructors = {
            r["fields"]["instructor_id"]
            for kind in (CO, LESSON)
            for r in plan.of(kind)
            if r["fields"].get("instructor_id") is not None
        }
        self.instructors = grade_input_users(organization, instructors)

    def check(self, kind: str, values: dict) -> tuple[str, list[str]]:
        """``(skip qərarı | "", NULL ediləcək sahələr)`` — ``values`` dəyişdirilmir."""

        nulls: list[str] = []
        for (policy_kind, attname), policy in REFERENCE_POLICY.items():
            if policy_kind != kind or values.get(attname) is None:
                continue
            if str(values[attname]) in self.present[(policy_kind, attname)]:
                continue
            if policy == SKIP:
                return f"skip_missing_{attname}", []
            nulls.append(attname)
        if (kind, "instructor_id") in USER_CHECKS and values.get("instructor_id") is not None:
            if values["instructor_id"] not in self.instructors:
                nulls.append("instructor_id")
        return "", nulls


def plan_own_offerings(organization, plan_sha256: str, *, reason: str) -> set[str]:
    """Bu planın ÖZ açılışları: planın pk-sı + ``create`` audit sətri (bu plan sha256-ı ilə).

    Yarımçıq tətbiqdən sonra (açılışlar yazılıb, yazılışlar yox) təkrar icrada bu açılışlar
    ledger-də MIGRATED deyil — amma planın özüdür, «legacy deyil» sayılmamalıdır.
    """

    audit_model = django_apps.get_model("audit", "AuditLog")
    return {
        str(object_id)
        for object_id in audit_model.objects.filter(
            organization=organization,
            reason=reason,
            action="create",
            new_values__plan_sha256=plan_sha256,
        ).values_list("object_id", flat=True)
    }


__all__ = [
    "NULL",
    "REFERENCE_POLICY",
    "SKIP",
    "USER_CHECKS",
    "LiveReferences",
    "check_fk_coverage",
    "classify_fk",
    "fk_attnames",
    "plan_own_offerings",
]
