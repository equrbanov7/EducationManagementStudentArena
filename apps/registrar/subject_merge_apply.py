"""Fənn birləşdirməsinin TƏTBİQİ — tək tranzaksiya, iz yoxlaması, audit (2026-10-19).

Ardıcıllıq (hamısı BİR ``transaction.atomic`` daxilində; istənilən uyğunsuzluq → tam geri):
1. hədəf + mənbə kartları ``SELECT … FOR UPDATE`` ilə kilidlənir, plan YENİDƏN toplanır;
2. iz (digest) önizləmədəki ilə eyni deyilsə → 409 ``drift``; bloklayan toqquşma → 409 ``conflicts``;
3. qaralama planda toqquşan mənbə sətirləri çıxarılır (tam snapshot audit-də);
4. hər ``repoint`` cədvəli YALNIZ qeydə alınmış id-lərlə köçürülür (say tutmalıdır);
   açılış üçün ``app.registrar_subject_merge_*`` icazəsi qurulur (``audit.0004``) və dərhal silinir;
5. imtahan qrupu əlaqələri + JSON prioritet açarları;
6. mənbələrdə qalan istinad (paralel yazı) varsa → ``drift``;
7. mənbələr arxivlənir, audit yazılır (``changes`` — geri qaytarma üçün kifayət edən tam iz).
"""

from __future__ import annotations

import datetime
import decimal
import uuid

from django.apps import apps as django_apps
from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core.audit import log_action, log_actions
from core.constants import AuditAction

from .models import CurriculumSubject, Subject
from .subject_merge import (
    AUDIT_RESOURCE,
    CHANGES_VERSION,
    MergeError,
    archive_reason_for,
    clean_reason,
    collect,
    counts,
    plan_digest,
    resolve_subjects,
)
from .subject_merge_inventory import M2M, RELATIONS, REPOINT, relation

_CTX = "registrar.subject_merge"


def _drift(message=None):
    return MergeError(
        "drift",
        message or pgettext(_CTX, "Məlumat önizləmədən sonra dəyişib — yenidən önizləyin."),
        status=409,
    )


def _json_value(value):
    if isinstance(value, uuid.UUID | decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    return value


def row_snapshot(instance) -> dict:
    """Sətrin bütün konkret sahələri (JSON-a yararlı) — geri qaytarmada eyni id ilə bərpa olunur."""
    return {field.attname: _json_value(getattr(instance, field.attname)) for field in instance._meta.concrete_fields}


def allow_offering_subject_change(from_ids, to_id) -> None:
    """``audit.0004`` icazəsi — cari tranzaksiya üçün (``set_config(..., true)`` = SET LOCAL).

    ⚠️ MİQRASİYA SIRASI: ``registrar_guard_conditional_parent_identity`` funksiyasını yenidən yazan
    İSTƏNİLƏN gələcək registrar miqrasiyası ``("audit", "0004_registrar_subject_merge_offering_guard")``-dan
    ASILI olmalı və bu icazə blokunu SAXLAMALIDIR — yoxsa miqrasiya sırasından asılı olaraq icazə itə bilər
    və sübutlu açılışın birləşməsi DB triggerində düşər. Qoruyucu test:
    ``apps/registrar/tests/test_subject_merge_postgres.py`` (``-m postgres``).
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.registrar_subject_merge_txid', pg_current_xact_id()::text, true), "
            "set_config('app.registrar_subject_merge_from', %s, true), "
            "set_config('app.registrar_subject_merge_to', %s, true)",
            [",".join(str(pk) for pk in from_ids), str(to_id)],
        )


def clear_offering_subject_change() -> None:
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.registrar_subject_merge_txid', '', true), "
            "set_config('app.registrar_subject_merge_from', '', true), "
            "set_config('app.registrar_subject_merge_to', '', true)"
        )


def _update_values(model, attname, subject_id, now) -> dict:
    values = {attname: subject_id}
    names = {field.name for field in model._meta.concrete_fields}
    if "updated_at" in names:
        values["updated_at"] = now
    return values


def repoint_rows(rel, ids, subject_id, now) -> int:
    model = rel.model()
    attname = model._meta.get_field(rel.field).attname
    return model._base_manager.filter(pk__in=ids).update(**_update_values(model, attname, subject_id, now))


def _remaining_references(source_ids) -> list:
    leftovers = []
    for rel in RELATIONS:
        model = rel.model()
        field = model._meta.get_field(rel.field)
        if rel.strategy == M2M:
            through = field.remote_field.through
            if through.objects.filter(subject_id__in=source_ids).exists():
                leftovers.append(rel.key)
        elif rel.strategy == REPOINT and model._base_manager.filter(**{f"{field.attname}__in": source_ids}).exists():
            leftovers.append(rel.key)
    return leftovers


def _apply_m2m(plan) -> None:
    rel = next(item for item in RELATIONS if item.strategy == M2M)
    through = rel.model()._meta.get_field(rel.field).remote_field.through
    target_id = plan["target"]["id"]
    move_ids = [entry["id"] for entry in plan["m2m"]["move"]]
    drop_ids = [entry["id"] for entry in plan["m2m"]["drop"]]
    if drop_ids and through.objects.filter(pk__in=drop_ids).delete()[0] != len(drop_ids):
        raise _drift()
    if move_ids and through.objects.filter(pk__in=move_ids).update(subject_id=target_id) != len(move_ids):
        raise _drift()


def _apply_json(plan) -> None:
    for ref in plan["json_refs"]:
        model = django_apps.get_model(ref["model"])
        changed = model._base_manager.filter(pk=ref["id"], **{ref["field"]: ref["before"]})
        if changed.update(**{ref["field"]: ref["after"]}) != 1:
            raise _drift()


def _drop_plan_rows(plan) -> list:
    ids = plan["dropped_plan_rows"]
    if not ids:
        return []
    rows = list(CurriculumSubject.objects.filter(pk__in=ids).order_by("pk"))
    if len(rows) != len(ids):
        raise _drift()
    snapshots = [row_snapshot(row) for row in rows]
    CurriculumSubject.objects.filter(pk__in=ids).delete()
    return snapshots


def _repoint_all(plan, target, sources, now) -> None:
    """Köçürmə ÖZ savepoint-ində: xətada savepoint geri qaytarılır (SET LOCAL icazəsi də onunla
    birlikdə sıfırlanır), təmizləmə SQL-i pozulmuş tranzaksiyada İŞLƏMİR — əsl DB xətası görünür."""
    source_ids = [source.pk for source in sources]
    with transaction.atomic():
        allow_offering_subject_change(source_ids, target.pk)
        for key, rows in plan["moved"].items():
            ids = [pk for pk_list in rows.values() for pk in pk_list]
            if ids and repoint_rows(relation(key), ids, target.pk, now) != len(ids):
                raise _drift()
        clear_offering_subject_change()


def check_deferred_constraints() -> None:
    """Gecikdirilmiş (DEFERRABLE) qaydaları İNDİ yoxla — məs. ``syllabus_reuse_same_org_subject``.

    Commit anında düşən xəta tranzaksiyadan kənarda 500 olardı; burada ``DatabaseError`` kimi çıxır.
    """
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def lock_offerings(subject_ids) -> None:
    """Hədəf + mənbə açılışlarını kilidlə: paralel qeydiyyat INSERT-i (FK → FOR KEY SHARE) gözləyir,
    önizləmə izi tətbiq anında etibarlı qalır."""
    from .models import CourseOffering

    list(
        CourseOffering._base_manager.select_for_update(of=("self",))
        .filter(subject_id__in=subject_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _archive_sources(sources, target, actor, now) -> None:
    reason = archive_reason_for(target)
    for source in sources:
        Subject.objects.filter(pk=source.pk).update(
            is_archived=True,
            is_active=False,
            archived_reason=reason,
            archived_at=now,
            archived_by=actor if getattr(actor, "pk", None) else None,
            updated_at=now,
        )


def _audit(*, organization, actor, request, target, sources, plan, snapshots, reason, digest):
    target_card = plan["target"]
    changes = {
        "kind": "subject_merge",
        "version": CHANGES_VERSION,
        "target": target_card["id"],
        "target_code": target.code,
        "sources": [card["id"] for card in plan["sources"]],
        "source_codes": [source.code for source in sources],
        "counts": counts(plan),
        "moved": plan["moved"],
        "kept": plan["kept"],
        "m2m": plan["m2m"],
        "json_refs": plan["json_refs"],
        "deleted_plan_rows": snapshots,
        "locked_plans": plan["locked_plans"],
        "archive_reason": archive_reason_for(target),
        "digest": digest,
    }
    entry = log_action(
        action=AuditAction.UPDATE,
        user=actor if getattr(actor, "pk", None) else None,
        organization=organization,
        obj=target,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(target.pk),
        resource_repr=f"{', '.join(source.code for source in sources)} → {target.code}"[:500],
        old_values={"sources": plan["sources"]},
        new_values={"target": target_card, "archived_reason": archive_reason_for(target)},
        changes=changes,
        reason=reason,
    )
    # Hər mənbə kartının ÖZ tarixçəsində də görünsün (əsas qeydə istinadla).
    log_actions(
        [
            {
                "action": AuditAction.UPDATE,
                "user": actor if getattr(actor, "pk", None) else None,
                "organization": organization,
                "obj": source,
                "request": request,
                "resource_type": f"{AUDIT_RESOURCE}.source",
                "resource_id": str(entry.pk),
                "resource_repr": f"{source.code} → {target.code}",
                "old_values": {"is_archived": card["is_archived"], "is_active": card["is_active"]},
                "new_values": {"is_archived": True, "is_active": False, "archived_reason": archive_reason_for(target)},
                "changes": {"merge_audit_id": str(entry.pk), "target": str(target.pk)},
                "reason": reason,
            }
            for source, card in zip(sources, plan["sources"], strict=True)
        ]
    )
    return entry


def apply(*, organization, actor, target_ref, source_refs, reason, expected_digest, request=None, by_code=False):
    """Önizlənmiş birləşdirməni yazır. Qaytarır: ``{"audit_id", "counts", ...}``."""
    reason = clean_reason(reason)
    expected = str(expected_digest or "").strip()
    if not expected:
        raise MergeError("preview_required", pgettext(_CTX, "Əvvəlcə önizləməyə baxın."))
    with transaction.atomic():
        target, sources = resolve_subjects(organization, target_ref, source_refs, by_code=by_code)
        locked = list(
            Subject.objects.select_for_update()
            .filter(pk__in=[target.pk, *(source.pk for source in sources)])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if len(locked) != len(sources) + 1:
            raise _drift()
        target, sources = resolve_subjects(organization, target_ref, source_refs, by_code=by_code)
        lock_offerings([target.pk, *(source.pk for source in sources)])
        plan = collect(organization, target, sources)
        digest = plan_digest(plan)
        if digest != expected:
            raise _drift()
        if plan["conflicts"]["blocking"]:
            raise MergeError(
                "conflicts",
                pgettext(_CTX, "Toqquşmalar həll edilməyib — birləşdirmə bloklanır."),
                status=409,
                details={"blocking": plan["conflicts"]["blocking"][:50]},
            )
        now = timezone.now()
        snapshots = _drop_plan_rows(plan)
        _repoint_all(plan, target, sources, now)
        _apply_m2m(plan)
        _apply_json(plan)
        leftovers = _remaining_references([source.pk for source in sources])
        if leftovers:
            raise _drift()
        try:
            with transaction.atomic():
                check_deferred_constraints()
        except DatabaseError as exc:
            raise MergeError(
                "db_rule",
                pgettext(_CTX, "Birləşmə DB qaydasını pozur — heç nə yazılmadı."),
                status=409,
                details={"error": str(exc)[:300]},
            ) from exc
        _archive_sources(sources, target, actor, now)
        entry = _audit(
            organization=organization,
            actor=actor,
            request=request,
            target=target,
            sources=sources,
            plan=plan,
            snapshots=snapshots,
            reason=reason,
            digest=digest,
        )
    return {
        "audit_id": str(entry.pk),
        "target": plan["target"],
        "sources": [source.code for source in sources],
        "counts": counts(plan),
    }


__all__ = [
    "allow_offering_subject_change",
    "apply",
    "check_deferred_constraints",
    "lock_offerings",
    "clear_offering_subject_change",
    "repoint_rows",
    "row_snapshot",
]
