"""Seed a demo "Qərbi Kaspi Universiteti" tenant with the full role hierarchy.

Creates one University organization, its academic-unit tree
(Faculty → Chair → Specialty → Group) and one sample user per university role
(rector … student), each wired to the matching organization Role via a
Membership (unit-scoped where the role is unit-scoped).

Idempotent: safe to re-run — users, org, units and memberships are
get_or_create / update_or_create keyed on stable slugs/usernames.

Usage::

    python manage.py seed_western_caspian --password "DemoPass123!"

The required password is explicit and shared by sample users; the first-login
flow replaces it and verifies email when enabled.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import finals as registrar_finals
from apps.registrar import gradebook as registrar_gradebook
from apps.registrar import schedule as registrar_schedule
from apps.registrar import services as registrar_services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Program,
    SlotKind,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.management.command_safety import ProductionCommandSafetyMixin
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

User = get_user_model()


class Command(ProductionCommandSafetyMixin, BaseCommand):
    safety_command_name = "seed_western_caspian"
    help = "Seed the Qərbi Kaspi Universiteti demo tenant with all university roles and the academic hierarchy."

    ORG_NAME = "Qərbi Kaspi Universiteti"
    ORG_SLUG = "qerbi-kaspi-universiteti"

    FACULTY_NAME = "Mühəndislik və Tətbiqi Elmlər fakültəsi"
    CHAIR_NAME = "Kompüter elmləri kafedrası"
    SPECIALTY_NAME = "Kompüter elmləri (ixtisas)"
    # A specialty can carry groups in more than one language SECTOR (bölmə):
    # Azerbaijani + English here. Sector structure varies per university, so it
    # is encoded in the group name rather than a hardcoded enum.
    GROUP_AZ_NAME = "KE-101 (Azərbaycan bölməsi)"
    GROUP_EN_NAME = "KE-101E (İngilis bölməsi)"

    # (username, role_name, ProfileRole, scope) —
    # scope: None | "faculty" | "chair" | "specialty" | "group_az" | "group_en"
    ROLE_USERS = [
        ("wcu_rector", "rector", ProfileRole.ORG_ADMIN, None),
        ("wcu_vice_rector", "vice_rector", ProfileRole.ORG_ADMIN, None),
        ("wcu_exam_center", "exam_center", ProfileRole.MEMBER, None),
        ("wcu_hr", "hr", ProfileRole.HR, None),
        ("wcu_dean", "dean", ProfileRole.ORG_ADMIN, "faculty"),
        ("wcu_department_head", "chair_head", ProfileRole.ORG_ADMIN, "chair"),
        ("wcu_program_coordinator", "program_coordinator", ProfileRole.MEMBER, "specialty"),
        ("wcu_teacher", "teacher", ProfileRole.TEACHER, None),
        ("wcu_assistant", "assistant", ProfileRole.ASSISTANT_TEACHER, None),
        ("wcu_lab_assistant", "lab_assistant", ProfileRole.ASSISTANT_TEACHER, None),
        # Azərbaycan bölməsi (AZ sector) — tutor + lead + 2 students.
        ("wcu_tutor", "tutor", ProfileRole.MEMBER, "group_az"),
        ("wcu_lead_student_az", "lead_student", ProfileRole.LEAD_STUDENT, "group_az"),
        ("wcu_student_az1", "student", ProfileRole.STUDENT, "group_az"),
        ("wcu_student_az2", "student", ProfileRole.STUDENT, "group_az"),
        # İngilis bölməsi (EN sector) — lead + 2 students.
        ("wcu_lead_student_en", "lead_student", ProfileRole.LEAD_STUDENT, "group_en"),
        ("wcu_student_en1", "student", ProfileRole.STUDENT, "group_en"),
        ("wcu_student_en2", "student", ProfileRole.STUDENT, "group_en"),
    ]

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Shared password for every seeded user (required).")
        parser.add_argument(
            "--no-first-login-flow",
            action="store_true",
            help="Do not flag seeded users for the first-login password/email step.",
        )
        parser.add_argument(
            "--with-superadmin",
            action="store_true",
            help="Also create a platform superadmin test user (wcu_superadmin, is_superuser).",
        )

    def handle(self, *args, **options):
        password = (options.get("password") or "").strip()
        if not password:
            raise CommandError("--password is required so seeded credentials are explicit.")
        flag_first_login = not options.get("no_first_login_flow")

        with rls_worker_atomic(), bypass_rls():
            owner = self._ensure_user(
                username="wcu_rector",
                password=password,
                email="rector@qku.edu.az",
                first_name="Rəşad",
                last_name="Rektorov",
                flag_first_login=flag_first_login,
            )
            org = self._ensure_org(owner)
            roles = {role.name: role for role in Role.objects.filter(organization=org)}
            units = self._ensure_academic_hierarchy(org)

            created = 0
            student_scope = []  # (user, group_scope_key) for the curriculum step
            for username, role_name, profile_role, scope_key in self.ROLE_USERS:
                role = roles.get(role_name)
                if role is None:
                    self.stdout.write(self.style.WARNING(f"  role '{role_name}' missing on org — skipped {username}"))
                    continue
                user = self._ensure_user(
                    username=username,
                    password=password,
                    email=f"{username}@qku.edu.az",
                    first_name=username.replace("wcu_", "").replace("_", " ").title(),
                    last_name="Test",
                    flag_first_login=flag_first_login and username != "wcu_rector",
                )
                self._configure_profile(user, org, profile_role, units, scope_key)
                scope_unit = self._scope_unit_for(role, units, scope_key)
                self._ensure_membership(
                    user=user, organization=org, role=role, scope_unit=scope_unit, assigned_by=owner
                )
                created += 1
                if role_name == "student":
                    student_scope.append((user, scope_key))

            self._seed_curriculum(org, units, student_scope, decided_by=owner)
            self._seed_lms_student_groups(org, units)

            superadmin_note = ""
            if options.get("with_superadmin"):
                self._ensure_user(
                    username="wcu_superadmin",
                    password=password,
                    email="superadmin@qku.edu.az",
                    first_name="Super",
                    last_name="Admin",
                    flag_first_login=False,
                    is_superuser=True,
                )
                superadmin_note = " + platform superadmin (wcu_superadmin)"

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Qərbi Kaspi Universiteti seeded: org='{org.slug}', {created} role users{superadmin_note}, "
                f"{len(units)} academic units (AZ + EN sectors) + LMS student groups. "
                "Shared password set as provided."
            )
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def _ensure_user(self, *, username, password, email, first_name, last_name, flag_first_login, is_superuser=False):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "first_name": first_name, "last_name": last_name, "is_active": True},
        )
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        if is_superuser:
            user.is_superuser = True
            user.is_staff = True
        user.set_password(password)
        user.save()
        # Flag the first-login password/email step when that flow is enabled
        # (only applied if the profile has the fields; ignored otherwise).
        profile = getattr(user, "profile", None)
        if profile is not None:
            updated = []
            if hasattr(profile, "password_change_required"):
                profile.password_change_required = flag_first_login
                updated.append("password_change_required")
            if hasattr(profile, "email_verified"):
                profile.email_verified = not flag_first_login
                updated.append("email_verified")
            if updated:
                profile.save(update_fields=[*updated, "updated_at"])
        return user

    def _ensure_org(self, owner):
        org, _ = Organization.objects.get_or_create(
            slug=self.ORG_SLUG,
            defaults={
                "name": self.ORG_NAME,
                "org_type": OrganizationType.UNIVERSITY,
                "owner": owner,
                "status": "active",
                "is_active": True,
            },
        )
        if org.owner_id != owner.id:
            org.owner = owner
            org.save(update_fields=["owner", "updated_at"])
        return org

    def _ensure_unit(self, *, org, unit_type, name, parent=None):
        unit, _ = OrgUnit.objects.get_or_create(
            organization=org,
            name=name,
            defaults={"unit_type": unit_type, "parent": parent},
        )
        changed = []
        if unit.unit_type != unit_type:
            unit.unit_type = unit_type
            changed.append("unit_type")
        if unit.parent_id != (parent.id if parent else None):
            unit.parent = parent
            changed.append("parent")
        if changed:
            unit.save(update_fields=[*changed, "updated_at"])
        return unit

    def _ensure_academic_hierarchy(self, org):
        faculty = self._ensure_unit(org=org, unit_type=OrgUnitType.FACULTY, name=self.FACULTY_NAME)
        chair = self._ensure_unit(org=org, unit_type=OrgUnitType.CHAIR, name=self.CHAIR_NAME, parent=faculty)
        specialty = self._ensure_unit(org=org, unit_type=OrgUnitType.SPECIALTY, name=self.SPECIALTY_NAME, parent=chair)
        # Two language sectors under the same specialty (AZ + EN). Structure is
        # tenant-configurable — other universities may use different sectors.
        group_az = self._ensure_unit(org=org, unit_type=OrgUnitType.GROUP, name=self.GROUP_AZ_NAME, parent=specialty)
        group_en = self._ensure_unit(org=org, unit_type=OrgUnitType.GROUP, name=self.GROUP_EN_NAME, parent=specialty)
        return {
            "faculty": faculty,
            "chair": chair,
            "specialty": specialty,
            "group_az": group_az,
            "group_en": group_en,
        }

    def _seed_curriculum(self, org, units, student_scope, *, decided_by):
        """Demo curriculum + enrollments so the student academic flow is testable.

        Semester-1 plan: 2 mandatory subjects + a 2-option elective block "SB1".
        Each seeded student gets an academic record; mandatory subjects are
        auto-enrolled; each group's elective is decided (→ all group members
        enrolled), demonstrating the group-level elective flow (roadmap §2.5).
        """
        specialty = units["specialty"]
        program, _ = Program.objects.get_or_create(
            organization=org,
            code="CS",
            defaults={"name": self.SPECIALTY_NAME, "specialty_unit": specialty, "ects_total": 240},
        )
        curriculum, _ = Curriculum.objects.get_or_create(
            organization=org, program=program, admission_year=2024, defaults={"name": "CS 2024 planı"}
        )
        subjects = {}
        for code, name, ects in [
            ("MATH101", "Riyaziyyat", 6),
            ("CS101", "Proqramlaşdırmanın əsasları", 6),
            ("EL-WEB", "Veb texnologiyalar (seçmə)", 4),
            ("EL-AI", "Süni intellekt (seçmə)", 4),
        ]:
            subjects[code], _ = Subject.objects.get_or_create(
                organization=org, code=code, defaults={"name": name, "ects": ects}
            )
        for code in ("MATH101", "CS101"):
            CurriculumSubject.objects.get_or_create(
                organization=org, curriculum=curriculum, subject=subjects[code], semester_number=1
            )
        for code in ("EL-WEB", "EL-AI"):
            CurriculumSubject.objects.get_or_create(
                organization=org,
                curriculum=curriculum,
                subject=subjects[code],
                semester_number=1,
                defaults={"is_elective": True, "elective_group": "SB1", "required_choices": 1},
            )

        period, _ = AcademicPeriod.objects.get_or_create(
            organization=org,
            name="2024/2025 Payız semestri",
            defaults={
                "period_type": AcademicPeriodType.SEMESTER,
                "academic_year": "2024/2025",
                "start_date": "2024-09-01",
                "end_date": "2025-01-31",
                # Akademik təqvim pəncərələri (U11) — demo dəyərlər.
                "registration_start": "2024-08-15",
                "registration_end": "2024-09-10",
                "exam_session_start": "2025-01-06",
                "exam_session_end": "2025-01-31",
                "is_current": True,
            },
        )

        # Academic records + mandatory auto-enroll per student.
        for user, scope_key in student_scope:
            group = units.get(scope_key)
            record, _ = StudentAcademicRecord.objects.get_or_create(
                organization=org,
                student=user,
                program=program,
                defaults={"curriculum": curriculum, "group": group, "admission_year": 2024},
            )
            registrar_services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)

        # Group-level elective decision: AZ group → Veb, EN group → AI.
        for group_key, subject_code in (("group_az", "EL-WEB"), ("group_en", "EL-AI")):
            group = units.get(group_key)
            if group and StudentAcademicRecord.objects.filter(organization=org, group=group).exists():
                registrar_services.choose_group_elective(
                    organization=org,
                    group=group,
                    curriculum=curriculum,
                    period=period,
                    elective_group="SB1",
                    subject=subjects[subject_code],
                    decided_by=decided_by,
                    enforce_window=False,  # seed: tarixi demo period üçün pəncərə keçilir
                )

        self._seed_demo_progress(org)

    def _seed_demo_progress(self, org):
        """Give the demo enrollments contact hours + some progress/absence data.

        So the student cabinet shows a real Bologna credit bar and the
        absence (qayıb) limit is exercisable: every offering gets 60 lesson
        hours, one mandatory subject is marked COMPLETED (earned credits), and
        one student is pushed over the 25% absence limit (barred from the exam).
        """
        CourseOffering.objects.filter(organization=org, lesson_hours=0).update(lesson_hours=60)

        # One completed mandatory subject per student → earned ECTS on the bar.
        for enrollment in Enrollment.objects.filter(
            organization=org, offering__subject__code="MATH101", status=Enrollment.Status.ENROLLED
        ):
            enrollment.status = Enrollment.Status.COMPLETED
            enrollment.save(update_fields=["status"])

        # The absence-barred demo is produced by the journal itself (wcu_student_az1
        # is marked absent in every session — see _seed_journal), which recomputes
        # Enrollment.absence_hours; no manual override needed here.
        self._seed_journal(org)

    def _seed_lms_student_groups(self, org, units):
        """Create StudentGroup rows used by exam/course access selectors.

        Registrar OrgUnit GROUP rows drive the academic structure; the exam
        wizard's "Allowed groups" selector uses exams.StudentGroup. Link them
        with org_unit so the WCU demo groups appear in both places.
        """
        from django.apps import apps as django_apps

        StudentGroup = django_apps.get_model("exams", "StudentGroup")
        teacher = User.objects.filter(username="wcu_teacher").first()
        if teacher is None:
            return

        co_teachers = User.objects.filter(username__in=["wcu_teacher", "wcu_assistant", "wcu_lab_assistant"])
        subjects = Subject.objects.filter(organization=org, code__in=["MATH101", "CS101"])
        group_specs = [
            (
                "group_az",
                self.GROUP_AZ_NAME,
                ["wcu_lead_student_az", "wcu_student_az1", "wcu_student_az2"],
            ),
            (
                "group_en",
                self.GROUP_EN_NAME,
                ["wcu_lead_student_en", "wcu_student_en1", "wcu_student_en2"],
            ),
        ]
        for scope_key, group_name, student_usernames in group_specs:
            org_unit = units.get(scope_key)
            group, _ = StudentGroup.objects.get_or_create(
                organization=org,
                teacher=teacher,
                name=group_name,
                defaults={"org_unit": org_unit},
            )
            if org_unit and group.org_unit_id != org_unit.id:
                group.org_unit = org_unit
                group.save(update_fields=["org_unit"])
            group.students.set(User.objects.filter(username__in=student_usernames))
            group.teachers.set(co_teachers)
            group.subjects.set(subjects)

    def _seed_journal(self, org):
        """Wire offerings to their LMS course + seed the electronic journal.

        Hər offering: müəllim instruktor, linked Course (üzvlər sync), keçirilmiş
        dərslər (mühazirə + seminar) davamiyyət/ballarla, mövzu planı (CourseTopic)
        və növbələnən slot tipi. az1 25% limiti keçir (barred → sətir qırmızı)."""
        import datetime

        teacher = User.objects.filter(username="wcu_teacher").first()
        # 8 sessions (2h each): mühazirə (yalnız davamiyyət) + seminar (davamiyyət + bal).
        base = datetime.date(2024, 10, 1)
        # fmt: off
        plan = [("lecture", 0), ("seminar", 3), ("lecture", 7), ("seminar", 10),
                ("lecture", 14), ("seminar", 17), ("lecture", 21), ("seminar", 24)]
        # Demo mövzu planı — yeni-dərs modalının mövzu seçimi + sol təqvim planı.
        demo_topics = [
            "Giriş və əsas anlayışlar", "Dəyişənlər və məlumat tipləri", "Şərt operatorları",
            "Dövrlər (loop)", "Funksiyalar", "Massivlər və siyahılar",
            "Sətir əməliyyatları", "Yekunlaşdırıcı mövzu",
        ]
        # fmt: on
        # App registry ilə — organizations→courses statik importu (dep dövrü) yox.
        from django.apps import apps as django_apps

        CourseTopic = django_apps.get_model("courses", "CourseTopic")
        offerings = CourseOffering.objects.filter(organization=org).select_related("subject", "group", "period")
        for offering in offerings:
            if teacher and offering.instructor_id is None:
                offering.instructor = teacher
                offering.save(update_fields=["instructor"])
            registrar_services.ensure_offering_course(offering=offering)
            registrar_services.sync_offering_course_members(offering=offering)
            registrar_gradebook.ensure_assessment_scheme(offering=offering)
            enrollments = list(offering.enrollments.filter(status=Enrollment.Status.ENROLLED).select_related("student"))

            # Kursa mövzu planı (idempotent) — modal seçimi + təqvim planı üçün.
            if offering.course_id and not CourseTopic.objects.filter(course_id=offering.course_id).exists():
                CourseTopic.objects.bulk_create(
                    [CourseTopic(course_id=offering.course_id, title=t, order=i) for i, t in enumerate(demo_topics, 1)]
                )
            if not offering.lessons.exists():  # idempotent — do not duplicate lessons
                for lesson_idx, (kind, day_offset) in enumerate(plan):
                    # Dərsə plandan mövzu bağla → təqvim planı mövzu adı ilə görünür.
                    lesson = registrar_gradebook.create_lesson(
                        allow_past=True,
                        offering=offering,
                        kind=kind,
                        created_by=teacher,
                        date=base + datetime.timedelta(days=day_offset),
                        topic=demo_topics[lesson_idx] if lesson_idx < len(demo_topics) else "",
                    )
                    entries = []
                    for enrollment in enrollments:
                        # wcu_student_az1 misses every session → exceeds the limit.
                        absent = enrollment.student.username == "wcu_student_az1"
                        entries.append(
                            {
                                "lesson_id": lesson.id,
                                "enrollment_id": enrollment.id,
                                "status": "absent" if absent else "present",
                                "score": None if kind == "lecture" or absent else 8,
                            }
                        )
                    registrar_gradebook.save_marks(
                        enforce_day=False, offering=offering, entries=entries, by_user=teacher
                    )

            # Yekun imtahan + təkrar imtahan demo (idempotent): barred AZ student
            # → resit (absence); az2 → low exam (fails → resit); others → pass.
            for enrollment in enrollments:
                uname = enrollment.student.username
                if uname == "wcu_student_az1":
                    registrar_finals.evaluate_resit(enrollment=enrollment, by_user=teacher)
                else:
                    registrar_finals.set_exam_score(
                        enrollment=enrollment, score=10 if uname == "wcu_student_az2" else 40, by_user=teacher
                    )

        self._seed_schedule(org)

    def _seed_schedule(self, org):
        """Give each offering a weekly timetable slot. Within a group two lessons
        are packed onto the same weekday (so a student sees MULTIPLE lessons per
        day), and each group gets its OWN time bands so the shared demo teacher
        never clashes across groups at the same weekday/time."""
        import datetime

        # Per-group time bands (two 90-min slots), offset by group so different
        # groups never occupy the same (weekday, time) → no shared-teacher clash.
        band_table = [
            (datetime.time(9, 0), datetime.time(10, 30)),
            (datetime.time(11, 0), datetime.time(12, 30)),
            (datetime.time(13, 0), datetime.time(14, 30)),
            (datetime.time(15, 0), datetime.time(16, 30)),
            (datetime.time(17, 0), datetime.time(18, 30)),
            (datetime.time(19, 0), datetime.time(20, 30)),
        ]
        offerings = list(
            CourseOffering.objects.filter(organization=org)
            .select_related("subject", "group")
            .order_by("group_id", "subject__code")
        )
        group_order: dict = {}
        group_count: dict = {}
        for index, offering in enumerate(offerings):
            if offering.schedule_slots.exists():
                continue  # idempotent
            gid = offering.group_id
            group_index = group_order.setdefault(gid, len(group_order))
            k = group_count.get(gid, 0)
            group_count[gid] = k + 1
            # Two lessons/day within the group; each group uses its own 2 bands.
            weekday = ((k // 2) % 6) + 1
            band = band_table[(group_index * 2 + (k % 2)) % len(band_table)]
            # Dərs tipini növbələ (Lecture/Seminar/Lab) → siyahıda "DƏRS TİPİ" varie olsun.
            slot_kind = [SlotKind.LECTURE, SlotKind.SEMINAR, SlotKind.LAB][index % 3]
            try:
                registrar_schedule.create_slot(
                    offering=offering,
                    weekday=weekday,
                    start_time=band[0],
                    end_time=band[1],
                    room=str(201 + index),
                    kind=slot_kind,
                    created_by=offering.instructor,
                )
            except registrar_schedule.ScheduleConflict:
                pass

        self._seed_exam(org)

    def _seed_exam(self, org):
        """One demo exam THIS week so the timetable shows the "imtahan on that day"
        integration. Dated relative to today (Wednesday of the current week) and
        linked to the AZ group's CS101 course, so the AZ students see it on the
        schedule. Idempotent (matched by title). Resolved via the app registry so
        the organizations module keeps no static import of exams (no dep cycle)."""
        import datetime

        from django.apps import apps as django_apps
        from django.utils import timezone

        Exam = django_apps.get_model("exams", "Exam")
        title = "CS101 aralıq imtahanı (demo)"
        if Exam.objects.filter(organization=org, title=title).exists():
            return

        offering = (
            CourseOffering.objects.filter(
                organization=org,
                subject__code="CS101",
                course__isnull=False,
                enrollments__student__username="wcu_student_az1",
            )
            .select_related("course", "instructor")
            .first()
        )
        if offering is None or offering.instructor is None:
            return

        today = timezone.localdate()
        wednesday = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(days=2)
        start = timezone.make_aware(datetime.datetime.combine(wednesday, datetime.time(10, 0)))
        Exam.objects.create(
            organization=org,
            author=offering.instructor,
            course=offering.course,
            title=title,
            exam_type="written",
            exam_type_extended="midterm",
            start_datetime=start,
            end_datetime=start + datetime.timedelta(hours=1, minutes=30),
            total_duration_minutes=90,
            is_active=True,
        )

    def _configure_profile(self, user, org, profile_role, units, scope_key):
        profile = user.profile
        profile.organization = org
        profile.organization_type = OrganizationType.UNIVERSITY
        profile.country = "Azerbaijan"
        profile.role = profile_role
        if profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
            profile.student_university_name = org.name
            profile.student_specialization = self.SPECIALTY_NAME
            group_unit = units.get(scope_key)
            profile.student_group_number = group_unit.name if group_unit else ""
        profile.save()
        return profile

    def _scope_unit_for(self, role, units, scope_key):
        # Only unit/course-scoped roles carry a scope_unit; org-scoped roles stay org-wide.
        if role.scope_type not in {RoleScopeType.UNIT, RoleScopeType.COURSE}:
            return None
        return units.get(scope_key) if scope_key else None

    def _ensure_membership(self, *, user, organization, role, scope_unit, assigned_by):
        membership, _ = Membership.objects.update_or_create(
            user=user,
            organization=organization,
            role=role,
            scope_unit=scope_unit,
            defaults={"assigned_by": assigned_by, "is_primary": True, "is_active": True},
        )
        return membership
