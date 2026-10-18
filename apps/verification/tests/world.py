"""Sənəd yoxlaması testləri üçün kiçik «universitet».

Struktur: Fakültə F1 → Qrup G1 (tələbə «Elvin Qurbanov», akademik qeyd + bir fənn nəticəsi);
Fakültə F2 → Qrup G2 (tələbə s2). Üzvlər: sahib (org-wide, transkript buraxır), Tədris şöbəsi əməkdaşı
(``teaching_office_staff`` — şablondan ``document_seal.manage``), açarsız müəllim, F1-ə bağlı vahid rolu
(``document_seal.manage`` əl ilə verilib). İkinci təşkilat B — öz sahibi və tələbəsi ilə (tenant izolyasiyası).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import finals, services
from apps.registrar.models import Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
PW = "DocVerifyPass123!"


def _member(org, username, role, *, unit=None, first="Ad", last=None):
    user = User.objects.create_user(
        username, f"{username}@qku.edu.az", PW, first_name=first, last_name=last or username
    )
    Membership.objects.create(
        user=user,
        organization=org,
        role=role if isinstance(role, Role) else org.roles.get(name=role),
        scope_unit=unit,
        is_primary=True,
        is_active=True,
    )
    return user


def _org(slug, owner):
    return Organization.objects.create(
        name="Qərbi Kaspi Universiteti" if slug.startswith("qku") else f"{slug} Univ",
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


def _student_with_record(org, *, username, first, last, group, program, curriculum, period, subject, teacher, score):
    student = _member(org, username, "student", first=first, last=last)
    record = StudentAcademicRecord.objects.create(
        organization=org, student=student, program=program, curriculum=curriculum, group=group, admission_year=2024
    )
    services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
    enrollment = student.enrollments.get(offering__subject=subject)
    finals.set_exam_score(enrollment=enrollment, score=score, by_user=teacher)
    return student, record, enrollment


def build_world(slug: str = "qkudv") -> dict:
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", PW)
    other_owner = User.objects.create_user(f"{slug}_bowner", f"{slug}_bowner@qku.edu.az", PW)
    with bypass_rls():
        org = _org(slug, owner)
        f1 = OrgUnit.objects.create(
            organization=org, name="Fakültə F1", slug=f"{slug}-f1", unit_type=OrgUnitType.FACULTY
        )
        g1 = OrgUnit.objects.create(
            organization=org, name="KE-101", slug=f"{slug}-g1", unit_type=OrgUnitType.GROUP, parent=f1
        )
        f2 = OrgUnit.objects.create(
            organization=org, name="Fakültə F2", slug=f"{slug}-f2", unit_type=OrgUnitType.FACULTY
        )
        g2 = OrgUnit.objects.create(
            organization=org, name="KE-201", slug=f"{slug}-g2", unit_type=OrgUnitType.GROUP, parent=f2
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name="2024/2025 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
            is_current=True,
        )
        program = Program.objects.create(organization=org, code=f"CS-{slug}", name="Kompüter elmləri")
        curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2024)
        subject = Subject.objects.create(organization=org, code="CS101", name="Proqramlaşdırmanın əsasları", ects=6)
        CurriculumSubject.objects.create(organization=org, curriculum=curriculum, subject=subject, semester_number=1)
        teacher = _member(org, f"{slug}_teacher", "teacher")
        common = {
            "program": program,
            "curriculum": curriculum,
            "period": period,
            "subject": subject,
            "teacher": teacher,
        }
        student, record, enrollment = _student_with_record(
            org, username=f"{slug}_s1", first="Elvin", last="Qurbanov", group=g1, score=45, **common
        )
        s2, record2, _ = _student_with_record(
            org, username=f"{slug}_s2", first="Nərmin", last="Əliyeva", group=g2, score=40, **common
        )
        office = _member(org, f"{slug}_office", "teaching_office_staff")
        unit_role = Role.objects.create(
            organization=org,
            name=f"{slug}_unit_sealer",
            display_name="F1 sənəd işçisi",
            level=40,
            scope_type=RoleScopeType.UNIT,
            permissions=["document_seal.manage"],
            is_active=True,
        )
        unit_staff = _member(org, f"{slug}_unit", unit_role, unit=f1)
        other = _org(f"{slug}b", other_owner)
    return {
        "org": org,
        "owner": owner,
        "f1": f1,
        "g1": g1,
        "g2": g2,
        "teacher": teacher,
        "student": student,
        "record": record,
        "enrollment": enrollment,
        "s2": s2,
        "record2": record2,
        "office": office,
        "unit_staff": unit_staff,
        "other": other,
        "other_owner": other_owner,
    }


def client_for(org, user) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def download_transcript(world, *, record=None, user=None):
    """Əməkdaş yolu (``registrar:student_transcript_pdf``) — canlı buraxılış səthi."""
    record = record or world["record"]
    client = client_for(world["org"], user or world["owner"])
    return client.get(reverse("registrar:student_transcript_pdf", args=[record.id]))


def latest_seal(**filters):
    from apps.verification.models import DocumentSeal

    with bypass_rls():
        return DocumentSeal.objects.filter(**filters).order_by("-issued_at").first()
