"""Dəqiqləşdirmə növbəsinin QİYMƏT qapısı — sorğu büdcəsi və sorğu FORMASI.

NİYƏ VAXT YOX, SORĞU SAYI
-------------------------
Millisaniyə həddi maşından, keşdən və paralel yükdən asılıdır — CI-da ya
saxta-qırmızı olur, ya da qırmızı olmamaq üçün elə boş qoyulur ki, heç nə
tutmur. Bu testlər əvəzinə **reqressiyanın ÖZ mexanizmini** kilidləyir:

1. **Sorğu sayı sabitdir** — ekran neçə fakt, neçə kateqoriya olmasından asılı
   olmayaraq eyni sayda sorğu atır. Sayğac başına bir ``COUNT`` qaytarılsa
   (əvvəl 16 sorğu idi) bu düşür.
2. **Canlı bal güzgüsü JOIN-dur** — korrelyasiyalı skalyar alt-sorğu deyil.
   Alt-sorğu qaytarılsa Postgres onu HƏR sətir üçün yenidən icra edir; 169 min
   faktda tək bir ``COUNT`` bir milyondan çox bufer toxunuşu edirdi.

Yəni bu fayl «nə qədər sürətlidir» yox, «hansı formadadır» sualını qoruyur —
forma pozulan kimi sürət də itir, amma test maşından asılı olmur.
"""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.views.legacy_review.api import DEFAULT_PAGE_SIZE, _paginator
from apps.registrar import legacy_grade_review as review_read
from apps.registrar import legacy_grade_review_counts as counts_read
from apps.registrar import legacy_grade_review_rows as rows_read
from apps.registrar.models import LegacyGradeMappingStatus
from apps.registrar.tests.test_legacy_grade_review import _ReviewSetup
from core.rls import bypass_rls

#: Növbə ekranının BÜTÜN qiyməti: sayğac aqreqatı + səhifə + yoxlama tarixçəsi.
#: Bu rəqəm məlumat həcmindən ASILI DEYİL — testlər bunu ayrıca sübut edir.
QUEUE_SCREEN_QUERY_BUDGET = 3


def _filters(**over):
    filters = {
        key: ""
        for key in (
            "faculty",
            "kafedra",
            "specialty",
            "group",
            "subject",
            "teacher",
            "period",
            "year",
            "severity",
            "status",
            "q",
        )
    }
    filters["categories"] = []
    filters.update(over)
    return filters


class QueueScreenCostTests(_ReviewSetup):
    """`legacy_review_queue` view-nun ETDİYİ işin eynisi, sorğu sayğacı ilə.

    View-nun özünü çağırmırıq (o, sessiya/tenant middleware-i tələb edir və bu
    testin mövzusu icazə deyil, QİYMƏTDİR); əvəzində view-nun işlətdiyi EYNİ
    funksiyalar eyni ardıcıllıqla çağırılır — ``_paginator`` və ``queue_counts``
    birbaşa view modulundan import olunur ki, view dəyişəndə test də onunla
    birlikdə sürüşsün.
    """

    def _seed(self, count, *, start=1):
        for index in range(count):
            self._fact(
                source_pk=start + index,
                mapping_status=LegacyGradeMappingStatus.UNRESOLVED,
                mapping_issue_code="legacy_grade_fact_unresolved",
                final_score_text="117",
                final_score=Decimal("117"),
            )

    def _queue_screen(self, filters=None, page=1):
        """View-nun gövdəsi — cavabın hər hissəsi həqiqətən istehsal olunur."""
        filters = filters if filters is not None else _filters()
        queryset = review_read.review_queue(
            organization=self.org,
            user=None,
            categories=filters["categories"],
            filters=filters,
        )
        prepared = rows_read.order_by_severity(
            rows_read.prepared_page_queryset(queryset, self.org),
            self.org,
        )
        counts = counts_read.queue_counts(organization=self.org, user=None, filters=filters)
        paginator = _paginator(prepared, DEFAULT_PAGE_SIZE, filters, counts)
        page_obj = paginator.get_page(page)
        return {
            "results": rows_read.serialize_page(page_obj.object_list, self.org, can_correct=True),
            "total": paginator.count,
            "progress": counts["progress"],
            "categories": counts["categories"],
        }

    def _measure(self):
        with CaptureQueriesContext(connection) as captured:
            payload = self._queue_screen()
        return len(captured.captured_queries), payload

    def test_the_whole_queue_screen_fits_in_a_fixed_query_budget(self):
        """Sətirlər + irəliləyiş + 7 kateqoriya çipi — hamısı bir neçə sorğuda."""
        with bypass_rls():
            self._seed(3)
        queries, payload = self._measure()
        self.assertEqual(
            queries,
            QUEUE_SCREEN_QUERY_BUDGET,
            "növbə ekranı sorğu büdcəsini aşdı — sayğaclar yenidən sətir-sətir sayılır?",
        )
        # Büdcə işi AZALTMAQLA yerinə yetirilməyib: cavab hələ də tamdır.
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["progress"]["total"], 3)
        self.assertEqual(len(payload["results"]), 3)
        self.assertEqual(len(payload["categories"]), len(review_read.category_specs(self.org)))

    def test_the_cost_does_not_grow_with_the_number_of_rows(self):
        """N+1 qapısı: 3 sətirlə 40 sətrin qiyməti EYNİ olmalıdır."""
        with bypass_rls():
            self._seed(3)
        small, _ = self._measure()
        with bypass_rls():
            self._seed(37, start=100)
        large, payload = self._measure()
        self.assertEqual(payload["total"], 40)
        self.assertEqual(
            large,
            small,
            "sətir sayı artdıqca sorğu sayı da artdı — sətir başına sorğu qayıdıb",
        )

    def test_every_category_counter_shares_a_single_query(self):
        """7 kateqoriya × (ümumi, baxılmış) + irəliləyiş = 16 sayğac, 1 sorğu."""
        with bypass_rls():
            self._seed(2)
        with CaptureQueriesContext(connection) as captured:
            counts = counts_read.queue_counts(organization=self.org, user=None, filters=_filters())
        self.assertEqual(
            len(captured.captured_queries),
            1,
            "kateqoriya sayğacları yenidən ayrı-ayrı COUNT-lara bölünüb",
        )
        # Sayğaclar «bir sorğu» olsun deyə İXTİSAR EDİLMƏYİB.
        self.assertEqual(len(counts["categories"]), len(review_read.category_specs(self.org)))
        self.assertEqual(counts["progress"]["total"], 2)

    def test_the_live_score_mirror_is_joined_not_re_run_per_row(self):
        """Canlı bal güzgüsü JOIN-dur — korrelyasiyalı alt-sorğu DEYİL.

        Bu, büdcə testlərinin tutmadığı reqressiyanı tutur: sorğu sayı 3 qala,
        amma həmin 3 sorğudan biri hər sətir üçün ``FinalGrade``-ə ayrıca
        getsin. Onda sayğac deyil, PLAN pozulur.
        """
        sql = str(review_read.review_queue(organization=self.org).query)
        self.assertIn(
            'JOIN "registrar_finalgrade"',
            sql,
            "canlı bal güzgüsü artıq JOIN deyil",
        )
        self.assertNotIn(
            'FROM "registrar_finalgrade"',
            sql,
            "canlı bal güzgüsü yenidən korrelyasiyalı alt-sorğuya çevrilib",
        )

    def test_the_review_stamp_lookup_is_not_correlated_either(self):
        """«Baxılıb» yoxlaması da sətir-sətir deyil, dəst üzvlüyü ilə aparılır."""
        sql = str(review_read.review_queue(organization=self.org).query)
        self.assertNotIn(
            'U0."fact_id" = ("registrar_legacygradefact"."id")',
            sql,
            "yoxlama möhürü hər sətir üçün ayrıca sorğulanır",
        )


class PaginatorShortcutHonestyTests(_ReviewSetup):
    """``_paginator`` qısayolu HƏMİŞƏ həqiqəti deməlidir.

    ``_paginator`` status süzgəci seçilməyəndə ``Paginator.count``-u irəliləyiş
    məxrəcindən götürür və bir tam skandan (169 min sətir) qaçır.  Qənaət realdır,
    LAKİN o, iki modul arasında YAZILMAMIŞ razılaşmaya söykənir:
    «irəliləyiş məxrəci == süzgəclənmiş növbənin həqiqi ölçüsü».

    Düşmən baxışı bu razılaşmanın qorunmadığını sübut etdi: qısayol süzgəc
    altında qəsdən yalançı ediləndə (``+ 7``) 36 testin HAMISI keçirdi.
    Belə bir sürüşmə səssizdir və istifadəçiyə belə görünür — cədvəldə N sətir,
    başlıqda və səhifələmədə M rəqəmi.

    Bu dəst razılaşmanı bərabərlik kimi kilidləyir: hansı süzgəc qoyulursa
    qoyulsun, ``paginator.count`` həmin süzgəcin HƏQİQİ sətir sayına bərabər
    olmalıdır.
    """

    def _seed_mixed(self):
        """İki fərqli statusda faktlar — süzgəc həqiqətən bölsün deyə."""
        for index in range(7):
            self._fact(
                source_pk=1000 + index,
                mapping_status=LegacyGradeMappingStatus.UNRESOLVED,
                mapping_issue_code="legacy_grade_fact_unresolved",
                final_score_text="117",
                final_score=Decimal("117"),
            )
        for index in range(5):
            self._fact(
                source_pk=2000 + index,
                mapping_status=LegacyGradeMappingStatus.CONFLICT,
                mapping_issue_code="legacy_grade_fact_conflict",
                final_score_text="42",
                final_score=Decimal("42"),
            )

    def _prepared_and_counts(self, filters):
        queryset = review_read.review_queue(
            organization=self.org,
            user=None,
            categories=filters["categories"],
            filters=filters,
        )
        prepared = rows_read.order_by_severity(
            rows_read.prepared_page_queryset(queryset, self.org),
            self.org,
        )
        counts = counts_read.queue_counts(organization=self.org, user=None, filters=filters)
        return prepared, counts

    def _assert_honest(self, filters, label):
        prepared, counts = self._prepared_and_counts(filters)
        paginator = _paginator(prepared, DEFAULT_PAGE_SIZE, filters, counts)
        self.assertEqual(
            paginator.count,
            prepared.count(),
            f"{label}: səhifələyicinin sayı süzgəcin həqiqi sətir sayından FƏRQLİDİR "
            f"— istifadəçi cədvəldə bir rəqəm, başlıqda başqasını görər",
        )

    def test_the_shortcut_is_honest_with_no_filter(self):
        with bypass_rls():
            self._seed_mixed()
            self._assert_honest(_filters(), "süzgəcsiz")

    def test_the_shortcut_is_honest_under_a_category_filter(self):
        """Kateqoriya süzgəci status süzgəci DEYİL — qısayol yenə də işləyir."""
        with bypass_rls():
            self._seed_mixed()
            self._assert_honest(_filters(categories=["conflict"]), "kateqoriya süzgəci")

    def test_the_shortcut_is_honest_under_a_text_search(self):
        with bypass_rls():
            self._seed_mixed()
            self._assert_honest(_filters(q="117"), "mətn axtarışı")

    def test_the_shortcut_is_honest_under_a_status_filter(self):
        """Status seçiləndə qısayol İŞLƏMİR — Paginator öz sayını özü etməlidir."""
        with bypass_rls():
            self._seed_mixed()
            self._assert_honest(_filters(status="pending"), "status süzgəci")

    def test_the_shortcut_is_honest_when_filters_are_combined(self):
        with bypass_rls():
            self._seed_mixed()
            self._assert_honest(
                _filters(categories=["unresolved"], q="117"),
                "kateqoriya + axtarış",
            )
