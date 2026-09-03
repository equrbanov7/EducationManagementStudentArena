"""Qrup idarəetməsi üçün demo data seed komandası.

Seed məntiqi mövzu üzrə mixin-lərə (`_seed_helpers/`) bölünüb; bu modul yalnız
CLI qoşması (add_arguments) və orkestrasiyanı (handle) saxlayır."""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.exams.models import StudentGroup
from core.constants import OrganizationType
from core.management.command_safety import ProductionCommandSafetyMixin
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

from ._seed_helpers import CoursesSeedMixin, ExamsSeedMixin, UsersSeedMixin


class Command(ProductionCommandSafetyMixin, UsersSeedMixin, CoursesSeedMixin, ExamsSeedMixin, BaseCommand):
    safety_command_name = "seed_group_demo_data"
    help = (
        "Qrup idarəetməsi üçün demo data yaradır: təşkilatlar, müəllimlər, tələbələr, "
        "qruplar, dolu kurslar, postlar, test/yazılı imtahanlar və suallar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="DemoPass123!",
            help="Yaradılan demo user-lər üçün şifrə (default: DemoPass123!).",
        )
        parser.add_argument(
            "--students-per-org",
            type=int,
            default=6,
            help="Hər təşkilat üçün neçə tələbə yaradılsın (default: 6).",
        )

    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        password = options["password"]
        students_per_org = max(3, options["students_per_org"])

        superadmin = self._ensure_user("demo_superadmin", "demo_superadmin@example.com", password)
        self._assign_profile(superadmin, None, ProfileRole.SUPERADMIN)

        # M2 (2026-07-02): blog modelləri lazy — exams→blog import kənarını kəsir.
        CourseMembership = django_apps.get_model("courses", "CourseMembership")
        Category = django_apps.get_model("blog", "Category")
        Post = django_apps.get_model("blog", "Post")

        category, _ = Category.objects.get_or_create(
            name="Demo xəbərlər",
            defaults={"slug": "demo-xeberler"},
        )

        org_specs = [
            ("school", "Demo Məktəb", OrganizationType.SCHOOL),
            ("university", "Demo Universitet", OrganizationType.UNIVERSITY),
            ("course", "Demo Kurs Mərkəzi", OrganizationType.COURSE_CENTER),
            ("individual", "Demo Fərdi", OrganizationType.INDIVIDUAL),
        ]

        created_groups = 0
        created_students = 0
        processed_courses = 0
        processed_exams = 0
        processed_questions = 0
        created_posts = 0

        for code, org_name, org_type in org_specs:
            owner = self._ensure_user(f"{code}_owner", f"{code}_owner@example.com", password)
            organization = self._ensure_organization(org_name, org_type, owner)
            self._assign_profile(owner, organization, ProfileRole.ORG_OWNER)

            owner_role = self._resolve_role(organization, ProfileRole.ORG_OWNER)
            self._ensure_membership(owner, organization, owner_role, owner)

            admin_user = self._ensure_user(f"{code}_admin", f"{code}_admin@example.com", password)
            self._assign_profile(admin_user, organization, ProfileRole.ORG_ADMIN)
            admin_role = self._resolve_role(organization, ProfileRole.ORG_ADMIN, owner_role=owner_role)
            self._ensure_membership(admin_user, organization, admin_role, owner)

            teacher_1 = self._ensure_user(f"{code}_teacher_1", f"{code}_teacher_1@example.com", password)
            teacher_2 = self._ensure_user(f"{code}_teacher_2", f"{code}_teacher_2@example.com", password)
            teacher_3 = self._ensure_user(f"{code}_teacher_3", f"{code}_teacher_3@example.com", password)
            teachers = [teacher_1, teacher_2, teacher_3]

            teacher_role = self._resolve_role(organization, ProfileRole.TEACHER)
            for teacher in teachers:
                self._assign_profile(teacher, organization, ProfileRole.TEACHER)
                self._ensure_membership(teacher, organization, teacher_role, owner)

            students = []
            student_role = self._resolve_role(organization, ProfileRole.STUDENT)
            for idx in range(1, students_per_org + 1):
                student = self._ensure_user(
                    f"{code}_student_{idx}",
                    f"{code}_student_{idx}@example.com",
                    password,
                )
                self._assign_profile(student, organization, ProfileRole.STUDENT)
                self._ensure_membership(student, organization, student_role, owner)
                students.append(student)
            created_students += len(students)

            group, group_created = StudentGroup.objects.get_or_create(
                organization=organization,
                teacher=teacher_1,
                name=f"{code.upper()}-GRUP-1",
            )
            if group.teacher_id != teacher_1.id:
                group.teacher = teacher_1
                group.save(update_fields=["teacher"])
            group.students.set(students)
            group.teachers.set(teachers)
            if group_created:
                created_groups += 1

            course = self._ensure_course(organization, teacher_1)
            processed_courses += 1
            CourseMembership.objects.get_or_create(course=course, user=teacher_1, defaults={"role": "teacher"})
            CourseMembership.objects.get_or_create(course=course, user=teacher_2, defaults={"role": "assistant"})
            CourseMembership.objects.get_or_create(course=course, user=teacher_3, defaults={"role": "assistant"})
            for student in students:
                CourseMembership.objects.get_or_create(
                    course=course,
                    user=student,
                    defaults={"role": "student", "group_name": group.name},
                )
            self._seed_course_content(course, teachers, students, group.name)

            test_exam = self._ensure_exam(
                teacher_1,
                course,
                f"{organization.name} Test İmtahanı",
                exam_type="test",
                enable_paint=False,
            )
            written_exam = self._ensure_exam(
                teacher_1,
                course,
                f"{organization.name} Yazılı Praktiki İmtahanı",
                exam_type="written",
                enable_paint=True,
            )
            for exam in [test_exam, written_exam]:
                exam.allowed_groups.add(group)
                exam.allowed_users.add(students[0])
                processed_exams += 1

            self._seed_test_exam_questions(test_exam)
            self._seed_written_exam_questions(written_exam)
            processed_questions += test_exam.questions.count() + written_exam.questions.count()

            post_1, post_1_created = Post.objects.get_or_create(
                author=teacher_1,
                title=f"{organization.name}: İlk Demo Post",
                defaults={
                    "category": category,
                    "excerpt": "Demo post xülasəsi.",
                    "content": "Bu demo post group management yoxlaması üçün yaradılıb.",
                    "is_published": True,
                },
            )
            post_2, post_2_created = Post.objects.get_or_create(
                author=teacher_2,
                title=f"{organization.name}: İkinci Demo Post",
                defaults={
                    "category": category,
                    "excerpt": "İkinci demo post xülasəsi.",
                    "content": "Bu post tenant daxilində məzmun yoxlaması üçündür.",
                    "is_published": True,
                },
            )
            if post_1_created:
                created_posts += 1
            if post_2_created:
                created_posts += 1

        self.stdout.write(self.style.SUCCESS("Demo data hazırdır."))
        self.stdout.write(
            self.style.SUCCESS(
                (
                    "Superadmin: demo_superadmin (credential dəyəri loglanmır)\n"
                    f"Təşkilatlar: {len(org_specs)}\n"
                    f"Tələbələr (yenilənən/yaradılan): {created_students}\n"
                    f"Qruplar (yeni): {created_groups}\n"
                    f"Kurslar (dolu): {processed_courses}\n"
                    f"İmtahanlar (test + yazılı): {processed_exams}\n"
                    f"İmtahan sualları (cəmi): {processed_questions}\n"
                    f"Postlar (yeni): {created_posts}"
                )
            )
        )
