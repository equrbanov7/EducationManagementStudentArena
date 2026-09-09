"""Media təsnifatı DENY-BY-DEFAULT-dur (2026-09-10, üçüncü eyni tipli P0-dan sonra).

NİYƏ BU TEST VAR
----------------
`_is_private()` əvvəl əks istiqamətdə işləyirdi: yalnız siyahıdakı prefikslər
məxfi sayılır, QALANI ictimai olurdu. Nəticədə hər dəfə yeni `FileField`
əlavə edən adam prefiksi siyahıya yazmağı unutduqda sənəd sükutla
autentifikasiyasız açılırdı. Bu, ÜÇ ayrı P0 verdi:

* 2026-09-02 — imtahan yükləmələri,
* 2026-09-03 — ``student_movements/`` (köçürmə/xaric əmrləri),
* 2026-09-10 — ``workload_amendments/`` (dərs yükü düzəlişinin rəsmi PDF-i).

Testlər məhz həmin sürüşməni kilidləyir: siyahıda OLMAYAN prefiks məxfi
sayılmalıdır, ictimai səthlərin siyahısı isə qısa və qəsdi olmalıdır.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.media_views import _PUBLIC_PREFIXES, _is_private


class DenyByDefaultClassificationTest(SimpleTestCase):
    def test_unknown_prefix_is_private(self):
        """Sabah əlavə olunacaq, bu gün heç kimin bilmədiyi prefiks."""
        for path in (
            "workload_amendments/1/2/emr.pdf",
            "brand_new_feature/2026/senet.pdf",
            "reports/hesabat.xlsx",
        ):
            with self.subTest(path=path):
                self.assertTrue(_is_private(path))

    def test_only_the_whitelist_is_public(self):
        for prefix in _PUBLIC_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertFalse(_is_private(prefix + "fayl.png"))

    def test_public_whitelist_stays_small_and_deliberate(self):
        """Ağ siyahı böyüyürsə, bu, şüurlu qərar olmalıdır — test onu görünən edir."""
        self.assertEqual(
            set(_PUBLIC_PREFIXES),
            {"post_images/", "course_covers/", "org_logos/"},
        )

    def test_leading_slash_does_not_bypass_classification(self):
        self.assertTrue(_is_private("/workload_amendments/1/2/emr.pdf"))


class WorkloadAmendmentMediaGateTest(TestCase):
    """Dərs yükü düzəlişinin sənədi anonim istifadəçiyə VERİLMİR."""

    def test_anonymous_request_is_redirected_to_login(self):
        url = reverse("protected_media", kwargs={"path": "workload_amendments/1/2/emr.pdf"})
        response = self.client.get(url)
        # Məxfi yol: anonim aktor girişə yönləndirilir (faylın mövcudluğu
        # bildirilmir — bax `protected_media` şərhi).
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])
