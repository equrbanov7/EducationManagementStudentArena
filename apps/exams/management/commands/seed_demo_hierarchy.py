"""Tam iyerarxiyalı demo data — universitet strukturu + bütün rol tipləri.

Yaradır:
* superadmin;
* universitet + rektor (org sahibi);
* fakültə → kafedra iyerarxiyası (OrgUnit);
* imtahan mərkəzi RƏHBƏRİ + 2 İŞÇİ (yeni rollar);
* kafedralara bağlı müəllimlər (nəzarətçi namizədləri — kafedra adı ilə);
* qruplara + kafedralara bağlı tələbələr;
* nümunə final imtahanı + zal + oturum + biletlər (fərdi PIN-lər) — PIN axtarışı
  və monitor üçün canlı data.

İşə salma (yenidən işə salına bilər — idempotent):
    python manage.py seed_demo_hierarchy
    python manage.py seed_demo_hierarchy --password DemoPass123!
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
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
from apps.exams.services.final_center import assign_students, decrypt_ticket_pin, open_entry, set_ticket_pin
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

from ._seed_helpers import UsersSeedMixin

User = get_user_model()

_HEAD_PERMS = [
    "org.view",
    "unit.view",
    "member.view",
    "course.view",
    "exam.*",
    "grade.view",
    "grade.publish",
    "appeal.respond",
    "appeal.decide",
    "qa.*",
    "analytics.view_all",
    "audit.view",
]
_STAFF_PERMS = [
    "org.view",
    "unit.view",
    "member.view",
    "course.view",
    "exam.*",
    "grade.view",
    "qa.*",
    "analytics.view_all",
    "audit.view",
]


class Command(UsersSeedMixin, BaseCommand):
    help = "Tam iyerarxiyalı demo (superadmin + struktur + imtahan mərkəzi rəhbər/işçi + müəllim/tələbə + final)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="DemoPass123!", help="Demo user-lər üçün şifrə.")
        parser.add_argument("--org-name", default="Demo Universiteti", help="Təşkilatın adı.")
        parser.add_argument("--prefix", default="demo", help="İstifadəçi adı prefiksi (məs. demo, qk).")
        parser.add_argument(
            "--computer-mac", default="AA:BB:CC:DD:EE:02", help="Zal kompüterinin baza MAC ünvanı (identifikasiya)."
        )
        parser.add_argument(
            "--computer-ips",
            default="127.0.0.1",
            help="Zala qeyd olunacaq IP-lər (vergüllə). Hər IP üçün ayrı kompüter yaradılır — giriş IP → zal.",
        )

    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        pw = options["password"]
        self.prefix = (options["org_name"] and options["prefix"]) or "demo"
        self.org_name = options["org_name"]
        self.computer_mac = options["computer_mac"]
        self.computer_ips = [ip.strip() for ip in (options["computer_ips"] or "").split(",") if ip.strip()]

        # ── Superadmin (bütün demo-lar üçün ortaq) ─────────────────────────
        superadmin = self._ensure_superuser("demo_superadmin", "demo_superadmin@example.com", pw)

        # ── Universitet + rektor (owner) ───────────────────────────────────
        rector = self._ensure_user(f"{self.prefix}_rector", f"{self.prefix}_rector@example.com", pw)
        org = self._ensure_organization(self.org_name, OrganizationType.UNIVERSITY, rector)
        self._assign_profile(rector, org, ProfileRole.ORG_OWNER)
        self._ensure_membership(rector, org, self._resolve_role(org, ProfileRole.ORG_OWNER), rector)

        # ── İmtahan mərkəzi rolları (org default-larında yoxdursa yarat) ────
        head_role = self._ensure_role(org, "exam_center_head", "Exam Center Head", 85, _HEAD_PERMS)
        staff_role = self._ensure_role(org, "exam_center_staff", "Exam Center Staff", 60, _STAFF_PERMS)
        teacher_role = self._resolve_role(org, ProfileRole.TEACHER)
        student_role = self._resolve_role(org, ProfileRole.STUDENT)

        # ── Fakültə → kafedra iyerarxiyası ─────────────────────────────────
        fac_it = self._ensure_unit(org, "İnformasiya Texnologiyaları Fakültəsi", OrgUnitType.FACULTY, None, "ITF")
        kaf_cs = self._ensure_unit(org, "Kompüter Elmləri kafedrası", OrgUnitType.DEPARTMENT, fac_it, "CS")
        kaf_se = self._ensure_unit(org, "Proqram Mühəndisliyi kafedrası", OrgUnitType.DEPARTMENT, fac_it, "SE")
        fac_econ = self._ensure_unit(org, "İqtisadiyyat Fakültəsi", OrgUnitType.FACULTY, None, "ECON")
        kaf_fin = self._ensure_unit(org, "Maliyyə kafedrası", OrgUnitType.DEPARTMENT, fac_econ, "FIN")

        # ── İmtahan mərkəzi: rəhbər + 2 işçi ───────────────────────────────
        ec_head = self._ensure_user(f"{self.prefix}_ec_head", f"{self.prefix}_ec_head@example.com", pw)
        self._assign_profile(ec_head, org, ProfileRole.EXAM_CENTER_HEAD)
        self._ensure_membership(ec_head, org, head_role, rector)

        ec_staff = []
        for i in (1, 2):
            s = self._ensure_user(f"{self.prefix}_ec_staff{i}", f"{self.prefix}_ec_staff{i}@example.com", pw)
            self._assign_profile(s, org, ProfileRole.EXAM_CENTER_STAFF)
            self._ensure_membership(s, org, staff_role, rector)
            ec_staff.append(s)

        # ── Müəllimlər (nəzarətçi namizədləri) — kafedraya bağlı ───────────
        teacher_specs = [
            (f"{self.prefix}_teacher_cs1", "Aygün", "Məmmədova", kaf_cs),
            (f"{self.prefix}_teacher_cs2", "Rəşad", "Əliyev", kaf_cs),
            (f"{self.prefix}_teacher_se1", "Nigar", "Hüseynova", kaf_se),
            (f"{self.prefix}_teacher_se2", "Elçin", "Quliyev", kaf_se),
            (f"{self.prefix}_teacher_fin1", "Kamran", "İsmayılov", kaf_fin),
        ]
        teachers = []
        for username, first, last, kafedra in teacher_specs:
            t = self._ensure_user(username, f"{username}@example.com", pw)
            self._set_name(t, first, last)
            self._assign_profile(t, org, ProfileRole.TEACHER)
            self._ensure_membership_scoped(t, org, teacher_role, rector, kafedra)
            teachers.append(t)

        # ── Tələbələr + qruplar (kafedraya bağlı) ──────────────────────────
        cs_students = self._make_students(org, rector, student_role, "cs", 4, pw, kaf_cs)
        se_students = self._make_students(org, rector, student_role, "se", 3, pw, kaf_se)
        group_cs = self._ensure_group(org, teachers[0], "CS-2024 (Kompüter Elmləri)", cs_students, kaf_cs)
        group_se = self._ensure_group(org, teachers[2], "SE-2024 (Proqram Mühəndisliyi)", se_students, kaf_se)
        all_students = list(cs_students) + list(se_students)

        # ── Fənlər (registrar.Subject) — qruplara təyin (sual göndərişi üçün) ──
        # Müəllim sual göndərəndə fənn ÖZ qruplarının fənlərindən gəlir.
        subj_alg = self._ensure_subject(org, "CS101", "Alqoritmlər")
        subj_db = self._ensure_subject(org, "CS201", "Verilənlər bazası")
        subj_oop = self._ensure_subject(org, "SE101", "Obyekt-yönümlü proqramlaşdırma")
        group_cs.subjects.set([subj_alg, subj_db])
        group_se.subjects.set([subj_oop, subj_alg])  # Alqoritmlər hər iki qrupda

        # ── Final imtahanı + zal + oturum + biletlər (PIN axtarışı üçün) ────
        exam = self._ensure_final_exam(ec_head, org)
        self._seed_questions(exam)
        exam.allowed_groups.set([group_cs, group_se])

        room = self._ensure_room(org, ec_head)
        self._ensure_local_computer(org, room, ec_head)
        ExamRoomSession.objects.filter(room=room).exclude(state__in=("ended",)).delete()
        now = timezone.now()
        session = ExamRoomSession.objects.create(
            organization=org,
            room=room,
            scheduled_start=now - timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=3),
            created_by=ec_head,
        )
        # Təyinat İMTAHANA olur (zaldan asılı deyil); tələbə giriş anında oturuma qoşulur.
        assign_students(exam, all_students, ec_head)
        for ticket in FinalExamTicket.objects.filter(exam=exam):
            if not ticket.pin_hash:
                set_ticket_pin(ticket, ec_head)
        open_entry(session, ec_head)

        # Rəhbər zala 2 nəzarətçi təyin etsin (demo).
        room.invigilators.set([teachers[0], teachers[2]])

        # Bütün demo user-lər DƏRHAL login ola bilsin: aktiv + email təsdiqli +
        # parol dəyişikliyi tələb olunmasın (first-login flow atlanır).
        for du in [superadmin, rector, ec_head] + ec_staff + teachers + all_students:
            if not du.is_active:
                du.is_active = True
                du.save(update_fields=["is_active"])
            p = getattr(du, "profile", None)
            if p and (not p.email_verified or p.password_change_required):
                p.email_verified = True
                p.password_change_required = False
                p.save(update_fields=["email_verified", "password_change_required", "updated_at"])

        self._report(
            pw,
            superadmin,
            org,
            rector,
            ec_head,
            ec_staff,
            teachers,
            all_students,
            group_cs,
            group_se,
            room,
            session,
            exam,
        )

    # ------------------------------------------------------------------ helpers

    def _ensure_superuser(self, username, email, password):
        u = self._ensure_user(username, email, password)
        fields = []
        if not u.is_superuser:
            u.is_superuser = True
            fields.append("is_superuser")
        if not u.is_staff:
            u.is_staff = True
            fields.append("is_staff")
        if fields:
            u.save(update_fields=fields)
        from django.apps import apps as django_apps

        UserProfile = django_apps.get_model("accounts", "UserProfile")
        profile, _ = UserProfile.objects.get_or_create(user=u)
        if profile.role != ProfileRole.SUPERADMIN:
            profile.role = ProfileRole.SUPERADMIN
            profile.save(update_fields=["role", "updated_at"])
        return u

    def _set_name(self, user, first, last):
        if user.first_name != first or user.last_name != last:
            user.first_name = first
            user.last_name = last
            user.save(update_fields=["first_name", "last_name"])

    def _ensure_role(self, org, name, display_name, level, permissions):
        from apps.organizations.models import Role

        role, _ = Role.objects.get_or_create(
            organization=org,
            name=name,
            defaults={
                "display_name": display_name,
                "level": level,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": permissions,
                "is_system": True,
                "is_active": True,
            },
        )
        return role

    def _ensure_unit(self, org, name, unit_type, parent, code):
        from apps.organizations.models import OrgUnit

        unit, created = OrgUnit.objects.get_or_create(
            organization=org,
            name=name,
            defaults={"unit_type": unit_type, "parent": parent, "code": code, "is_active": True},
        )
        changed = []
        if unit.unit_type != unit_type:
            unit.unit_type = unit_type
            changed.append("unit_type")
        if unit.parent_id != (parent.id if parent else None):
            unit.parent = parent
            changed.append("parent")
        if not unit.is_active:
            unit.is_active = True
            changed.append("is_active")
        if changed or created:
            unit.save()  # save() level/path-ı parent-dən yenidən hesablayır
        return unit

    def _ensure_membership_scoped(self, user, org, role, assigned_by, scope_unit):
        membership = self._ensure_membership(user, org, role, assigned_by)
        if membership is not None and membership.scope_unit_id != (scope_unit.id if scope_unit else None):
            membership.scope_unit = scope_unit
            membership.save(update_fields=["scope_unit", "updated_at"])
        return membership

    def _make_students(self, org, owner, student_role, prefix, count, password, kafedra):
        students = []
        for idx in range(1, count + 1):
            username = f"{self.prefix}_{prefix}_student_{idx}"
            student = self._ensure_user(username, f"{username}@example.com", password)
            self._set_name(student, f"Tələbə{idx}", prefix.upper())
            self._assign_profile(student, org, ProfileRole.STUDENT)
            self._ensure_membership_scoped(student, org, student_role, owner, kafedra)
            students.append(student)
        return students

    def _ensure_group(self, org, teacher, name, students, org_unit=None):
        group, _ = StudentGroup.objects.get_or_create(organization=org, teacher=teacher, name=name)
        group.students.set(students)
        group.teachers.set([teacher])
        if org_unit is not None and group.org_unit_id != org_unit.id:
            group.org_unit = org_unit
            group.save(update_fields=["org_unit"])
        return group

    def _ensure_final_exam(self, author, org):
        exam, _ = Exam.objects.get_or_create(
            author=author,
            title="Final İmtahanı — Alqoritmlər (Demo Hierarxiya)",
            organization=org,
            defaults={
                "description": "İyerarxiya demo-su üçün nümunə final imtahanı.",
                "exam_type": "test",
                "exam_type_extended": "final",
                "is_active": True,
                "is_public": False,
                "total_duration_minutes": 60,
                "random_question_count": 3,
                "default_question_points": 1,
            },
        )
        if not exam.is_active or exam.exam_type_extended != "final":
            exam.is_active = True
            exam.exam_type_extended = "final"
            exam.save(update_fields=["is_active", "exam_type_extended"])
        return exam

    def _seed_questions(self, exam):
        exam.questions.all().delete()
        data = [
            (
                "Alqoritmin mürəkkəbliyi nə ilə ölçülür?",
                [("A", "Zaman və yaddaş", True), ("B", "Rəng", False), ("C", "Uzunluq", False)],
            ),
            (
                "Binary search hansı struktur tələb edir?",
                [("A", "Sıralanmış massiv", True), ("B", "Qarışıq siyahı", False), ("C", "Qraf", False)],
            ),
            ("Stack hansı prinsiplə işləyir?", [("A", "LIFO", True), ("B", "FIFO", False), ("C", "Random", False)]),
        ]
        for order, (text, options) in enumerate(data, start=1):
            q = ExamQuestion.objects.create(exam=exam, order=order, text=text, points=1, is_active=True)
            for label, opt_text, correct in options:
                ExamQuestionOption.objects.create(question=q, label=label, text=opt_text, is_correct=correct)

    def _ensure_room(self, org, creator):
        room, _ = ExamRoom.objects.get_or_create(
            organization=org,
            code="DEMO-201",
            defaults={
                "name": "Demo Zal 201",
                "building": "İT korpusu",
                "floor": "2",
                "capacity": 40,
                "computer_count": 40,
                "created_by": creator,
                "is_active": True,
            },
        )
        return room

    def _ensure_subject(self, org, code, name):
        """registrar.Subject yaradır/tapır (sual göndərişi fənn seçimi üçün)."""
        from apps.registrar.models import Subject

        subject, _ = Subject.objects.get_or_create(
            organization=org, code=code, defaults={"name": name}
        )
        return subject

    def _ensure_local_computer(self, org, room, creator):
        """Zala qeydli kompüter(lər) — hər ``--computer-ips`` IP-si üçün bir
        kompüter (giriş IP → zal). MAC identifikasiya sahəsidir (HTTP-dən oxunmur;
        giriş IP ilə bloklanır). Baza MAC-ın son okteti hər IP üçün artırılır ki,
        `(room, mac)` unikallığı pozulmasın."""
        base_mac = (self.computer_mac or "AA:BB:CC:DD:EE:02").upper()
        ips = self.computer_ips or ["127.0.0.1"]
        for idx, ip in enumerate(ips, start=1):
            # Baza MAC-ın son baytını IP indeksinə görə dəyiş (unikal per-room).
            parts = base_mac.split(":")
            if len(parts) == 6:
                try:
                    parts[-1] = f"{(int(parts[-1], 16) + idx - 1) & 0xFF:02X}"
                except ValueError:
                    pass
            mac = ":".join(parts)
            ExamRoomComputer.objects.get_or_create(
                room=room,
                mac_address=mac,
                defaults={
                    "organization": org,
                    "label": f"PC-{idx:02d}",
                    "seat_number": idx,
                    "ip_address": ip,
                    "is_active": True,
                    "created_by": creator,
                },
            )

    def _report(
        self,
        pw,
        superadmin,
        org,
        rector,
        ec_head,
        ec_staff,
        teachers,
        students,
        group_cs,
        group_se,
        room,
        session,
        exam,
    ):
        out, ok, sub = self.stdout, self.style.SUCCESS, self.style.HTTP_INFO
        out.write(ok("\n══════════════════════════════════════════════════════════════"))
        out.write(ok("  DEMO İYERARXİYA HAZIRDIR — şifrə: " + pw))
        out.write(ok("══════════════════════════════════════════════════════════════"))
        out.write(sub(f"Təşkilat: {org.name}\n"))
        out.write(f"  SUPERADMIN            : {superadmin.username}")
        out.write(f"  REKTOR (owner)        : {rector.username}")
        out.write(f"  İMTAHAN MƏRKƏZİ RƏHBƏR: {ec_head.username}   (zala nəzarətçi TƏYİN EDƏ bilir)")
        out.write(
            f"  İMTAHAN MƏRKƏZİ İŞÇİ  : {', '.join(s.username for s in ec_staff)}   (təyin ETMİR — monitor/PIN/hesabat)"
        )
        out.write(sub("\n  MÜƏLLİMLƏR (nəzarətçi namizədləri, kafedra ilə):"))
        for t in teachers:
            out.write(f"    {t.username:20} {t.get_full_name()}")
        out.write(sub("\n  TƏLƏBƏLƏR (PIN axtarışı üçün):"))
        by_id = {t.student_id: t for t in FinalExamTicket.objects.filter(exam=exam).select_related("student")}
        for s in students:
            ticket = by_id.get(s.id)
            pin = decrypt_ticket_pin(ticket) if ticket else "—"
            out.write(f"    {s.username:20} PIN={pin}")
        out.write(
            ok(f"\n  Zal: {room.name} · Oturum vəziyyəti: {session.state} · PIN axtarışı: /exams/center/pin-lookup/\n")
        )
