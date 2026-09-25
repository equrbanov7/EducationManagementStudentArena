"""``legacy_repair_journal_enrollments`` — plan qurulması (LOKAL, atılabilən klonda).

Ardıcıllıq: seçim (``repair_enrollments_select``, oxu) → klonda fazaların
təkrarı (``repair_enrollments_replay``) → yalnız bərpa sətirlərinin çıxarılması
(``repair_enrollments_extract``) → sha256-lı plan faylı (``repair_plan_file``).

Qapılar J12 təmirinin eynisidir: plan YALNIZ ``emsarena.rehearsal_target=
'disposable'`` markerli bazada qurulur (faza klona real yazır), mənbə opt-in
settings ilə, ``@@GLOBAL.read_only=1``, sətir sayları table-plan ilə dəqiq.
Klon production-un nüsxəsi olmalıdır və ondan ƏVVƏL J12 planı tətbiq
olunmalıdır — server də planları eyni sıra ilə alır.  Klonda tətbiq olunmuş
planlar başlığa ``prerequisites`` kimi yazılır (xülasə audit sətirlərindən);
tətbiq onların canlıda da tətbiq olunduğunu yoxlayır, çünki bərpa xanalarının
bir hissəsi J12-nin yaratdığı dərslərə (plan pk-ları ilə) bağlanır.
"""

from __future__ import annotations

import os
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.export_safety import safe_csv_writer

from .rehearsal_contracts import SOURCE_SYSTEM
from .repair_enrollments_extract import extract, restored_from_run, summarise
from .repair_enrollments_replay import REPAIR_KEY, _context, replay, replay_policy
from .repair_enrollments_select import select_pairs
from .repair_lesson_recovery import _code_revision, resolve_source_run
from .repair_plan_file import RepairPlanError, write_plan
from .repair_support import database_is_disposable_target, disable_parallel_query
from .table_plan import load_legacy_table_plan

#: Bu plandan ƏVVƏL tətbiq olunmalı təmirlər (``legacy_repair:<açar>: xülasə`` audit sətri).
PREREQUISITE_REPAIRS = ("lesson_recovery",)
SUMMARY_RESOURCE_TYPE = "legacy_import.repair"


def summary_reason(repair: str) -> str:
    return f"legacy_repair:{repair}: xülasə"


def applied_prerequisites(organization) -> list[dict]:
    """Bu bazada ƏVVƏLCƏDƏN tətbiq olunmuş ön-şərt planları (sha256 ilə)."""

    audit_model = django_apps.get_model("audit", "AuditLog")
    found = []
    for repair in PREREQUISITE_REPAIRS:
        digests = audit_model.objects.filter(
            organization=organization, resource_type=SUMMARY_RESOURCE_TYPE, reason=summary_reason(repair)
        ).values_list("resource_id", flat=True)
        found.extend({"repair": repair, "plan_sha256": digest} for digest in sorted(set(digests)))
    return found


def schema_state() -> dict:
    """Planı quran bazanın son miqrasiyaları — server bu vəziyyətdə və ya ondan yeni olmalıdır."""

    from django.db.migrations.recorder import MigrationRecorder

    latest = {}
    for app, name in MigrationRecorder.Migration.objects.filter(app__in=("registrar", "legacy_import")).values_list(
        "app", "name"
    ):
        latest[app] = max(latest.get(app, ""), name)
    return dict(sorted(latest.items()))


def current_legacy_students(selection) -> dict:
    """Hazırda oxuyanlar: legacy tələbə id-si → sübut kodu (P0-1 süzgəci bu siyahını oxuyur)."""

    return {str(legacy): evidence for legacy, (_user, evidence) in sorted(selection.current.items())}


def write_skipped_csv(path: str, selection) -> None:
    """Bərpa OLUNMAYAN cütlər (səbəbi ilə) — yalnız lokal, 0600, repoya düşmür."""

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
        writer = safe_csv_writer(handle)
        writer.writerow(("category", "legacy_student_id", "journal_uniqid", "reason"))
        writer.writerows(sorted(selection.skipped_rows))


def build_plan(
    *,
    organization,
    actor,
    source_factory,
    out_path: str,
    source_run_id: str = "",
    note=print,
    table_plan=None,
    skipped_csv: str = "",
):
    if not database_is_disposable_target():
        raise RepairPlanError("legacy_repair_plan_target_not_disposable")
    disable_parallel_query(local=False)
    table_plan = table_plan or load_legacy_table_plan()
    source_run = resolve_source_run(organization, source_run_id)
    policy = replay_policy()
    notes: list[str] = []

    def stdout_note(text: str) -> None:
        notes.append(text)
        note(f"  · {text}")

    from .rehearsal_authorizer import build_rehearsal_authorizer

    read_context = _context(
        run_id=source_run.pk,
        organization=organization,
        actor=actor,
        authorize=build_rehearsal_authorizer(),
        policy=policy,
        table_plan=table_plan,
        source_factory=source_factory,
        note=stdout_note,
    )
    selection = select_pairs(read_context, source_run=source_run)
    stdout_note(
        f"journal_enrollments.current.{len(selection.current)} pairs.{len(selection.pairs)} "
        f"students.{len({pair.legacy_student for pair in selection.pairs})}"
    )
    if skipped_csv:
        write_skipped_csv(skipped_csv, selection)
    result = replay(
        organization=organization,
        actor=actor,
        source_factory=source_factory,
        source_run=source_run,
        selection=selection,
        table_plan=table_plan,
        policy=policy,
        note=stdout_note,
    )
    records, report = extract(
        organization, since=result.since, restored=result.restored, new_offerings=result.new_offerings
    )
    header = {
        "repair": REPAIR_KEY,
        "organization_id": str(organization.pk),
        "organization_slug": organization.slug,
        "source_system": SOURCE_SYSTEM,
        "source_snapshot_sha256": source_run.snapshot_sha256,
        "source_run_id": str(source_run.pk),
        "source_transform_version": source_run.transform_version,
        "planning_run_id": str(result.run.pk),
        "planning_transform_version": result.run.transform_version,
        "code_revision": _code_revision(),
        "generated_at": timezone.now().isoformat(),
        "prerequisites": applied_prerequisites(organization),
        "schema": schema_state(),
        "current_students": len(selection.current),
        "current_legacy_students": current_legacy_students(selection),
        "current_evidence": dict(sorted(Counter(evidence for _user, evidence in selection.current.values()).items())),
        "selected_pairs": dict(sorted(Counter(pair.category for pair in selection.pairs).items())),
        "slice_rules": dict(sorted(Counter(f"{pair.category}:{pair.slice_rule}" for pair in selection.pairs).items())),
        "skipped": dict(sorted((Counter(selection.skipped) + Counter(result.skipped)).items())),
        "restored_pairs": {
            key: {"category": pair.category, "slice_rule": pair.slice_rule, "guest": bool(pair.guest_unit)}
            for pair in selection.pairs
            for key in [pair.ledger_key]
            if key in result.restored
        },
        "extraction": report,
        "phase_notes": notes,
    }
    manifest = write_plan(out_path, header=header, records=records)
    return manifest, header, summarise(records)


def _drop_excluded(records, report, header, *, excluded, reason):
    """İstisna olunan cütlərin izi: seçim sayları azaldılır, YALNIZ onlar üçün yaranan sətirlər atılır.

    * yazılışı qalmayan yeni açılış (J1 onu yalnız istisna cütləri üçün qurub) — sxemi,
      komponentləri, mövzuları və dərsləri ilə;
    * balı qalmayan plan komponenti — J5 komponenti yalnız BAL olduqda yaradır (planın
      hər komponentinin ən azı bir balı var), yenidən qurulmuş planda da olmazdı.
    """

    used = {r["fields"]["offering_id"] for r in records if r["kind"] == "registrar.enrollment"}
    orphaned = {r["pk"] for r in records if r["kind"] == "registrar.courseoffering" and r["pk"] not in used}
    scored = {r["fields"]["component_id"] for r in records if r["kind"] == "registrar.componentscore"}

    def keep(record) -> bool:
        if record["kind"] == "registrar.courseoffering":
            return record["pk"] not in orphaned
        if record["fields"].get("offering_id") in orphaned:
            return False  # yalnız istisna cütləri üçün qurulmuş açılışın sxemi/komponenti/mövzusu/dərsi
        return record["kind"] != "registrar.assessmentcomponent" or record["pk"] in scored

    kept = [record for record in records if keep(record)]
    dropped_by_kind = summarise(records) - summarise(kept)
    for name in report:
        gone = dropped_by_kind.get(f"registrar.{name.lower()}", 0)
        if gone:
            report[name] = {
                **report[name],
                "plan": report[name]["plan"] - gone,
                "foreign_new": report[name]["foreign_new"] + gone,
            }
    pairs = header.get("restored_pairs") or {}
    gone = [pairs.get(key, {}) for key in excluded]
    categories = Counter(item.get("category", "?") for item in gone)
    header["restored_pairs"] = {key: value for key, value in pairs.items() if key not in set(excluded)}
    header["selected_pairs"] = dict(sorted((Counter(header.get("selected_pairs") or {}) - categories).items()))
    header["slice_rules"] = dict(
        sorted(
            (
                Counter(header.get("slice_rules") or {})
                - Counter(f"{item.get('category', '?')}:{item.get('slice_rule', '?')}" for item in gone)
            ).items()
        )
    )
    header["skipped"] = dict(
        sorted(
            (Counter(header.get("skipped") or {}) + Counter(f"{cat}:{reason}" for cat in categories.elements())).items()
        )
    )
    header["excluded_after_replay"] = {
        "reason": reason,
        "pairs": len(excluded),
        **{f"dropped_{kind.split('.')[-1]}": count for kind, count in sorted(dropped_by_kind.items())},
    }
    return kept, report


def reextract_plan(*, organization, planning_run_id: str, out_path: str, base_header=None, current=None, rosters=None):
    """Bitmiş plan run-undan planı YENİDƏN çıxar (klon toxunulmaz qalıb; mənbə lazım deyil).

    ``current`` (``Selection.current``) verilərsə başlığa hazırda oxuyanların siyahısı yazılır.
    ``rosters`` (``uniqid`` → jurnal siyahısı) verilərsə siyahıda OLMAYAN tələbənin bərpa
    cütü planı daxil edilmir (seçim qaydası sonradan sərtləşibsə, klonu yenidən qurmadan).
    """

    from apps.legacy_import.models import LegacyMigrationRun

    from .repair_enrollments_replay import REPAIR_SOURCE_SYSTEM

    if not database_is_disposable_target():
        raise RepairPlanError("legacy_repair_plan_target_not_disposable")
    run = LegacyMigrationRun.objects.filter(
        pk=planning_run_id, organization=organization, source_system=REPAIR_SOURCE_SYSTEM
    ).first()
    if run is None or run.status != LegacyMigrationRun.Status.CANCELLED:
        raise RepairPlanError("legacy_repair_plan_run_not_finished")
    source_run = resolve_source_run(organization)
    since, restored, new_offerings = restored_from_run(organization, run)
    excluded = []
    if rosters is not None:
        for key in sorted(restored):
            uniqid, _sep, student = key.rpartition(":")
            if not student.isdigit() or int(student) not in rosters.get(uniqid, ()):
                excluded.append(key)
        restored = {key: pk for key, pk in restored.items() if key not in set(excluded)}
    records, report = extract(organization, since=since, restored=restored, new_offerings=new_offerings)
    header = dict(base_header or {})
    if excluded:
        records, report = _drop_excluded(records, report, header, excluded=excluded, reason="not_in_roster")
    header.update(
        {
            "repair": REPAIR_KEY,
            "organization_id": str(organization.pk),
            "organization_slug": organization.slug,
            "source_system": SOURCE_SYSTEM,
            "source_snapshot_sha256": source_run.snapshot_sha256,
            "source_run_id": str(source_run.pk),
            "planning_run_id": str(run.pk),
            "planning_transform_version": run.transform_version,
            "code_revision": _code_revision(),
            "generated_at": timezone.now().isoformat(),
            "prerequisites": applied_prerequisites(organization),
            "schema": schema_state(),
            "reextracted": True,
            "extraction": report,
        }
    )
    header.setdefault("restored_pairs", {key: {} for key in restored})
    if current is not None:
        header["current_students"] = len(current)
        header["current_legacy_students"] = {
            str(legacy): evidence for legacy, (_user, evidence) in sorted(current.items())
        }
    manifest = write_plan(out_path, header=header, records=records)
    return manifest, header, summarise(records)


__all__ = [
    "PREREQUISITE_REPAIRS",
    "SUMMARY_RESOURCE_TYPE",
    "applied_prerequisites",
    "build_plan",
    "current_legacy_students",
    "reextract_plan",
    "schema_state",
    "summary_reason",
    "write_skipped_csv",
]
