from django.utils import timezone


class AttemptGradingMixin:
    def mark_checked(self):
        self.checked_by_teacher = True
        if not self.teacher_checked_at:
            self.teacher_checked_at = timezone.now()
            self.save(update_fields=["checked_by_teacher", "teacher_checked_at"])
            return
        self.save(update_fields=["checked_by_teacher"])


class AnswerGradingMixin:
    def auto_evaluate(self):
        exam = self.question.exam
        if exam.exam_type != "test":
            return

        correct_options = set(self.question.options.filter(is_correct=True).values_list("id", flat=True))
        selected = set(self.selected_options.values_list("id", flat=True))

        if not correct_options:
            self.is_correct = False
        else:
            self.is_correct = selected == correct_options

        self.save()


__all__ = [
    "AnswerGradingMixin",
    "AttemptGradingMixin",
]
