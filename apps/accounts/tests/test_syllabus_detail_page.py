"""Sillabusun AYRICA TAM SƏHİFƏSİ — icazə, əhatə və tələbə görünüşü qapıları.

Nəyi qoruyur
------------
Detal artıq profil qabığının içindəki drawer DEYİL: onun öz URL-i var
(``/accounts/syllabus/<uuid>/``) və siyahıdan ``target="_blank"`` ilə yeni
tabda açılır. Öz URL-i olan hər səth üçün sual eynidir — **birbaşa URL yazan
kim nə görür?**

1. müəllif öz sənədini görür;
2. ÖZ kafedrasının müdiri görür, BAŞQA kafedranınkı 404 alır (fail-closed —
   403 yox, çünki mövcudluq da sızmamalıdır);
3. sillabusla heç bir əlaqəsi olmayan işçi 404 alır;
4. qeydiyyatlı tələbə YALNIZ təsdiqlənmiş versiyanı görür — ``?version=``
   ilə qaralamaya keçə BİLMİR;
5. təsdiqlənmiş nüsxə yoxdursa tələbə üçün səhifə ümumiyyətlə yoxdur;
6. başqa kirayəçinin UUID-i 404-dür (tenant izolyasiyası);
7. PDF endpoint-i EYNİ qapıdan keçir (sənəd səhifəsi bağlıdırsa PDF də bağlıdır).

⚠️ PostgreSQL tələb olunur: ``registrar_guard_active_member`` trigger-i və RLS
sqlite-da yoxdur, yəni bu qapılar yalnız PG-də real yoxlanılır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from apps.registrar.models import Enrollment
from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import RoleScopeType

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "StrongPass123!"

# `grade.input` — PG `registrar_guard_active_member` trigger-i CourseOffering
# müəlliminin bu icazəsini tələb edir (bax registrar 0041).
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve"]
STUDENT_PERMS = ["course.view"]


def _client(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _fill(version, actor):
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    return version


@pytest.fixture()
def world():
    """Bir kafedra, bir açılış, dörd aktor — hamısı AKTİV üzvlüklə."""
    org = make_org("syl-detail")
    stack = make_academic_stack(org, code="DET101")

    teacher = User.objects.create_user("det_teacher", "det_teacher@x.test", PASSWORD)
    chair = User.objects.create_user("det_chair", "det_chair@x.test", PASSWORD)
    outsider = User.objects.create_user("det_outsider", "det_outsider@x.test", PASSWORD)
    student = User.objects.create_user("det_student", "det_student@x.test", PASSWORD)

    activate_member(org, teacher, "det_teacher_role", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair,
        "det_chair_role",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    # BAŞQA kafedranın müdiri: icazə açarları eynidir, əhatəsi fərqlidir.
    other_chair_unit = make_academic_stack(org, code="OTH909")["chair"]
    activate_member(
        org,
        outsider,
        "det_other_chair_role",
        permissions=CHAIR_PERMS,
        scope_unit=other_chair_unit,
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(org, student, "det_student_role", permissions=STUDENT_PERMS, level=10)

    offering = make_offering(org, stack, teacher)
    Enrollment.objects.create(organization=org, student=student, offering=offering)

    actor = services.resolve_actor(teacher, org)
    syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        plan_hours=PLAN_HOURS,
    )
    return {
        "org": org,
        "stack": stack,
        "teacher": teacher,
        "chair": chair,
        "outsider": outsider,
        "student": student,
        "offering": offering,
        "syllabus": syllabus,
        "version": _fill(version, actor),
        "teacher_actor": actor,
    }


def _approve(world_):
    """Qaralamanı təsdiqlənmiş versiyaya çevirir (state maşını ilə)."""
    chair_actor = services.resolve_actor(world_["chair"], world_["org"])
    version = services.submit(version=world_["version"], actor=world_["teacher_actor"])
    version = services.approve(version=version, actor=chair_actor)
    world_["syllabus"].refresh_from_db()
    return version


def _detail_url(syllabus, **params):
    url = reverse("accounts:syllabus_detail", kwargs={"syllabus_id": str(syllabus.pk)})
    if params:
        url = f"{url}?" + "&".join(f"{key}={value}" for key, value in params.items())
    return url


# ── Görməli olan görür ─────────────────────────────────────────────────────


def test_author_opens_the_standalone_document_page(world):
    """Müəllif öz qaralamasını ayrıca səhifədə tam görür."""
    response = _client(world["teacher"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert world["stack"]["subject"].name in body
    assert world["stack"]["subject"].code in body
    # 8 məzmun bölməsinin hamısı səhifədədir (drawer-in qısaldılmış nüsxəsi deyil).
    assert body.count('class="syl-doc__section"') == 8
    # PDF keçidi mövcud axına bağlıdır.
    assert reverse("accounts:syllabus_detail_pdf", kwargs={"syllabus_id": str(world["syllabus"].pk)}) in body


def test_chair_head_of_the_same_department_opens_it(world):
    """Öz kafedrasının sillabusu — `syllabus.view` + əhatə uyğundur."""
    response = _client(world["chair"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200


def test_page_is_rendered_outside_the_profile_shell(world):
    """Səhifə profil qabığından KƏNARDIR — profil sidebar-ı render olunmur."""
    body = _client(world["teacher"], world["org"]).get(_detail_url(world["syllabus"])).content.decode("utf-8")

    assert "data-syllabus-detail" in body
    assert "data-profile-section-panel" not in body


# ── Görməməli olan görmür (fail-closed) ────────────────────────────────────


def test_other_department_chair_head_gets_404_on_direct_url(world):
    """İcazə açarı var, ƏHATƏSİ yoxdur → mövcudluq da sızdırılmır."""
    response = _client(world["outsider"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 404


def test_unrelated_staff_member_gets_404(world):
    """Sillabus icazəsi olmayan işçi birbaşa URL ilə də girə bilmir."""
    clerk = User.objects.create_user("det_clerk", "det_clerk@x.test", PASSWORD)
    activate_member(world["org"], clerk, "det_clerk_role", permissions=["post.view"])

    response = _client(clerk, world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 404


def test_syllabus_of_another_tenant_is_not_reachable(world):
    """Tenant izolyasiyası: özgə təşkilatın UUID-i 404-dür."""
    other_org = make_org("syl-detail-other")
    stranger = User.objects.create_user("det_stranger", "det_stranger@x.test", PASSWORD)
    activate_member(other_org, stranger, "det_stranger_role", permissions=CHAIR_PERMS)

    response = _client(stranger, other_org).get(_detail_url(world["syllabus"]))

    assert response.status_code == 404


# ── Tələbə: YALNIZ təsdiqlənmiş versiya ────────────────────────────────────


def test_student_without_an_approved_version_gets_404(world):
    """Qaralama tələbəyə görünmür — səhifənin özü mövcud deyil."""
    response = _client(world["student"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 404


def test_student_sees_the_approved_version(world):
    """Təsdiqdən sonra qeydiyyatlı tələbə sənədi görür və izah bannerini alır."""
    approved = _approve(world)

    response = _client(world["student"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert approved.label in body
    assert str(SyllabusStatus.APPROVED.label) in body


def test_student_cannot_reach_a_draft_version_through_the_url(world):
    """`?version=` tələbəyə TƏTBİQ OLUNMUR — yeni qaralama URL ilə sızmır."""
    approved = _approve(world)
    draft = services.create_next_version(
        syllabus=world["syllabus"],
        actor=world["teacher_actor"],
        kind="minor",
    )
    assert draft.status == SyllabusStatus.DRAFT

    response = _client(world["student"], world["org"]).get(_detail_url(world["syllabus"], version=draft.pk))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert approved.label in body
    assert f">{draft.label}<" not in body


def test_student_of_another_offering_gets_404(world):
    """Qeydiyyatı olmayan tələbə — açılışa bağlı olmayan hesab 404 alır."""
    stranger = User.objects.create_user("det_student2", "det_student2@x.test", PASSWORD)
    activate_member(world["org"], stranger, "det_student2_role", permissions=STUDENT_PERMS, level=10)
    _approve(world)

    response = _client(stranger, world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 404


# ── PDF eyni qapıdan keçir ─────────────────────────────────────────────────


def test_pdf_download_uses_the_same_gate(world):
    """Sənəd səhifəsi bağlıdırsa PDF də bağlıdır; açıqdırsa PDF fayl qaytarır."""
    _approve(world)
    pdf_url = reverse("accounts:syllabus_detail_pdf", kwargs={"syllabus_id": str(world["syllabus"].pk)})

    denied = _client(world["outsider"], world["org"]).get(pdf_url)
    assert denied.status_code == 404

    allowed = _client(world["teacher"], world["org"]).get(pdf_url)
    assert allowed.status_code == 200
    assert allowed["Content-Type"] == "application/pdf"
    assert "attachment;" in allowed["Content-Disposition"]


# ── Siyahı və növbə keçidləri YENİ TABDA açılır ────────────────────────────


def test_list_and_queue_rows_link_to_the_detail_page_in_a_new_tab(world):
    """Sətir view-modeli detal URL-ini daşıyır, şablon onu `_blank` ilə yazır."""
    from apps.accounts.views.syllabus.review_rows import build_queue_row
    from apps.accounts.views.syllabus.rows import build_row

    _approve(world)
    world["syllabus"].refresh_from_db()
    row = build_row(world["syllabus"])
    queue_row = build_queue_row(world["syllabus"].approved_version, now=None)

    expected = reverse("accounts:syllabus_detail", kwargs={"syllabus_id": str(world["syllabus"].pk)})
    assert row["detail_url"] == expected
    assert queue_row["detail_url"].startswith(expected)

    for template in (
        "accounts/profile/sections/syllabus/_list_table.html",
        "accounts/profile/sections/syllabus/_list_cards.html",
        "accounts/profile/sections/syllabus/_review_queue.html",
    ):
        from django.template.loader import get_template

        source = get_template(template).template.source
        assert 'target="_blank"' in source, template
        assert 'rel="noopener"' in source, template


# ── Tələbə DAXİLİ təsdiq tarixçəsini GÖRMÜR (fail-closed ağ siyahı) ─────────

#: Kafedra müdirinin MÜƏLLİMƏ yazdığı daxili irad — tələbəyə aid deyil.
INTERNAL_REASON = "DAXILI QEYD: metodik shuranin iradi, menbeler kohnedir"


def _pending_next_version(world_):
    """v1.0 təsdiqlənir, sonra v1.1 göndərilib DÜZƏLİŞƏ qaytarılır.

    Nəticədə dosyedə eyni anda: tələbənin görməli olduğu TƏSDİQLƏNMİŞ nüsxə +
    tələbənin görməməli olduğu təsdiqlənməmiş versiya, onun statusu, rəyçinin
    adı və sərbəst mətnli rədd səbəbi olur.
    """
    approved = _approve(world_)

    reviewer = User.objects.create_user("det_reviewer", "det_reviewer@x.test", PASSWORD)
    reviewer.first_name = "Rəyçi"
    reviewer.last_name = "Rəyçiyev"
    reviewer.save(update_fields=["first_name", "last_name"])
    activate_member(
        world_["org"],
        reviewer,
        "det_reviewer_role",
        # `syllabus.revise` — REQUEST_REVISION keçidinin öz açarı (state machine).
        permissions=[*CHAIR_PERMS, "syllabus.revise"],
        scope_unit=world_["stack"]["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )

    draft = services.create_next_version(syllabus=world_["syllabus"], actor=world_["teacher_actor"], kind="minor")
    submitted = services.submit(version=draft, actor=world_["teacher_actor"])
    pending = services.request_revision(
        version=submitted,
        actor=services.resolve_actor(reviewer, world_["org"]),
        reason=INTERNAL_REASON,
    )
    world_["syllabus"].refresh_from_db()
    return approved, pending, reviewer


def test_student_page_carries_no_internal_review_timeline(world):
    """Tələbənin HTML-ində nə rədd səbəbi, nə rəyçinin adı, nə də digər versiya."""
    approved, pending, reviewer = _pending_next_version(world)

    response = _client(world["student"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    # Görməli olduğu: təsdiqlənmiş nüsxənin özü.
    assert approved.label in body
    # Görməməli olduqları:
    assert response.context["syllabus_detail"]["timeline"] == []
    assert INTERNAL_REASON not in body
    assert reviewer.last_name not in body
    assert pending.label not in body
    assert str(SyllabusStatus.REVISION.label) not in body
    assert "syl-doc__timeline" not in body


def test_staff_page_still_shows_the_review_timeline(world):
    """Ştat rejimi POZULMUR — müəllim öz dosyesinin tarixçəsini görməyə davam edir."""
    _approved, _pending, reviewer = _pending_next_version(world)

    response = _client(world["teacher"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert response.context["syllabus_detail"]["timeline"]
    assert INTERNAL_REASON in body
    assert reviewer.last_name in body
    assert "syl-doc__timeline" in body


def test_timeline_is_withheld_for_any_unlisted_mode(world):
    """Ağ siyahı AÇIQDIR: gələcək yeni rejim defolt olaraq tarixçə ALMIR."""
    from apps.accounts.views.syllabus.detail_context import MODE_STAFF, TIMELINE_MODES, build_detail_context

    _approved, _pending, _reviewer = _pending_next_version(world)
    version = services.approved_version_for(world["syllabus"])

    def timeline_for(mode):
        context = build_detail_context(
            organization=world["org"],
            syllabus=world["syllabus"],
            version=version,
            mode=mode,
            is_student=False,
        )
        return context["syllabus_detail"]["timeline"]

    assert TIMELINE_MODES == {MODE_STAFF}
    assert timeline_for(MODE_STAFF)
    for unlisted in ("student", "parent", "auditor", "", None):
        assert timeline_for(unlisted) == [], unlisted


MIGRATION_NOTE = "PROB-KOCURME-QEYDI: kohne sistemden 1234"


def test_student_never_sees_the_decision_reason_of_an_approved_version(world):
    """Köçürmə TƏSDİQLƏNMİŞ versiyaya qeyd yazır — o qeyd tələbəyə sızmamalıdır.

    Qoruma «APPROVED-da ``decision_reason`` onsuz da boşdur» invariantına
    söykənə BİLMƏZ: ``drafts.import_migrated_version(..., note=…)`` məhz
    təsdiqlənmiş versiyaya ``decision_reason=note`` yazır.  Sillabus köçürməsi
    qoşulan gün həmin invariant pozulur, ona görə qapı rejim ağ siyahısıdır.
    """

    _pending_next_version(world)
    version = services.approved_version_for(world["syllabus"])
    version.decision_reason = MIGRATION_NOTE
    version.save(update_fields=["decision_reason"])

    response = _client(world["student"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200
    assert MIGRATION_NOTE not in response.content.decode("utf-8")
    assert response.context["syllabus_detail"]["status"]["reason"] == ""


def test_staff_still_sees_the_decision_reason(world):
    """Ştat rejimi POZULMUR — səbəb müəllim/kafedra müdiri üçün qalır."""

    _pending_next_version(world)
    version = services.approved_version_for(world["syllabus"])
    version.decision_reason = MIGRATION_NOTE
    version.save(update_fields=["decision_reason"])

    response = _client(world["teacher"], world["org"]).get(_detail_url(world["syllabus"]))

    assert response.status_code == 200
    # Ştat üçün qapı BAĞLI DEYİL — göstərilən versiyanın daxili səbəbi görünür.
    # (Bu, dosyedə açıq olan versiyadır, ona görə dəyəri fixture-dan gəlir.)
    assert response.context["syllabus_detail"]["status"]["reason"] == INTERNAL_REASON


def test_decision_reason_is_withheld_for_any_unlisted_mode(world):
    """Ağ siyahı AÇIQDIR: siyahıda olmayan hər yeni rejim boş sətir alır."""

    from apps.accounts.views.syllabus.detail_context import MODE_STAFF, REASON_MODES, build_detail_context

    _pending_next_version(world)
    version = services.approved_version_for(world["syllabus"])
    version.decision_reason = MIGRATION_NOTE
    version.save(update_fields=["decision_reason"])

    def reason_for(mode):
        context = build_detail_context(
            organization=world["org"],
            syllabus=world["syllabus"],
            version=version,
            mode=mode,
            is_student=False,
        )
        return context["syllabus_detail"]["status"]["reason"]

    assert reason_for(MODE_STAFF) == MIGRATION_NOTE
    for mode in ("student", "parent", "auditor", "", None):
        assert reason_for(mode) == "", mode
    assert REASON_MODES == frozenset({MODE_STAFF})
