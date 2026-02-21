from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import ProfileRole, UserProfile
from apps.blog.models import Category, Post
from apps.courses.models import Course, CourseGroup, CourseInstructor, CourseMembership, CourseResource, CourseTopic
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock, StudentGroup
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType

User = get_user_model()


class Command(BaseCommand):
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

    def _ensure_user(self, username, email, password):
        user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
        updated_fields = []
        if user.email != email:
            user.email = email
            updated_fields.append("email")

        user.is_active = True
        updated_fields.append("is_active")
        user.set_password(password)
        updated_fields.append("password")
        user.save(update_fields=updated_fields)
        return user

    def _assign_profile(self, user, organization, role):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.organization = organization
        profile.organization_type = organization.org_type if organization else OrganizationType.INDIVIDUAL
        profile.role = role
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        user.__dict__["profile"] = profile

    def _ensure_organization(self, name, org_type, owner):
        organization, created = Organization.objects.get_or_create(
            name=name,
            defaults={
                "org_type": org_type,
                "owner": owner,
                "status": "active",
                "is_active": True,
            },
        )
        if created:
            return organization

        update_fields = []
        if organization.org_type != org_type:
            organization.org_type = org_type
            update_fields.append("org_type")
        if organization.owner_id != owner.id:
            organization.owner = owner
            update_fields.append("owner")
        if organization.status != "active":
            organization.status = "active"
            update_fields.append("status")
        if not organization.is_active:
            organization.is_active = True
            update_fields.append("is_active")
        if update_fields:
            organization.save(update_fields=update_fields)
        return organization

    def _resolve_role(self, organization, profile_role, owner_role=None):
        roles = Role.objects.filter(organization=organization, is_active=True)
        if not roles.exists():
            return None

        if profile_role == ProfileRole.ORG_OWNER:
            return roles.order_by("-level").first()

        if profile_role == ProfileRole.ORG_ADMIN:
            if owner_role is not None:
                role = roles.filter(level__lt=owner_role.level).order_by("-level").first()
                if role:
                    return role
            return roles.order_by("-level").first()

        if profile_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
            for role_name in ["teacher", "instructor", "assistant_teacher", "assistant", "professor", "associate_professor"]:
                role = roles.filter(name=role_name).first()
                if role:
                    return role
            return roles.filter(level__gte=50).order_by("level").first() or roles.order_by("-level").first()

        if profile_role == ProfileRole.STUDENT:
            return roles.filter(name="student").first() or roles.order_by("level").first()

        if profile_role == ProfileRole.MEMBER:
            return roles.filter(name="member").first() or roles.filter(name="student").first() or roles.order_by("level").first()

        return roles.order_by("level").first()

    def _ensure_membership(self, user, organization, role, assigned_by):
        if role is None:
            return None
        membership, _ = Membership.objects.get_or_create(
            user=user,
            organization=organization,
            defaults={
                "role": role,
                "is_primary": True,
                "is_active": True,
                "assigned_by": assigned_by,
            },
        )
        update_fields = []
        if membership.role_id != role.id:
            membership.role = role
            update_fields.append("role")
        if not membership.is_primary:
            membership.is_primary = True
            update_fields.append("is_primary")
        if not membership.is_active:
            membership.is_active = True
            update_fields.append("is_active")
        if membership.assigned_by_id != assigned_by.id:
            membership.assigned_by = assigned_by
            update_fields.append("assigned_by")
        if update_fields:
            membership.save(update_fields=update_fields + ["updated_at"])
        return membership

    def _ensure_course(self, organization, teacher):
        course, _ = Course.objects.get_or_create(
            owner=teacher,
            title=f"{organization.name} Demo Kursu",
            defaults={
                "description": f"{organization.name} üçün demo kurs.",
                "status": "published",
                "settings": {"seeded": True},
            },
        )
        update_fields = []
        if course.status != "published":
            course.status = "published"
            update_fields.append("status")
        if not course.settings:
            course.settings = {"seeded": True}
            update_fields.append("settings")
        if update_fields:
            course.save(update_fields=update_fields)
        return course

    def _seed_course_content(self, course, teachers, students, group_name):
        topic_specs = [
            ("Giriş və struktur", "Kursun məqsədi, qaydalar və ilkin materiallar.", 1),
            ("Əsas anlayışlar", "Mövzu üzrə baza nümunələr və izah.", 2),
            ("Praktiki tətbiq", "Real task və layihə əsaslı məşğələ.", 3),
        ]
        topics = []
        for title, description, order in topic_specs:
            topic, _ = CourseTopic.objects.get_or_create(
                course=course,
                order=order,
                defaults={"title": title, "description": description},
            )
            update_fields = []
            if topic.title != title:
                topic.title = title
                update_fields.append("title")
            if topic.description != description:
                topic.description = description
                update_fields.append("description")
            if update_fields:
                topic.save(update_fields=update_fields)
            topics.append(topic)

        for idx, topic in enumerate(topics, start=1):
            resource, _ = CourseResource.objects.get_or_create(
                course=course,
                topic=topic,
                title=f"{topic.title} - Material {idx}",
                defaults={
                    "description": "Demo dərs materialı",
                    "resource_type": "link",
                    "url": f"https://example.com/{course.slug}/topic-{idx}",
                },
            )
            update_fields = []
            if resource.resource_type != "link":
                resource.resource_type = "link"
                update_fields.append("resource_type")
            if not resource.url:
                resource.url = f"https://example.com/{course.slug}/topic-{idx}"
                update_fields.append("url")
            if update_fields:
                resource.save(update_fields=update_fields)

        for idx, teacher in enumerate(teachers, start=1):
            role = "primary" if idx == 1 else "assistant"
            instructor, _ = CourseInstructor.objects.get_or_create(
                course=course,
                user=teacher,
                defaults={
                    "role": role,
                    "permissions": {
                        "can_grade": True,
                        "can_edit": idx == 1,
                        "can_publish": idx == 1,
                    },
                },
            )
            update_fields = []
            if instructor.role != role:
                instructor.role = role
                update_fields.append("role")
            if not instructor.permissions:
                instructor.permissions = {
                    "can_grade": True,
                    "can_edit": idx == 1,
                    "can_publish": idx == 1,
                }
                update_fields.append("permissions")
            if update_fields:
                instructor.save(update_fields=update_fields)

        course_group, _ = CourseGroup.objects.get_or_create(
            course=course,
            name=f"{group_name} - Praktik Qrup",
            defaults={
                "schedule": {"day": "Monday", "time": "10:00", "room": "Lab-101"},
                "instructor": teachers[0],
                "max_students": max(30, len(students) + 5),
            },
        )
        group_update_fields = []
        if course_group.instructor_id != teachers[0].id:
            course_group.instructor = teachers[0]
            group_update_fields.append("instructor")
        if not course_group.schedule:
            course_group.schedule = {"day": "Monday", "time": "10:00", "room": "Lab-101"}
            group_update_fields.append("schedule")
        if course_group.max_students < len(students):
            course_group.max_students = len(students) + 5
            group_update_fields.append("max_students")
        if group_update_fields:
            course_group.save(update_fields=group_update_fields)
        course_group.members.set(students)

    def _ensure_exam(self, teacher, course, title, exam_type, enable_paint):
        exam, _ = Exam.objects.get_or_create(
            author=teacher,
            title=title,
            defaults={
                "description": f"{title} üçün demo məzmun.",
                "exam_type": exam_type,
                "is_active": True,
                "is_public": False,
                "enable_paint": enable_paint,
                "random_question_count": 10,
                "default_question_points": 1,
                "course": course,
            },
        )
        update_fields = []
        if exam.exam_type != exam_type:
            exam.exam_type = exam_type
            update_fields.append("exam_type")
        if exam.enable_paint != enable_paint:
            exam.enable_paint = enable_paint
            update_fields.append("enable_paint")
        if not exam.is_active:
            exam.is_active = True
            update_fields.append("is_active")
        if exam.is_public:
            exam.is_public = False
            update_fields.append("is_public")
        if exam.course_id != course.id:
            exam.course = course
            update_fields.append("course")
        if update_fields:
            exam.save(update_fields=update_fields)
        return exam

    def _set_test_question_options(self, question, options):
        question.options.all().delete()
        for label, text, is_correct in options:
            ExamQuestionOption.objects.create(
                question=question,
                label=label,
                text=text,
                is_correct=is_correct,
            )

    def _seed_test_exam_questions(self, exam):
        block_1, _ = QuestionBlock.objects.get_or_create(
            exam=exam,
            order=1,
            defaults={"name": "Əsas Mövzular", "time_limit_minutes": 15},
        )
        block_2, _ = QuestionBlock.objects.get_or_create(
            exam=exam,
            order=2,
            defaults={"name": "Praktik Tətbiq", "time_limit_minutes": 20},
        )

        question_specs = [
            (
                block_1,
                1,
                "Python-da list comprehension nə üçün istifadə olunur?",
                "single",
                [
                    ("A", "Sadəcə string çevirmək üçün", False),
                    ("B", "Qısa sintaksislə yeni list yaratmaq üçün", True),
                    ("C", "Yalnız dövrü dayandırmaq üçün", False),
                    ("D", "Faylları avtomatik silmək üçün", False),
                ],
            ),
            (
                block_1,
                2,
                "Django model migration nə edir?",
                "single",
                [
                    ("A", "Yalnız frontend CSS dəyişir", False),
                    ("B", "Database schema dəyişikliklərini tətbiq edir", True),
                    ("C", "Serveri söndürür", False),
                    ("D", "Statik faylları sıxır", False),
                ],
            ),
            (
                block_2,
                3,
                "Aşağıdakılardan hansıları backend tenant isolation üçün doğrudur?",
                "multiple",
                [
                    ("A", "Hər sorğuda tenant filter tətbiq olunmalıdır", True),
                    ("B", "Yalnız frontend gizlətməsi kifayətdir", False),
                    ("C", "Authorization server-side yoxlanmalıdır", True),
                    ("D", "Cross-tenant ID qəbul etmək olar", False),
                ],
            ),
        ]

        for block, order, text, answer_mode, options in question_specs:
            question, _ = ExamQuestion.objects.get_or_create(
                exam=exam,
                text=text,
                defaults={
                    "block": block,
                    "order": order,
                    "answer_mode": answer_mode,
                    "points": 1,
                    "difficulty": "medium",
                    "explanation": "Demo izahat",
                },
            )
            update_fields = []
            if question.block_id != block.id:
                question.block = block
                update_fields.append("block")
            if question.order != order:
                question.order = order
                update_fields.append("order")
            if question.answer_mode != answer_mode:
                question.answer_mode = answer_mode
                update_fields.append("answer_mode")
            if question.points != 1:
                question.points = 1
                update_fields.append("points")
            if update_fields:
                question.save(update_fields=update_fields)
            self._set_test_question_options(question, options)

    def _seed_written_exam_questions(self, exam):
        block_1, _ = QuestionBlock.objects.get_or_create(
            exam=exam,
            order=1,
            defaults={"name": "Yazılı Hissə", "time_limit_minutes": 25},
        )
        block_2, _ = QuestionBlock.objects.get_or_create(
            exam=exam,
            order=2,
            defaults={"name": "Praktiki Hissə", "time_limit_minutes": 35},
        )

        question_specs = [
            (
                block_1,
                1,
                "RBAC ilə tenant isolation fərqini izah edin və real nümunə verin.",
                "Bu cavabda rol əsaslı icazələr və tenant scope birlikdə izah olunmalıdır.",
            ),
            (
                block_2,
                2,
                "Qrup yaratma flow-u üçün backend validasiya ardıcıllığını yazın.",
                "Tenant yoxlaması, rol yoxlaması və teacher/student uyğunluğu qeyd olunmalıdır.",
            ),
        ]

        for block, order, text, ideal_answer in question_specs:
            question, _ = ExamQuestion.objects.get_or_create(
                exam=exam,
                text=text,
                defaults={
                    "block": block,
                    "order": order,
                    "answer_mode": "single",
                    "correct_answer": ideal_answer,
                    "points": 5,
                    "difficulty": "medium",
                    "enable_paint": True,
                },
            )
            update_fields = []
            if question.block_id != block.id:
                question.block = block
                update_fields.append("block")
            if question.order != order:
                question.order = order
                update_fields.append("order")
            if question.correct_answer != ideal_answer:
                question.correct_answer = ideal_answer
                update_fields.append("correct_answer")
            if not question.enable_paint:
                question.enable_paint = True
                update_fields.append("enable_paint")
            if question.points != 5:
                question.points = 5
                update_fields.append("points")
            if update_fields:
                question.save(update_fields=update_fields)

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        students_per_org = max(3, options["students_per_org"])

        superadmin = self._ensure_user("demo_superadmin", "demo_superadmin@example.com", password)
        self._assign_profile(superadmin, None, ProfileRole.SUPERADMIN)

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
                    f"Superadmin: demo_superadmin / {password}\n"
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
