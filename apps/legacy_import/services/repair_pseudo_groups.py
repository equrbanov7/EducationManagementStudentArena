"""P2-8 təmiri: köçürmədən gələn PSEVDO-QRUPLAR («Level …», «Xaric ол(un)anlar»).

Qüsur (QA auditi 2026-09-05, tam hesabat: ``docs/audits/2026-09-05
/LEVEL_GROUPS.md``).  Mənbə sistemi bəzi tələbə STATUSLARINI (xaric edilib) və
dil-kursu koqortlarını (İngilis dili mərkəzinin "Level" səviyyələri) ayrıca
sahə ilə deyil, adi bir ``groups`` sətri ilə kodlaşdırırdı.  Köçürmə bunları
olduğu kimi ``OrgUnit(unit_type='group')`` sətrinə çevirdi — nəticədə onlar
dekan/RİM tələbə kataloqunda, struktur ağacında və qrup seçicilərində HƏQİQİ
akademik qrup kimi görünür.

Auditin tapdığı 74 vahid (72 «Level …» + 2 «Xaric ол(un)anlar»):

* 69-u tamamilə BOŞDUR (0 ``StudentAcademicRecord``) — «mark_service» risk
  daşımır;
* 2-si («Level - Group 2/3») kiçik, canlı İngilis-kursu koqortudur (11 tələbə,
  hamısında real ``Enrollment`` var);
* 1-i («Level 2025-2026») REAL bir ixtisasın (Dizayn/Qrafik) bölüşdürülməmiş
  2025 qəbulu tutucu qrupudur (228 tələbə, HEÇ BİRİNDƏ ``Enrollment`` yoxdur)
  — say/risk görə DEFAULT olaraq ``mark_service``-dən İSTİSNA olunur (bax
  ``include_large_holding``), ``--include-level-2025-2026`` ilə açıla bilər;
* 1-i («Xaric olunanlar 2023») boşdur;
* 1-i («Xaric olanlar») 31 tələbə daşıyır — HAMISININ statusu ``enrolled``
  qalıb (mənbə xaric statusunu YALNIZ konteyner üzvlüyü ilə kodlaşdırıb,
  ``status`` sahəsinə yazmayıb) — bu, əmrin İKİNCİ əməlinin («expel») əsas
  hədəfidir.

İKİ TƏHLÜKƏSİZ ƏMƏL (təmir əmrinin təklif etdiyi yeganə əməllər):

1. **mark_service** — ``OrgUnit.is_service_unit=True`` təyin edir (yeni,
   ``is_active``-dən ORTOQONAL sahə — bax ``apps.organizations.models.OrgUnit``
   şərhi: arxiv semantikası «aktiv tələbəsi yoxdur» tələb edir,
   ``apps.organizations.group_actions._archive`` bunu invariant kimi
   qoruyur; bizim 3 vahidimizin (Level-Group2/3, Level 2025-2026, Xaric
   olanlar) aktiv tələbəsi VAR, ona görə ``is_active`` YOX). Akademik qrup
   seçicisi (``apps.accounts.services.student_groups.groups_under``) və
   struktur ağacı (``apps.organizations.structure_views.tree``) bunu artıq
   göstərmir. Mövcud ``StudentAcademicRecord.group`` istinadı TOXUNULMUR.
2. **expel** — «Xaric ол(un)anlar» konteynerindəki ``enrolled``/``academic_
   leave`` statuslu sətirləri RƏSMİ hərəkət mexanizmi ilə
   (``apps.registrar.movements.create_movement(kind=EXPULSION)``) ``expelled``-ə
   keçirir. XAM ``UPDATE`` YOXDUR — status dəyişikliyi validasiyadan keçir,
   ``StudentMovement`` ledger sətri yazılır və giriş avtomatik bağlanır
   (``movements._sync_access_state``).

Hər iki əməl İDEMPOTENTDİR: artıq ``is_service_unit=True`` olan vahid və
artıq ``expelled``/``graduated`` statuslu sətir təkrar icrada TOXUNULMUR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.apps import apps as django_apps
from django.db.models import Count
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

#: ``core.audit.log_action`` sətirlərinin səbəb prefiksi (mark_service üçün —
#: ``expel`` öz auditini ``StudentMovement`` ledger sətri ilə aparır, bax modul
#: sənədi).
AUDIT_REASON = "legacy_repair:pseudo_groups"

#: Sənədləşdirilmiş audit hesabatı — xəta mesajlarında/README-də istinad üçün.
AUDIT_DOC = "docs/audits/2026-09-05/LEVEL_GROUPS.md"

#: Naxış C (bax audit §3) — böyük, bölüşdürülməmiş qəbul-ili tutucu qrupu.
#: Default olaraq ``mark_service``-dən İSTİSNA olunur: 228 REAL, aktiv tələbəsi
#: var və «Level» adı burada dil-kursu deyil, əksinə «hələ qrupa bölünməyib»
#: mənasında işlənib — gizlətmək 228 tələbənin real qrup bölgüsü ehtiyacını
#: HƏLL ETMİR, sadəcə gizlədir. Operator ``--include-level-2025-2026`` ilə
#: açıq şəkildə daxil edə bilər.
LARGE_HOLDING_GROUP_NAME = "Level 2025-2026"

#: Bu statuslardan «expel» keçidi qanunidir (``movements.RULES`` ilə EYNİ).
EXPELLABLE_STATUSES = ("enrolled", "academic_leave")

TABLE_HEADERS_UNITS = ("Ad", "İxtisas", "Fakültə", "Tələbə sayı", "Əməl")
TABLE_HEADERS_RECORDS = ("İstifadəçi", "Ad Soyad", "Konteyner", "Cari status", "Əməl")


def _is_level_name(name: str) -> bool:
    return str(name or "").strip().casefold().startswith("level")


def _is_expelled_container_name(name: str) -> bool:
    """«Xaric olunanlar» VƏ yazım fərqli «Xaric olanlar» — hər ikisini tutur.

    Audit tapıntısı (§1): dəqiq ad üzrə axtarış ikinci konteyneri qaçırırdı —
    ``un`` yoxdur. ``"olan"`` ``"olunanlar"``-ın ARDICIL alt-mətni DEYİL
    (``ol-U-N-an-lar`` — "u" arada), ona görə HƏR İKİ yazılış açıq yoxlanılır.
    """

    text = str(name or "").strip().casefold()
    return "xaric" in text and ("olan" in text or "olunan" in text)


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def _student_academic_record_model():
    return django_apps.get_model("registrar", "StudentAcademicRecord")


@dataclass(frozen=True)
class UnitDecision:
    """Bir psevdo-qrup üçün qərar sətri."""

    unit_id: str
    name: str
    specialty: str
    faculty: str
    record_count: int
    is_expelled_container: bool
    action: str  # "mark_service" | "already_service" | "skip_large_holding"

    def as_row(self):
        return [self.name, self.specialty, self.faculty, self.record_count, self.action]


@dataclass(frozen=True)
class RecordDecision:
    """Bir «xaric» konteynerindəki tələbə qeydi üçün qərar sətri."""

    record_id: str
    container_name: str
    student_username: str
    student_full_name: str
    current_status: str
    action: str  # "expel" | "already_expelled"

    def as_row(self):
        return [self.student_username, self.student_full_name, self.container_name, self.current_status, self.action]


def _unit_labels(unit):
    specialty = getattr(unit.parent, "name", "") or ""
    faculty = getattr(getattr(unit.parent, "parent", None), "name", "") or ""
    return specialty, faculty


def candidate_units(organization):
    """72 «Level …» + 2 «Xaric ол(un)anlar» — dəqiq audit hədəf çoxluğu.

    ``unit_type=GROUP`` MƏCBURİDİR: «Level» adlı psevdo-İXTİSAS (``unit_type=
    'specialty'``) və ``Xarici dillər`` kafedrası kimi ADI oxşar, LAKİN real
    struktur vahidləri bu şəkildə İSTİSNA olunur (bax audit §5).
    """

    OrgUnit = _org_unit_model()
    units = OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP).select_related(
        "parent", "parent__parent"
    )
    return [unit for unit in units if _is_level_name(unit.name) or _is_expelled_container_name(unit.name)]


def plan_unit_decisions(organization, *, include_large_holding: bool = False, limit: int = 0):
    """``mark_service`` qərar cədvəli — HEÇ NƏ YAZMADAN."""

    record_model = _student_academic_record_model()
    units = sorted(candidate_units(organization), key=lambda unit: unit.name.casefold())
    if limit:
        units = units[:limit]

    counts = {
        row["group_id"]: row["total"]
        for row in record_model.objects.filter(organization=organization, group_id__in=[unit.id for unit in units])
        .values("group_id")
        .annotate(total=Count("id"))
    }

    decisions = []
    for unit in units:
        specialty, faculty = _unit_labels(unit)
        record_count = int(counts.get(unit.id, 0))
        is_container = _is_expelled_container_name(unit.name)
        if unit.name.strip().casefold() == LARGE_HOLDING_GROUP_NAME.casefold() and not include_large_holding:
            action = "skip_large_holding"
        elif unit.is_service_unit:
            action = "already_service"
        else:
            action = "mark_service"
        decisions.append(
            UnitDecision(
                unit_id=str(unit.id),
                name=unit.name,
                specialty=specialty,
                faculty=faculty,
                record_count=record_count,
                is_expelled_container=is_container,
                action=action,
            )
        )
    return decisions


def plan_record_decisions(organization, *, limit: int = 0):
    """«Xaric ол(un)anlar» konteynerlərindəki tələbə qeydləri — ``expel`` qərar cədvəli."""

    OrgUnit = _org_unit_model()
    record_model = _student_academic_record_model()

    containers = [
        unit
        for unit in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP)
        if _is_expelled_container_name(unit.name)
    ]
    container_by_id = {unit.id: unit for unit in containers}
    if not container_by_id:
        return []

    records = list(
        record_model.objects.filter(organization=organization, group_id__in=container_by_id.keys())
        .select_related("student")
        .order_by("student__username")
    )
    if limit:
        records = records[:limit]

    decisions = []
    for record in records:
        container = container_by_id[record.group_id]
        action = "expel" if record.status in EXPELLABLE_STATUSES else "already_expelled"
        student = record.student
        full_name = f"{student.first_name} {student.last_name}".strip()
        decisions.append(
            RecordDecision(
                record_id=str(record.id),
                container_name=container.name,
                student_username=student.username,
                student_full_name=full_name,
                current_status=record.status,
                action=action,
            )
        )
    return decisions


def apply_mark_service(*, organization, actor, decision: UnitDecision, request=None) -> bool:
    """Bir vahidi ``is_service_unit=True`` edir. ``False`` — dəyişiklik YOXDUR (idempotent)."""

    if decision.action != "mark_service":
        return False
    OrgUnit = _org_unit_model()
    unit = OrgUnit.objects.filter(organization=organization, pk=decision.unit_id).first()
    if unit is None or unit.is_service_unit:
        return False
    unit.is_service_unit = True
    unit.save(update_fields=["is_service_unit", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=unit,
        request=request,
        reason=f"{AUDIT_REASON}: mark_service — {AUDIT_DOC}",
        old_values={"is_service_unit": False},
        new_values={"is_service_unit": True},
    )
    return True


def apply_expel(
    *,
    organization,
    actor,
    decision: RecordDecision,
    order_number: str,
    order_date: date | None = None,
    reason: str,
) -> bool:
    """Bir tələbə qeydini rəsmi EXPULSION hərəkəti ilə ``expelled``-ə keçirir.

    Xam ``UPDATE`` YOXDUR — ``apps.registrar.movements.create_movement`` (state
    maşını + append-only ``StudentMovement`` ledger sətri) tam yolla çağırılır.
    ``False`` — dəyişiklik YOXDUR (idempotent: artıq expelled/qraduated).
    """

    if decision.action != "expel":
        return False

    from apps.registrar import movements
    from apps.registrar.models import MovementKind, StudentAcademicRecord

    record = StudentAcademicRecord.objects.select_related("organization", "student", "group").get(
        pk=decision.record_id, organization_id=organization.pk
    )
    if record.status not in EXPELLABLE_STATUSES:
        return False

    movements.create_movement(
        record=record,
        kind=MovementKind.EXPULSION,
        order_number=order_number,
        order_date=order_date or timezone.localdate(),
        reason=reason,
        actor=actor,
    )
    return True


__all__ = [
    "AUDIT_DOC",
    "AUDIT_REASON",
    "EXPELLABLE_STATUSES",
    "LARGE_HOLDING_GROUP_NAME",
    "TABLE_HEADERS_RECORDS",
    "TABLE_HEADERS_UNITS",
    "RecordDecision",
    "UnitDecision",
    "apply_expel",
    "apply_mark_service",
    "candidate_units",
    "plan_record_decisions",
    "plan_unit_decisions",
]
