"""``services.get_exam_eligibility`` — idmançı-tələbə istisnası (milli yığma).

Rəsmi cədvəlin qeydi: Gənclər və İdman Nazirliyinin Kollegiyası tərəfindən
təsdiq edilmiş milli yığma komandaların üzvü olan idmançı-tələbələr 25% qayıb
həddinə görə imtahana buraxılmamazlıqdan İSTİSNA olunur.

⚠️ Sahə (``StudentAcademicRecord.national_athlete_exemption``) köçürmə ilə
AVTOMATİK DOLDURULMUR — köhnə sistemdə istisna üçün struktur sahə yox idi.
Defolt ``False`` olduğu üçün mövcud çağırışların davranışı DƏYİŞMİR; bu test
məhz həmin «dəyişməzliyi» kilidləyir.

``get_exam_eligibility`` yalnız ``enrollment.absence_hours`` və
``enrollment.offering.lesson_hours`` atributlarını oxuyur — ona görə testin
DB-yə ehtiyacı yoxdur.
"""

from types import SimpleNamespace

import pytest

from apps.registrar import services


def _enrollment(lesson_hours, absence_hours):
    return SimpleNamespace(
        absence_hours=absence_hours,
        offering=SimpleNamespace(lesson_hours=lesson_hours),
    )


# ── defolt davranış DƏYİŞMİR ─────────────────────────────────────────────────


def test_default_still_bars_over_the_limit():
    result = services.get_exam_eligibility(enrollment=_enrollment(90, 30), limit_percent=25)
    assert result["barred"] is True
    assert result["over_limit"] is True
    assert result["exempt"] is False


def test_default_does_not_bar_at_or_under_the_limit():
    result = services.get_exam_eligibility(enrollment=_enrollment(120, 30), limit_percent=25)
    assert result["barred"] is False
    assert result["over_limit"] is False


# ── istisna ──────────────────────────────────────────────────────────────────


def test_exemption_lifts_the_bar_only():
    result = services.get_exam_eligibility(enrollment=_enrollment(90, 30), limit_percent=25, exempt=True)
    assert result["barred"] is False
    # Saatlar OLDUĞU KİMİ qalır — istisna qayıbı «silmir», yalnız qərarı ləğv edir.
    assert result["over_limit"] is True
    assert result["exempt"] is True
    assert result["absence_hours"] == 30


def test_exemption_is_a_different_mechanism_from_excused_absence():
    """Üzrlü qayıb saatı ``absence_hours``-a heç vaxt daxil olmur (həm balı, həm
    həddi dəyişir); istisna isə saatı saxlayıb yalnız buraxılışı açır."""
    excused = services.get_exam_eligibility(enrollment=_enrollment(90, 0), limit_percent=25)
    exempted = services.get_exam_eligibility(enrollment=_enrollment(90, 30), limit_percent=25, exempt=True)
    assert excused["barred"] is exempted["barred"] is False
    assert excused["absence_hours"] == 0
    assert exempted["absence_hours"] == 30  # qayıb İTMİR


@pytest.mark.parametrize("exempt", [True, False])
def test_unknown_lesson_hours_never_bars(exempt):
    result = services.get_exam_eligibility(enrollment=_enrollment(0, 40), limit_percent=25, exempt=exempt)
    assert result["barred"] is False
    assert result["over_limit"] is False


def test_reported_shape_is_backwards_compatible():
    result = services.get_exam_eligibility(enrollment=_enrollment(90, 30), limit_percent=25)
    for key in ("barred", "absence_hours", "lesson_hours", "allowed_hours", "limit_percent"):
        assert key in result
