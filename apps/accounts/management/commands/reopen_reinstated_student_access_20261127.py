"""``reopen_reinstated_student_access_20261127`` — bərpa əmri verilib, girişi arxivdə qalmış tələbələr (2026-11-27).

Hal: xaric/məzun əmri girişi bağlayır (``registrar.movements._sync_access_state``, təşkilatsız profil də daxil), bərpa
əmri isə əvvəl yalnız ``organization = org`` profilini açırdı — təşkilatsız (``organization IS NULL``) profilli tələbə
«Bərpa et»dən sonra akademik olaraq ``enrolled`` olur, amma daxil ola bilmirdi. Düzəliş (``identity_reinstate`` +
accounts 0039) yeni əmrlər üçündür; bu əmr ARTIQ verilmiş bərpa əmrlərinin girişini eyni rəsmi səthlə açır.

NAMİZƏD (hamısı birlikdə): akademik qeyd ``enrolled``; tələbənin profili (bu təşkilat və ya təşkilatsız) ``archived``;
qeydin SON hərəkət əmri ``reinstatement``-dir. Son əmri bərpa OLMAYAN arxiv hesablarına (köhnə köçürmə izləri)
TOXUNULMUR — onlar yalnız sayılır (``skip_no_reinstatement_order``); onları RİM-in «Arxivdən çıxar» səthi həll edir.

Açılış ``reinstate_student_access`` ilə (accounts 0021/0039 funksiyası, sübut = həmin bərpa əmrinin nömrə + tarixi),
hər tələbə öz SAVEPOINT-ində: rədd olunan sayılır, paket dayanmır.

* DEFOLT DRY-RUN; ``--apply`` yazır; paket ``reopen-YYYYMMDD-HHMMSS-xxxx`` audit sətrindədir (hesab id-ləri).
* ``--undo <paket> --apply`` — paketdə açılmış və hələ ``active`` olan hesabları yenidən ``archived`` edir.
* Stdout-a YALNIZ saylar (``reopen_access: açar=dəyər …``) — tələbə adı çap olunmur.

    manage.py reopen_reinstated_student_access_20261127 --org qku --actor <superadmin> [--apply] [--undo <paket>]
"""

from __future__ import annotations

import re
import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "reopen_access:"
RESOURCE = "accounts.reinstated_access_reopen_batch"
BATCH_RE = re.compile(r"^reopen-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


class _DryRunRollback(Exception):
    pass


def new_batch() -> str:
    return f"reopen-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def candidates(organization, *, counts: Counter) -> list:
    """``(record, reinstatement_movement)`` cütləri — hər tələbə bir dəfə."""
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    movement_model = django_apps.get_model("registrar", "StudentMovement")
    profile_model = django_apps.get_model("accounts", "UserProfile")

    archived = {
        user_id: org_id
        for user_id, org_id in profile_model.objects.filter(access_state=profile_model.AccessState.ARCHIVED)
        .filter(Q(organization=organization) | Q(organization__isnull=True))
        .values_list("user_id", "organization_id")
    }
    records = list(
        record_model.objects.filter(organization=organization, status="enrolled", student_id__in=list(archived))
        .select_related("student")
        .order_by("pk")
    )
    last = {}
    for movement in (
        movement_model.objects.filter(organization=organization, record_id__in=[record.pk for record in records])
        .only("record_id", "kind", "order_number", "order_date", "created_at")
        .order_by("-created_at", "-pk")
    ):
        last.setdefault(movement.record_id, movement)

    chosen, seen = [], set()
    for record in records:
        if record.student_id in seen:
            continue
        seen.add(record.student_id)
        counts["archived_enrolled"] += 1
        if archived.get(record.student_id) is None:
            counts["orgless_profile"] += 1
        movement = last.get(record.pk)
        if movement is None or movement.kind != "reinstatement":
            counts["skip_no_reinstatement_order"] += 1
            continue
        counts["candidates"] += 1
        chosen.append((record, movement))
    return chosen


def reopen(organization, *, actor, done: list) -> Counter:
    from apps.accounts.services.identity_reinstate import order_evidence_digest, reinstate_student_access

    counts = Counter(reopened=0)
    for record, movement in candidates(organization, counts=counts):
        digest = order_evidence_digest(
            order_number=movement.order_number,
            order_date=movement.order_date,
            record_id=record.pk,
            actor_id=actor.pk,
        )
        try:
            with transaction.atomic():
                result = reinstate_student_access(
                    user=record.student, organization=organization, actor=actor, evidence_digest=digest
                )
        except Exception as exc:  # noqa: BLE001 — bir hesabın rəddi paketi dayandırmır
            counts[failure_code(exc, prefix="failed")] += 1
            continue
        if result.reopened:
            counts["reopened"] += 1
            done.append(record.student_id)
        else:
            counts["already_active"] += 1
    return counts


def undo(organization, batch: str) -> Counter:
    audit_model = django_apps.get_model("audit", "AuditLog")
    profile_model = django_apps.get_model("accounts", "UserProfile")
    entry = audit_model.objects.filter(resource_type=RESOURCE, resource_id=batch).order_by("-pk").first()
    if entry is None:
        raise CommandError("batch_not_found")
    ids = [int(pk) for pk in (entry.new_values or {}).get("users", [])]
    # `active → archived` məhdudlaşdırıcıdır (trigger sərbəst buraxır) — xaric əmrinin öz yolu ilə eyni.
    rearchived = profile_model.objects.filter(
        user_id__in=ids, organization=organization, access_state=profile_model.AccessState.ACTIVE
    ).update(access_state=profile_model.AccessState.ARCHIVED, updated_at=timezone.now())
    return Counter(rearchived=rearchived, skipped_not_active=len(ids) - rearchived)


def failure_code(exc, *, prefix: str = "reopen_access_failed") -> str:
    text = re.sub(r"[^a-z0-9]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"{prefix}_{text}"[:120]


class Command(BaseCommand):
    help = "Bərpa əmri verilmiş, girişi arxivdə qalmış tələbələrin girişini açır — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--undo", default="")

    def handle(self, *args, **options):
        organization = (
            django_apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
        )
        if organization is None:
            raise CommandError("organization_not_found")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        undo_batch = (options["undo"] or "").strip()
        if undo_batch and not BATCH_RE.match(undo_batch):
            raise CommandError("bad_batch")
        batch = new_batch()
        counts, done = Counter(), []
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo_batch:
                    counts = undo(organization, undo_batch)
                else:
                    counts = reopen(organization, actor=actor, done=done)
                    if done:
                        log_action(
                            AuditAction.UPDATE,
                            user=actor,
                            organization=organization,
                            new_values={"users": [str(pk) for pk in done]},
                            reason=f"reopen_reinstated_student_access_20261127 {batch}",
                            resource_type=RESOURCE,
                            resource_id=batch,
                            resource_repr=batch,
                        )
                if not options["apply"]:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız kodu göstərir
            raise CommandError(failure_code(exc)) from exc
        mode = "apply" if options["apply"] else "dry_run"
        shown = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        self.stdout.write(f"{PREFIX} mode={mode} {shown}")
        if options["apply"] and not undo_batch and done:
            self.stdout.write(f"{PREFIX} batch={batch}")
