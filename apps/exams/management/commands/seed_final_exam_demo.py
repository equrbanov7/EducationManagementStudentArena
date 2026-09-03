"""Final imtahan mərkəzi üçün uçdan-uca demo data.

Yaradır: universitet + imtahan mərkəzi istifadəçisi + nəzarətçi + suallı final
imtahanı + tələbə qrupları (əsas + alt-sektor) + fərdi tələbə + zal + oturum.
Tələbələri qrup VƏ fərdi olaraq oturuma təyin edir və hər tələbə üçün fərqli
PIN yaradır. Oturumu "giriş açıq" (entry_open) vəziyyətinə gətirir ki, tələbə
dərhal PIN ilə daxil ola bilsin; STARTı nəzarətçi əl ilə versin (demonstrasiya).

Sonda demo hesablarını və təhlükəsiz test addımlarını çap edir.

İşə salma:
    python manage.py seed_final_exam_demo
    python manage.py seed_final_exam_demo --password DemoPass123!  (yenidən işə salına bilər)
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.exams.models import (
    Exam,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomComputer,
    ExamRoomSession,
    FinalExamTicket,
    StudentGroup,
)
from apps.exams.services.final_center import assign_students, open_entry
from core.constants import OrganizationType
from core.management.command_safety import ProductionCommandSafetyMixin
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

from ._seed_helpers import UsersSeedMixin


class Command(ProductionCommandSafetyMixin, UsersSeedMixin, BaseCommand):
    safety_command_name = "seed_final_exam_demo"
    help = "Final imtahan mərkəzi üçün uçdan-uca demo (imtahan + suallar + qrup/fərdi təyinat + PIN + oturum)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="DemoPass123!", help="Demo user-lər üçün şifrə.")

    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        password = options["password"]

        # ── Təşkilat + imtahan mərkəzi + nəzarətçi ──────────────────────────
        owner = self._ensure_user("final_demo_owner", "final_demo_owner@example.com", password)
        org = self._ensure_organization("Final Demo Universiteti", OrganizationType.UNIVERSITY, owner)
        self._assign_profile(owner, org, ProfileRole.ORG_OWNER)
        owner_role = self._resolve_role(org, ProfileRole.ORG_OWNER)
        self._ensure_membership(owner, org, owner_role, owner)

        center = self._ensure_user("final_demo_center", "final_demo_center@example.com", password)
        self._assign_profile(center, org, ProfileRole.MEMBER)
        center_role = self._resolve_role(org, ProfileRole.MEMBER)
        # İmtahan mərkəzi rolu (exam_center) — universitet default rollarında var.
        from apps.organizations.models import Role

        exam_center_role = Role.objects.filter(organization=org, name="exam_center").first() or center_role
        self._ensure_membership(center, org, exam_center_role, owner)

        invigilator = self._ensure_user("final_demo_invigilator", "final_demo_invig@example.com", password)
        self._assign_profile(invigilator, org, ProfileRole.TEACHER)
        teacher_role = self._resolve_role(org, ProfileRole.TEACHER)
        self._ensure_membership(invigilator, org, teacher_role, owner)

        # ── Final imtahanı + suallar (müəllif: imtahan mərkəzi) ─────────────
        exam = self._ensure_final_exam(center, org)
        self._seed_questions(exam)

        # ── Tələbələr: əsas qrup (AZ sektor) + alt-sektor (EN) + fərdi ──────
        student_role = self._resolve_role(org, ProfileRole.STUDENT)
        az_students = self._make_students(org, owner, student_role, "az", 3, password)
        en_students = self._make_students(org, owner, student_role, "en", 2, password)
        individual = self._make_students(org, owner, student_role, "solo", 1, password)[0]

        main_group = self._ensure_group(org, invigilator, "FINAL-DEMO-2024 (AZ sektor)", az_students)
        sub_group = self._ensure_group(org, invigilator, "FINAL-DEMO-2024-EN (alt-sektor)", en_students)

        # İmtahanı qruplara + fərdi tələbəyə görünən et (siyahıda da çıxsın).
        exam.allowed_groups.set([main_group, sub_group])
        exam.allowed_users.set([individual])

        # ── Zal + oturum (imtahandan asılı deyil) + qeydli kompüter (IP→zal) ──
        room = self._ensure_room(org, center)
        self._ensure_local_computer(org, room, center)
        ExamRoomSession.objects.filter(room=room, created_by=center).exclude(state__in=("ended",)).delete()
        now = timezone.now()
        session = ExamRoomSession.objects.create(
            organization=org,
            room=room,
            invigilator=invigilator,
            scheduled_start=now - timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=3),
            created_by=center,
        )

        # ── Təyinat: tələbələr İMTAHANA təyin olunur (zaldan asılı deyil) ────
        all_students = list(az_students) + list(en_students) + [individual]
        created, skipped = assign_students(exam, all_students, center)

        # ── Girişi aç (tələbələr dərhal PIN ilə daxil ola bilsin) ───────────
        open_entry(session, center)

        self._report(org, center, invigilator, exam, session, main_group, sub_group, individual, all_students)

    # ------------------------------------------------------------------ helpers

    def _ensure_final_exam(self, author, org):
        exam, _ = Exam.objects.get_or_create(
            author=author,
            title="Final İmtahanı — İnformatika (Demo)",
            organization=org,
            defaults={
                "description": (
                    "Bu, final imtahan mərkəzi axınını sınamaq üçün nümunə imtahandır. "
                    "İmtahan zamanı səhifəni tərk etməyin."
                ),
                "exam_type": "test",
                "exam_type_extended": "final",
                "is_active": True,
                "is_public": False,
                "total_duration_minutes": 60,
                "random_question_count": 5,
                "default_question_points": 1,
            },
        )
        updates = {}
        if not exam.is_active:
            updates["is_active"] = True
        if exam.exam_type_extended != "final":
            updates["exam_type_extended"] = "final"
        if exam.total_duration_minutes != 60:
            updates["total_duration_minutes"] = 60
        if exam.random_question_count != 5:
            updates["random_question_count"] = 5
        if updates:
            for field, value in updates.items():
                setattr(exam, field, value)
            exam.save(update_fields=list(updates.keys()))
        return exam

    def _seed_questions(self, exam):
        """
        İmtahana 3 dil variantı (AZ/EN/RU) və hər dildə eyni sual dəstini
        yaradır — beləliklə giriş modalında dil seçimi görünür və məcburidir.
        """
        from apps.exams.services.language_variants import create_variant

        from ._final_exam_demo_data import DEMO_LANGUAGES, MULTILINGUAL_QUESTIONS

        # Köhnə tək-dilli seed işləmişdisə, variantsız (orphan) sualları təmizlə
        # ki, demo təkrar işə salınanda dillər arası sual sayı bərabər qalsın.
        exam.questions.filter(language_variant__isnull=True).delete()

        variants = {
            code: create_variant(exam, code, display_name=name, is_active=True) for code, name in DEMO_LANGUAGES
        }

        for order, answer_mode, per_language in MULTILINGUAL_QUESTIONS:
            for code, (text, options) in per_language.items():
                variant = variants[code]
                question, _ = ExamQuestion.objects.get_or_create(
                    exam=exam,
                    language=code,
                    text=text,
                    defaults={
                        "order": order,
                        "answer_mode": answer_mode,
                        "points": 1,
                        "difficulty": "medium",
                        "is_active": True,
                        "language_variant": variant,
                    },
                )
                if question.language_variant_id != variant.id or not question.is_active:
                    question.language_variant = variant
                    question.is_active = True
                    question.save(update_fields=["language_variant", "is_active"])
                question.options.all().delete()
                for label, opt_text, is_correct in options:
                    ExamQuestionOption.objects.create(
                        question=question, label=label, text=opt_text, is_correct=is_correct
                    )

    def _make_students(self, org, owner, student_role, prefix, count, password):
        students = []
        for idx in range(1, count + 1):
            username = f"final_{prefix}_student_{idx}"
            student = self._ensure_user(username, f"{username}@example.com", password)
            self._assign_profile(student, org, ProfileRole.STUDENT)
            self._ensure_membership(student, org, student_role, owner)
            students.append(student)
        return students

    def _ensure_group(self, org, teacher, name, students):
        group, _ = StudentGroup.objects.get_or_create(organization=org, teacher=teacher, name=name)
        group.students.set(students)
        group.teachers.set([teacher])
        return group

    def _ensure_room(self, org, center):
        room, _ = ExamRoom.objects.get_or_create(
            organization=org,
            code="DEMO-101",
            defaults={
                "name": "Demo İmtahan Zalı 101",
                "building": "Əsas korpus",
                "floor": "1",
                "capacity": 50,
                "computer_count": 50,
                "created_by": center,
                "is_active": True,
            },
        )
        return room

    def _ensure_local_computer(self, org, room, center):
        """Zala 127.0.0.1 IP-li kompüter qeyd et — lokal test/demo-da tələbə öz
        maşınından girəndə IP→zal həlli işləsin (oturum sisteminin ləğvi)."""
        ExamRoomComputer.objects.get_or_create(
            room=room,
            label="PC-DEMO-01",
            defaults={
                "organization": org,
                "seat_number": 1,
                "mac_address": "AA:BB:CC:DD:EE:01",
                "ip_address": "127.0.0.1",
                "is_active": True,
                "created_by": center,
            },
        )

    def _report(self, org, center, invigilator, exam, session, main_group, sub_group, individual, students):
        out = self.stdout
        ok = self.style.SUCCESS
        warn = self.style.WARNING

        out.write(ok("\n══════════════════════════════════════════════════════════════"))
        out.write(ok("  FINAL İMTAHAN MƏRKƏZİ — DEMO DATA HAZIRDIR"))
        out.write(ok("══════════════════════════════════════════════════════════════\n"))

        out.write(f"Təşkilat        : {org.name}")
        out.write(f"İmtahan         : {exam.title}")
        out.write(f"Zal / Oturum    : {session.room.name} · vəziyyət = {session.state} (giriş açıq)")
        out.write(
            f"Vaxt            : {timezone.localtime(session.scheduled_start):%d.%m.%Y %H:%M}"
            f" – {timezone.localtime(session.scheduled_end):%H:%M}\n"
        )

        out.write(ok("── İMTAHAN MƏRKƏZİ (yaradan) ──"))
        out.write(f"  İstifadəçi: {center.username}")
        out.write(f"  Panel     : /exams/center/sessions/{session.pk}/\n")

        out.write(ok("── NƏZARƏTÇI (start + monitorinq) ──"))
        out.write(f"  İstifadəçi: {invigilator.username}")
        out.write(f"  Monitor   : /exams/center/sessions/{session.pk}/monitor/")
        out.write("  → Monitor səhifəsində 'İmtahanı başlat' düyməsi ilə hamıya sinxron start verilir.\n")

        out.write(ok("── TƏLƏBƏLƏR (credential dəyərləri loglanmır) ──"))
        by_id = {t.student_id: t for t in FinalExamTicket.objects.filter(session=session).select_related("student")}
        for student in students:
            ticket = by_id.get(student.id)
            if ticket is None:
                out.write(warn(f"  {student.username:26}  — bilet yaradılmadı (ötürüldü)"))
                continue
            sector = self._sector_label(student, main_group, sub_group, individual)
            out.write(f"  {student.username:26}  [{sector}]")

        out.write(ok("\n── TEST ADDIMLARI (tələbə tərəfi) ──"))
        first_student = students[0]
        out.write("  1) İmtahan giriş səhifəsini aç:   /exams/final/")
        out.write("     (normal login LAZIM DEYİL — birbaşa istifadəçi adı + PIN yazılır)")
        out.write(f"  2) İstifadəçi adı: {first_student.username}; PIN-i mərkəz panelindən təhlükəsiz götür")
        out.write("  3) Açılan MODALDA imtahan məlumatı + qaydalar → təsdiqlə → 'Davam et'")
        out.write("  4) Gözləmə otağı → nəzarətçi 'İmtahanı başlat' basanda imtahan avtomatik açılır.\n")
        out.write(ok("Qeyd: PIN-lər hər tələbədə fərqlidir və yalnız bir imtahana keçərlidir.\n"))

    def _sector_label(self, student, main_group, sub_group, individual):
        if student.id == individual.id:
            return "fərdi təyinat"
        if main_group.students.filter(id=student.id).exists():
            return "əsas qrup (AZ)"
        if sub_group.students.filter(id=student.id).exists():
            return "alt-sektor (EN)"
        return "qrup"
