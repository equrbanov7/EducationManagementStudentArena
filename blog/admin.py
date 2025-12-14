from django.contrib import admin
from .models import Category, Post, Comment, Question, Exam, ExamQuestion, ExamQuestionOption, ExamAttempt, ExamAnswer, StudentGroup


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "created_at", "is_published")
    list_filter = ("is_published", "category", "created_at")
    search_fields = ("title", "excerpt", "content")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("author",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("question_text", "author", "visible_to_all", "created_at")
    list_filter = ("visible_to_all", "created_at", "author")
    search_fields = ("question_text", "answer_text", "author__username")


#--- Exam related admin registrations ---

class ExamQuestionOptionInline(admin.TabularInline):
    model = ExamQuestionOption
    extra = 4
    can_delete = True


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("title", "exam_type", "author", "is_active", "is_public", "created_at")
    list_filter = ("exam_type", "is_active", "is_public", "author")
    search_fields = ("title", "description", "author__username")


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam", "order", "answer_mode", "short_text")
    list_filter = ("exam", "answer_mode")
    search_fields = ("text",)
    inlines = [ExamQuestionOptionInline]

    def short_text(self, obj):
        return obj.text[:60]
    short_text.short_description = "Sual"


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "exam", "attempt_number", "status", "correct_count", "wrong_count", "duration_seconds")
    list_filter = ("exam", "status")
    search_fields = ("user__username", "exam__title")


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "updated_at")
    list_filter = ("question__exam", "is_correct")
    search_fields = ("attempt__user__username", "question__text")



@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "teacher", "created_at")
    search_fields = ("name", "teacher__username", "students__username")
    filter_horizontal = ("students",)

