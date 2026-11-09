"""``move_politologiya_rows_20261109`` — Politologiya kafedrasının rəsmi dərs yükü faylında olan, sistemdə isə BAŞQA
kafedranın tapşırığına düşmüş 6 sətri öz kafedrasına köçürür (sahib 2026-11-09: «düzgün olsun»).

Fayl (Ders_yuku_2026-2027.xlsx, Politologiya və beynəlxalq münasibətlər kafedrası) ilə sistem tutuşdurması:
Heydərli Aytənin 4 payız sətri «İnformasiya texnologiyaları kafedrası», Əsgərov Muradın 2 payız sətri «Dizayn
kafedrası» tapşırığındadır — faylda hər ikisi Politologiyanın yüküdür; yükləyici (``load_upload``) həmin sətirləri
``other_chair_row`` deyə ATLAYIR (saat iki dəfə sayılmasın). Jurnalların hamısı var və aparılır — yalnız sətirlər
yerində deyil. :data:`PLAN`:

* 6 sətir → Politologiya tapşırığı (``task`` dəyişir; faculty/ixtisas/qrup toxunulmaz); Məmmədov Adıgözəlin 2 payız
  sətri (sosial iş fənləri, Sİ qrupları) Politologiyadan → Sosial iş tapşırığı (sahib 2026-11-09);
* Heydərlinin bölgüləri faylda «saathesabı: bəli» → ``is_hourly_paid=True``;
* «Politologiya 533DBİ» (S30, ayrıca sətir) faylda «533 İ, 533 DBİ, 533 ML, 533 MU» BİR sətirdir (M15 S15) →
  533DBİ qrupu ML/MU/İ sətrinə əlavə olunur, ayrıca sətir bölgüsü ilə silinir (jurnal qalır — açılış sətrə bağlı
  deyil).

Hər dəyişiklik audit sətrindədir (``workload.task_row_move``). Defolt dry-run; stdout-a YALNIZ saylar
(``task_rows_move: açar=say``). Təkrar qaçış idempotentdir (``already_*``).
"""

from __future__ import annotations

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
REASON = "Sahib 2026-11-09: Politologiya kafedrasının rəsmi dərs yükü faylı — sətir öz kafedrasına köçürüldü"

#: Hədəf: Politologiya və beynəlxalq münasibətlər kafedrasının 2026/2027 tapşırığı.
TARGET_TASK = "574fdd61-6f93-4387-8b1c-55f7b98bfab2"
#: Sosial iş kafedrasının 2026/2027 tapşırığı (sahib 2026-11-09: «fənn hansı kafedraya aiddirsə ora»).
SOSIAL_TASK = "a2415422-6b68-4752-920c-47502b6a5ae1"
IT_TASK = "663dbec7-6043-4b12-9f69-9d1278a1b7cb"
DIZAYN_TASK = "d52fe9ce-94ae-422f-8829-69e988f986f9"

#: Köçürülən sətirlər (id, mənbə tapşırıq, hədəf tapşırıq, saathesabı?).
MOVES = (
    # Heydərli Aytən — İnformasiya texnologiyaları tapşırığından → Politologiya (faylda saathesabı «bəli»)
    {"row": "7f26354c-e1e6-4552-92a0-a663837afcb9", "source_task": IT_TASK, "target_task": TARGET_TASK, "hourly": True},
    {"row": "86b25c1e-0427-48eb-8fbf-3a2477a4452a", "source_task": IT_TASK, "target_task": TARGET_TASK, "hourly": True},
    {"row": "5816b4bd-f9a5-4976-818e-794f95239fd1", "source_task": IT_TASK, "target_task": TARGET_TASK, "hourly": True},
    # Əsgərov Murad — Dizayn tapşırığından → Politologiya
    {
        "row": "66f3c6c3-c09d-4012-837f-f1d74b7ecb1c",
        "source_task": DIZAYN_TASK,
        "target_task": TARGET_TASK,
        "hourly": False,
    },
    {
        "row": "6cb19568-2c2d-480e-afa2-fefdc9b729d5",
        "source_task": DIZAYN_TASK,
        "target_task": TARGET_TASK,
        "hourly": False,
    },
    # Məmmədov Adıgözəl — Politologiya tapşırığından → Sosial iş («bu semestr bizdə dərsi yoxdur»; fənnlər sosial iş
    # fənləridir: Sosial layihələrin idarəedilməsi 134 Sİ rus, Keys menecment 135 Sİ ing). «BM-də mental
    # portretologiya» (133 Sİ ing) beynəlxalq münasibətlər fənnidir — Politologiyada qalır.
    {
        "row": "7ef9cf41-fa9d-4052-81ad-4ee9d5d1d255",
        "source_task": TARGET_TASK,
        "target_task": SOSIAL_TASK,
        "hourly": False,
    },
    {
        "row": "33f5ff81-9aa7-4dcc-bec5-ed64a9aac0af",
        "source_task": TARGET_TASK,
        "target_task": SOSIAL_TASK,
        "hourly": False,
    },
)

#: «Politologiya 533DBİ» (S30) → ML/MU/İ sətrinə qrup kimi qoşulur, özü silinir.
MERGE = {
    "row": "1f11d914-8634-4d7d-b021-44a875a10920",
    "source_task": "663dbec7-6043-4b12-9f69-9d1278a1b7cb",
    "into_row": "7f26354c-e1e6-4552-92a0-a663837afcb9",
    "group": "a44ea3af-023e-4a30-b3f7-5b46f0af6a40",  # 533DBİ
    "groups_text": "533ML, 533MU, 533İ, 533DBİ",
}


def _row(organization, row_id, task_ids):
    TeachingTaskRow = django_apps.get_model("workload", "TeachingTaskRow")
    return (
        TeachingTaskRow.objects.select_for_update()
        .select_related("task")
        .filter(organization=organization, pk=row_id, task_id__in=task_ids)
        .first()
    )


def run(*, organization, actor, counts: Counter) -> None:
    TeachingTask = django_apps.get_model("workload", "TeachingTask")
    TeacherAssignment = django_apps.get_model("workload", "TeacherAssignment")
    targets = {
        pk: TeachingTask.objects.filter(organization=organization, pk=pk).first()
        for pk in {spec["target_task"] for spec in MOVES} | {TARGET_TASK}
    }
    if any(task is None for task in targets.values()):
        raise CommandError("task_rows_move_target_missing")

    def audit(row, *, old, new):
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=row,
            old_values=old,
            new_values=new,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(row.pk),
        )

    # 1) 533DBİ sətri ML/MU/İ sətrinə qoşulur, özü silinir.
    merge_row = _row(organization, MERGE["row"], (MERGE["source_task"], TARGET_TASK))
    into = _row(organization, MERGE["into_row"], (MERGE["source_task"], TARGET_TASK))
    if into is None:
        counts["merge_target_missing"] += 1
    elif merge_row is None:
        counts["already_merged"] += 1
    else:
        if not into.groups.filter(pk=MERGE["group"]).exists():
            into.groups.add(MERGE["group"])
        into.groups_text = MERGE["groups_text"]
        into.save(update_fields=["groups_text", "updated_at"])
        removed = TeacherAssignment.objects.filter(organization=organization, row=merge_row)
        audit(
            into,
            old={
                "groups_text": "533ML, 533MU, 533İ",
                "merged_row": str(merge_row.pk),
                "merged_assignments": removed.count(),
            },
            new={"groups_text": MERGE["groups_text"]},
        )
        counts["merged_assignments_removed"] += removed.count()
        removed.delete()
        merge_row.delete()
        counts["merged_rows_removed"] += 1

    # 2) Sətirlər hədəf tapşırığa; saathesabı bayrağı fayla görə.
    for spec in MOVES:
        row = _row(organization, spec["row"], (spec["source_task"], spec["target_task"]))
        if row is None:
            counts["row_missing"] += 1
            continue
        assignments = TeacherAssignment.objects.filter(organization=organization, row=row)
        if str(row.task_id) == spec["target_task"]:
            counts["already_moved"] += 1
        else:
            audit(row, old={"task": str(row.task_id)}, new={"task": spec["target_task"], "hourly": spec["hourly"]})
            row.task = targets[spec["target_task"]]
            row.save(update_fields=["task", "updated_at"])
            counts["rows_moved"] += 1
        changed = assignments.exclude(is_hourly_paid=spec["hourly"]).update(is_hourly_paid=spec["hourly"])
        counts["assignments_hourly_set"] += changed
        counts["assignments_total"] += assignments.count()


class Command(BaseCommand):
    help = "Politologiya kafedrasının başqa tapşırığa düşmüş 6 yük sətrini öz tapşırığına köçürür (defolt dry-run)."

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
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("task_rows_move_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                run(organization=organization, actor=actor, counts=counts)
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
