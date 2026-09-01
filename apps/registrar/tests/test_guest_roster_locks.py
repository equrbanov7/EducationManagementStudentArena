"""«Alt qrupdan tələbə əlavə et» — DONDURULMUŞ jurnal + KEÇMİŞ dövr qapısı.

NİYƏ (düşmən yoxlayıcının tapıntısı, 2026-08-31)
────────────────────────────────────────────────
Siyahı idarəsi jurnalın YEGANƏ qapısız mutasiya yolu idi: qalan bütün yollar
(``gradebook_lessons``, ``gradebook_components``, ``journal_extras``,
``rubrics``, ``finals``, ``item_corrections``) ``gradebook.journal_is_locked``
qapısından keçir, alt-qrup yolu isə NƏ kilidi, NƏ dövrü yoxlayırdı. Nəticədə
RƏSMƏN bağlanmış jurnala və KÖÇÜRÜLMÜŞ 2019/2020 semestrinə tələbə əlavə edilə
bilirdi — tələbənin TRANSKRİPTİ dəyişirdi. Bu, layihənin ən sərt qaydasını
(«köhnə datanı dəyişmirik, sadəcə köçürürük») pozurdu.

Aşağıdakı beş test məhz sübut edilmiş beş zondun eynisidir; hamısı ARTIQ
RƏDD ilə bitməlidir:

* (A) ``journal_close.close_journals()`` ilə bağlanmış jurnala servis əlavəsi;
* (B) 2019/2020 (``is_current=False``) dövrünün jurnalına servis əlavəsi;
* (C) kilidli jurnala ``POST …/alt-qrup/elave/``;
* (D) kilidli jurnalda ``POST …/alt-qrup/cixar/``;
* (E) bağlı semestrə əlavədən sonra transkript sətir sayı DƏYİŞMƏMƏLİDİR.

Əlavə olaraq səth süzgəci yoxlanılır: keçmiş dövrün jurnalı koordinatorun
siyahısında ÇIXMAMALIDIR və jurnal səhifəsində düymə görünməməlidir.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership
from apps.registrar import guest_roster, journal_close, page_contexts, transcript
from apps.registrar.models import CourseOffering, Enrollment, EnrollmentKind
from core.constants import AcademicPeriodType
from core.rls import bypass_rls

from .test_guest_roster import _GuestRosterBase

User = get_user_model()


def _transcript_row_count(student, organization) -> int:
    """Transkriptdəki FƏNN sətirlərinin ümumi sayı (bütün semestrlər üzrə)."""
    data = transcript.build_student_transcript(student=student, organization=organization)
    return sum(len(bucket["rows"]) for bucket in data["semesters"])


class _FrozenRosterBase(_GuestRosterBase):
    """Baza fixtura + RİM (jurnal bağlayan) + KÖÇÜRÜLMÜŞ 2019/2020 semestri."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.rim = User.objects.create_user("gr_rim", "gr_rim@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.rim,
                organization=cls.org,
                role=cls.org.roles.get(name="ikt_rehber"),
                is_primary=True,
                is_active=True,
            )
            # Köçürülmüş tarixi semestr: bitib, cari deyil — transkriptdədir.
            cls.past_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2019/2020 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2019/2020",
                start_date="2019-09-01",
                end_date="2020-01-31",
                is_current=False,
            )
            cls.past_offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.history,
                period=cls.past_period,
                group=cls.group1,
                instructor=cls.teacher,
            )
            Enrollment.objects.create(
                organization=cls.org,
                student=cls.host,
                offering=cls.past_offering,
                kind=EnrollmentKind.MANDATORY,
                status=Enrollment.Status.ENROLLED,
            )

    def _close_current_journals(self):
        """(A/C/D) Jurnalı RƏSMƏN bağla — RİM-in toplu bağlama axını ilə."""
        with bypass_rls():
            return journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)


class ClosedJournalRosterTest(_FrozenRosterBase):
    """(A) + (C) + (D) — bağlanmış jurnal siyahı dəyişikliyini qəbul etmir."""

    def test_probe_a_service_add_into_closed_journal_is_refused(self):
        self._drop_own_history(self.guest)
        self._close_current_journals()
        with bypass_rls():
            self.assertFalse(guest_roster.roster_is_open(self.offering))
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
            self.assertFalse(
                Enrollment.objects.filter(offering=self.offering, student=self.guest).exists(),
            )

    def test_probe_c_http_add_into_closed_journal_is_refused(self):
        self._drop_own_history(self.guest)
        self._close_current_journals()
        client = self._client(self.coordinator)
        response = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.guest).exists())

    def test_probe_d_http_remove_in_closed_journal_is_refused(self):
        """Əvvəl AÇIQ jurnalda əlavə → sonra bağlanır → çıxarma keçməməlidir."""
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        added = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )
        self.assertEqual(added.status_code, 200)
        enrollment_id = added.json()["enrollment_id"]

        self._close_current_journals()
        removed = client.post(
            reverse("registrar:journal_guest_remove", args=[self.offering.id]),
            {"enrollment": enrollment_id},
        )
        self.assertNotEqual(removed.status_code, 200)
        self.assertEqual(removed.status_code, 409)
        with bypass_rls():
            # Bağlandıqdan sonra sətir OLDUĞU KİMİ qalır — status dəyişmir.
            self.assertEqual(Enrollment.objects.get(pk=enrollment_id).status, Enrollment.Status.ENROLLED)

    def test_lookup_surfaces_close_with_the_journal(self):
        """Kilidli jurnalda namizəd lookup-ları ümumiyyətlə açılmır (404)."""
        self._close_current_journals()
        client = self._client(self.coordinator)
        for name in ("registrar:journal_guest_group_search", "registrar:journal_guest_student_search"):
            self.assertEqual(client.get(reverse(name, args=[self.offering.id])).status_code, 404)


class PastPeriodRosterTest(_FrozenRosterBase):
    """(B) + (E) — keçmiş dövrün jurnalı və tarixi transkript toxunulmazdır."""

    def test_probe_b_service_add_into_past_period_is_refused(self):
        with bypass_rls():
            self.assertFalse(guest_roster.period_allows_roster(self.past_period))
            self.assertFalse(guest_roster.roster_is_open(self.past_offering))
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(
                    offering=self.past_offering, student=self.guest, by_user=self.coordinator
                )
            self.assertFalse(
                Enrollment.objects.filter(offering=self.past_offering, student=self.guest).exists(),
            )

    def test_probe_e_historic_transcript_row_count_does_not_change(self):
        """ƏN PİS HAL: bağlı semestrə əlavə transkripti BÜYÜTMƏMƏLİDİR."""
        with bypass_rls():
            before = _transcript_row_count(self.guest, self.org)
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(
                    offering=self.past_offering, student=self.guest, by_user=self.coordinator
                )
            after = _transcript_row_count(self.guest, self.org)
        self.assertEqual(after, before)

    def test_reopen_does_not_unfreeze_a_past_period(self):
        """İcazə üst-üstə düşməsi: RİM həm bağlayır, həm siyahını idarə edir.

        Kilidi geri AÇMAQ (``reopen_journals``) keçmiş semestri açmır — dövr
        qapısı ayrıca dayanır. Yəni jurnalı bağlayan şəxs onu açıb tarixi
        transkripti dəyişə bilmir.
        """
        with bypass_rls():
            journal_close.close_journals(organization=self.org, period=self.past_period, by_user=self.rim)
            journal_close.reopen_journals(
                organization=self.org, period=self.past_period, by_user=self.rim, reason="səhv bağlama"
            )
            self.assertFalse(guest_roster.roster_is_open(self.past_offering))
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(offering=self.past_offering, student=self.guest, by_user=self.rim)

    def test_http_add_into_past_period_is_refused(self):
        client = self._client(self.coordinator)
        response = client.post(
            reverse("registrar:journal_guest_add", args=[self.past_offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])


class FrozenRosterSurfaceTest(_FrozenRosterBase):
    """Səth: düymə ümumiyyətlə görünməsin (gizlətmək tək qapı deyil — əlavədir)."""

    def test_past_period_offering_is_absent_from_roster_journal_list(self):
        client = self._client(self.coordinator)
        response = client.get(reverse("registrar:journal_list"))
        ids = {str(offering.id) for offering in response.context["offerings"]}
        self.assertIn(str(self.offering.id), ids)
        self.assertNotIn(str(self.past_offering.id), ids)

    def test_teacher_keeps_own_past_journals_in_the_list(self):
        """Dövr süzgəci YALNIZ əhatə budağına aiddir — müəllimin tarixçəsi qalır.

        Müəllim görünüşü DEFAULT cari semestri seçir (mövcud davranış), ona görə
        keçmiş il AÇIQ filtrlə istənilir: mühüm olan odur ki, `base_qs` müəllimin
        öz köhnə jurnalını ATMIR.
        """
        client = self._client(self.teacher)
        response = client.get(reverse("registrar:journal_list"), {"year": "2019/2020"})
        ids = {str(offering.id) for offering in response.context["offerings"]}
        self.assertIn(str(self.past_offering.id), ids)

    def test_coordinator_cannot_reach_past_journal_even_with_explicit_year(self):
        """Süzgəc GET parametri ilə açıla bilməz — queryset səviyyəsindədir."""
        client = self._client(self.coordinator)
        response = client.get(reverse("registrar:journal_list"), {"year": "2019/2020"})
        ids = {str(offering.id) for offering in response.context["offerings"]}
        self.assertNotIn(str(self.past_offering.id), ids)

    def test_button_is_hidden_but_page_still_opens_for_closed_journal(self):
        self._close_current_journals()
        client = self._client(self.coordinator)
        response = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage_roster"])
        self.assertTrue(response.context["roster_frozen_reason"])
        self.assertNotContains(response, "data-jgs-open")

    def test_button_is_hidden_on_past_period_journal(self):
        client = self._client(self.coordinator)
        response = client.get(reverse("registrar:journal_detail", args=[self.past_offering.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage_roster"])
        self.assertNotContains(response, "data-jgs-open")

    def test_open_current_journal_still_shows_the_button(self):
        """Reqressiya qapısı: qapı düz işi BLOKLAMAMALIDIR."""
        client = self._client(self.coordinator)
        response = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertTrue(response.context["can_manage_roster"])
        self.assertEqual(response.context["roster_frozen_reason"], "")
        self.assertContains(response, "data-jgs-open")


class JournalListContextRosterFilterTest(_FrozenRosterBase):
    """`page_contexts` səviyyəsində eyni süzgəc (profil bölməsi də bu yoldan gedir)."""

    def test_context_builder_filters_past_periods_for_roster_scope(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.coordinator
        request.organization = self.org
        with bypass_rls():
            context = page_contexts.journal_list_context(self.coordinator, request=request)
        ids = {str(offering.id) for offering in context["offerings"]}
        self.assertIn(str(self.offering.id), ids)
        self.assertNotIn(str(self.past_offering.id), ids)
