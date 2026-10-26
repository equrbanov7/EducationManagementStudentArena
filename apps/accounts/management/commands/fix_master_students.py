"""``fix_master_students`` — bakalavrdan magistraturaya keçən tələbəyə magistr qeydi (sahib 2026-10-26).

Köhnə sistemdə magistr qrupunda oxuyan, yeni sistemdə isə köhnə BAKALAVR hesabı ilə tutuşdurulan tələbələr (ad +
ata adı eynidir — eyni şəxs): xanaları magistr jurnallarına yazılıb, amma akademik qeydi hələ bakalavr qrupunda
«oxuyur» idi — magistr qrupunda görünmürdü.

Plan faylı (lokal qurulur, YALNIZ id-lər)::

    {"format": "master-students/1",
     "records": [{"user": int, "bachelor_record": uuid, "group": uuid, "program": uuid, "curriculum": uuid,
                  "admission_year": int, "substituted": bool}],
     "transfers": [{"record": uuid, "group": uuid, "program": uuid, "curriculum": uuid}]}

* ``records`` — bakalavr qeydi ``graduated`` + qeyri-aktiv olur (BİRBAŞA, audit ilə): rəsmi «Məzun etmə» hərəkəti
  tələbənin açıq qeydiyyatlarını dondurur və hesabı arxivləyir — magistr dərsləri dayanardı. Sonra magistr qrupunda
  magistr proqramı + planı ilə YENİ qeyd açılır (qəbul axınının ``_write_academic_record`` sahələri ilə).
* ``transfers`` — magistr proqramındakı, amma səhv qrupdakı qeyd: rəsmi köçürmə xidməti
  (``transfer_student_group``) + lazım olsa proqram/plan.

Hər sətir yenidən yoxlanılır (köhnəlibsə atlanır, sayılır). DEFOLT DRY-RUN. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import datetime
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


def _model(name):
    return django_apps.get_model("registrar", name)


PREFIX = "master_students:"
FORMAT = "master-students/1"
#: Arxivlənmiş hesabın girişini açan sübutun «əmri» — sistem düzəlişi (delta məzun etmə əmri kimi sabit).
ORDER_NUMBER = "MAG-SINX-2026"
ORDER_DATE = datetime.date(2026, 10, 26)
REASON = "Bakalavrdan magistraturaya keçid — köhnə sistemin magistr qrupu (jurnal datası), sahibin 2026-10-26 tapşırığı"


class Command(BaseCommand):
    help = "Magistraturaya keçən tələbələrə magistr qeydi açır, səhv qrupdakı magistr qeydini köçürür (plan faylı)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", required=True, help="master-students/1 JSON faylı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        try:
            with open(options["file"], encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            raise CommandError("master_students_file_unreadable") from None
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise CommandError("master_students_format_unknown")
        Organization = django_apps.get_model("organizations", "Organization")
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        counts = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("master_students_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            with transaction.atomic():
                for row in data.get("records") or []:
                    with transaction.atomic():
                        self._new_record(organization, actor, row, counts)
                period = organization.academic_periods.filter(is_current=True, is_active=True).first()
                for row in data.get("transfers") or []:
                    with transaction.atomic():
                        self._transfer(organization, actor, period, row, counts)
                if not options["apply"]:
                    transaction.set_rollback(True)
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))

    @staticmethod
    def _targets(organization, row):
        Program, Curriculum = _model("Program"), _model("Curriculum")
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        group = OrgUnit.objects.filter(organization=organization, pk=row.get("group"), unit_type="group").first()
        program = Program.objects.filter(
            organization=organization, pk=row.get("program"), degree_level="master"
        ).first()
        curriculum = Curriculum.objects.filter(organization=organization, pk=row.get("curriculum")).first()
        if group is None or program is None or curriculum is None or curriculum.program_id != program.pk:
            return None
        return group, program, curriculum

    def _new_record(self, organization, actor, row, counts):
        StudentAcademicRecord = _model("StudentAcademicRecord")
        counts["records_in_file"] += 1
        targets = self._targets(organization, row)
        if targets is None:
            counts["target_invalid"] += 1
            return
        group, program, curriculum = targets
        bachelor = (
            StudentAcademicRecord.objects.select_for_update(of=("self",))
            .select_related("program")
            .filter(organization=organization, pk=row.get("bachelor_record"), student_id=row.get("user"))
            .first()
        )
        if bachelor is None or not bachelor.is_active or bachelor.program.degree_level == "master":
            counts["bachelor_record_stale"] += 1
            return
        if StudentAcademicRecord.objects.filter(
            organization=organization, student_id=bachelor.student_id, program=program
        ).exists():
            counts["master_record_exists"] += 1
            return
        old = {"status": bachelor.status, "is_active": bachelor.is_active}
        bachelor.status = "graduated"
        bachelor.is_active = False
        bachelor.save(update_fields=["status", "is_active", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=bachelor,
            reason=f"registrar: bachelor record closed (master continuation, not a movement) — {REASON}",
            old_values=old,
            new_values={"status": "graduated", "is_active": False},
        )
        record = StudentAcademicRecord.objects.create(
            organization=organization,
            student_id=bachelor.student_id,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=int(row.get("admission_year") or curriculum.admission_year),
            status="enrolled",
            is_active=True,
            education_form=bachelor.education_form or "full_time",
            funding_type=getattr(bachelor, "funding_type", "") or "paid",
        )
        log_action(
            action=AuditAction.CREATE,
            user=actor,
            organization=organization,
            obj=record,
            reason=f"registrar: master record opened — {REASON}",
            new_values={"group": str(group.pk), "program": str(program.pk), "curriculum": str(curriculum.pk)},
        )
        counts["records_created"] += 1
        counts["records_curriculum_substituted"] += int(bool(row.get("substituted")))
        counts[self._reopen_access(organization, actor, record)] += 1
        counts[self._student_role(organization, actor, record)] += 1

    @staticmethod
    def _student_role(organization, actor, record) -> str:
        """Bakalavrı bitirəndə üzvlük «alumni» roluna keçirilib — magistr tələbəsi yenə «student»dir (jurnala yazılış
        və kabinet bu rolu tələb edir)."""
        Membership = django_apps.get_model("organizations", "Membership")
        Role = django_apps.get_model("organizations", "Role")
        if Membership.objects.filter(
            organization=organization, user_id=record.student_id, role__name="student", is_active=True
        ).exists():
            return "role_already_student"
        membership = Membership.objects.filter(
            organization=organization, user_id=record.student_id, role__name="alumni"
        ).first()
        role = Role.objects.filter(organization=organization, name="student").first()
        if membership is None or role is None:
            return "role_not_switched"
        old = {"role": "alumni", "is_active": membership.is_active}
        membership.role = role
        membership.is_active = True
        membership.save(update_fields=["role", "is_active", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=membership,
            reason=f"accounts: alumni → student (master continuation) — {REASON}",
            old_values=old,
            new_values={"role": "student", "is_active": True},
        )
        return "role_switched_to_student"

    @staticmethod
    def _reopen_access(organization, actor, record) -> str:
        """Jurnalsız qaldığı üçün arxivlənmiş hesab — aktiv magistr qeydi açıldı, giriş də açılır (rəsmi bərpa
        səthi, sübutu sabit sistem əmri). Savepoint: alınmasa qeyd qalır, sayılır."""
        from apps.accounts.services.identity_reinstate import order_evidence_digest, reinstate_student_access

        profile_model = django_apps.get_model("accounts", "UserProfile")
        profile = profile_model.objects.filter(user_id=record.student_id).first()
        if profile is None or profile.access_state != profile_model.AccessState.ARCHIVED:
            return "access_already_active"
        digest = order_evidence_digest(
            order_number=ORDER_NUMBER, order_date=ORDER_DATE, record_id=record.pk, actor_id=actor.pk
        )
        try:
            with transaction.atomic():
                reinstate_student_access(
                    user=record.student, organization=organization, actor=actor, evidence_digest=digest
                )
        except Exception:  # noqa: BLE001 — qeyd qalır; səbəb audit/log-dadır
            return "access_reopen_failed"
        return "access_reopened"

    def _transfer(self, organization, actor, period, row, counts):
        from apps.registrar.public import transfer as group_transfer

        StudentAcademicRecord = _model("StudentAcademicRecord")

        counts["transfers_in_file"] += 1
        targets = self._targets(organization, row)
        if targets is None:
            counts["target_invalid"] += 1
            return
        group, program, curriculum = targets
        record = (
            StudentAcademicRecord.objects.select_related("organization", "student", "group", "program")
            .filter(organization=organization, pk=row.get("record"), is_active=True)
            .first()
        )
        if record is None or record.program.degree_level != "master":
            counts["transfer_record_stale"] += 1
            return
        if record.program_id != program.pk:
            clash = (
                StudentAcademicRecord.objects.filter(
                    organization=organization, student_id=record.student_id, program=program
                )
                .exclude(pk=record.pk)
                .exists()
            )
            if clash:
                counts["transfer_program_exists"] += 1
                return
            old = {"program": str(record.program_id), "curriculum": str(record.curriculum_id)}
            record.program = program
            record.curriculum = curriculum
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
            counts["transfer_program_switched"] += 1
        if record.group_id != group.pk:
            group_transfer.transfer_student_group(
                record=record, new_group=group, period=period, by_user=actor, reason=REASON
            )
            counts["transfers_moved"] += 1
        else:
            counts["transfer_already_in_group"] += 1
