from django.contrib import admin
from django import forms

from .models import Category, Comment, Post, PostApprovalLog, Question
from .services import can_user_manage_categories


class HiddenFromSidebarAdminMixin:
    """
    Keep models registered but hide Blog app from Django admin sidebar.
    """

    def has_module_permission(self, request):
        return False


class SuperadminOnlyAdminMixin:
    @staticmethod
    def _can_manage(request):
        return can_user_manage_categories(getattr(request, "user", None))

    def has_module_permission(self, request):
        return self._can_manage(request)

    def has_view_permission(self, request, obj=None):
        return self._can_manage(request)

    def has_add_permission(self, request):
        return self._can_manage(request)

    def has_change_permission(self, request, obj=None):
        return self._can_manage(request)

    def has_delete_permission(self, request, obj=None):
        return self._can_manage(request)


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "parent",
            "slug",
            "name_az",
            "name_en",
            "name_ru",
            "name_tr",
            "sort_order",
            "show_in_navbar",
            "is_default",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(parent__isnull=True).order_by("sort_order", "name_en", "name_az")
        for field_name in ("name_az", "name_en", "name_ru", "name_tr"):
            self.fields[field_name].required = True

        if self.instance.pk:
            invalid_parent_ids = {self.instance.pk, *self.instance.get_descendant_ids(include_self=False)}
            self.fields["parent"].queryset = self.fields["parent"].queryset.exclude(pk__in=invalid_parent_ids)


@admin.register(Category)
class CategoryAdmin(SuperadminOnlyAdminMixin, admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = ("name_en", "name_az", "parent", "show_in_navbar", "is_default", "sort_order", "slug")
    list_filter = ("show_in_navbar", "is_default", "parent")
    search_fields = ("name", "name_az", "name_en", "name_ru", "name_tr", "slug", "parent__name_en", "parent__name_az")
    list_editable = ("show_in_navbar", "is_default", "sort_order")
    autocomplete_fields = ("parent",)
    fieldsets = (
        (
            "Hierarchy",
            {
                "fields": ("parent", "slug", "sort_order"),
            },
        ),
        (
            "Translations",
            {
                "fields": ("name_az", "name_en", "name_ru", "name_tr"),
            },
        ),
        (
            "Visibility",
            {
                "fields": ("show_in_navbar", "is_default"),
            },
        ),
    )


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
