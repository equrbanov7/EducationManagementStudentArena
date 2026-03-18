from django.contrib import admin

from .models import Category, Comment, Post, PostApprovalLog, Question


class HiddenFromSidebarAdminMixin:
    """
    Keep models registered but hide Blog app from Django admin sidebar.
    """

    def has_module_permission(self, request):
        return False


@admin.register(Category)
class CategoryAdmin(HiddenFromSidebarAdminMixin, admin.ModelAdmin):
    list_display = ("name", "parent", "show_in_navbar", "is_default", "sort_order", "slug")
    list_filter = ("show_in_navbar", "is_default", "parent")
    search_fields = ("name", "slug", "parent__name")
    list_editable = ("show_in_navbar", "is_default", "sort_order")
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Post)
class PostAdmin(HiddenFromSidebarAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "author",
        "category",
        "approval_status",
        "is_published",
        "created_at",
    )
    list_filter = ("is_published", "approval_status", "requires_approval", "category", "created_at")
    search_fields = ("title", "excerpt", "content")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("author",)


@admin.register(Comment)
class CommentAdmin(HiddenFromSidebarAdminMixin, admin.ModelAdmin):
    list_display = ("post", "user", "rating", "created_at")
    list_filter = ("rating", "created_at")


@admin.register(Question)
class QuestionAdmin(HiddenFromSidebarAdminMixin, admin.ModelAdmin):
    list_display = ("question_text", "author", "visible_to_all", "created_at")
    list_filter = ("visible_to_all", "created_at", "author")
    search_fields = ("question_text", "answer_text", "author__username")


@admin.register(PostApprovalLog)
class PostApprovalLogAdmin(HiddenFromSidebarAdminMixin, admin.ModelAdmin):
    list_display = ("post", "reviewer", "action", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("post__title", "reviewer__username", "feedback")
