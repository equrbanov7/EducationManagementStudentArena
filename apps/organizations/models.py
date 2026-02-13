"""
Models for the organizations app.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from core.constants import (AcademicPeriodType, OrganizationType, OrgUnitType,
                            RoleScopeType)
from core.models import (ActiveManager, OrderedModel, TimeStampedModel,
                         UUIDModel)


class Organization(UUIDModel, TimeStampedModel):
    """
    Represents a top-level organization (university, school, course center, or individual).
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    org_type = models.CharField(max_length=50, choices=OrganizationType.CHOICES)
    logo = models.ImageField(upload_to="org_logos/", null=True, blank=True)
    description = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_organizations",
    )
    enabled_apps = models.JSONField(default=list, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("organizations:detail", kwargs={"slug": self.slug})


class OrgUnit(UUIDModel, TimeStampedModel, OrderedModel):
    """
    Represents a unit within an organization (faculty, department, class, etc.).
    Supports hierarchical structure with materialized path.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="units"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    unit_type = models.CharField(max_length=50, choices=OrgUnitType.ALL_CHOICES)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_units",
    )
    settings = models.JSONField(default=dict, blank=True)
    level = models.PositiveIntegerField(default=0, db_index=True)
    path = models.CharField(max_length=1000, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["organization", "path", "order"]
        unique_together = [["organization", "slug"]]
        verbose_name = "Organizational Unit"
        verbose_name_plural = "Organizational Units"
        indexes = [
            models.Index(fields=["organization", "unit_type"]),
            models.Index(fields=["organization", "parent"]),
        ]

    def __str__(self):
        return f"{self.organization.name} - {self.name}"

    def save(self, *args, **kwargs):
        # Auto-generate slug if not provided
        if not self.slug:
            self.slug = slugify(self.name)

        # Calculate level and path
        if self.parent:
            self.level = self.parent.level + 1
            self.path = f"{self.parent.path}/{self.id}"
        else:
            self.level = 0
            self.path = str(self.id)

        super().save(*args, **kwargs)

    def get_ancestors(self):
        """Get all ancestor units."""
        if not self.parent:
            return OrgUnit.objects.none()

        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors

    def get_descendants(self):
        """Get all descendant units."""
        return OrgUnit.objects.filter(path__startswith=f"{self.path}/")

    def get_children(self):
        """Get direct children units."""
        return self.children.all()

    def get_full_path(self):
        """Get full path as list of unit names."""
        ancestors = self.get_ancestors()
        return " > ".join([a.name for a in reversed(ancestors)] + [self.name])

    def get_depth(self):
        """Get depth in hierarchy."""
        return self.level


class AcademicPeriod(UUIDModel, TimeStampedModel):
    """
    Represents an academic period (semester, trimester, quarter, year).
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="academic_periods"
    )
    name = models.CharField(max_length=100)
    period_type = models.CharField(max_length=20, choices=AcademicPeriodType.CHOICES)
    academic_year = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["-start_date"]
        unique_together = [["organization", "name", "academic_year"]]
        verbose_name = "Academic Period"
        verbose_name_plural = "Academic Periods"
        indexes = [
            models.Index(fields=["organization", "-start_date"]),
            models.Index(fields=["organization", "is_current"]),
        ]

    def __str__(self):
        return f"{self.organization.name} - {self.name} {self.academic_year}"

    def save(self, *args, **kwargs):
        # Auto-deactivate previous current period
        if self.is_current:
            AcademicPeriod.objects.filter(
                organization=self.organization, is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def clean(self):
        """Validate that start_date is before end_date."""
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError("Start date must be before end date.")

            # Check for overlapping periods
            overlapping = AcademicPeriod.objects.filter(
                organization=self.organization,
                period_type=self.period_type,
            ).exclude(pk=self.pk)

            for period in overlapping:
                if (
                    self.start_date <= period.end_date
                    and self.end_date >= period.start_date
                ):
                    raise ValidationError(
                        f"This period overlaps with existing period: {period.name}"
                    )


class Role(UUIDModel, TimeStampedModel):
    """
    Represents a role within an organization with associated permissions.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="roles"
    )
    name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    level = models.PositiveIntegerField(default=50, db_index=True)
    scope_type = models.CharField(max_length=50, choices=RoleScopeType.CHOICES)
    permissions = models.JSONField(default=list, blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["-level", "name"]
        unique_together = [["organization", "name"]]
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        indexes = [
            models.Index(fields=["organization", "-level"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return f"{self.organization.name} - {self.display_name}"


class Membership(UUIDModel, TimeStampedModel):
    """
    Represents a user's membership in an organization with a specific role.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="memberships")
    scope_unit = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    title = models.CharField(max_length=100, blank=True)
    employee_id = models.CharField(max_length=50, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_memberships",
    )
    is_primary = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["-is_primary", "role__level"]
        unique_together = [["user", "organization", "role", "scope_unit"]]
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"
        indexes = [
            models.Index(fields=["user", "organization"]),
            models.Index(fields=["organization", "role"]),
            models.Index(fields=["user", "is_primary"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.role.display_name} @ {self.organization.name}"

    def save(self, *args, **kwargs):
        # Ensure only one primary membership per user per organization
        if self.is_primary:
            Membership.objects.filter(
                user=self.user, organization=self.organization, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

    def clean(self):
        """Validate scope_unit belongs to the same organization."""
        from django.core.exceptions import ValidationError

        if self.scope_unit and self.scope_unit.organization != self.organization:
            raise ValidationError(
                "Scope unit must belong to the same organization as the membership."
            )

    def can_manage(self, target_membership):
        """Check if this membership can manage another membership."""
        if not self.is_active:
            return False

        # Must be in same organization
        if self.organization != target_membership.organization:
            return False

        # Must have higher level
        if self.role.level <= target_membership.role.level:
            return False

        return True
