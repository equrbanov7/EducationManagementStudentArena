"""Atılmış jurnal yazılışlarının KLONDA bərpası — J1/J3–J9 fazalarının ÖZ kodu ilə (plan qatı).

Niyə fazalar «ayrı ledger ad-sahəsində» təkrarlanır
--------------------------------------------------
J4/J5/J5b/J6 yazılışları, dərsləri və açılışları ``run_id``-yə bağlı ledger
müşahidələrindən oxuyur və jurnal-səviyyə möhür qoyur.  Hədəfi qurmuş run
``succeeded``-dir, onun möhürləri isə köhnə nəticəni daşıyır: həmin açarları
yeni nəticə ilə təkrar möhürləmək ``legacy_entity_identity_conflict`` verir
(qəsdən — sübutun toxunulmazlığı).  Ona görə ATILABİLƏN klonda:

1. yeni plan run-u AYRI ``source_system`` ad-sahəsində açılır
   (``myedu-repair``) — kanonik açarlar orijinal ledger ilə toqquşmur;
2. fazaların oxuyacağı istinadlar orijinal run-dan KÖÇÜRÜLÜR (fənn, dövr, qrup,
   müəllim; təsirlənən açılışların dilim və yazılış xəritələri);
3. seçilmiş fake və qrupu silinmiş jurnallar üçün J1 öz kodu ilə açılış qurur
   və ya mövcud (fənn, dövr, qrup) açılışına BİRLƏŞDİRİR (C6); bərpa yazılışları yaradılır
   (``repair_enrollments_select`` qaydası) və ad-sahəsinə möhürlənir;
4. J3 → J4 → J12 → J5 → J5b → J6 → J9 dəyişmədən işləyir; fazalar yalnız
   ad-sahəsindəki yazılışlara YAZA bilir (qalan jurnallar «orphan»dır),
   mövcud sətirlər isə get_or_create ilə TAPILIR, üstündən yazılmır.  J12
   YALNIZ bərpa yazılışlarının xanalarını emal edir (``RestoredOnlyLessonRecovery``):
   qalan yazılışların itən xanalarını J12 planı artıq bərpa edib;
5. yeni açılışların sxemi J7-nin ``apply_lock``-u ilə bağlanır (dövr bitib).

Klondan sonra ``repair_enrollments_extract`` YALNIZ bərpa yazılışlarına və yeni
açılışlara aid sətirləri plana çıxarır; qalan hər dəyişiklik hesabatda sayılır.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace

from django.apps import apps as django_apps
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun

from .ledger import create_run, finish_run, start_run
from .ledger_batch import SealRequest, seal_entity_maps
from .rehearsal_authorizer import (
    ENROLLMENT_MODEL_LABEL,
    build_bulk_target_validators,
    build_rehearsal_authorizer,
    build_target_validators,
)
from .rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    EmailTrustPolicy,
    RehearsalContext,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
)
from .rehearsal_journal_components_phase import JournalComponentsPhase
from .rehearsal_journal_enrollments_phase import JOURNAL_ENROLLMENT_ENTITY_TYPE
from .rehearsal_journal_entry_scores_phase import JournalEntryScoresPhase
from .rehearsal_journal_finals_phase import JournalFinalsPhase
from .rehearsal_journal_lessons_phase import JournalLessonsPhase
from .rehearsal_journal_lock_phase import apply_lock
from .rehearsal_journal_marks_phase import JournalMarksPhase, build_resolution
from .rehearsal_journal_offerings_phase import JournalOfferingsPhase
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .rehearsal_journal_points_source import POINT_ARCHIVE_TABLE, POINT_SOURCE_TABLE
from .rehearsal_journal_selfwork_phase import JournalSelfWorkPhase
from .rehearsal_lesson_recovery_phase import JournalLessonRecoveryPhase
from .repair_lesson_recovery_apply import LEGACY_CUTOFF, grade_input_users
from .table_plan import TABLE_PLAN_VERSION

REPAIR_KEY = "journal_enrollments"
AUDIT_REASON = "legacy_repair:journal_enrollments"
REPAIR_TRANSFORM_FAMILY = "legacy-repair-enroll-v1"
#: Plan run-unun ledger ad-sahəsi — orijinal ``myedu`` açarları ilə toqquşmasın.
REPAIR_SOURCE_SYSTEM = "myedu-repair"
PLAN_RUN_END_CODE = "legacy_repair_plan_extracted"
PLAN_RUN_FAILED_CODE = "legacy_repair_plan_failed"
REFERENCE_ENTITY_TYPES = ("lesson_subject", "academic_period", "group_unit", "worker")
#: J1-in YENİDƏN qurduğu dilimlər: fake jurnal (J-V6 keçilir) və qrupu silinmiş jurnal
#: (qrup sübutla seçilib, ``repair_enrollments_select``).
NEW_SLICE_CATEGORIES = ("fake", "deleted")
PHASE_KEYS = (
    "academic_structure",
    "academic_catalog",
    "identity_cohort",
    "student_placement",
    "sar_materialisation",
    "journal_periods",
    "journal_offerings",
    "journal_enrollments",
    "journal_lessons",
    "journal_marks",
    "journal_lesson_recovery",
    "journal_components",
    "journal_entry_scores",
    "journal_finals",
    "journal_selfwork",
    "journal_lock",
)
_MIGRATED = LegacyEntityMap.State.MIGRATED
_CHUNK = 2_000


def replay_policy() -> RehearsalPolicy:
    return RehearsalPolicy(
        phase_keys=PHASE_KEYS,
        username_policy=UsernamePolicy.LEGACY_KEY,
        student_identifier_policy=StudentIdentifierPolicy.LEGACY_PK,
        email_trust_policy=EmailTrustPolicy.DENY_ALL,
        email_trust_manifest_digest="",
        batch_rows=DEFAULT_BATCH_ROWS,
        source_chunk_size=1_000,
        max_staged_accounts=0,
        student_role_name="",
        worker_role_name="",
    )


class SelectedJournalOfferings(JournalOfferingsPhase):
    """J1 — YALNIZ seçilmiş fake / qrupu silinmiş jurnalların lazım olan dilimləri üçün.

    J-V6 (``fake=1`` → atılır) qaydası BU jurnallar üçün qəsdən keçilir (sahibin
    qaydası: tələbənin yeganə nəticə daşıyıcısıdır); qrupu silinmiş jurnalın
    ``groups_id``-si sübutla seçilmiş qrupla əvəz olunur.  Açılış açarı, C6
    birləşməsi, müəllim və dərs saatı J1-in öz məntiqidir.  Müəllimin
    ``grade.input``-lu aktiv üzvlüyü yoxdursa açılış müəllimsiz qurulur (PG
    ``registrar_active_member_instructor_guard`` onu rədd edərdi) — uydurulmur.
    """

    def __init__(self, *, wanted_groups: dict, permitted: set) -> None:
        self._wanted = wanted_groups
        self._permitted = permitted

    def _journal_entries(self, *, legacy_pk, row, uniqid, **rest):
        groups = self._wanted.get(uniqid)
        if not groups:
            return
        patched = {key: row[key] for key in row}
        patched.update({"fake": 0, "sonra_sil": 0, "groups_id": json.dumps(list(groups))})
        yield from super()._journal_entries(legacy_pk=legacy_pk, row=patched, uniqid=uniqid, **rest)

    def _request(self, *, row, uniqid, row_hash, members, indexes):
        request, codes = super()._request(row=row, uniqid=uniqid, row_hash=row_hash, members=members, indexes=indexes)
        if request.instructor_pk and int(request.instructor_pk) not in self._permitted:
            request = replace(request, instructor_pk="", instructor_state=f"dropped:{request.instructor_state}")
            codes = (*codes, "legacy_journal_instructor_unresolved")
        return request, codes


class RestoredOnlyLessonRecovery(JournalLessonRecoveryPhase):
    """J12 — YALNIZ bərpa yazılışlarının xanaları.

    Təsirlənən açılışların digər yazılışları J5b-nin «tam açılış» qapısı üçün
    indeksdədir, amma onların dərsi olmayan xanalarını J12 planı (bu plandan
    ƏVVƏL tətbiq olunur) artıq bərpa edib.  Onları ikinci dəfə emal etmək eyni
    mənbə xanası üçün BAŞQA transform versiyalı sübut faktı istəyərdi
    (``legacy_rehearsal_conflict_fact_conflict``).  Qərar nərdivanı dəyişmir:
    indeksdən kənar yazılışın xanası J4-dəki kimi ``enrollment`` sayılır, fakt
    yaranmır.  Bərpa yazılışının slotu J12 planının dərsinə düşürsə, dərs
    ``SynthLessonWriter``-in öz axtarışı ilə İŞLƏDİLİR (yenisi yaradılmır).
    """

    def __init__(self, restored_keys) -> None:
        self._restored_keys = frozenset(restored_keys)

    def _resolution(self, context):
        resolution = build_resolution(context)
        wanted = {key: pk for key, pk in resolution.enrollments.items() if key in self._restored_keys}
        return replace(resolution, enrollments=wanted)


@dataclass
class ReplayResult:
    run: object
    since: object
    restored: dict  # ledger açarı → Enrollment pk
    new_offerings: set
    skipped: dict
    reports: list


def _context(*, run_id, organization, actor, authorize, policy, table_plan, source_factory, note):
    return RehearsalContext(
        run_id=run_id,
        organization=organization,
        actor=actor,
        authorize=authorize,
        target_validators=build_target_validators(),
        policy=policy,
        plan=table_plan,
        source_connection_factory=source_factory,
        target_identity_snapshot=None,
        authoritative_email_policy=None,
        cancellation_requested=lambda: False,
        stdout_note=note,
        bulk_target_validators=build_bulk_target_validators(),
    )


def open_replay_run(*, organization, actor, authorize, source_run, table_plan, policy):
    rows = table_plan.entry_for(POINT_SOURCE_TABLE).expected_rows
    rows += table_plan.entry_for(POINT_ARCHIVE_TABLE).expected_rows
    rows += table_plan.entry_for("journals").expected_rows * 4
    run = create_run(
        actor=actor,
        authorize=authorize,
        organization=organization,
        source_system=REPAIR_SOURCE_SYSTEM,
        snapshot_sha256=source_run.snapshot_sha256,
        snapshot_size_bytes=source_run.snapshot_size_bytes,
        source_row_count=rows + 1_000_000,
        schema_version=f"{TABLE_PLAN_VERSION}.{table_plan.fingerprint[:12]}",
        transform_version=f"{REPAIR_TRANSFORM_FAMILY}.{policy.policy_digest()[:12]}",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=authorize)


def _chunks(values, size=_CHUNK):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def copy_maps(context, *, source_run, entity_type, target_pks=None) -> int:
    """Orijinal run-un MIGRATED xəritələrini plan run-una (eyni açar/digest/hədəf) köçür."""

    queryset = LegacyEntityMap.objects.filter(
        organization=context.organization, created_run=source_run, entity_type=entity_type, state=_MIGRATED
    )
    batches = [None] if target_pks is None else list(_chunks(sorted({str(pk) for pk in target_pks})))
    copied = 0
    for chunk in batches:
        rows = queryset if chunk is None else queryset.filter(target_pk__in=chunk)
        requests = [
            SealRequest(
                legacy_pk=legacy_pk,
                source_row_hash=row_hash,
                state=_MIGRATED,
                target_model_label=label,
                target_pk=target_pk,
            )
            for legacy_pk, row_hash, label, target_pk in rows.values_list(
                "legacy_pk", "source_row_hash", "target_model_label", "target_pk"
            ).iterator(10_000)
        ]
        seal_entity_maps(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            entity_type=entity_type,
            requests=requests,
            target_validators=context.target_validators,
            bulk_target_validators=context.bulk_target_validators,
        )
        copied += len(requests)
    return copied


def _restore_digest(pair, enrollment_pk) -> str:
    digest = hashlib.sha256(b"legacy-repair-journal-enrollment-v1\x00")
    for part in (pair.category, pair.ledger_key, pair.group_ref, pair.slice_rule, pair.guest_unit, str(enrollment_pk)):
        digest.update(str(part).encode("utf-8") + b"\x00")
    return digest.hexdigest()


def _fake_offerings(context, *, selection, source_run, note):
    """Seçilmiş fake dilimlər üçün J1 (öz kodu) — açılış yaradılır və ya birləşdirilir."""

    wanted: dict[str, list] = defaultdict(list)
    for pair in selection.pairs:
        if pair.category in NEW_SLICE_CATEGORIES and pair.group_ref not in wanted[pair.uniqid]:
            wanted[pair.uniqid].append(pair.group_ref)
    if not wanted:
        return {}, set()
    workers = LegacyEntityMap.objects.filter(
        organization=context.organization, created_run=source_run, entity_type="worker", state=_MIGRATED
    ).values_list("target_pk", flat=True)
    permitted = grade_input_users(context.organization, [int(pk) for pk in workers if str(pk).isdigit()])
    offering_model = django_apps.get_model("registrar", "CourseOffering")
    before = set(offering_model.objects.filter(organization=context.organization).values_list("pk", flat=True))
    SelectedJournalOfferings(wanted_groups={k: tuple(v) for k, v in wanted.items()}, permitted=permitted).run(context)
    slices = dict(
        LegacyEntityMap.objects.filter(
            organization=context.organization,
            created_run_id=context.run_id,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            state=_MIGRATED,
        ).values_list("legacy_pk", "target_pk")
    )
    created = {
        str(pk)
        for pk in offering_model.objects.filter(organization=context.organization).values_list("pk", flat=True)
        if pk not in before
    }
    note(f"journal_enrollments.fake_slices.{len(slices)} new_offerings.{len(created)}")
    return slices, created


def _seal_request(pair, enrollment_pk: str) -> SealRequest:
    return SealRequest(
        legacy_pk=pair.ledger_key,
        source_row_hash=_restore_digest(pair, enrollment_pk),
        state=_MIGRATED,
        target_model_label=ENROLLMENT_MODEL_LABEL,
        target_pk=str(enrollment_pk),
    )


def _create_enrollments(context, *, selection, fake_slices):
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    existing = {
        (student_id, str(offering_id))
        for student_id, offering_id in enrollment_model.objects.filter(organization=context.organization)
        .values_list("student_id", "offering_id")
        .iterator(10_000)
    }
    restored, skipped, requests = {}, defaultdict(int), []
    created_here: dict[tuple[int, str], str] = {}
    now = timezone.now()
    for pair in selection.pairs:
        offering_pk = pair.offering_pk or fake_slices.get(f"{pair.uniqid}:{pair.group_ref}", "")
        if not offering_pk:
            skipped[f"{pair.category}:offering_unresolved"] += 1
            continue
        same = created_here.get((pair.user_id, str(offering_pk)))
        if same is not None:
            # Eyni açılışa İKİNCİ jurnal (C6: məs. mühazirə + seminar jurnalı) — J2 kimi EYNİ
            # yazılışa bağlanır ki, bu jurnalın xanaları da J4–J9-da həmin yazılışa yazılsın.
            restored[pair.ledger_key] = same
            skipped[f"merged:{pair.category}"] += 1
            requests.append(_seal_request(pair, same))
            continue
        if (pair.user_id, str(offering_pk)) in existing:
            skipped[f"{pair.category}:already_enrolled"] += 1
            continue
        row = enrollment_model.objects.create(
            organization=context.organization,
            student_id=pair.user_id,
            offering_id=offering_pk,
            kind="mandatory",
            status="enrolled",
            source_group_id=pair.guest_unit or None,
            added_by=context.actor if pair.guest_unit else None,
            added_at=now if pair.guest_unit else None,
        )
        existing.add((pair.user_id, str(row.offering_id)))
        created_here[(pair.user_id, str(row.offering_id))] = str(row.pk)
        restored[pair.ledger_key] = str(row.pk)
        requests.append(_seal_request(pair, str(row.pk)))
    seal_entity_maps(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
        requests=requests,
        target_validators=context.target_validators,
        bulk_target_validators=context.bulk_target_validators,
    )
    return restored, dict(skipped)


def _seed_affected(context, *, source_run, restored, fake_slices):
    """Təsirlənən açılışların BÜTÜN dilim və yazılış xəritələri (J5b «tam açılış» qapısı üçün)."""

    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    affected = set(
        str(pk)
        for pk in enrollment_model.objects.filter(pk__in=list(restored.values())).values_list("offering_id", flat=True)
    )
    affected |= {str(pk) for pk in fake_slices.values()}
    already = set(fake_slices)
    slice_maps = LegacyEntityMap.objects.filter(
        organization=context.organization,
        created_run=source_run,
        entity_type=COURSE_OFFERING_ENTITY_TYPE,
        state=_MIGRATED,
        target_pk__in=sorted(affected),
    ).exclude(legacy_pk__in=sorted(already))
    copy_maps(
        context,
        source_run=source_run,
        entity_type=COURSE_OFFERING_ENTITY_TYPE,
        target_pks=sorted({target for target in slice_maps.values_list("target_pk", flat=True)}),
    )
    members = enrollment_model.objects.filter(offering_id__in=sorted(affected)).exclude(pk__in=list(restored.values()))
    copy_maps(
        context,
        source_run=source_run,
        entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
        target_pks=[str(pk) for pk in members.values_list("pk", flat=True)],
    )
    return affected


def replay(*, organization, actor, source_factory, source_run, selection, table_plan, policy, note) -> ReplayResult:
    """Klonda bütün ardıcıllıq; çağıran marker + paralel sorğu qapısını artıq keçib."""

    authorize = build_rehearsal_authorizer()
    run = open_replay_run(
        organization=organization,
        actor=actor,
        authorize=authorize,
        source_run=source_run,
        table_plan=table_plan,
        policy=policy,
    )
    context = _context(
        run_id=run.pk,
        organization=organization,
        actor=actor,
        authorize=authorize,
        policy=policy,
        table_plan=table_plan,
        source_factory=source_factory,
        note=note,
    )
    since = timezone.now()
    reports = []
    try:
        for entity_type in REFERENCE_ENTITY_TYPES:
            note(
                f"journal_enrollments.copied.{entity_type}.{copy_maps(context, source_run=source_run, entity_type=entity_type)}"
            )
        fake_slices, new_offerings = _fake_offerings(context, selection=selection, source_run=source_run, note=note)
        restored, skipped = _create_enrollments(context, selection=selection, fake_slices=fake_slices)
        affected = _seed_affected(context, source_run=source_run, restored=restored, fake_slices=fake_slices)
        note(f"journal_enrollments.restored.{len(restored)} affected_offerings.{len(affected)}")
        for phase in (
            JournalLessonsPhase(),
            JournalMarksPhase(),
            RestoredOnlyLessonRecovery(restored),
            JournalComponentsPhase(),
            JournalEntryScoresPhase(),
            JournalFinalsPhase(),
            JournalSelfWorkPhase(),
        ):
            note(f"journal_enrollments.phase.{phase.phase_key}")
            reports.append(phase.run(context))
        offering_model = django_apps.get_model("registrar", "CourseOffering")
        for offering_pk, end_date in offering_model.objects.filter(pk__in=sorted(new_offerings)).values_list(
            "pk", "period__end_date"
        ):
            if end_date is not None and end_date < LEGACY_CUTOFF:
                apply_lock(context, offering_pk=str(offering_pk))
    except Exception:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=authorize,
            outcome=LegacyMigrationRun.Status.FAILED,
            failure_code=PLAN_RUN_FAILED_CODE,
        )
        raise
    finish_run(
        run_id=run.pk,
        actor=actor,
        authorize=authorize,
        outcome=LegacyMigrationRun.Status.CANCELLED,
        failure_code=PLAN_RUN_END_CODE,
    )
    return ReplayResult(
        run=run, since=since, restored=restored, new_offerings=new_offerings, skipped=skipped, reports=reports
    )


__all__ = [
    "AUDIT_REASON",
    "NEW_SLICE_CATEGORIES",
    "PHASE_KEYS",
    "REPAIR_KEY",
    "REPAIR_SOURCE_SYSTEM",
    "REPAIR_TRANSFORM_FAMILY",
    "ReplayResult",
    "RestoredOnlyLessonRecovery",
    "SelectedJournalOfferings",
    "copy_maps",
    "replay",
    "replay_policy",
]
