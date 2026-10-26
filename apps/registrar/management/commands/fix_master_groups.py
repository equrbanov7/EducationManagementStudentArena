"""``fix_master_groups`` — magistr qrupunun dərəcəsi, ixtisası və tələbə proqramı (sahib 2026-10-26).

Sahib: «Magistr dataları köçməyib … dərslər 18:40 / 20:00 varsa magistr say onları». İlk köçürmədə yaradılan
birinci kurs magistr qruplarında (``505/6 G``, ``631/6 K``, ``632/6 İ``, ``709/6 SBİO`` …) qrupun dərəcəsi yazılmamış,
qrup bakalavr ixtisasının altına düşmüş, tələbə qeydi isə ixtisasın BAKALAVR proqramına bağlanmışdı — sonrakı
deltalar yalnız yeni qrupa dərəcə yazırdı.

Plan faylı lokal qurulur (köhnə sistemin ixtisas bağlantısı + 18:40/20:00 dərs payı ≥ 30 %), YALNIZ id-lərdir::

    {"format": "master-groups/1", "groups": [{"group": uuid, "degree": "master"|null, "specialty": uuid|null,
      "records": [{"record": uuid, "program": uuid, "curriculum": uuid, "substituted": bool}]}]}

Yazı (hər biri yenidən yoxlanılır, plan köhnəlibsə həmin sətir atlanır və sayılır):

* qrup ``settings.degree_level = master``; ``specialty`` verilibsə qrup həmin magistr ixtisasının altına keçir
  (``OrgUnit.save`` yolu yenidən hesablayır);
* tələbə qeydi (aktiv, hələ həmin qrupda, proqramı magistr DEYİL) → magistr proqramı + plan (eyni qəbul ili,
  yoxsa ən yaxın təsdiqlənmiş plan — ``substituted``). Bu, «İxtisas dəyişikliyi» HƏRƏKƏTİ deyil (əmr yoxdur) —
  köçürmə xətasının düzəlişidir; ``movements._apply_program`` ilə eyni sahələr, audit ilə.

DEFOLT DRY-RUN (eyni kod, geri qaytarılır). Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import json
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...models import Curriculum, Program, StudentAcademicRecord

PREFIX = "master_groups:"
FORMAT = "master-groups/1"
REASON = "Magistr qrupu düzəlişi (18:40/20:00 dərsləri + köhnə sistemin ixtisası) — sahibin 2026-10-26 tapşırığı"


class Command(BaseCommand):
    help = "Magistr qruplarının dərəcəsini, ixtisasını və tələbə proqramını plan faylı ilə düzəldir."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", required=True, help="master-groups/1 JSON faylı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        try:
            with open(options["file"], encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            raise CommandError("master_groups_file_unreadable") from None
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise CommandError("master_groups_format_unknown")
        Organization = django_apps.get_model("organizations", "Organization")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("master_groups_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                for item in data.get("groups") or []:
                    self._group(organization, actor, item, counts)
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))

    def _group(self, organization, actor, item, counts):
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        counts["groups_in_file"] += 1
        unit = OrgUnit.objects.filter(organization=organization, pk=item.get("group"), unit_type="group").first()
        if unit is None:
            counts["group_missing"] += 1
            return
        old = {"degree_level": (unit.settings or {}).get("degree_level", ""), "parent": str(unit.parent_id or "")}
        changed = []
        if item.get("degree") == "master" and old["degree_level"] != "master":
            unit.settings = {**(unit.settings or {}), "degree_level": "master"}
            changed.append("settings")
            counts["group_degree_set"] += 1
        specialty_id = item.get("specialty")
        if specialty_id and str(unit.parent_id) != str(specialty_id):
            specialty = OrgUnit.objects.filter(
                organization=organization, pk=specialty_id, unit_type="specialty"
            ).first()
            if specialty is None:
                counts["specialty_missing"] += 1
            else:
                unit.parent = specialty
                changed.append("parent")
                counts["group_moved"] += 1
        if changed:
            unit.save()
            log_action(
                action=AuditAction.UPDATE,
                user=actor,
                organization=organization,
                obj=unit,
                reason=f"groups: master group fix — {REASON}",
                old_values=old,
                new_values={
                    "degree_level": (unit.settings or {}).get("degree_level", ""),
                    "parent": str(unit.parent_id or ""),
                },
            )
        for row in item.get("records") or []:
            self._record(organization, actor, unit, row, counts)

    def _record(self, organization, actor, unit, row, counts):
        counts["records_in_file"] += 1
        record = (
            StudentAcademicRecord.objects.select_for_update(of=("self",))
            .select_related("program")
            .filter(organization=organization, pk=row.get("record"), is_active=True)
            .first()
        )
        if record is None or record.group_id != unit.pk:
            counts["record_stale"] += 1
            return
        if record.program.degree_level == "master":
            counts["record_already_master"] += 1
            return
        program = Program.objects.filter(
            organization=organization, pk=row.get("program"), degree_level="master"
        ).first()
        curriculum = Curriculum.objects.filter(organization=organization, pk=row.get("curriculum")).first()
        if program is None or curriculum is None or curriculum.program_id != program.pk:
            counts["program_or_curriculum_invalid"] += 1
            return
        clash = (
            StudentAcademicRecord.objects.filter(
                organization=organization, student_id=record.student_id, program_id=program.pk
            )
            .exclude(pk=record.pk)
            .exists()
        )
        if clash:
            counts["record_program_exists"] += 1
            return
        old = {"program": str(record.program_id), "curriculum": str(record.curriculum_id)}
        record.program = program
        record.curriculum = curriculum
        # `update_fields` MƏCBURİDİR — tam save qrup sahəsini rəsmi köçürmə sübutu olmadan yoxlayır.
        record.save(update_fields=["program", "curriculum", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=record,
            reason=f"registrar: master program fix (not a movement) — {REASON}",
            old_values=old,
            new_values={"program": str(program.pk), "curriculum": str(curriculum.pk)},
        )
        counts["records_switched"] += 1
        counts["records_curriculum_substituted"] += int(bool(row.get("substituted")))
