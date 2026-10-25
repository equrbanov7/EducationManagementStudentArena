"""``fix_group_education_form`` — qrupların və tələbə qeydlərinin təhsil formasını ad qaydasına uyğunlaşdırır.

Sahib 2026-10-25: «qrup nömrəsində 4 rəqəm varsa («2232 K») — QİYABİ, 3 rəqəm varsa («234 KE») — ƏYANİ;
harada varsa o səhv — düzəlt». Qayda: ``apps.organizations.group_education_form``.

* Qrup (``OrgUnit.settings.education_form``): qayda birmənalıdırsa (bakalavr, 3/4 rəqəmli kod, magistr və
  kollec deyil) dəyər qaydanın dəyərinə gətirilir (boşdursa doldurulur). Qeyri-standart adlar
  (magistr «409/6MBA», kollec «1226 A», «1025», «3/336 F» …) DƏYİŞMİR — yalnız sayılır.
* Tələbə qeydi (``StudentAcademicRecord.education_form``): QİYABİ (4 rəqəmli) qrupdakı «əyani» qeydlər qrupun
  formasına gətirilir (aktiv/qeyri-aktiv fərqi yoxdur — qeydin qrupu onun formasını müəyyən edir).
  ƏYANİ (3 rəqəmli) qrupdakı «qiyabi» qeydlər DEFOLT DƏYİŞMİR — ``records_part_in_full_group`` kimi sayılır:
  prod-da bunlar ATİS-in qiyabi kimi verdiyi, lakin əyani qrupa («536 Bİ») yerləşdirilmiş tələbələrdir (qiyabi
  cüt qrup «2536 Bİ» boşdur) — yerləşdirmə sualıdır, formanı əzmək izi silərdi. ``--align-part-to-full`` ilə
  onlar da qrupun formasına gətirilir.
* Dərs yükü sətri (``workload.TeachingTaskRow.education_form`` — ``eyani`` / ``qiyabi``): sətrin BÜTÜN qrupları
  qaydaya görə eyni formadadırsa sətir ona gətirilir (``intensiv`` / ``distant`` toxunulmur; qrupları fərqli
  formada olan və ya qaydadan kənar qrupu olan sətir dəyişmir). Saat hesabı formadan asılı deyil — yalnız
  etiket/süzgəc. Bölüşdürülmüş (kilidli) tapşırıqların sətirləri də daxildir, ona görə AYRI bayraqla:
  ``--task-rows`` (verilməsə yalnız sayılır).
* DEFOLT DRY-RUN; ``--apply`` ilə bir tranzaksiyada; hər dəyişən qrup üçün AuditLog (köhnə/yeni forma +
  uyğunlaşdırılan tələbə sayı). İdempotent — təkrar qaçış 0 yazır.
* Stdout-a YALNIZ saylar (``group_education_form: açar=say …``). ``--list`` (yalnız lokal) qrup adlarını
  da çap edir — prod-data-ops onu ÖTÜRMÜR.

İstifadə::

    manage.py fix_group_education_form --org qku [--apply] [--task-rows] [--align-part-to-full] [--list]
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.group_education_form import FULL_TIME, PART_TIME, group_rule_form
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "group_education_form:"
AUDIT_REASON = "groups: education form from group code (owner rule 2026-10-25: 3 digits = full-time, 4 = part-time)"


def _line(pairs) -> str:
    return PREFIX + " " + " ".join(f"{key}={value}" for key, value in pairs)


class Command(BaseCommand):
    help = "Qrup/tələbə təhsil formasını qrup kodu qaydasına uyğunlaşdırır (3 rəqəm əyani, 4 rəqəm qiyabi)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument(
            "--align-part-to-full",
            action="store_true",
            help="Əyani qrupdakı «qiyabi» tələbə qeydlərini də əyani et (defolt: yalnız sayılır)",
        )
        parser.add_argument(
            "--task-rows", action="store_true", help="Dərs yükü sətirlərinin formasını da yaz (defolt: yalnız sayılır)"
        )
        parser.add_argument("--list", action="store_true", help="Qrup adlarını da çap et (yalnız lokal hesabat)")

    def handle(self, *args, **options):
        Organization = django_apps.get_model("organizations", "Organization")
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("group_education_form_organization_unknown")
            if options["apply"]:
                with transaction.atomic():
                    counts, rows = fix_group_forms(
                        organization, apply=True, align_part_to_full=options["align_part_to_full"]
                    )
                    counts.update(fix_task_row_forms(organization, apply=options["task_rows"]))
            else:
                counts, rows = fix_group_forms(
                    organization, apply=False, align_part_to_full=options["align_part_to_full"]
                )
                counts.update(fix_task_row_forms(organization, apply=False))
        self.stdout.write(_line([("mode", "apply" if options["apply"] else "dry_run")]))
        self.stdout.write(_line(counts.items()))
        if options["list"]:
            for row in rows:
                self.stdout.write(" | ".join(str(value) for value in row))


def fix_group_forms(organization, *, apply: bool, align_part_to_full: bool = False):
    """``(counts, rows)`` qaytarır; ``apply=True`` olduqda yazır (çağıran tranzaksiyanı açır).

    ``rows`` — ``(status, ad, köhnə forma, qayda forması/səbəb, uyğunlaşdırılacaq tələbə)`` (yalnız ``--list``).
    """

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    names_by_id = _unit_names(organization)
    groups = list(OrgUnit.objects.filter(organization=organization, unit_type="group").order_by("name"))
    counts = Counter(
        {
            "groups": len(groups),
            "groups_ok": 0,
            "groups_filled": 0,
            "groups_full_to_part": 0,
            "groups_part_to_full": 0,
            "groups_other_corrected": 0,
            "groups_skipped": 0,
            "records_checked": 0,
            "records_to_part": 0,
            "records_to_full": 0,
            "records_part_in_full_group": 0,
            "written_groups": 0,
            "written_records": 0,
        }
    )
    rows = []
    for unit in groups:
        settings = unit.settings if isinstance(unit.settings, dict) else {}
        current = str(settings.get("education_form") or "").strip()
        form, reason = group_rule_form(unit, names=_ancestors(unit, names_by_id))
        if form is None:
            counts["groups_skipped"] += 1
            counts[f"skipped_{reason}"] += 1
            rows.append(("skip:" + reason, unit.name, current or "—", "—", 0))
            continue
        records = StudentAcademicRecord.objects.filter(organization=organization, group=unit)
        counts["records_checked"] += records.count()
        mismatched = records.exclude(education_form=form)
        if form == FULL_TIME and not align_part_to_full:
            held = mismatched.filter(education_form=PART_TIME).count()
            counts["records_part_in_full_group"] += held
            mismatched = mismatched.exclude(education_form=PART_TIME)
        mismatch_count = mismatched.count()
        counts["records_to_part" if form == PART_TIME else "records_to_full"] += mismatch_count
        status = _group_status(current, form)
        counts[f"groups_{status}"] += 1
        if status != "ok" or mismatch_count:
            rows.append((status, unit.name, current or "—", form, mismatch_count))
        if not apply or (status == "ok" and not mismatch_count):
            continue
        if status != "ok":
            locked = OrgUnit.objects.select_for_update().get(pk=unit.pk)
            blob = dict(locked.settings) if isinstance(locked.settings, dict) else {}
            blob["education_form"] = form
            locked.settings = blob
            locked.save(update_fields=["settings", "updated_at"])
            counts["written_groups"] += 1
        written = mismatched.update(education_form=form) if mismatch_count else 0
        counts["written_records"] += written
        log_action(
            action=AuditAction.UPDATE,
            organization=organization,
            obj=unit,
            reason=AUDIT_REASON,
            old_values={"education_form": current},
            new_values={"education_form": form, "records_aligned": written},
        )
    return counts, rows


_ROW_FORMS = {FULL_TIME: "eyani", PART_TIME: "qiyabi"}


def fix_task_row_forms(organization, *, apply: bool) -> Counter:
    """Dərs yükü sətirləri: bütün qrupları eyni qayda formasında olan ``eyani``/``qiyabi`` sətir → həmin forma."""

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    TeachingTaskRow = django_apps.get_model("workload", "TeachingTaskRow")
    names_by_id = _unit_names(organization)
    counts = Counter({"task_rows": 0, "task_rows_to_qiyabi": 0, "task_rows_to_eyani": 0, "task_rows_written": 0})
    group_forms: dict = {}
    for unit in OrgUnit.objects.filter(organization=organization, unit_type="group"):
        group_forms[unit.pk] = group_rule_form(unit, names=_ancestors(unit, names_by_id))[0]
    links = TeachingTaskRow.groups.through.objects.filter(teachingtaskrow__organization=organization)
    row_groups: dict = {}
    for row_id, group_id in links.values_list("teachingtaskrow_id", "orgunit_id"):
        row_groups.setdefault(row_id, []).append(group_id)
    targets: dict = {}
    rows = TeachingTaskRow.objects.filter(organization=organization, education_form__in=_ROW_FORMS.values())
    for row_id, task_id, current in rows.values_list("pk", "task_id", "education_form"):
        counts["task_rows"] += 1
        forms = {group_forms.get(group_id) for group_id in row_groups.get(row_id, [])}
        if not forms:
            counts["task_rows_no_group"] += 1
            continue
        if None in forms or len(forms) != 1:
            counts["task_rows_undetermined"] += 1
            continue
        target = _ROW_FORMS[forms.pop()]
        if target == current:
            continue
        counts["task_rows_to_qiyabi" if target == "qiyabi" else "task_rows_to_eyani"] += 1
        targets.setdefault((task_id, target), []).append(row_id)
    if not apply:
        return counts
    for (task_id, target), row_ids in targets.items():
        written = (
            TeachingTaskRow.objects.filter(pk__in=row_ids).exclude(education_form=target).update(education_form=target)
        )
        counts["task_rows_written"] += written
        log_action(
            action=AuditAction.UPDATE,
            organization=organization,
            resource_type="workload.teachingtask",
            resource_id=str(task_id),
            reason=AUDIT_REASON,
            new_values={"education_form": target, "rows": written},
        )
    return counts


def _unit_names(organization) -> dict:
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return {str(pk): name for pk, name in OrgUnit.objects.filter(organization=organization).values_list("pk", "name")}


def _ancestors(unit, names_by_id: dict) -> list:
    path_ids = [segment for segment in (unit.path or "").strip("/").split("/") if segment and segment != str(unit.pk)]
    return [names_by_id.get(pk, "") for pk in path_ids]


def _group_status(current: str, form: str) -> str:
    if current == form:
        return "ok"
    if not current:
        return "filled"
    if current == FULL_TIME and form == PART_TIME:
        return "full_to_part"
    if current == PART_TIME and form == FULL_TIME:
        return "part_to_full"
    return "other_corrected"
