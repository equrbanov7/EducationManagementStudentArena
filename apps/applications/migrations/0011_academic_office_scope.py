"""Dekanlıq və koordinator eyni proqramın məktəb/proqram rəhbərlərinə açılır."""
from django.db import migrations, models


OFFICE_ROLES = ["dean", "vice_dean", "program_coordinator", "tutor"]


def bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")


def ancestor(Unit, organization_id, unit_id, unit_type):
    seen = set()
    while unit_id and unit_id not in seen:
        seen.add(unit_id)
        unit = Unit.objects.filter(pk=unit_id, organization_id=organization_id).first()
        if unit is None:
            break
        if unit.unit_type == unit_type:
            return unit.pk
        unit_id = unit.parent_id
    return None


def applicant_scope(apps, application, Unit):
    source_id = application.sender_scope_unit_id
    if application.sender_family == "student":
        Record = apps.get_model("registrar", "StudentAcademicRecord")
        record = (Record.objects.filter(organization_id=application.organization_id, student_id=application.created_by_id, is_active=True, program__organization_id=application.organization_id)
                  .order_by("-created_at").values("program__specialty_unit_id", "group_id").first())
        if record:
            source_id = record["program__specialty_unit_id"] or record["group_id"] or source_id
    return ancestor(Unit, application.organization_id, source_id, "specialty") or ancestor(Unit, application.organization_id, source_id, "faculty")


def seed(apps, schema_editor):
    bypass(schema_editor)
    Catalog = apps.get_model("applications", "ApplicationUnit")
    Application = apps.get_model("applications", "Application")
    Watch = apps.get_model("applications", "ApplicationWatch")
    Unit = apps.get_model("organizations", "OrgUnit")
    for catalog in Catalog.objects.filter(code__in=["dekan", "koordinator"]):
        Catalog.objects.filter(pk=catalog.pk).update(
            handler_role_names=list(dict.fromkeys(list(catalog.handler_role_names or []) + OFFICE_ROLES)),
            resolve_by="specialty", requires_scope=True,
        )
        for application in Application.objects.filter(current_unit=catalog).iterator():
            scope = applicant_scope(apps, application, Unit)
            if scope is not None:
                Application.objects.filter(pk=application.pk).update(current_scope_unit_id=scope)
        for watch in Watch.objects.filter(unit=catalog).select_related("application").iterator():
            scope = applicant_scope(apps, watch.application, Unit)
            if scope is not None:
                Watch.objects.filter(pk=watch.pk).update(scope_unit_id=scope)
    Catalog.objects.filter(code="kafedra").update(requires_scope=True)


def unseed(apps, schema_editor):
    bypass(schema_editor)
    Catalog = apps.get_model("applications", "ApplicationUnit")
    Application = apps.get_model("applications", "Application")
    Watch = apps.get_model("applications", "ApplicationWatch")
    Unit = apps.get_model("organizations", "OrgUnit")
    for catalog in Catalog.objects.filter(code__in=["dekan", "koordinator"]):
        removed = {"vice_dean", "program_coordinator", "tutor"} if catalog.code == "dekan" else {"dean", "vice_dean"}
        Catalog.objects.filter(pk=catalog.pk).update(handler_role_names=[r for r in catalog.handler_role_names or [] if r not in removed], resolve_by="faculty" if catalog.code == "dekan" else "specialty", requires_scope=False)
        if catalog.code == "dekan":
            for application in Application.objects.filter(current_unit=catalog).iterator():
                scope = ancestor(Unit, application.organization_id, application.sender_scope_unit_id, "faculty")
                Application.objects.filter(pk=application.pk).update(current_scope_unit_id=scope)
            for watch in Watch.objects.filter(unit=catalog).select_related("application").iterator():
                scope = ancestor(Unit, watch.organization_id, watch.application.sender_scope_unit_id, "faculty")
                Watch.objects.filter(pk=watch.pk).update(scope_unit_id=scope)
    Catalog.objects.filter(code="kafedra").update(requires_scope=False)


class Migration(migrations.Migration):
    dependencies = [("applications", "0010_content_revision_soft_delete"), ("organizations", "0076_vice_dean_application_handle"), ("registrar", "0107_offering_seminar_is_practical")]
    operations = [migrations.AddField("applicationunit", "requires_scope", models.BooleanField(default=False)), migrations.RunPython(seed, unseed)]
