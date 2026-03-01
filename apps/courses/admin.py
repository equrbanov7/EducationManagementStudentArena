"""
courses/admin.py
────────────────
Django admin panel-də kursları idarəetmə.

Nə üçün:
- Admin müəllim olmadan DB-ə əl ile data daxil edə bilər
- Testləşdirmə zamanı test data yaratmaq üçün rahat
- Kurs, mövzu, resurs siliş/redaksiya işləmləri
"""

from django.contrib import admin

from .models import Course, CourseGroup, CourseInstructor, CourseMembership, CourseResource, CourseTopic

# ════════════════════════════════════════════════════════════════════════════
# COURSE ADMIN
# ════════════════════════════════════════════════════════════════════════════


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """
    Kurs admin paneli.

    Neyi göstər: title, owner, status, mövzu sayı, tələbə sayı
    Neyi filter et: status, yaradılma tarixi
    Neyi aç: slug (əl ilə dəyişdirmə lazım deyil)
    """

    list_display = (
        "title",
        "owner",
        "status",
        "topic_count",
        "student_count",
        "created_at",
    )

    list_filter = ("status", "created_at", "owner")

    search_fields = ("title", "owner__username", "description")

    readonly_fields = ("slug", "created_at", "updated_at")

    fieldsets = (
        (
            "Əsas Məlumat",
            {
                "fields": ("title", "owner", "description"),
            },
        ),
        (
            "Görünüş",
            {
                "fields": ("status", "cover_image"),
            },
        ),
        (
            "URL",
            {
                "fields": ("slug",),
                "classes": ("collapse",),
            },
        ),
        (
            "Vaxt Məlumatı",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def topic_count(self, obj):
        """Mövzu sayı göstər."""
        count = obj.topic_count
        return f"{count} mövzu"

    topic_count.short_description = "Mövzular"

    def student_count(self, obj):
        """Tələbə sayı göstər."""
        count = obj.student_count
        return f"{count} tələbə"

    student_count.short_description = "Tələbələr"


# ════════════════════════════════════════════════════════════════════════════
# COURSE MEMBERSHIP ADMIN (Inline)
# ════════════════════════════════════════════════════════════════════════════


class CourseMembershipInline(admin.TabularInline):
    """
    Kurs üzvlərini inline (eyni səhifədə) redaktə et.

    Misal: Kurs səhifəsində tələbə əlavə et.
    """

    model = CourseMembership
    extra = 1
    fields = ("user", "role", "group_name", "joined_at")
    readonly_fields = ("joined_at",)
    raw_id_fields = ("user",)


# ════════════════════════════════════════════════════════════════════════════
# COURSE TOPIC ADMIN (Nested)
# ════════════════════════════════════════════════════════════════════════════


class CourseTopicInline(admin.TabularInline):
    """
    Mövzuları inline redaktə et.
    """

    model = CourseTopic
    extra = 1
    fields = ("title", "order", "created_at")
    readonly_fields = ("created_at",)


@admin.register(CourseTopic)
class CourseTopicAdmin(admin.ModelAdmin):
    """
    Mövzu admin paneli.
    """

    list_display = ("title", "course", "order", "created_at")
    list_filter = ("course", "created_at")
    search_fields = ("title", "course__title")
    ordering = ("course", "order")

    fieldsets = (
        (
            "Əsas Məlumat",
            {
                "fields": ("course", "title", "order"),
            },
        ),
        (
            "Açıqlama",
            {
                "fields": ("description",),
            },
        ),
    )


# ════════════════════════════════════════════════════════════════════════════
# COURSE RESOURCE ADMIN
# ════════════════════════════════════════════════════════════════════════════


@admin.register(CourseResource)
class CourseResourceAdmin(admin.ModelAdmin):
    """
    Resurs admin paneli.
    """

    list_display = (
        "title",
        "course",
        "topic",
        "resource_type",
        "is_file_or_link",
        "created_at",
    )

    list_filter = ("resource_type", "course", "topic", "created_at")

    search_fields = ("title", "description", "course__title")

    fieldsets = (
        (
            "Əsas Məlumat",
            {
                "fields": ("course", "topic", "title", "description"),
            },
        ),
        (
            "Resurs Tipi",
            {
                "fields": ("resource_type", "file", "url"),
            },
        ),
    )

    def is_file_or_link(self, obj):
        """Fayl yoxsa link?"""
        if obj.file:
            return f"📄 Fayl ({obj.file.name.split('/')[-1]})"
        elif obj.url:
            return "🔗 Link"
        return "⚠️ Boş"

    is_file_or_link.short_description = "Tür"


# ════════════════════════════════════════════════════════════════════════════
# COURSE MEMBERSHIP ADMIN (Standalone)
# ════════════════════════════════════════════════════════════════════════════


@admin.register(CourseMembership)
class CourseMembershipAdmin(admin.ModelAdmin):
    """
    Kurs üzvlüyü admin paneli.
    """

    list_display = ("user", "course", "role", "group_name", "joined_at")
    list_filter = ("role", "course", "joined_at")
    search_fields = ("user__username", "course__title", "group_name")

    fieldsets = (
        (
            "Əlaqə",
            {
                "fields": ("course", "user"),
            },
        ),
        (
            "Rol və Qrup",
            {
                "fields": ("role", "group_name"),
            },
        ),
        (
            "Tarix",
            {
                "fields": ("joined_at",),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("joined_at",)


# ════════════════════════════════════════════════════════════════════════════
# COURSE INSTRUCTOR ADMIN (Sprint 7)
# ════════════════════════════════════════════════════════════════════════════


@admin.register(CourseInstructor)
class CourseInstructorAdmin(admin.ModelAdmin):
    """
    Kurs müəllimləri admin paneli.
    """

    list_display = ("user", "course", "role", "created_at")
    list_filter = ("role", "course", "created_at")
    search_fields = ("user__username", "course__title")

    fieldsets = (
        (
            "Əsas Məlumat",
            {
                "fields": ("course", "user", "role"),
            },
        ),
        (
            "Səlahiyyətlər",
            {
                "fields": ("permissions",),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("created_at",)


# ════════════════════════════════════════════════════════════════════════════
# COURSE GROUP ADMIN (Sprint 7)
# ════════════════════════════════════════════════════════════════════════════


@admin.register(CourseGroup)
class CourseGroupAdmin(admin.ModelAdmin):
    """
    Kurs qrupları admin paneli.
    """

    list_display = (
        "name",
        "course",
        "instructor",
        "student_count_display",
        "max_students",
        "created_at",
    )
    list_filter = ("course", "instructor", "created_at")
    search_fields = ("name", "course__title", "instructor__username")

    fieldsets = (
        (
            "Əsas Məlumat",
            {
                "fields": ("course", "name", "instructor", "max_students"),
            },
        ),
        (
            "Cədvəl",
            {
                "fields": ("schedule",),
                "classes": ("collapse",),
            },
        ),
        (
            "Üzvlər",
            {
                "fields": ("members",),
            },
        ),
    )

    filter_horizontal = ("members",)
    readonly_fields = ("created_at",)

    def student_count_display(self, obj):
        """Tələbə sayı göstər."""
        return f"{obj.student_count} / {obj.max_students}"

    student_count_display.short_description = "Tələbə Sayı"
