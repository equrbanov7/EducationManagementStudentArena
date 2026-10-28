"""MR46 bir jurnal/sahib üçün tam məzmun; adaş fənn və digər müəllim sillabusları dəyişmir."""

import datetime as dt
import hashlib
import io
import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.legacy_import.services.mr46_syllabus import AUTHOR, OFFERING, ORG, PERIOD, UNIQID
from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, JournalShare, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.public import import_migrated_version, section_data_map
from core.rls import bypass_rls


def plan():
    source = dict(id=8891, teacher_id=442, lesson_id=457, uniqid=UNIQID, ders_saati=90, language="az", active=1)
    source["week"] = [
        dict(
            id=147705 + i,
            uniqid=UNIQID,
            movzu=f"M&ouml;vzu {i}",
            muh_saat="2",
            sem_saat="2",
            praktiki_saat="0",
            lab_saat="0",
            qeyd="source note",
        )
        for i in range(23)
    ]
    source["sections"] = {table: [[10, f"Tam mətn {table}"]] for table in SYLLABUS_SECTION_CONTRACTS}
    source["sections"]["sillabus_serbest_is"] = [[176195 + i, f"Tapşırıq {i}"] for i in range(18)]
    return dict(
        format="mr46-syllabus/1",
        source=source,
        source_journal=dict(id=15363, teacher_id=442, lesson_id=1500, sillabus_id=8891),
    )


class MR46SyllabusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("mr46_admin", "admin@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                id=ORG, name="QKU", slug="qku", org_type="university", owner=cls.actor, status="active", is_active=True
            )
            cls.author = User.objects.create_user(id=AUTHOR, username="arus.test", first_name="Arus")
            UserProfile.objects.filter(user=cls.author).update(organization=cls.org)
            Membership.objects.create(user=cls.author, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            other = User.objects.create_user(id=8415, username="ramiz.test")
            Membership.objects.create(user=other, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            cls.period = AcademicPeriod.objects.create(
                id=PERIOD,
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            cls.subject = Subject.objects.create(
                organization=cls.org, code="QKU-1500", name="Ekoloji kartoqrafiya və coğrafi informasiya sistemləri"
            )
            group = OrgUnit.objects.create(organization=cls.org, name="Group", slug="mr46-group", unit_type="group")
            cls.offering = CourseOffering.objects.create(
                id=OFFERING,
                organization=cls.org,
                subject=cls.subject,
                period=cls.period,
                group=group,
                instructor=cls.author,
            )
            other_group = OrgUnit.objects.create(
                organization=cls.org, name="Other", slug="mr46-other", unit_type="group"
            )
            other_offering = CourseOffering.objects.create(
                organization=cls.org, subject=cls.subject, period=cls.period, group=other_group, instructor=other
            )
            cls.others = []
            for offering, period in ((other_offering, cls.period), (None, None)):
                syllabus, version = import_migrated_version(
                    organization=cls.org,
                    subject=cls.subject,
                    period=period,
                    offering=offering,
                    author=other,
                    approved_at=timezone.now(),
                    section_data={"desc": {"description": "Ramiz original"}},
                )
                cls.others.append((syllabus.pk, version.pk, section_data_map(version)))

    def run_command(self, *, apply=True, data=None, undo="", sha_bad=False):
        out = io.StringIO()
        with tempfile.NamedTemporaryFile(suffix=".json") as f:
            raw = json.dumps(data or plan(), ensure_ascii=False).encode()
            f.write(raw)
            f.flush()
            kwargs = dict(org="qku", actor="mr46_admin", apply=apply, stdout=out)
            if undo:
                kwargs["undo"] = undo
            else:
                kwargs.update(file=f.name, sha256="0" * 64 if sha_bad else hashlib.sha256(raw).hexdigest())
            call_command("recover_mr46_syllabus", **kwargs)
        return out.getvalue()

    def assert_others_unchanged(self):
        for pk, version, data in self.others:
            syllabus = Syllabus.objects.get(pk=pk)
            self.assertTrue(syllabus.is_active)
            self.assertEqual(str(syllabus.current_version_id), str(version))
            self.assertEqual(section_data_map(SyllabusVersion.objects.get(pk=version)), data)

    def test_dry_apply_full_content_approved_idempotent_and_other_teacher_untouched(self):
        self.assertIn("topics_restored=23", self.run_command(apply=False))
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())
        self.run_command()
        syllabus = Syllabus.objects.get(offering=self.offering)
        version = syllabus.current_version
        data = section_data_map(version)
        self.assertEqual(version.status, "approved")
        self.assertEqual(version.approval_source, "migration")
        self.assertIsNone(version.approved_by_id)
        self.assertEqual(syllabus.author_id, AUTHOR)
        self.assertEqual(len(data["week"]["rows"]), 23)
        self.assertEqual(data["week"]["rows"][0]["topic"], "Mövzu 0")
        self.assertEqual(len(data["self"]["topics"]), 18)
        self.assertIn("Tam mətn", data["desc"]["description"])
        self.assertIn("Tam mətn", data["assess"]["note"])
        self.assertTrue(data["info"]["research_interests"])
        self.assertIn("already_present=1", self.run_command())
        self.assertEqual(SyllabusVersion.objects.filter(syllabus=syllabus).count(), 1)
        self.assert_others_unchanged()

    def test_existing_target_syllabus_is_never_overwritten(self):
        import_migrated_version(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            offering=self.offering,
            author=self.author,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Teacher current"}},
        )
        with self.assertRaisesMessage(Exception, "existing_syllabus_no_overwrite"):
            self.run_command()
        self.assertEqual(Syllabus.objects.filter(offering=self.offering).count(), 1)
        self.assert_others_unchanged()

    def test_source_wrong_author_target_digest_or_content_loss_fails(self):
        with self.assertRaisesMessage(Exception, "plan_digest_mismatch"):
            self.run_command(sha_bad=True)
        for field, value in (("teacher_id", 977), ("id", 8892)):
            data = plan()
            data["source"][field] = value
            with self.assertRaisesMessage(Exception, "syllabus_source_scope"):
                self.run_command(data=data)
        data = plan()
        data["source"]["week"].pop()
        with self.assertRaisesMessage(Exception, "week_source_scope"):
            self.run_command(data=data)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_undo_archives_only_unchanged_import_and_repeat_is_safe(self):
        batch = self.run_command().split("batch=")[1].strip()
        self.run_command(undo=batch)
        syllabus = Syllabus.objects.get(offering=self.offering)
        self.assertFalse(syllabus.is_active)
        self.assertEqual(syllabus.versions.get().status, "archived")
        self.assertEqual(SyllabusSection.objects.filter(version__syllabus=syllabus).count(), 10)
        self.assertIn("already_undone=1", self.run_command(undo=batch))
        self.assert_others_unchanged()

    def test_undo_refuses_later_content_change_atomically(self):
        batch = self.run_command().split("batch=")[1].strip()
        syllabus = Syllabus.objects.get(offering=self.offering)
        SyllabusSection.objects.filter(version=syllabus.current_version, section_id="desc").update(
            data={"description": "later change"}
        )
        with self.assertRaisesMessage(Exception, "undo_content_or_usage_changed"):
            self.run_command(undo=batch)
        syllabus.refresh_from_db()
        self.assertTrue(syllabus.is_active)
        self.assert_others_unchanged()

    def test_shared_teacher_gets_own_syllabus_without_owner_handover(self):
        owner = get_user_model().objects.get(pk=8415)
        CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=owner)
        JournalShare.objects.create(
            organization=self.org, offering=self.offering, teacher=self.author, source="legacy", kinds=["seminar"]
        )
        self.run_command()
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.instructor_id, 8415)
        self.assertEqual(Syllabus.objects.get(offering=self.offering).author_id, AUTHOR)
        self.assert_others_unchanged()

    def test_other_owner_without_current_share_cannot_receive_this_import(self):
        CourseOffering.objects.filter(pk=self.offering.pk).update(instructor_id=8415)
        with self.assertRaisesMessage(Exception, "author_journal_access_missing"):
            self.run_command()
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_undo_refuses_later_reused_dossier_or_version(self):
        batch = self.run_command().split("batch=")[1].strip()
        syllabus = Syllabus.objects.get(offering=self.offering)
        child = Syllabus.objects.get(pk=self.others[0][0])
        child.reused_from = syllabus
        child.save(update_fields=["reused_from"])
        with self.assertRaisesMessage(Exception, "undo_content_or_usage_changed"):
            self.run_command(undo=batch)
        child.reused_from = None
        child.save(update_fields=["reused_from"])
        child_version = child.current_version
        child_version.source_version = syllabus.current_version
        child_version.save(update_fields=["source_version"])
        with self.assertRaisesMessage(Exception, "undo_content_or_usage_changed"):
            self.run_command(undo=batch)
        syllabus.refresh_from_db()
        self.assertTrue(syllabus.is_active)
        self.assertEqual(syllabus.current_version.status, "approved")

    def test_undo_refuses_later_plan_metadata_change_without_partial_archive(self):
        batch = self.run_command().split("batch=")[1].strip()
        syllabus = Syllabus.objects.get(offering=self.offering)
        version = syllabus.current_version
        original = syllabus.plan_hours_override
        Syllabus.objects.filter(pk=syllabus.pk).update(plan_hours_override={"lecture": 14, "seminar": 16})
        with self.assertRaisesMessage(Exception, "undo_content_or_usage_changed"):
            self.run_command(undo=batch)
        Syllabus.objects.filter(pk=syllabus.pk).update(plan_hours_override=original)
        SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours={"lecture": 14, "seminar": 16})
        with self.assertRaisesMessage(Exception, "undo_content_or_usage_changed"):
            self.run_command(undo=batch)
        syllabus.refresh_from_db()
        version.refresh_from_db()
        self.assertTrue(syllabus.is_active)
        self.assertEqual(version.status, "approved")
