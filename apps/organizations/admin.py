"""
Admin configuration for the organizations app.
"""

from django.contrib import admin

from .models import AcademicPeriod, Country, Institution, Membership, Organization, OrgUnit, Role


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ["name", "institution_type", "country", "code", "is_active"]
    list_filter = ["institution_type", "country", "is_active"]
    search_fields = ["name", "code", "country__name", "country__code"]


class OrgUnitInline(admin.TabularInline):
    """Inline admin for OrgUnit under Organization."""

    model = OrgUnit
    extra = 0
    fields = ["name", "unit_type", "parent", "code", "head", "is_active"]
    raw_id_fields = ["parent", "head"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for Organization model."""

    list_display = [
        "name",
        "org_type",
        "status",
        "owner",
        "is_active",
        "created_at",
    ]
    list_filter = ["org_type", "status", "is_active", "created_at"]
    search_fields = ["name", "slug", "description", "email"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = [
        (
            "Basic Information",
            {
                "fields": [
                    "name",
                    "slug",
                    "org_type",
                    "status",
                    "owner",
                    "country",
                    "organization_identifier",
                    "license_identifier",
                    "logo",
                    "description",
                ]
            },
        ),
        (
            "Contact Information",
            {"fields": ["email", "phone", "address", "website"]},
        ),
        (
            "Configuration",
            {"fields": ["enabled_apps", "settings", "is_active", "suspended_at", "suspension_reason"]},
        ),
        ("Metadata", {"fields": ["id", "created_at", "updated_at"]}),
    ]
    inlines = [OrgUnitInline]
    actions = ["activate", "deactivate"]

    def activate(self, request, queryset):
        """Activate selected organizations."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} organization(s) activated.")

    activate.short_description = "Activate selected organizations"

    def deactivate(self, request, queryset):
        """Deactivate selected organizations."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} organization(s) deactivated.")

    deactivate.short_description = "Deactivate selected organizations"


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    """Admin interface for OrgUnit model with tree display."""

    list_display = [
        "name",
        "organization",
        "unit_type",
        "parent",
        "level",
        "head",
        "is_active",
    ]
    list_filter = ["organization", "unit_type", "is_active", "level"]
    search_fields = ["name", "slug", "code"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "level", "path", "created_at", "updated_at"]
    raw_id_fields = ["parent", "head"]
    fieldsets = [
        (
            "Basic Information",
            {
                "fields": [
                    "organization",
                    "parent",
                    "unit_type",
                    "name",
                    "slug",
                    "code",
                ]
            },
        ),
        ("Leadership", {"fields": ["head"]}),
        ("Hierarchy", {"fields": ["level", "path", "order"]}),
        ("Configuration", {"fields": ["settings", "is_active"]}),
        ("Metadata", {"fields": ["id", "created_at", "updated_at"]}),
    ]
    actions = ["activate", "deactivate"]

    def activate(self, request, queryset):
        """Activate selected units."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} unit(s) activated.")

    activate.short_description = "Activate selected units"

    def deactivate(self, request, queryset):
        """Deactivate selected units."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} unit(s) deactivated.")

    deactivate.short_description = "Deactivate selected units"


@admin.register(AcademicPeriod)
class AcademicPeriodAdmin(admin.ModelAdmin):
    """Admin interface for AcademicPeriod model."""

    list_display = [
        "name",
        "organization",
        "period_type",
        "academic_year",
        "start_date",
        "end_date",
        "is_current",
        "is_active",
    ]
    list_filter = ["organization", "period_type", "is_current", "is_active"]
    search_fields = ["name", "academic_year"]
    readonly_fields = ["id", "created_at", "updated_at"]
    date_hierarchy = "start_date"
    fieldsets = [
        (
            "Basic Information",
            {
                "fields": [
                    "organization",
                    "name",
                    "period_type",
                    "academic_year",
                ]
            },
        ),
        ("Dates", {"fields": ["start_date", "end_date"]}),
        ("Status", {"fields": ["is_current", "is_active"]}),
        ("Metadata", {"fields": ["id", "created_at", "updated_at"]}),
    ]
    actions = ["set_current", "activate", "deactivate"]

    def set_current(self, request, queryset):
        """Set selected period as current."""
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one period.", level="error")
            return

        period = queryset.first()
        AcademicPeriod.objects.filter(organization=period.organization, is_current=True).update(is_current=False)
        period.is_current = True
        period.save()
        self.message_user(request, f"{period.name} set as current period.")

    set_current.short_description = "Set as current period"

    def activate(self, request, queryset):
        """Activate selected periods."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} period(s) activated.")

    activate.short_description = "Activate selected periods"

    def deactivate(self, request, queryset):
        """Deactivate selected periods."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} period(s) deactivated.")

    deactivate.short_description = "Deactivate selected periods"


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin interface for Role model."""

    list_display = [
        "display_name",
        "name",
        "organization",
        "level",
        "scope_type",
        "is_system",
        "is_active",
    ]
    list_filter = ["organization", "scope_type", "is_system", "is_active", "level"]
    search_fields = ["name", "display_name", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = [
        (
            "Basic Information",
            {
                "fields": [
                    "organization",
                    "name",
                    "display_name",
                    "description",
                ]
            },
        ),
        ("Configuration", {"fields": ["level", "scope_type", "permissions"]}),
        ("Status", {"fields": ["is_system", "is_active"]}),
        ("Metadata", {"fields": ["id", "created_at", "updated_at"]}),
    ]
    actions = ["activate", "deactivate"]

    def activate(self, request, queryset):
        """Activate selected roles."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} role(s) activated.")

    activate.short_description = "Activate selected roles"

    def deactivate(self, request, queryset):
        """Deactivate selected roles."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} role(s) deactivated.")

    deactivate.short_description = "Deactivate selected roles"


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    """Admin interface for Membership model."""

    list_display = [
        "user",
        "organization",
        "role",
        "scope_unit",
        "is_primary",
        "is_active",
    ]
    list_filter = ["organization", "role", "is_primary", "is_active"]
    search_fields = [
        "user__username",
        "user__email",
        "title",
        "employee_id",
    ]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["user", "scope_unit", "assigned_by"]
    fieldsets = [
        (
            "Basic Information",
            {
                "fields": [
                    "user",
                    "organization",
                    "role",
                    "scope_unit",
                ]
            },
        ),
        ("Additional Info", {"fields": ["title", "employee_id", "assigned_by"]}),
        ("Status", {"fields": ["is_primary", "is_active"]}),
        ("Metadata", {"fields": ["id", "created_at", "updated_at"]}),
    ]
    actions = ["activate", "deactivate", "set_primary"]

    def activate(self, request, queryset):
        """Activate selected memberships."""
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} membership(s) activated.")

    activate.short_description = "Activate selected memberships"

    def deactivate(self, request, queryset):
        """Deactivate selected memberships."""
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} membership(s) deactivated.")

    deactivate.short_description = "Deactivate selected memberships"

    def set_primary(self, request, queryset):
        """Set selected membership as primary."""
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one membership.", level="error")
            return

        membership = queryset.first()
        Membership.objects.filter(
            user=membership.user,
            organization=membership.organization,
            is_primary=True,
        ).update(is_primary=False)
        membership.is_primary = True
        membership.save()
        self.message_user(request, "Membership set as primary.")

    set_primary.short_description = "Set as primary membership"
