"""Ledger authorizer and target validators bound to the platform's RBAC.

Models are resolved through ``django.apps`` rather than deep imports so the
module-boundary graph gains no new edge for the rehearsal orchestrator.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from django.apps import apps as django_apps

from core.permissions import has_permission, is_superadmin_user

from .ledger import LedgerAction, LedgerAuthorizer, TargetValidation, TargetValidator, TargetValidatorRegistry

LEDGER_PERMISSION = "member.invite"  # the gate identity_access._assert_tenant_permission uses
# Every label is lower-case app_label.model_name so it satisfies
# ``models.MODEL_LABEL_PATTERN``; the ledger stores the label verbatim.
USER_MODEL_LABEL = "auth.user"  # settings.AUTH_USER_MODEL default; matches MODEL_LABEL_PATTERN
ORG_UNIT_MODEL_LABEL = "organizations.orgunit"
ACADEMIC_PERIOD_MODEL_LABEL = "organizations.academicperiod"
PROGRAM_MODEL_LABEL = "registrar.program"
SUBJECT_MODEL_LABEL = "registrar.subject"
CURRICULUM_MODEL_LABEL = "registrar.curriculum"
CURRICULUM_SUBJECT_MODEL_LABEL = "registrar.curriculumsubject"
STUDENT_RECORD_MODEL_LABEL = "registrar.studentacademicrecord"
COURSE_OFFERING_MODEL_LABEL = "registrar.courseoffering"
ENROLLMENT_MODEL_LABEL = "registrar.enrollment"
LESSON_MODEL_LABEL = "registrar.lesson"
# J7 (journal_lock) hədəfi: kilid qərarı məhz sxemin üzərində yaşayır
# (``approval_status`` + ``is_published`` CheckConstraint cütü).
ASSESSMENT_SCHEME_MODEL_LABEL = "registrar.assessmentscheme"
LEGACY_GRADE_FACT_MODEL_LABEL = "registrar.legacygradefact"
LEGACY_GRADE_ARTIFACT_MODEL_LABEL = "registrar.legacygradeartifact"
# J10 (legacy_rooms) hədəfi.  ``registrar.Lesson.room`` FK-sı (miqrasiya 0051)
# məhz bu modelə baxır — təşkilatın yeganə otaq reyestri odur.  Model burada da
# ``django.apps`` ilə həll olunur, yəni ``legacy_import → exams`` idxal tili
# yaranmır.
EXAM_ROOM_MODEL_LABEL = "exams.examroom"


def build_rehearsal_authorizer() -> LedgerAuthorizer:
    """Return a strict True/False authorizer for every ledger write."""

    def authorize(*, actor: Any, organization: Any, action: LedgerAction) -> bool:
        if not isinstance(action, LedgerAction):
            return False
        if organization is None or getattr(organization, "pk", None) is None:
            return False
        if not getattr(actor, "is_active", False) or getattr(actor, "pk", None) is None:
            return False
        if is_superadmin_user(actor):
            return True
        membership_model = django_apps.get_model("organizations", "Membership")
        permissions = {
            item
            for membership in membership_model.objects.filter(
                user=actor,
                organization=organization,
                is_active=True,
                role__is_active=True,
            ).select_related("role")
            for item in (membership.role.permissions or [])
        }
        return has_permission(list(permissions), LEDGER_PERMISSION)

    return authorize


def _tenant_owned_validator(app_label: str, model_name: str) -> TargetValidator:
    """Validator for a target that carries its own ``organization`` column.

    A malformed primary key makes ``.filter()`` raise, which
    ``ledger._target_validation`` converts into ``legacy_target_validation_failed``
    — fail closed by design, never a silent "not found".
    """

    def validate(*, target_pk: str, organization: Any) -> TargetValidation:
        model = django_apps.get_model(app_label, model_name)
        row = model._default_manager.filter(pk=target_pk).values("organization_id").first()
        return TargetValidation(
            exists=row is not None,
            organization_matches=row is not None and str(row["organization_id"]) == str(organization.pk),
        )

    return validate


def _tenant_owned_bulk_validator(app_label: str, model_name: str):
    """Toplu variant: bir sorğu ilə "mövcud VƏ bu tenantındır" açarlar dəsti.

    Sətir-başına validator ilə EYNİ şərti yoxlayır (``organization_id`` bərabərliyi),
    sadəcə ``pk__in`` ilə — 2000 hədəf üçün 2000 sorğu yerinə BİRİ.  Pozuq açar
    ``.filter()``-i çökdürürsə ``ledger_batch`` onu ``legacy_target_validation_failed``
    kimi tərcümə edir (fail closed, səssiz "tapılmadı" yox).
    """

    def validate_bulk(*, target_pks, organization) -> set[str]:
        model = django_apps.get_model(app_label, model_name)
        rows = model._default_manager.filter(pk__in=list(target_pks), organization=organization).values_list(
            "pk", flat=True
        )
        return {str(pk) for pk in rows}

    return validate_bulk


def build_bulk_target_validators():
    """``ledger_batch.seal_entity_maps`` üçün etiket → toplu validator.

    Yalnız jurnal fazalarının yazdığı hədəflər buradadır; qeydə alınmamış etiket
    üçün ``ledger_batch`` avtomatik olaraq sətir-başına validatora qayıdır.
    """

    return MappingProxyType(
        {
            COURSE_OFFERING_MODEL_LABEL: _tenant_owned_bulk_validator("registrar", "CourseOffering"),
            ENROLLMENT_MODEL_LABEL: _tenant_owned_bulk_validator("registrar", "Enrollment"),
            LESSON_MODEL_LABEL: _tenant_owned_bulk_validator("registrar", "Lesson"),
            ASSESSMENT_SCHEME_MODEL_LABEL: _tenant_owned_bulk_validator("registrar", "AssessmentScheme"),
            LEGACY_GRADE_FACT_MODEL_LABEL: _tenant_owned_bulk_validator("registrar", "LegacyGradeFact"),
            LEGACY_GRADE_ARTIFACT_MODEL_LABEL: _tenant_owned_bulk_validator("registrar", "LegacyGradeArtifact"),
            EXAM_ROOM_MODEL_LABEL: _tenant_owned_bulk_validator("exams", "ExamRoom"),
        }
    )


def build_target_validators() -> TargetValidatorRegistry:
    """Return the allowlisted target models and their tenant validators."""

    def validate_user(*, target_pk: str, organization: Any) -> TargetValidation:
        user_model = django_apps.get_model("auth", "User")
        profile_model = django_apps.get_model("accounts", "UserProfile")
        membership_model = django_apps.get_model("organizations", "Membership")
        exists = user_model._default_manager.filter(pk=target_pk).exists()
        owned = (
            profile_model.objects.filter(user_id=target_pk, organization=organization).exists()
            or membership_model.objects.filter(user_id=target_pk, organization=organization).exists()
        )
        return TargetValidation(exists=exists, organization_matches=owned)

    return MappingProxyType(
        {
            USER_MODEL_LABEL: validate_user,
            ORG_UNIT_MODEL_LABEL: _tenant_owned_validator("organizations", "OrgUnit"),
            ACADEMIC_PERIOD_MODEL_LABEL: _tenant_owned_validator("organizations", "AcademicPeriod"),
            PROGRAM_MODEL_LABEL: _tenant_owned_validator("registrar", "Program"),
            SUBJECT_MODEL_LABEL: _tenant_owned_validator("registrar", "Subject"),
            CURRICULUM_MODEL_LABEL: _tenant_owned_validator("registrar", "Curriculum"),
            CURRICULUM_SUBJECT_MODEL_LABEL: _tenant_owned_validator("registrar", "CurriculumSubject"),
            STUDENT_RECORD_MODEL_LABEL: _tenant_owned_validator("registrar", "StudentAcademicRecord"),
            COURSE_OFFERING_MODEL_LABEL: _tenant_owned_validator("registrar", "CourseOffering"),
            ENROLLMENT_MODEL_LABEL: _tenant_owned_validator("registrar", "Enrollment"),
            LESSON_MODEL_LABEL: _tenant_owned_validator("registrar", "Lesson"),
            ASSESSMENT_SCHEME_MODEL_LABEL: _tenant_owned_validator("registrar", "AssessmentScheme"),
            LEGACY_GRADE_FACT_MODEL_LABEL: _tenant_owned_validator("registrar", "LegacyGradeFact"),
            LEGACY_GRADE_ARTIFACT_MODEL_LABEL: _tenant_owned_validator("registrar", "LegacyGradeArtifact"),
            EXAM_ROOM_MODEL_LABEL: _tenant_owned_validator("exams", "ExamRoom"),
        }
    )
