"""``legacy_repair_journal_enrollments`` — planın CANLI bazaya tətbiqi (server, mənbəsiz).

Qərar keçidi (dry-run ilə apply EYNİ yolu gedir) plan sətirlərini
``repair_enrollments_specs.ORDER`` sırasında təsnif edir və plan pk → canlı pk
xəritəsini qurur; yazı keçidi yalnız ``create`` qərarlarını dəstə-dəstə,
hər dəstə öz tranzaksiyasında və RLS kontekstində əlavə edir.

Canlı qapılar (plan nüsxədən qurulub, canlı data dəyişmiş ola bilər):

* başlıq — eyni tenant, eyni snapshot, eyni import run-u (``validate_header``);
* ön-şərt — plan qurulanda klonda tətbiq olunmuş J12 planı canlıda da tətbiq
  olunub (xülasə audit sətri, ``check_prerequisites``); yoxdursa HEÇ NƏ edilmir;
* açılış — dövrü ``LEGACY_CUTOFF``-dan əvvəl bitməlidir; mövcud açılış ledger-də
  MIGRATED olmalıdır (ledgersiz yalnız bu planın YENİ açılışı) — 2026/2027-yə
  TOXUNULMUR;
* yazılış — tələbənin aktiv üzvlüyü olmalıdır (PG qoruyucusu); eyni
  (tələbə, açılış) üçün BAŞQA yazılış varsa sətir və uşaqları atlanır;
* dərs — tarix kəsimdən əvvəl; müəllim ``grade.input``-lu deyilsə boş;
* plandan kənar FK hədəfi (mövcud dərs/komponent/açılış) canlıda olmalıdır;
* xana — dərs və yazılış EYNİ açılışdadır (PG ``lesson_mark_coherence``);
* xana/bal/yekun/fakt — mövcuddursa ÜSTÜNDƏN YAZILMIR (``skip_live_conflict``).

Audit: hər yeni açılış, sxem, komponent, sərbəst iş mövzusu, yazılış, dərs və sübut
faktı üçün ``core.audit.log_action`` (eyni tranzaksiyada) — hədəfli geri qaytarma
(``scripts/ops/restore_legacy_enrollments_rollback.psql``) məhz bu izdən işləyir;
yarpaqlar (xana, bal, yekun …) yazılışla birlikdə silinir.  Sonda plan sha256-lı
xülasə.  İkinci icra 0 dəyişiklik.
"""

from __future__ import annotations

import datetime
from collections import Counter
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap

from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .repair_enrollments_plan import SUMMARY_RESOURCE_TYPE, summary_reason
from .repair_enrollments_replay import AUDIT_REASON, REPAIR_KEY
from .repair_enrollments_specs import (
    ACTOR_FIELDS,
    CO,
    ENR,
    LESSON,
    NULL_USER_FIELDS,
    ORDER,
    SPECS,
    coerce,
    natural_key,
    same_values,
)
from .repair_lesson_recovery_apply import LEGACY_CUTOFF, grade_input_users, recompute_and_audit_absence, validate_header
from .repair_plan_file import RepairPlanError
from .repair_support import scoped_atomic

TABLE_HEADERS = ("model", "qərar", "say")
MARK = "registrar.lessonmark"
FACT = "registrar.legacygradefact"
AUDITED = frozenset(
    {CO, "registrar.assessmentscheme", "registrar.assessmentcomponent", "registrar.selfworktopic", ENR, LESSON, FACT}
)
#: uşaq → (valideyn FK, valideyn növü) — valideyn və yazılış eyni açılışda olmalıdır.
COHERENT_PARENT = {
    MARK: ("lesson_id", LESSON),
    "registrar.componentscore": ("component_id", "registrar.assessmentcomponent"),
    "registrar.selfworkmark": ("topic_id", "registrar.selfworktopic"),
}
_CHUNK = 1_000
_BATCH = 500


@dataclass
class Decision:
    kind: str
    record: dict
    values: dict
    action: str
    live_pk: str = ""


@dataclass
class Decided:
    decisions: list = field(default_factory=list)
    counters: Counter = field(default_factory=Counter)

    def rows(self):
        grouped = Counter((decision.kind.split(".")[-1], decision.action) for decision in self.decisions)
        return sorted((kind, action, count) for (kind, action), count in grouped.items())


def _chunks(values, size=_CHUNK):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


class OfferingIndex:
    """Canlı açılış → legacy-dirmi; bu planın YENİ açılışları ledger tələb etmir."""

    def __init__(self, organization) -> None:
        self._organization = organization
        self._cache: dict[str, bool] = {}
        self.planned_new: set[str] = set()

    def is_legacy(self, offering_pk: str) -> bool:
        offering_pk = str(offering_pk)
        if offering_pk not in self._cache:
            model = django_apps.get_model("registrar", "CourseOffering")
            row = model.objects.filter(organization=self._organization, pk=offering_pk).values_list(
                "period__end_date", flat=True
            )
            end_date = next(iter(row), None)
            migrated = LegacyEntityMap.objects.filter(
                organization=self._organization,
                entity_type=COURSE_OFFERING_ENTITY_TYPE,
                state=LegacyEntityMap.State.MIGRATED,
                target_pk=offering_pk,
            ).exists()
            self._cache[offering_pk] = end_date is not None and end_date < LEGACY_CUTOFF and migrated
        return self._cache[offering_pk] or offering_pk in self.planned_new


def _period_is_legacy(period_pk) -> bool:
    period = django_apps.get_model("organizations", "AcademicPeriod").objects.filter(pk=period_pk).first()
    return period is not None and period.end_date < LEGACY_CUTOFF


def _live_rows(kind, organization, *, pks, key_values):
    spec = SPECS[kind]
    names = sorted({*spec.key, *spec.compare, "id"})
    by_pk, by_key = {}, {}
    model = spec.model
    for chunk in _chunks(sorted(pks)):
        for row in model.objects.filter(organization=organization, pk__in=chunk).values(*names):
            by_pk[str(row["id"])] = row
    first = _lookup_field(kind)
    for chunk in _chunks(sorted(key_values)):
        for row in model.objects.filter(organization=organization, **{f"{first}__in": chunk}).values(*names):
            by_key.setdefault(natural_key(spec, row), row)
    return by_pk, by_key


def _lookup_field(kind) -> str:
    """Təbii açar axtarışının süzgəc sahəsi (faktda ``source_system`` deyil — seçiciliyi yoxdur)."""

    return "source_pk" if kind == FACT else SPECS[kind].key[0]


def _external(organization, kind, pks) -> dict[str, dict]:
    """Plandan kənar FK hədəfləri (mövcud sətirlər) — canlıda VARMI, açılışı nədir."""

    spec = SPECS[kind]
    wanted = {"id", *(["offering_id"] if kind != CO else [])}
    found = {}
    for chunk in _chunks(sorted(pks)):
        for row in spec.model.objects.filter(organization=organization, pk__in=chunk).values(*sorted(wanted)):
            found[str(row["id"])] = row
    return found


class _Resolver:
    """Plan pk → canlı pk və canlı açılış (dərs/yazılış üçün) — keçid boyu dolur."""

    def __init__(self, organization) -> None:
        self.organization = organization
        self.pk_map: dict[tuple[str, str], str | None] = {}
        self.offering_of: dict[tuple[str, str], str] = {}

    def resolve(self, kind, pk):
        return self.pk_map.get((kind, str(pk)), "__external__")

    def load_external(self, kind, pks):
        missing = [pk for pk in pks if (kind, str(pk)) not in self.pk_map]
        for pk, row in _external(self.organization, kind, missing).items():
            self.pk_map[(kind, pk)] = pk
            if "offering_id" in row:
                self.offering_of[(kind, pk)] = str(row["offering_id"])
        for pk in missing:
            self.pk_map.setdefault((kind, str(pk)), None)


def check_prerequisites(organization, header: dict) -> None:
    """Başlığın ``prerequisites`` planları bu bazada tətbiq olunubmu (xülasə audit sətri)?"""

    audit_model = django_apps.get_model("audit", "AuditLog")
    for item in header.get("prerequisites") or ():
        repair, digest = str(item.get("repair", "")), str(item.get("plan_sha256", ""))
        applied = audit_model.objects.filter(
            organization=organization,
            resource_type=SUMMARY_RESOURCE_TYPE,
            reason=summary_reason(repair),
            resource_id=digest,
        ).exists()
        if not applied:
            raise RepairPlanError(f"legacy_repair_plan_prerequisite_missing:{repair}:{digest[:12]}")


def check_fields(plan) -> None:
    """Plan sətirlərinin HƏR sahəsi canlı modeldə varmı — yazıdan ƏVVƏL (yarımçıq tətbiq olmasın).

    Plan başqa miqrasiya vəziyyəti ilə qurulubsa (sahə silinib / hələ deploy olunmayıb)
    tətbiq bütövlükdə rədd edilir; planda olmayan YENİ sahə isə model defoltunu alır.
    """

    for kind in ORDER:
        names = set()
        for record in plan.of(kind):
            names.update(record["fields"])
        if names:
            coerce(SPECS[kind].model, dict.fromkeys(names))


def decide(organization, plan, *, limit: int = 0) -> Decided:
    validate_header(organization, plan.header, repair=REPAIR_KEY)
    check_prerequisites(organization, plan.header)
    check_fields(plan)
    decided = Decided()
    resolver = _Resolver(organization)
    offerings = OfferingIndex(organization)
    included = sorted(record["pk"] for record in plan.of(ENR))
    included = set(included[:limit] if limit else included)
    needed_offerings = {record["fields"]["offering_id"] for record in plan.of(ENR) if record["pk"] in included}
    students = set(
        django_apps.get_model("organizations", "Membership")
        .objects.filter(
            organization=organization,
            user_id__in=sorted({record["fields"]["student_id"] for record in plan.of(ENR)}),
            is_active=True,
            role__is_active=True,
            user__is_active=True,
        )
        .values_list("user_id", flat=True)
    )
    for kind in ORDER:
        spec = SPECS[kind]
        records = plan.of(kind)
        for fk, target_kind in spec.fks.items():
            external = {
                r["fields"][fk]
                for r in records
                if r["fields"].get(fk) and (target_kind, r["fields"][fk]) not in resolver.pk_map
            }
            if external:
                resolver.load_external(target_kind, external)
        remapped = []
        for record in records:
            values = dict(record["fields"])
            skip = ""
            for fk, target_kind in spec.fks.items():
                if values.get(fk) is None:
                    continue
                mapped = resolver.pk_map.get((target_kind, values[fk]))
                if mapped is None:
                    skip = skip or "skip_parent"
                else:
                    values[fk] = mapped
            remapped.append((record, values, skip))
        by_pk, by_key = _live_rows(
            kind,
            organization,
            pks={record["pk"] for record, _v, _s in remapped},
            key_values={
                values[_lookup_field(kind)]
                for _r, values, _s in remapped
                if values.get(_lookup_field(kind)) is not None
            },
        )
        for record, values, skip in remapped:
            action, live_pk = _classify(
                kind,
                spec,
                record,
                values,
                skip=skip,
                by_pk=by_pk,
                by_key=by_key,
                included=included,
                needed_offerings=needed_offerings,
                offerings=offerings,
                students=students,
                resolver=resolver,
            )
            resolver.pk_map[(kind, record["pk"])] = live_pk or None
            if live_pk and values.get("offering_id"):
                resolver.offering_of[(kind, live_pk)] = str(values["offering_id"])
            if kind == CO and action == "create":
                offerings.planned_new.add(record["pk"])
            decided.decisions.append(Decision(kind=kind, record=record, values=values, action=action, live_pk=live_pk))
            decided.counters[f"{kind.split('.')[-1]}:{action}"] += 1
    return decided


def _classify(
    kind, spec, record, values, *, skip, by_pk, by_key, included, needed_offerings, offerings, students, resolver
):
    """``(qərar, canlı pk)`` — boş pk = sətir atlanır (uşaqları da)."""

    # ``--limit`` kənarındakı sətir valideynindən asılı olmayaraq ``skip_limit`` sayılır.
    if kind == ENR and record["pk"] not in included:
        return "skip_limit", ""
    if kind == CO and record["pk"] not in needed_offerings:
        return "skip_limit", ""
    if skip:
        return skip, ""
    live = by_pk.get(record["pk"])
    if live is not None:
        if natural_key(spec, live) != natural_key(spec, values):
            raise RepairPlanError(f"legacy_repair_plan_pk_collision:{kind}")
        return "already_present", record["pk"]
    live = by_key.get(natural_key(spec, values))
    if live is not None:
        if spec.reuse:
            return "reuse_existing", str(live["id"])
        if kind == ENR:
            return "skip_enrollment_exists", ""
        return ("already_present", str(live["id"])) if same_values(spec, live, values) else ("skip_live_conflict", "")
    if kind == CO:
        return ("create", record["pk"]) if _period_is_legacy(values["period_id"]) else ("skip_offering_not_legacy", "")
    if kind in (ENR, LESSON) and not offerings.is_legacy(values["offering_id"]):
        return "skip_offering_not_legacy", ""
    if kind == ENR and values["student_id"] not in students:
        return "skip_student_inactive", ""
    if kind == LESSON and datetime.date.fromisoformat(values["date"]) >= LEGACY_CUTOFF:
        return "skip_date_after_cutoff", ""
    parent = COHERENT_PARENT.get(kind)
    if parent is not None:
        # PG coherence qoruyucuları: dərs/komponent/mövzu və yazılış EYNİ açılışda.
        parent_offering = resolver.offering_of.get((parent[1], str(values[parent[0]])))
        enrollment_offering = resolver.offering_of.get((ENR, str(values["enrollment_id"])))
        if parent_offering is None or parent_offering != enrollment_offering:
            return "skip_offering_mismatch", ""
    return "create", record["pk"]


def _row(kind, decision, *, organization, actor, instructors):
    spec = SPECS[kind]
    values = coerce(spec.model, decision.values)
    for name in list(values):
        if name in ACTOR_FIELDS:
            values[name] = actor.pk if values[name] is not None else None
        elif name in NULL_USER_FIELDS:
            values[name] = None
        elif name == "instructor_id" and values[name] is not None and values[name] not in instructors:
            values[name] = None
    return spec.model(pk=decision.record["pk"], organization=organization, **values)


def apply_decided(context, decided: Decided, *, plan, plan_sha256: str) -> Counter:
    from core.audit import log_action
    from core.constants import AuditAction

    organization, actor = context.organization, context.actor
    instructors = grade_input_users(
        organization, [d.values.get("instructor_id") for d in decided.decisions if d.values.get("instructor_id")]
    )
    written: Counter = Counter()
    created_enrollments: list[str] = []
    for kind in ORDER:
        batch = [d for d in decided.decisions if d.kind == kind and d.action == "create"]
        for chunk in _chunks(batch, _BATCH):
            with scoped_atomic(context):
                rows = [_row(kind, d, organization=organization, actor=actor, instructors=instructors) for d in chunk]
                SPECS[kind].model.objects.bulk_create(rows)
                if kind in AUDITED:
                    for decision, row in zip(chunk, rows):
                        log_action(
                            action=AuditAction.CREATE,
                            user=actor,
                            organization=organization,
                            obj=row,
                            reason=f"{AUDIT_REASON}: {kind.split('.')[-1]}",
                            new_values={
                                "plan_sha256": plan_sha256,
                                "restore_key": decision.record.get("restore_key", ""),
                                **{k: v for k, v in decision.values.items() if k.endswith("_id") or k == "date"},
                            },
                        )
            written[kind.split(".")[-1]] += len(chunk)
        if kind == ENR:
            created_enrollments = [d.record["pk"] for d in batch]
    written["absence_hours"] = recompute_and_audit_absence(
        context, created_enrollments, plan_sha256=plan_sha256, reason=AUDIT_REASON
    )
    if not any(written.values()):
        return written
    with scoped_atomic(context):
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            resource_type="legacy_import.repair",
            resource_id=plan_sha256,
            reason=f"{AUDIT_REASON}: xülasə",
            new_values={
                "plan_sha256": plan_sha256,
                "source_run_id": plan.header.get("source_run_id"),
                "planning_run_id": plan.header.get("planning_run_id"),
                "written": dict(sorted(written.items())),
                "decisions": dict(sorted(decided.counters.items())),
            },
        )
    return written


__all__ = [
    "TABLE_HEADERS",
    "Decided",
    "Decision",
    "OfferingIndex",
    "apply_decided",
    "check_fields",
    "check_prerequisites",
    "decide",
]
