"""``fix_azdili_load_20261110`` — Azərbaycan dili və ədəbiyyatı kafedrasının rəsmi dərs yükü faylı ilə tutuşdurma
(sahib 2026-11-10: «müəllimlərin dərs yüklərinə əsasən düzəlt»). Fayl: «Azərbaycan dili və ədəbiyyatı dərs yükü
şablon (2).xlsx».

Sistemdə kafedranın tapşırığında olub faylda OLMAYAN sətirlər başqa kafedranın fənləridir (sahib 2026-11-09:
«fənn hansı kafedraya aiddirsə ora»):

* Hacıyeva Nigar — «Öyrənilən əsas dil-1/-3/-5» (336 F1, 335F1, 335F2, 334F1+334F2) Filologiya (İngilis dili və
  ədəbiyyatı) qruplarıdır → İngilis dili və tərcümə, ingilis dili və ədəbiyyatı kafedrasının tapşırığı (eyni fənnin
  336F2 sətri oradadır);
* Mursalıyeva Gültəkin — «Klinik psixologiya» (034, 134 TSPX), «Tətbiqi sosial psixologiyanın aktual məsələləri»
  (209/6SP), Bəhmənli Dilbər — «Tədqiqat metodları» (209/6KP ing) → Sosial iş kafedrasının tapşırığı (034 ing və
  209/6 MP/KP/SP sətirləri oradadır).

Faylın digər fərqləri:

* «136 Sİ» seminarı faylda BİR sətirdir (45 saat) — 136 Si-1 sətri artıq hər iki alt qrupu daşıyır, ayrıca qalan boş
  (bölgüsüz) «136 Si-2» sətri silinir (jurnal qalır — açılış sətrə bağlı deyil);
* Heydərov Rasimin bütün sətirləri və Qəniyeva Jalənin «536 T az» sətri faylda «saathesabı: bəli»;
* «Dünya ədəbiyyatı - 3 (XX-XXI əsr)» 3/334F2 seminar sətri (fənni ``fix_offering_subject`` ilə əvvəl düzəldilir)
  3/334F1 mühazirə sətrinin axın ortağıdır (``patok_lead``) — faylda «M15, S30+30».

Hər dəyişiklik audit sətrindədir (``workload.task_row_move``). Defolt dry-run; stdout-a YALNIZ saylar
(``task_rows_move: açar=say``). Təkrar qaçış idempotentdir (``already_*``).
"""

from __future__ import annotations

import re
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "task_rows_move:"
RESOURCE = "workload.task_row_move"
REASON = "Sahib 2026-11-10: Azərbaycan dili və ədəbiyyatı kafedrasının rəsmi dərs yükü faylı ilə tutuşdurma"

SOURCE_TASK = "45b29907-4290-4028-bea7-943599cb0b48"  # Azərbaycan dili və ədəbiyyatı 2026/2027
ENGLISH_TASK = "9becb08c-5b1a-4893-99fa-e8494d6f6335"  # İngilis dili və tərcümə, ingilis dili və ədəbiyyatı
SOSIAL_TASK = "a2415422-6b68-4752-920c-47502b6a5ae1"  # Sosial iş

MOVES = (
    # Hacıyeva Nigar — Öyrənilən əsas dil (İngilis dili və ədəbiyyatı filologiyası qrupları)
    ("49ec0f69-b2bc-437c-aa28-d8ae8d31de7c", ENGLISH_TASK),
    ("14697e74-876b-44eb-9119-e3f4852058d3", ENGLISH_TASK),
    ("17d4e3c9-4e19-4e2b-aa64-dc69ec6b2f08", ENGLISH_TASK),
    ("e5043cf8-1b3b-425a-9206-cb7551ed34ad", ENGLISH_TASK),
    # Mursalıyeva Gültəkin — psixologiya fənləri
    ("40305d22-dac5-4ee8-91b8-7c7f6ed826b9", SOSIAL_TASK),
    ("0e8f5f38-1660-4b2c-a07a-6b72d4bd06f4", SOSIAL_TASK),
    ("8e4be310-9400-4402-8bd0-9725a1d4c3c9", SOSIAL_TASK),
    # Bəhmənli Dilbər — Tədqiqat metodları 209/6KP ing
    ("732755cf-ddca-4131-9a7b-ae5b6c0b7bba", SOSIAL_TASK),
)

#: Bölgüsüz qalmış «136 Si-2» seminar sətri (136 Si-1 sətri iki alt qrupu daşıyır).
DELETE_ROWS = ("37204b05-e260-4c96-802e-abde7f90bc58",)

#: Faylda «saathesabı: bəli» — sətir id-ləri (bütün bölgüləri).
HOURLY_ROWS = (
    "34a57a39-2ea6-41ba-8939-6b322bcc4e51",  # Heydərov — Sintaksis-2 mühazirə 3/334F1+F2
    "61a56a45-217f-4502-8440-c5c739f1431b",  # Heydərov — Fonetika 3/336F1
    "20e3a7f5-f6f9-465d-9416-2e16ff78394c",  # Heydərov — Fonetika 3/336F2
    "0fdcc48f-013a-4e37-b58f-5f06666089eb",  # Heydərov — Öyrənilən əsas dil-4 3/335F1 (yaz)
    "0796607f-c37f-467e-87c1-0bfc2ba6c6d6",  # Heydərov — Mətn sintaksisi 3/334F2 (yaz)
    "5294f2fa-af7d-47cc-8a3d-dffee7620325",  # Qəniyeva — 536 T az (yaz)
)

#: Axın: (ortaq sətir, aparıcı sətir) — eyni fənn, ortaqda mühazirə 0.
PATOK = (("e6ee5a21-e700-49cb-99f5-56f8c6379ec4", "9f87ef1e-57ed-4fc1-8a06-65e001bd0017"),)


def failure_code(exc) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"azdili_load_failed_{slug}"[:120]


def run(*, organization, actor, counts: Counter) -> None:
    TeachingTask = django_apps.get_model("workload", "TeachingTask")
    TeachingTaskRow = django_apps.get_model("workload", "TeachingTaskRow")
    TeacherAssignment = django_apps.get_model("workload", "TeacherAssignment")
    tasks = {
        pk: TeachingTask.objects.filter(organization=organization, pk=pk).first() for pk in (ENGLISH_TASK, SOSIAL_TASK)
    }
    if any(task is None for task in tasks.values()):
        raise CommandError("task_rows_move_target_missing")

    def row(pk, task_ids):
        return (
            TeachingTaskRow.objects.select_for_update()
            .filter(organization=organization, pk=pk, task_id__in=task_ids)
            .first()
        )

    def audit(obj, *, old, new):
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=obj,
            old_values=old,
            new_values=new,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(obj.pk),
        )

    for pk, target in MOVES:
        item = row(pk, (SOURCE_TASK, target))
        if item is None:
            counts["row_missing"] += 1
        elif str(item.task_id) == target:
            counts["already_moved"] += 1
        else:
            audit(item, old={"task": str(item.task_id)}, new={"task": target})
            item.task = tasks[target]
            item.save(update_fields=["task", "updated_at"])
            counts["rows_moved"] += 1

    for pk in DELETE_ROWS:
        item = row(pk, (SOURCE_TASK,))
        if item is None:
            counts["already_deleted"] += 1
            continue
        if TeacherAssignment.objects.filter(organization=organization, row=item).exclude(teacher__isnull=True).exists():
            counts["delete_skipped_assigned"] += 1
            continue
        TeacherAssignment.objects.filter(organization=organization, row=item).delete()
        audit(
            item,
            old={"row": str(item.pk), "groups_text": item.groups_text, "seminar_total": item.seminar_total},
            new={"deleted": True},
        )
        item.delete()
        counts["rows_deleted"] += 1

    for pk in HOURLY_ROWS:
        assignments = TeacherAssignment.objects.filter(organization=organization, row_id=pk, row__task_id=SOURCE_TASK)
        counts["hourly_assignments_total"] += assignments.count()
        counts["hourly_set"] += assignments.exclude(is_hourly_paid=True).update(is_hourly_paid=True)

    for partner_pk, lead_pk in PATOK:
        partner, lead = row(partner_pk, (SOURCE_TASK,)), row(lead_pk, (SOURCE_TASK,))
        if partner is None or lead is None:
            counts["patok_row_missing"] += 1
        elif str(partner.patok_lead_id or "") == lead_pk:
            counts["already_patok"] += 1
        elif partner.subject_id != lead.subject_id or partner.season != lead.season or partner.lecture_total:
            counts["patok_skipped_mismatch"] += 1
        else:
            audit(partner, old={"patok_lead": str(partner.patok_lead_id or "")}, new={"patok_lead": lead_pk})
            partner.patok_lead = lead
            partner.save(update_fields=["patok_lead", "updated_at"])
            counts["patok_linked"] += 1


class Command(BaseCommand):
    help = "Azərbaycan dili və ədəbiyyatı kafedrasının yükü — rəsmi fayla uyğunlaşdırma (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        actor = (
            get_user_model()
            .objects.filter(username=str(options["actor"]).strip(), is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        Organization = django_apps.get_model("organizations", "Organization")
        counts: Counter = Counter()
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("task_rows_move_organization_unknown")
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
                with transaction.atomic():
                    run(organization=organization, actor=actor, counts=counts)
                    if not options["apply"]:
                        transaction.set_rollback(True)
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops yalnız kodu göstərir
            raise CommandError(failure_code(exc)) from exc
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
