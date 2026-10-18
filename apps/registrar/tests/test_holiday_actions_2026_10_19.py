"""«Akademik təqvim» → «Bayram və qeyri-iş günləri» — idarə endpoint-i və kart (2026-10-19).

Kilidlənən qaydalar: org-wide ``semester.open`` əlavə / redaktə / silir / sabit bayramları əlavə edir (audit);
açarsız və ya yalnız bölmə səviyyəli açar — 403; yad təşkilatın qeydi — 404; view-as — 403. Kart hamıya
görünür, idarə düymələri yalnız idarə edənə.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

import pytest

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicHoliday, OrgUnit
from apps.syllabus.tests.factories import activate_member, make_org
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

pytestmark = pytest.mark.django_db

URL = "registrar:holiday_action"


@pytest.fixture()
def world():
    org = make_org("hol-ui")
    faculty = OrgUnit.objects.create(organization=org, name="Fakültə", slug="hol-ui-fak", unit_type=OrgUnitType.FACULTY)
    office = User.objects.create_user("hol_office", "hol_office@x.test", "pw")
    dean = User.objects.create_user("hol_dean", "hol_dean@x.test", "pw")
    teacher = User.objects.create_user("hol_teacher", "hol_teacher@x.test", "pw")
    activate_member(org, office, "teaching_office_head", permissions=["semester.view", "semester.open"], level=80)
    activate_member(
        org,
        dean,
        "dean",
        permissions=["semester.view", "semester.open"],
        level=75,
        scope_unit=faculty,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(org, teacher, "teacher", permissions=["course.view"])
    return {"org": org, "office": office, "dean": dean, "teacher": teacher}


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def test_org_wide_open_holder_adds_edits_and_removes_with_audit(world):
    client = _client(world["office"], world["org"])
    created = client.post(
        reverse(URL), {"action": "save", "date": "2027-03-31", "name": "Ramazan bayramı", "kind": "holiday"}
    )
    assert created.status_code == 200, created.content
    holiday = AcademicHoliday.objects.get(organization=world["org"], date=date(2027, 3, 31))
    edited = client.post(
        reverse(URL),
        {"action": "save", "id": str(holiday.pk), "date": "2027-04-01", "name": "Ramazan bayramı", "kind": "day_off"},
    )
    assert edited.status_code == 200 and edited.json()["created"] is False
    holiday.refresh_from_db()
    assert (holiday.date, holiday.kind) == (date(2027, 4, 1), "day_off")
    duplicate = client.post(reverse(URL), {"action": "save", "date": "2027-04-01", "name": "Təkrar"})
    assert duplicate.status_code == 400 and duplicate.json()["field"] == "date"
    removed = client.post(reverse(URL), {"action": "delete", "id": str(holiday.pk)})
    assert removed.status_code == 200
    assert not AcademicHoliday.objects.filter(pk=holiday.pk).exists()
    reasons = set(AuditLog.objects.filter(organization=world["org"]).values_list("reason", flat=True))
    assert {"calendar: holiday saved", "calendar: holiday removed"} <= reasons


def test_seed_fixed_holidays_via_endpoint(world):
    client = _client(world["office"], world["org"])
    first = client.post(reverse(URL), {"action": "seed_fixed", "academic_year": "2026/2027"})
    assert first.status_code == 200, first.content
    assert first.json()["created"] == 16
    again = client.post(reverse(URL), {"action": "seed_fixed", "academic_year": "2026/2027"})
    assert again.json()["created"] == 0 and again.json()["skipped"] == 16
    bad = client.post(reverse(URL), {"action": "seed_fixed", "academic_year": "sabah"})
    assert bad.status_code == 400


def test_unit_scope_and_missing_key_are_forbidden(world):
    payload = {"action": "save", "date": "2027-03-31", "name": "Ramazan bayramı"}
    assert _client(world["dean"], world["org"]).post(reverse(URL), payload).status_code == 403
    assert _client(world["teacher"], world["org"]).post(reverse(URL), payload).status_code == 403
    assert not AcademicHoliday.objects.exists()


def test_foreign_or_unknown_holiday_is_404(world):
    other = make_org("hol-ui-other")
    foreign = AcademicHoliday.objects.create(organization=other, date=date(2026, 11, 8), name="Zəfər günü")
    client = _client(world["office"], world["org"])
    assert client.post(reverse(URL), {"action": "delete", "id": str(foreign.pk)}).status_code == 404
    assert client.post(reverse(URL), {"action": "delete", "id": "nope"}).status_code == 404
    response = client.post(
        reverse(URL), {"action": "save", "id": str(foreign.pk), "date": "2026-11-08", "name": "Ələ keçir"}
    )
    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.name == "Zəfər günü"


@override_settings(UNIVERSITY_MODE=True)
def test_calendar_card_is_read_only_for_others_and_managed_by_office(world):
    AcademicHoliday.objects.create(organization=world["org"], date=date.today(), name="Bu günün bayramı")
    params = {"section": "academic-calendar"}
    teacher_page = _client(world["teacher"], world["org"]).get(reverse("accounts:profile"), params)
    assert teacher_page.status_code == 200
    html = teacher_page.content.decode()
    assert "Bu günün bayramı" in html
    assert "data-acal-hol-open" not in html and "acalHolidayDialog" not in html
    office_page = _client(world["office"], world["org"]).get(reverse("accounts:profile"), params).content.decode()
    assert "acalHolidayDialog" in office_page and "acalHolidaySeedDialog" in office_page
    assert "registrar/js/academic_holidays.js" in office_page


def test_view_as_never_writes(world, rf):
    from apps.registrar.holiday_actions import holiday_action

    request = rf.post(reverse(URL), {"action": "save", "date": "2027-03-31", "name": "Ramazan bayramı"})
    request.user = world["office"]
    request.organization = world["org"]
    request.org_permissions = ["semester.view", "semester.open"]
    request.is_view_as = True
    response = holiday_action(request)
    assert response.status_code == 403
    assert not AcademicHoliday.objects.exists()
