"""«Yeni dərs» köhnə dərsi dəyişmir (sahib 2026-11-26, Səliqə Qazi «Sitologiya və histologiya» 13.11).

Müəllim 13.11-ə 10:10 laboratoriya dərsi əlavə etmək istəyirdi; o saatda köhnə sistemdən gələn MÜHAZİRƏ var idi. Server
«dərs artıq var — qeydləri həmin sütuna yazın» deyib jurnalı mühazirənin sütununda açırdı, müəllim də onu ✎ ilə
laboratoriyaya çevirdi (mühazirənin 30 qeydi ilə birlikdə). İndi:

* EYNİ növ dərs o saatdadırsa (köçürülmüş dərs, MR-000125) — əvvəlki kimi həmin sütuna keçid;
* BAŞQA növ dərs o saatdadırsa — keçid YOXDUR, mesaj o dərsin adını deyir və «yeni dərs onu dəyişmir» izah edir;
* modal canlı deyir: o tarix + saatda dərs var (``taken``) / seçilən mövzu artıq keçilib — yeni dərs ayrıca sütundur.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.registrar.models import Lesson, LessonMark
from apps.registrar.tests.test_lesson_modal_backdate_patok_2026_11_15 import _Base, _prod_settings
from core.rls import bypass_rls


class NewLessonSlotTakenTest(_Base):
    prefix = "nlst"

    @staticmethod
    def day():
        return timezone.localdate() - dt.timedelta(days=5)

    def test_other_kind_at_the_same_time_does_not_jump_into_the_old_lesson(self):
        lecture = self.lesson(day=self.day(), kind="lecture")
        with bypass_rls():
            Lesson.objects.filter(pk=lecture.pk).update(topic="ontogenez toxumalar")
        with _prod_settings():
            resp = self.add(day=self.day(), kind="lab")
        ((location, status),) = resp.redirect_chain
        self.assertEqual(status, 302)
        self.assertNotIn("#jd-lesson-", location)
        (message,) = self.messages(resp)
        self.assertIn("«Mühazirə — ontogenez toxumalar»", message)
        self.assertIn("Yeni dərs mövcud dərsi dəyişmir", message)
        # Köhnə dərs toxunulmayıb, yeni dərs yaranmayıb.
        (only,) = self.lessons(date=self.day())
        self.assertEqual((only.pk, only.kind, only.topic), (lecture.pk, "lecture", "ontogenez toxumalar"))

    def test_same_kind_at_the_same_time_still_opens_the_existing_column(self):
        existing = self.lesson(day=self.day(), kind="lecture")
        with _prod_settings():
            resp = self.add(day=self.day(), kind="lecture", follow=False)
        self.assertTrue(resp["Location"].endswith(f"#jd-lesson-{existing.pk}"), resp["Location"])
        self.assertEqual(len(self.lessons(date=self.day())), 1)

    def test_other_time_creates_a_separate_lesson_and_keeps_the_old_one(self):
        lecture = self.lesson(day=self.day(), kind="lecture")
        with bypass_rls():
            LessonMark.objects.create(
                organization=self.org, lesson=lecture, enrollment=self.enrollment, status="present"
            )
        with _prod_settings():
            resp = self.add(day=self.day(), kind="lab", time="10:10|11:40")
        self.assertIn("Dərs əlavə edildi.", self.messages(resp))
        old, new = sorted(self.lessons(date=self.day()), key=lambda lesson: lesson.start_time)
        self.assertEqual((old.pk, old.kind), (lecture.pk, "lecture"))
        self.assertEqual(new.kind, "lab")
        with bypass_rls():
            self.assertEqual(LessonMark.objects.filter(lesson=old).count(), 1)

    def test_prefill_lists_taken_whole_group_slots_only(self):
        lecture = self.lesson(day=self.day(), kind="lecture")
        lab = self.lesson(day=self.day(), kind="lab", start="10:10", end="11:40")
        with bypass_rls():
            Lesson.objects.filter(pk=lecture.pk).update(topic="ontogenez toxumalar")
            Lesson.objects.filter(pk=lab.pk).update(lab_group=1)  # alt qrup dərsi — eyni saatda Lab-2 qanunidir
        taken = self.prefill(dt.time(9, 0))["taken"]
        key = f"{self.day().isoformat()}|08:30"
        self.assertEqual(taken[key], {"kind": "lecture", "label": "Mühazirə — ontogenez toxumalar"})
        self.assertNotIn(f"{self.day().isoformat()}|10:10", taken)

    def test_modal_renders_both_warnings_hidden(self):
        page = self.client_for(self.teacher).get(self.url())
        self.assertContains(page, 'data-jd-prefill-hint="taken" hidden')
        self.assertContains(page, "Yeni dərs onu dəyişmir")
