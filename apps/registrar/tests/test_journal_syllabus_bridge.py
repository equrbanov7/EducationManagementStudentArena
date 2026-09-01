"""Jurnal ↔ sillabus körpüsü: vəziyyət banneri, oxu paneli, tələbə görünüşü + PDF.

Üç qapı yoxlanılır:
  1. müəllim jurnalında hansı banner çıxır (yoxdur / gözləyir / düzəliş / rədd
     / təsdiqlənib) və jurnalın KİLİDLƏNMƏDİYİ;
  2. ``offering_syllabus_json`` — kim, hansı versiyanı görür (fail-closed);
  3. tələbə YALNIZ təsdiqlənmiş nüsxəni görür, PDF onu qaytarır.
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import services as registrar_services
from apps.registrar.models import Curriculum, Enrollment, Program, StudentAcademicRecord, Subject
from apps.syllabus import services as syllabus_services
from apps.syllabus.constants import SectionKey
from apps.syllabus.tests.factories import PLAN_HOURS, complete_section_data
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

#: Canlı MyEdu xanası (``sillabus_yoxlama_formasi``, uniqid ``xT3TV90663lSdMvRT6LL``,
#: id=26): çoxsətirli, HTML entity daşıyan və NK-nın 348 nömrəli qərarına istinad
#: edən ƏSL qayda mətni.  Köçürmə onu ``assess.note``-a yazır.
LEGACY_ASSESSMENT_COLUMN = (
    "1.\tİmtahandan əvvəl məsləhət saatları təşkil olunur.\r\n"
    "2.\tTələbələrin imtahana buraxılması fak&uuml;ltə dekanı tərəfindən həll edilir. "
    "İmtahanlar Nazirlər Kabinetinin 348 n&ouml;mrəli qərarı ilə təsdiq edilmiş "
    "&ldquo;kredit sistemi ilə təlimin təşkili Qaydaları&rdquo;na əsasən aparılır."
)

#: ⚠️ Qoruma NAXIŞA baxır, konkret sətrə YOX.
#: Mutasiya sınağı (2026-08-31): qurucudan qorumanı çıxaranda blok
#: «10 + 10 + 0 + 0 + 50 = 70 bal» verdi — köhnə ``assertNotIn("10 + 10 + 0 + 30 + 50")``
#: bunu BURAXDI, çünki yalnız BİR konkret uydurma cütlüyü tanıyırdı.  Naxış isə
#: qurulmuş bal bölgüsünün BÜTÜN formasını tutur: beş toplanan + cəm.
FABRICATED_SPLIT_RE = re.compile(r"\d+ \+ \d+ \+ \d+ \+ \d+ \+ \d+ = ")


class JournalSyllabusBridgeTest(TestCase):
    """Hər test öz sillabus vəziyyətini qurur, ona görə `setUp` (setUpTestData yox)."""

    def setUp(self):
        with bypass_rls():
            self.owner = User.objects.create_user("jsb_owner", "jsb_owner@qku.edu.az", "pw")
            self.org = Organization.objects.create(
                name="JSB Univ",
                slug="jsb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.chair_unit = OrgUnit.objects.create(
                organization=self.org, name="JSB Kafedra", slug="jsb-chair", unit_type=OrgUnitType.DEPARTMENT
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="JSB-G1", slug="jsb-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            self.subject = Subject.objects.create(organization=self.org, code="JSB101", name="Alqoritmlər")
            self.teacher = User.objects.create_user("jsb_teacher", "jsb_teacher@qku.edu.az", "pw")
            self.chair = User.objects.create_user("jsb_chair", "jsb_chair@qku.edu.az", "pw")
            self.student = User.objects.create_user("jsb_student", "jsb_student@qku.edu.az", "pw")
            self.stranger = User.objects.create_user("jsb_stranger", "jsb_stranger@qku.edu.az", "pw")

            self._member(self.teacher, "teacher", TEACHER_PERMS)
            self._member(self.chair, "chair_head", CHAIR_PERMS, scope_unit=self.chair_unit, level=70)
            self._member(self.student, "student", [])
            self._member(self.stranger, "student", [], suffix="-2")

            self.offering = registrar_services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
            self.offering.instructor = self.teacher
            self.offering.lesson_hours = sum(PLAN_HOURS.values())
            self.offering.save(update_fields=["instructor", "lesson_hours"])
            self.enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.offering
            )
            # Tələbənin kabinet görünüşü ``StudentAcademicRecord``-a söykənir:
            # qeyd yoxdursa ``build_student_journal_context`` ``None`` qaytarır
            # (istifadəçi bu orqda tələbə sayılmır) və panel ümumiyyətlə qurulmur.
            self.program = Program.objects.create(organization=self.org, code="JSB-PRG", name="Alqoritmlər proqramı")
            # ⚠️ ``registrar_guard_student_record_coherence`` PG trigger-i tədris
            # planının öz proqramına aid olmasını tələb edir — plansız qeyd
            # yaratmaq mümkün deyil.
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group,
                admission_year=2024,
            )

    # ── köməkçilər ───────────────────────────────────────────────────────
    def _member(self, user, role_name, permissions, *, scope_unit=None, level=50, suffix=""):
        role, _created = Role.objects.get_or_create(
            organization=self.org,
            name=f"{role_name}{suffix}",
            defaults={"display_name": role_name.title(), "level": level, "permissions": list(permissions)},
        )
        Role.objects.filter(pk=role.pk).update(
            is_active=True,
            permissions=list(permissions),
            level=level,
            scope_type=RoleScopeType.UNIT if scope_unit else RoleScopeType.ORGANIZATION,
        )
        membership, _ = Membership.objects.get_or_create(
            organization=self.org, user=user, role=role, defaults={"is_active": True}
        )
        Membership.objects.filter(pk=membership.pk).update(is_active=True, scope_unit=scope_unit)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _actor(self, user):
        return syllabus_services.resolve_actor(user, self.org)

    def _draft(self):
        actor = self._actor(self.teacher)
        syllabus, version = syllabus_services.create_draft(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            actor=actor,
            offering=self.offering,
            program=None,
            chair_unit=self.chair_unit,
            plan_hours=PLAN_HOURS,
        )
        return syllabus, version, actor

    def _fill(self, version, actor):
        for section_id, data in complete_section_data().items():
            if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
                continue
            syllabus_services.save_section(version=version, section_id=section_id, data=data, actor=actor)
        version.refresh_from_db()
        return version

    def _approved(self):
        """Uçdan-uca təsdiqlənmiş sillabus qaytarır."""
        syllabus, version, actor = self._draft()
        version = self._fill(version, actor)
        version = syllabus_services.submit(version=version, actor=actor)
        chair_actor = self._actor(self.chair)
        version = syllabus_services.start_review(version=version, actor=chair_actor)
        version = syllabus_services.approve(version=version, actor=chair_actor, comment="Uyğundur")
        syllabus.refresh_from_db()
        return syllabus, version, actor

    def _journal(self):
        return self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))

    def _json_url(self):
        return reverse("registrar:offering_syllabus_json", args=[self.offering.id])

    def _pdf_url(self):
        return reverse("registrar:offering_syllabus_pdf", args=[self.offering.id])

    # ── 1. Jurnal banneri ────────────────────────────────────────────────
    def test_missing_syllabus_warns_the_teacher_with_a_link(self):
        resp = self._journal()
        self.assertEqual(resp.status_code, 200)
        notice = resp.context["syllabus_notice"]
        self.assertEqual(notice["state"], "missing")
        self.assertTrue(notice["show_banner"])
        self.assertFalse(notice["can_open"])
        self.assertIn("section=syllabus-list", notice["action_url"])
        self.assertContains(resp, "jd2-sylbar")

    def test_pending_syllabus_says_it_is_with_the_chair(self):
        _syllabus, version, actor = self._draft()
        version = self._fill(version, actor)
        syllabus_services.submit(version=version, actor=actor)

        notice = self._journal().context["syllabus_notice"]
        self.assertEqual(notice["state"], "pending")
        self.assertEqual(notice["tone"], "info")
        self.assertTrue(notice["can_open"])
        self.assertIn("section=syllabus-editor", notice["action_url"])

    def test_revision_banner_shows_the_chair_reason(self):
        _syllabus, version, actor = self._draft()
        version = self._fill(version, actor)
        version = syllabus_services.submit(version=version, actor=actor)
        chair_actor = self._actor(self.chair)
        version = syllabus_services.start_review(version=version, actor=chair_actor)
        syllabus_services.request_revision(version=version, actor=chair_actor, reason="Ədəbiyyat yenilənməlidir")

        resp = self._journal()
        notice = resp.context["syllabus_notice"]
        self.assertEqual(notice["state"], "revision")
        self.assertEqual(notice["reason"], "Ədəbiyyat yenilənməlidir")
        self.assertContains(resp, "Ədəbiyyat yenilənməlidir")

    def test_rejected_banner_shows_the_reason(self):
        _syllabus, version, actor = self._draft()
        version = self._fill(version, actor)
        version = syllabus_services.submit(version=version, actor=actor)
        chair_actor = self._actor(self.chair)
        version = syllabus_services.start_review(version=version, actor=chair_actor)
        syllabus_services.reject(version=version, actor=chair_actor, reason="Siyasətə uyğun deyil")

        notice = self._journal().context["syllabus_notice"]
        self.assertEqual(notice["state"], "rejected")
        self.assertEqual(notice["tone"], "danger")
        self.assertEqual(notice["reason"], "Siyasətə uyğun deyil")

    def test_approved_syllabus_hides_the_banner_but_keeps_the_link(self):
        self._approved()
        resp = self._journal()
        notice = resp.context["syllabus_notice"]
        self.assertEqual(notice["state"], "approved")
        self.assertFalse(notice["show_banner"])
        self.assertTrue(notice["can_open"])
        self.assertNotContains(resp, "jd2-sylbar ")
        self.assertContains(resp, "data-sylv-open")

    def test_banner_never_locks_the_journal(self):
        """⚠️ Sahib kilidləmə istəməyib — sillabussuz müəllim bal yazmağa davam edir."""
        resp = self._journal()
        self.assertEqual(resp.context["syllabus_notice"]["state"], "missing")
        self.assertTrue(resp.context["can_edit"])

    # ── 2. Oxu paneli — giriş qapıları ───────────────────────────────────
    def test_teacher_reads_the_open_version_even_before_approval(self):
        _syllabus, version, actor = self._draft()
        version = self._fill(version, actor)
        syllabus_services.submit(version=version, actor=actor)

        resp = self._client(self.teacher).get(self._json_url())
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "staff")
        self.assertEqual(payload["version"], "v1.0")
        self.assertEqual(payload["student_note"], "")
        self.assertEqual(len(payload["blocks"]), 8)

    def test_student_gets_404_while_nothing_is_approved(self):
        _syllabus, version, actor = self._draft()
        version = self._fill(version, actor)
        syllabus_services.submit(version=version, actor=actor)

        self.assertEqual(self._client(self.student).get(self._json_url()).status_code, 404)
        self.assertEqual(self._client(self.student).get(self._pdf_url()).status_code, 404)

    def test_student_reads_the_approved_version(self):
        self._approved()
        resp = self._client(self.student).get(self._json_url())
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["mode"], "student")
        self.assertEqual(payload["status"], "approved")
        self.assertTrue(payload["student_note"])
        self.assertTrue(payload["pdf_url"].endswith("sillabus.pdf"))

    def test_unenrolled_user_is_404_not_403(self):
        """Mövcudluq sızdırılmır — jurnalın qalan səthləri ilə eyni davranış."""
        self._approved()
        self.assertEqual(self._client(self.stranger).get(self._json_url()).status_code, 404)
        self.assertEqual(self._client(self.stranger).get(self._pdf_url()).status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        self._approved()
        resp = Client().get(self._json_url())
        self.assertIn(resp.status_code, (302, 301))

    # ── 3. ⚠️ Tələbə köhnə təsdiqlənmiş versiyanı görməyə davam edir ─────
    def test_student_still_sees_v1_while_v2_awaits_approval(self):
        syllabus, _v1, actor = self._approved()
        v2 = syllabus_services.create_next_version(syllabus=syllabus, actor=actor, kind="minor")
        v2 = self._fill(v2, actor)
        syllabus_services.submit(version=v2, actor=actor)

        student_payload = self._client(self.student).get(self._json_url()).json()
        self.assertEqual(student_payload["version"], "v1.0")

        teacher_payload = self._client(self.teacher).get(self._json_url()).json()
        self.assertEqual(teacher_payload["version"], "v1.1")

    def test_student_cabinet_exposes_the_button_only_when_approved(self):
        from apps.registrar.public import build_student_journal_context

        url = f"{reverse('accounts:profile')}?section=my-journal&subject={self.enrollment.id}"
        request = self._client(self.student).get(url).wsgi_request

        section = build_student_journal_context(request, organization=self.org)["journal_student_section"]
        self.assertIsNotNone(section["detail"])
        self.assertFalse(section["detail"]["syllabus_available"])

        self._approved()
        section = build_student_journal_context(request, organization=self.org)["journal_student_section"]
        self.assertTrue(section["detail"]["syllabus_available"])

    # ── 4. PDF ───────────────────────────────────────────────────────────
    def test_student_downloads_the_approved_pdf(self):
        self._approved()
        resp = self._client(self.student).get(self._pdf_url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("sillabus-JSB101-v1.0.pdf", resp["Content-Disposition"])
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_download_is_written_to_the_shared_audit_log(self):
        from django.apps import apps as django_apps

        self._approved()
        self._client(self.student).get(self._pdf_url())
        AuditLog = django_apps.get_model("audit", "AuditLog")
        self.assertTrue(AuditLog.objects.filter(resource_type="registrar.syllabus_pdf").exists())

    # ── 5. ⚠️ Köçürülmüş sillabus: tələbə MƏNBƏNİ görür, defoltu YOX ─────
    #
    # Köçürülən sillabusun nə semestri, nə açılışı var — tələbə ona
    # ``syllabus_for_offering``-in 3-cü pilləsi (fənn + müəllim, açılışsız və
    # semestrsiz «baza sillabus») ilə çatır.  Aşağıdakı üç test məhz o yolu
    # gedir: köhnə MyEdu xanası → köçürmə borusu → tələbənin HTTP cavabı.
    def _migrate_legacy_syllabus(self):
        """Köçürmə borusunun ÖZ addımları: mənbə sətri → bölmə datası → yazı."""
        from django.utils import timezone

        from apps.legacy_import.services.rehearsal_syllabus_documents import SyllabusDocument
        from apps.legacy_import.services.rehearsal_syllabus_source import (
            SyllabusHeaderRow,
            distilled_section_row,
        )
        from apps.legacy_import.services.rehearsal_syllabus_targets import (
            ASSESSMENT_TABLE,
            EXAM_QUESTION_TABLE,
            SELF_WORK_TABLE,
            build_section_data,
        )
        from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

        rows = {
            ASSESSMENT_TABLE: (distilled_section_row(26, LEGACY_ASSESSMENT_COLUMN),),
            EXAM_QUESTION_TABLE: (distilled_section_row(1, "Sual 1: alqoritmin m&uuml;rəkkəbliyi"),),
            SELF_WORK_TABLE: (distilled_section_row(1, "Sərbəst iş m&ouml;vzusu"),),
        }
        document = SyllabusDocument(
            header=SyllabusHeaderRow(
                legacy_pk=1,
                uniqid="xT3TV90663lSdMvRT6LL",
                lesson_id=4,
                teacher_id=282,
                lesson_hours=45,
                language="az",
                active=True,
                issues=(),
            ),
            week=(),
            sections=tuple((table, rows.get(table, ())) for table in SYLLABUS_SECTION_CONTRACTS),
        )
        section_data, codes = build_section_data(document)

        with bypass_rls():
            syllabus, version = syllabus_services.import_migrated_version(
                organization=self.org,
                subject=self.subject,
                approved_at=timezone.now(),
                author=self.teacher,  # açılışsız, semestrsiz «baza sillabus»
                section_data=section_data,
                note="myedu:sillabus:1",
            )
        return syllabus, version, codes

    def test_student_of_a_migrated_syllabus_reads_the_source_rule_text(self):
        from apps.syllabus.document import BLOCK_TITLES

        _syllabus, version, _codes = self._migrate_legacy_syllabus()
        self.assertEqual(version.status, "approved")
        self.assertEqual(version.approval_source, "migration")

        payload = self._client(self.student).get(self._json_url()).json()
        self.assertEqual(payload["mode"], "student")
        blocks = {block["title"]: block["body"] for block in payload["blocks"]}
        body = blocks[str(BLOCK_TITLES["assessment"])]

        # 1) QURULMUŞ bal bölgüsü HEÇ BİR blokda yoxdur — mənbədə bölgü yoxdur,
        #    yəni hər hansı «a + b + c + d + e = ...» sətri uydurma olardı;
        for block in payload["blocks"]:
            self.assertIsNone(FABRICATED_SPLIT_RE.search(block["body"]), block["body"])
        # 2) mənbənin öz qayda mətni tələbədədir (HTML entity açılmış);
        self.assertIn("348 nömrəli qərarı", body)
        self.assertIn("fakültə dekanı", body)
        # 3) imtahan sualı da göstərilir (mənbədə 20,835 sətir);
        self.assertIn("Sual 1: alqoritmin mürəkkəbliyi", body)
        # 4) sərbəst iş mövzusunda uydurma «0 bal» yoxdur.
        self.assertEqual(blocks[str(BLOCK_TITLES["selfwork"])], "1. Sərbəst iş mövzusu")

    def test_the_migrated_pdf_is_the_same_document(self):
        """PDF ekranla EYNİ qurucudan gəlir — mətn orada da olmalıdır."""
        import fitz

        self._migrate_legacy_syllabus()
        resp = self._client(self.student).get(self._pdf_url())

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
        with fitz.open(stream=resp.content, filetype="pdf") as pdf:
            # PDF sətri səhifə eninə görə sarılır → boşluqlar normallaşdırılır.
            text = " ".join(" ".join(page.get_text() for page in pdf).split())
        self.assertIn("348 nömrəli qərarı", text)
        self.assertIsNone(FABRICATED_SPLIT_RE.search(text), text)

    def test_the_unsurfaced_assessment_note_is_counted_by_the_migration(self):
        from apps.legacy_import.services.rehearsal_syllabus_targets import (
            ASSESSMENT_NOTE_UNSURFACED,
            EXAM_QUESTIONS_UNSURFACED,
        )

        _syllabus, _version, codes = self._migrate_legacy_syllabus()

        self.assertIn(ASSESSMENT_NOTE_UNSURFACED, codes)
        self.assertIn(EXAM_QUESTIONS_UNSURFACED, codes)
