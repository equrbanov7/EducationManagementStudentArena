"""``move_merged_fin_20261115`` — birləşdirilmiş dublikat hesabın FİN-ini əsas hesaba köçürür (sahib 2026-11-15).

Hal: dekan Afərin Abbasova — dublikat 9507 (FİN-i var) ``merge_duplicate_teacher`` ilə 7742-yə birləşdirildi və
bloklandı; 7742-də FİN yoxdur. FİN unikal olduğu üçün (``accounts_userprofile_fin_primary_uniq``) əvvəl mənbədən
silinir, sonra hədəfə yazılır — bir tranzaksiyada.

Qapılar: mənbə bloklu (``is_active=False``), hədəf aktiv; mənbənin FİN-i var, hədəfinki BOŞDUR; heç biri bağlı
(``fin_shared_with``) hesab deyil. Pozulsa həmin cüt ötürülür (``skipped_<səbəb>``), heç nə yazılmır.

* DEFOLT DRY-RUN; ``--apply`` yazır; paket ``finmove-YYYYMMDD-HHMMSS-xxxx`` audit sətrindədir (FİN audit-ə yazılmır —
  yalnız id-lər).
* ``--undo <paket> --apply`` — FİN-i hədəfdən mənbəyə qaytarır (hədəfin FİN-i o vaxtdan dəyişməyibsə).
* Stdout-a YALNIZ saylar: ``fin_move: açar=dəyər …`` (ad / FİN çap olunmur).

    manage.py move_merged_fin_20261115 --org qku --actor <superadmin> --pairs 9507:7742[,SRC:TGT…] [--apply]
"""

from __future__ import annotations

import re
import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PAIRS_RE = re.compile(r"^[0-9]{1,7}:[0-9]{1,7}(,[0-9]{1,7}:[0-9]{1,7}){0,49}$")
BATCH_RE = re.compile(r"^finmove-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
RESOURCE = "accounts.fin_move_batch"
PREFIX = "fin_move:"


class _DryRunRollback(Exception):
    pass


def new_batch() -> str:
    return f"finmove-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def parse_pairs(raw: str) -> list[tuple[int, int]]:
    raw = (raw or "").strip()
    if not PAIRS_RE.match(raw):
        raise CommandError("bad_pairs")
    return [tuple(int(part) for part in pair.split(":")) for pair in raw.split(",")]


def _profiles(source_id, target_id):
    profile_model = django_apps.get_model("accounts", "UserProfile")
    rows = {
        p.user_id: p
        for p in profile_model.objects.select_for_update()
        .select_related("user")
        .filter(user_id__in=[source_id, target_id])
    }
    return rows.get(source_id), rows.get(target_id)


def skip_reason(source, target) -> str:
    if source is None or target is None:
        return "profile_missing"
    if source.user.is_active:
        return "source_active"
    if not target.user.is_active:
        return "target_inactive"
    if not source.fin:
        return "source_no_fin"
    if target.fin:
        return "target_has_fin"
    if source.fin_shared_with_id or target.fin_shared_with_id:
        return "shared_fin"
    return ""


def move(organization, pairs, *, actor, batch) -> Counter:
    counts = Counter(pairs=len(pairs), moved=0)
    moved = []
    for source_id, target_id in pairs:
        source, target = _profiles(source_id, target_id)
        reason = skip_reason(source, target)
        if reason:
            counts[f"skipped_{reason}"] += 1
            continue
        fin = source.fin
        source.fin = None
        source.save(update_fields=["fin"])
        target.fin = fin
        target.save(update_fields=["fin"])
        moved.append([source_id, target_id])
        counts["moved"] += 1
    if moved:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"pairs": moved},
            reason=f"move_merged_fin_20261115 {batch}",
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=batch,
        )
    return counts


def undo(organization, batch, *, actor) -> Counter:
    audit_model = django_apps.get_model("audit", "AuditLog")
    entry = audit_model.objects.filter(resource_type=RESOURCE, resource_id=batch).order_by("-pk").first()
    if entry is None:
        raise CommandError("batch_not_found")
    counts = Counter(restored=0)
    for source_id, target_id in (entry.new_values or {}).get("pairs", []):
        source, target = _profiles(source_id, target_id)
        if source is None or target is None or not target.fin or source.fin:
            counts["skipped"] += 1
            continue
        fin = target.fin
        target.fin = None
        target.save(update_fields=["fin"])
        source.fin = fin
        source.save(update_fields=["fin"])
        counts["restored"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"undo": batch, "restored": counts["restored"]},
        reason=f"move_merged_fin_20261115 undo {batch}",
        resource_type=RESOURCE,
        resource_id=f"{batch}-undo",
        resource_repr=batch,
    )
    return counts


def failure_code(exc) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"fin_move_failed_{text}"[:120]


class Command(BaseCommand):
    help = "Birləşdirilmiş dublikatın FİN-ini əsas hesaba köçürür — dry-run defolt, --undo geri qaytarır."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--pairs", default="", help="MƏNBƏ:HƏDƏF[,MƏNBƏ:HƏDƏF…]")
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
        pairs = [] if undo_batch else parse_pairs(options["pairs"])
        batch = new_batch()
        counts = Counter()
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo_batch:
                    counts = undo(organization, undo_batch, actor=actor)
                else:
                    counts = move(organization, pairs, actor=actor, batch=batch)
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
        if options["apply"] and not undo_batch and counts.get("moved"):
            self.stdout.write(f"{PREFIX} batch={batch}")
