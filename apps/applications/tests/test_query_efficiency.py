"""QA P2-26/P2-6 reqressiya qapısı: bölmə açılışı KIND/UNIT sayı ilə XƏTTİ artmamalıdır.

Kök səbəb idi: ``build_applications_context`` hər aktiv KIND üçün ayrı-ayrı
``route_for`` çağırırdı və bu da (a) hər KIND üçün ayrı ``ApplicationUnit``
sorğusu (``unit_by_code``), (b) ``sender_unit`` nəticəsi HƏQİQƏTƏN ``None``
olanda (mərkəzi/org-scope aktor) onu «hələ hesablanmayıb»la qarışdırıb hər
KIND üçün üzvlük/SAR sorğusunu TƏKRARLAYIRDI. Nəticə: bölmə açılışında
80-86 sorğu, 37-42 dublikat (ölçülüb: ``qa.dean`` / ``applications`` bölməsi).

Bu test kataloqu SÜNI böyüdür (3 → 15 aktiv növ, eyni ailəyə) və sorğu sayının
DƏYİŞMƏDİYİNİ sübut edir — ``apps/workload/tests/test_stage4_sections.py``-dakı
``test_aggregation_uses_a_bounded_number_of_queries`` ilə eyni naxış.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpRequest
from django.test.utils import CaptureQueriesContext

import pytest

from apps.applications.models import ApplicationKind
from apps.applications.public import build_applications_context
from apps.applications.tests.factories import make_world, unit_of
from apps.organizations.models import Organization

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture()
def world():
    return make_world("qeff")


def _build_context_query_count(*, organization_id, user_id) -> int:
    """Hər çağırış TƏZƏ ``organization``/``user`` obyekti ilə işləyir.

    ``access.active_memberships`` / ``access.active_units`` request-daxili
    keşi obyekt-atributu ilə saxlanılır (əsl HTTP request-lərdə hər sorğu
    üçün təbii şəkildə TƏZƏ obyektlər olur). Eyni Python obyektini iki dəfə
    işlətmək keşi «sızdırardı» və müqayisəni saxta şəkildə ucuzlaşdırardı —
    ona görə hər ölçmədə bazadan YENİDƏN gətiririk.
    """
    organization = Organization.objects.get(pk=organization_id)
    user = User.objects.get(pk=user_id)
    request = HttpRequest()
    request.user = user
    with CaptureQueriesContext(connection) as ctx:
        build_applications_context(request, organization=organization)
    return len(ctx.captured_queries)


def test_context_query_count_is_independent_of_active_kind_count(world):
    org = world["organization"]
    # ``staff`` ailəsi ilə: `can_create` açıqdır (application.create daşıyır) VƏ
    # org-scope (unit-scope DEYİL) üzvlükdür → ``sender_scope_unit_for`` HƏQİQƏTƏN
    # ``None`` qaytarır — məhz bu, əvvəlki "hələ hesablanmayıb" ilə qarışdırılan
    # dəyər idi.
    staff = world["staff"]

    baseline = _build_context_query_count(organization_id=org.pk, user_id=staff.pk)

    rim = unit_of(world, "rim")
    ApplicationKind.objects.bulk_create(
        [
            ApplicationKind(
                organization=org,
                code=f"qeff-extra-{index}",
                label=f"Əlavə növ {index}",
                allowed_sender_families=["staff"],
                target_unit=rim,
            )
            for index in range(12)
        ]
    )

    scaled = _build_context_query_count(organization_id=org.pk, user_id=staff.pk)

    assert scaled == baseline, (
        f"KIND sayı 3-dən 15-ə qalxanda sorğu sayı {baseline}-dan {scaled}-a dəyişdi — "
        "kataloq/üzvlük keşi hər KIND üçün TƏKRAR sorğulanır (N+1 geri qayıdıb)."
    )
    # Ucuz saxlanmalıdır: dövrün sabit qaldığını sübut etmək kifayət deyil,
    # məlum absurd (80+) həddən UZAQ olmalıdır.
    assert baseline < 30, baseline
