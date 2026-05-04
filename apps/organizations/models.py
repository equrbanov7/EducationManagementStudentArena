"""
Models for the organizations app.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import pgettext, pgettext_lazy

from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.models import ActiveManager, OrderedModel, TimeStampedModel, UUIDModel

REVIEW_VISIBILITY_SETTINGS_KEY = "review_visibility"
WRITTEN_EXAM_IDENTITY_REVEAL_SETTINGS_KEY = "written_exam_identity_reveal_enabled"
ASSIGNMENT_IDENTITY_REVEAL_SETTINGS_KEY = "assignment_identity_reveal_enabled"
PROJECT_IDENTITY_REVEAL_SETTINGS_KEY = "project_identity_reveal_enabled"
LAB_IDENTITY_REVEAL_SETTINGS_KEY = "lab_identity_reveal_enabled"
REVIEW_VISIBILITY_FEATURES = {
    "written_exam": {
        "setting_key": WRITTEN_EXAM_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Yazılı imtahanda müəllimə tələbə adını göstər",
        "short_label": "Yazılı imtahan",
    },
    "assignment": {
        "setting_key": ASSIGNMENT_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Sərbəst işdə müəllimə tələbə adını göstər",
        "short_label": "Sərbəst iş",
    },
    "project": {
        "setting_key": PROJECT_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Kurs işində müəllimə tələbə adını göstər",
        "short_label": "Kurs işi",
    },
    "lab": {
        "setting_key": LAB_IDENTITY_REVEAL_SETTINGS_KEY,
        "label": "Lab işində müəllimə tələbə adını göstər",
        "short_label": "Lab işi",
    },
}


class Country(models.Model):
    """
    Country master data for signup institution filtering.
    """

    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Institution(models.Model):
    """
    Institution master data (school/university/course center) scoped by country.
    """

    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="institutions")
    institution_type = models.CharField(
        max_length=30,
        choices=[
            (OrganizationType.SCHOOL, pgettext_lazy("organizations.model.institution.choice", "school")),
            (OrganizationType.UNIVERSITY, pgettext_lazy("organizations.model.institution.choice", "university")),
            (
                OrganizationType.COURSE_CENTER,
                pgettext_lazy("organizations.model.institution.choice", "course_center"),
            ),
        ],
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=120, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("country", "institution_type", "name")]
        indexes = [
            models.Index(
                fields=["country", "institution_type", "is_active"],
                name="org_inst_country_type_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.country.code})"


class Organization(UUIDModel, TimeStampedModel):
    """
    Represents a top-level organization (university, school, course center, or individual).
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    org_type = models.CharField(max_length=50, choices=OrganizationType.CHOICES)
    country = models.CharField(max_length=100, blank=True, default="")
    organization_identifier = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=pgettext_lazy("organizations.model.organization.help", "organization_identifier"),
    )
    license_identifier = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=pgettext_lazy("organizations.model.organization.help", "license_identifier"),
    )
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
    status = models.CharField(
        max_length=20,
        choices=[
            ("active", pgettext_lazy("organizations.model.organization.choice.status", "active")),
            ("pending", pgettext_lazy("organizations.model.organization.choice.status", "pending")),
            ("suspended", pgettext_lazy("organizations.model.organization.choice.status", "suspended")),
        ],
        default="active",
    )
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True, default="")

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        ordering = ["name"]
        verbose_name = pgettext_lazy("organizations.model.organization.meta", "singular")
        verbose_name_plural = pgettext_lazy("organizations.model.organization.meta", "plural")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "organization"
            self.slug = base_slug
            suffix = 2
            while Organization.objects.exclude(pk=self.pk).filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{suffix}"
                suffix += 1
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("organizations:dashboard", kwargs={"slug": self.slug})

    @property
    def is_suspended(self):
        return self.status == "suspended" or not self.is_active

    def _review_visibility_settings(self):
        settings_payload = self.settings if isinstance(self.settings, dict) else {}
        review_settings = settings_payload.get(REVIEW_VISIBILITY_SETTINGS_KEY)
        if isinstance(review_settings, dict):
            return review_settings
        return {}

    def is_review_identity_reveal_enabled(self, feature_name: str) -> bool:
        feature_config = REVIEW_VISIBILITY_FEATURES.get(feature_name)
        if feature_config is None:
            return False

        return bool(
            self._review_visibility_settings().get(
                feature_config["setting_key"],
                False,
            )
        )

    def set_review_identity_reveal_enabled(self, feature_name: str, enabled: bool):
        feature_config = REVIEW_VISIBILITY_FEATURES.get(feature_name)
        if feature_config is None:
            raise ValueError(f"Unsupported review visibility feature: {feature_name}")

        settings_payload = dict(self.settings or {})
        review_settings = dict(self._review_visibility_settings())
        review_settings[feature_config["setting_key"]] = bool(enabled)
        settings_payload[REVIEW_VISIBILITY_SETTINGS_KEY] = review_settings
        self.settings = settings_payload

    @property
    def written_exam_identity_reveal_enabled(self):
        return self.is_review_identity_reveal_enabled("written_exam")

    def set_written_exam_identity_reveal_enabled(self, enabled: bool):
        self.set_review_identity_reveal_enabled("written_exam", enabled)

    @property
    def assignment_identity_reveal_enabled(self):
        return self.is_review_identity_reveal_enabled("assignment")

    def set_assignment_identity_reveal_enabled(self, enabled: bool):
        self.set_review_identity_reveal_enabled("assignment", enabled)

    @property
    def project_identity_reveal_enabled(self):
        return self.is_review_identity_reveal_enabled("project")

    def set_project_identity_reveal_enabled(self, enabled: bool):
        self.set_review_identity_reveal_enabled("project", enabled)

    @property
    def lab_identity_reveal_enabled(self):
        return self.is_review_identity_reveal_enabled("lab")

    def set_lab_identity_reveal_enabled(self, enabled: bool):
        self.set_review_identity_reveal_enabled("lab", enabled)


class OrgUnit(UUIDModel, TimeStampedModel, OrderedModel):
    """
    Represents a unit within an organization (faculty, department, class, etc.).
    Supports hierarchical structure with materialized path.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="units")
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
        verbose_name = pgettext_lazy("organizations.model.org_unit.meta", "singular")
        verbose_name_plural = pgettext_lazy("organizations.model.org_unit.meta", "plural")
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

        # Capture current DB path before updating (for descendant cascade)
        old_path = None
        if self.pk:
            old_path = OrgUnit.objects.filter(pk=self.pk).values_list("path", flat=True).first()

        # Calculate level and path, always fetching parent fresh from DB
        # to avoid using a stale cached instance.
        if self.parent_id:
            try:
                parent = OrgUnit.objects.get(pk=self.parent_id)
                self.level = parent.level + 1
                self.path = f"{parent.path}/{self.id}"
            except OrgUnit.DoesNotExist:
                self.parent_id = None
                self.level = 0
                self.path = str(self.id)
        else:
            self.level = 0
            self.path = str(self.id)

        super().save(*args, **kwargs)

        # If this unit's path changed, cascade the update to all descendants.
        if old_path is not None and old_path != self.path:
            self._cascade_path_update(old_path)

    def _cascade_path_update(self, old_path):
        """
        Bulk-update paths and levels for all descendants after this unit
        was reparented or its own path changed.
        """
        new_path = self.path
        descendants = list(
            OrgUnit.objects.filter(
                path__startswith=f"{old_path}/",
                organization=self.organization,
            )
            .order_by("level")
            .values("pk", "path")
        )
        if not descendants:
            return
        to_update = []
        for desc in descendants:
            new_desc_path = new_path + desc["path"][len(old_path) :]
            obj = OrgUnit(pk=desc["pk"])
            obj.path = new_desc_path
            obj.level = new_desc_path.count("/")
            to_update.append(obj)
        OrgUnit.objects.bulk_update(to_update, ["path", "level"])

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

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="academic_periods")
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
        verbose_name = pgettext_lazy("organizations.model.academic_period.meta", "singular")
        verbose_name_plural = pgettext_lazy("organizations.model.academic_period.meta", "plural")
        indexes = [
            models.Index(fields=["organization", "-start_date"]),
            models.Index(fields=["organization", "is_current"]),
        ]

    def __str__(self):
        return f"{self.organization.name} - {self.name} {self.academic_year}"

    def save(self, *args, **kwargs):
        # Auto-deactivate previous current period
        if self.is_current:
            AcademicPeriod.objects.filter(organization=self.organization, is_current=True).exclude(pk=self.pk).update(
                is_current=False
            )
        super().save(*args, **kwargs)

    def clean(self):
        """Validate that start_date is before end_date."""
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError(pgettext("organizations.model.academic_period.error", "start_before_end"))

            # Check for overlapping periods
            overlapping = AcademicPeriod.objects.filter(
                organization=self.organization,
                period_type=self.period_type,
            ).exclude(pk=self.pk)

            for period in overlapping:
                if self.start_date <= period.end_date and self.end_date >= period.start_date:
                    raise ValidationError(
                        pgettext("organizations.model.academic_period.error", "overlaps_existing").format(
                            period_name=period.name
                        )
                    )


class Role(UUIDModel, TimeStampedModel):
    """
    Represents a role within an organization with associated permissions.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="roles")
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
        verbose_name = pgettext_lazy("organizations.model.role.meta", "singular")
        verbose_name_plural = pgettext_lazy("organizations.model.role.meta", "plural")
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
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
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
        verbose_name = pgettext_lazy("organizations.model.membership.meta", "singular")
        verbose_name_plural = pgettext_lazy("organizations.model.membership.meta", "plural")
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
            Membership.objects.filter(user=self.user, organization=self.organization, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)
        super().save(*args, **kwargs)

    def clean(self):
        """Validate scope_unit belongs to the same organization."""
        from django.core.exceptions import ValidationError

        if self.scope_unit and self.scope_unit.organization != self.organization:
            raise ValidationError(pgettext("organizations.model.membership.error", "scope_unit_must_match_org"))

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
