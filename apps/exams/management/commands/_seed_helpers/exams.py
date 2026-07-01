"""seed_group_demo_data — İmtahan (test/yazılı) və sual seed köməkçiləri."""

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock


class ExamsSeedMixin:
    """İmtahan (test/yazılı) və sual seed köməkçiləri (Command tərəfindən MRO ilə istifadə olunur)."""

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
