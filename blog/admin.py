from django.contrib import admin

from .models import Category, Comment, Post, Question


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
