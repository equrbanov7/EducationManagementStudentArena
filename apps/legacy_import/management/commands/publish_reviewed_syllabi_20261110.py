"""``publish_reviewed_syllabi_20261110`` — həftəlik planı dolu qaralama sillabusları operator kimi göndər + təsdiqlə.

Sahib 2026-11-10: «əgər həftəlik dərslər varsa göndər və təsdiqlə». Kafedra yoxlamasında təsdiqsiz qalan 10
qaralamadan həftəlik mövzuları dolu olanlar :data:`VERSIONS`-dədir. Yol ``publish_reviewed_draft``-dır: müəllim
TƏQLİD OLUNMUR (göndərən/təsdiqləyən aktiv superadmin, müəlliflik müəllimdə qalır) və yalnız 100% tamamlanmış
qaralama yayımlanır — natamam olan ``skipped_incomplete`` sayılır, heç nə yazılmır.

Defolt dry-run; stdout-a YALNIZ saylar (``reviewed_publish: açar=say``). Təkrar qaçış idempotentdir.
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.legacy_import.services.repair_support import RepairContext, establish_rls_scope, resolve_organization
from apps.syllabus.public import (
    TransitionDenied,
    completion_report,
    content_fingerprints,
    publish_reviewed_draft,
    resolve_actor,
    section_data_map,
)
from core.rls_pooling import rls_worker_atomic

PREFIX = "reviewed_publish:"
REASON = "Sahib 2026-11-10: həftəlik planı dolu qaralama — operator göndərişi və təsdiqi (müəlliflik müəllimdədir)."

#: Kafedra yoxlaması (2026-11-10): həftəlik mövzuları dolu qaralamalar (versiya id → qısa açar).
VERSIONS = {
    "a752921f-1914-4144-9da9-bda4dfc9b86b": "neyro_209_5",  # 15/15 həftə, 100%
    "948ea12f-65d7-404f-9bcf-d1641a921ccd": "biologiya_235qm",  # 15/15 həftə
    "7bc68bd7-1d5b-40b3-9e19-29f6c28ceed5": "diskret_235ke",  # 15 həftə dolu
}


def failure_code(exc: Exception) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"reviewed_publish_failed_{slug}"[:120]


def run(*, organization, actor, apply: bool, counts: Counter) -> None:
    SyllabusVersion = django_apps.get_model("syllabus", "SyllabusVersion")
    syllabus_actor = resolve_actor(actor, organization)
    for version_id, key in VERSIONS.items():
        version = SyllabusVersion.objects.filter(organization=organization, pk=version_id).first()
        if version is None:
            counts[f"{key}_missing"] += 1
            continue
        if version.status == "approved":
            counts[f"{key}_already_approved"] += 1
            continue
        if version.status not in ("draft", "revision"):
            counts[f"{key}_status_{version.status}"] += 1
            continue
        report = completion_report(version, organization)
        if report.percent != 100:
            counts[f"{key}_skipped_incomplete_{report.percent}"] += 1
            for issue in report.issues:
                counts[f"{key}_issue_{issue.section}_{issue.code}"[:60]] += 1
            continue
        if not apply:
            counts[f"{key}_would_publish"] += 1
            continue
        sha = content_fingerprints(section_data_map(version))["canonical_body_sha256"]
        try:
            publish_reviewed_draft(version=version, actor=syllabus_actor, expected_body_sha256=sha, reason=REASON)
        except TransitionDenied as denied:
            counts[f"{key}_denied_{denied.code}"[:60].replace(".", "_")] += 1
            continue
        counts[f"{key}_published"] += 1


class Command(BaseCommand):
    help = "Həftəlik planı dolu qaralama sillabusları operator kimi göndərib təsdiqləyir (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=str(options["actor"]).strip(), is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        counts: Counter = Counter()
        try:
            with rls_worker_atomic():
                organization = resolve_organization(options["org"])
                # Bypass YOX — yalnız bu tenant + aktor konteksti (repair_audit_syllabi_20261109 ilə eyni yol).
                establish_rls_scope(RepairContext(organization, actor, options["apply"], 0))
                with transaction.atomic():
                    run(organization=organization, actor=actor, apply=options["apply"], counts=counts)
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız CommandError kodunu göstərir
            raise CommandError(failure_code(exc)) from None
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
