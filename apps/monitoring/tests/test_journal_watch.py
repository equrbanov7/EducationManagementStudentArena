from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.monitoring import journal_watch_config as rules
from apps.monitoring.journal_watch_mail import deliver_confirmation, deliver_journal_watch, recover_journal_watch_outbox
from apps.monitoring.journal_watch_models import (
    JournalWatchBatch,
    JournalWatchEvent,
    JournalWatchMailItem,
    JournalWatchRecipient,
    JournalWatchRoute,
    PersonKind,
    WatchKind,
)
from apps.registrar import corrections, gradebook
from apps.registrar.models import Lesson, LessonMark
from apps.subject_folder.tests.factories import (
    activate_member,
    add_lesson,
    enroll,
    make_offering,
    make_org,
    make_period,
    make_student,
    make_subject,
    make_teacher,
    make_user,
)
from core.rls import bypass_rls


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", SITE_URL="https://synthetic.test")
class JournalWatchTests(TestCase):
    def setUp(self):
        super().setUp()
        tenant_scope = bypass_rls()
        tenant_scope.__enter__()
        self.addCleanup(tenant_scope.__exit__, None, None, None)
        self.org = make_org()
        self.teacher = make_teacher(self.org)
        self.student = make_student(self.org)
        self.head = make_user("watchhead")
        role = activate_member(self.org, self.head, "ikt_rehber", permissions=["system.monitoring.view"])
        role.is_system = True
        role.save(update_fields=["is_system"])
        self.req = RequestFactory().get("/")
        self.req.user = self.head
        self.req.organization = self.org
        today = timezone.localdate()
        period = make_period(self.org, start=today - timedelta(days=10), end=today + timedelta(days=10))
        self.offering = make_offering(self.org, subject=make_subject(self.org), period=period, instructor=self.teacher)
        self.enrollment = enroll(self.offering, self.student)
        self.lesson = add_lesson(self.offering, self.teacher)
        self.rec = JournalWatchRecipient.objects.create(
            organization=self.org, email="synthetic@example.test", verified_at=timezone.now()
        )

    def watch(self, kind=PersonKind.STUDENT, events=WatchKind.values, rec=None, person=None):
        return rules.save_watch(
            request=self.req,
            person_kind=kind,
            person_id=(person or (self.student if kind == PersonKind.STUDENT else self.teacher)).pk,
            events=events,
            recipient_ids=[(rec or self.rec).pk],
        )

    def entry(self, status, score=None, enrollment=None):
        return {
            "lesson_id": self.lesson.pk,
            "enrollment_id": (enrollment or self.enrollment).pk,
            "status": status,
            "score": score,
        }

    def mark(self, *entries, **kwargs):
        return gradebook.save_marks(
            offering=self.offering, by_user=self.teacher, entries=entries, enforce_day=False, **kwargs
        )

    def due(self, **filters):
        batch = JournalWatchBatch.objects.get(**filters)
        if not batch.immediate:
            JournalWatchRecipient.objects.filter(pk=batch.recipient_id).update(
                cooldown_until=timezone.now() - timedelta(seconds=1)
            )
        batch.send_after = timezone.now() - timedelta(seconds=1)
        batch.save(update_fields=["send_after"])
        return batch

    def test_saved_cell_transitions_overlap_resave_and_cooldown(self):
        self.watch()
        self.watch(PersonKind.ACTOR)
        self.mark(self.entry("absent"), self.entry("absent"))
        self.mark(self.entry("absent"))
        self.mark(self.entry("present", 7))
        self.mark(self.entry("present"))
        self.mark(self.entry("clear"), full_edit=True, override_locks=True, full_reason="Synthetic correction")
        events = JournalWatchEvent.objects.order_by("created_at")
        self.assertEqual(
            list(events.values_list("kind", "old_value", "new_value", "is_correction")),
            [
                ("absent", "—", "qb", False),
                ("score", "qb", "iə 7", True),
                ("present", "iə 7", "iə", True),
                ("clear", "iə", "—", True),
            ],
        )
        for e in events:
            self.assertEqual(
                (e.actor_id, e.student_id, e.lesson_id, e.offering_id),
                (self.teacher.pk, self.student.pk, self.lesson.pk, self.offering.pk),
            )
            self.assertTrue(e.actor_label and e.student_label and e.offering_label)
        self.assertEqual(JournalWatchBatch.objects.count(), 2)
        self.assertEqual(JournalWatchMailItem.objects.count(), 4)
        first = JournalWatchBatch.objects.get(immediate=True)
        self.assertLessEqual(first.send_after, timezone.now())
        deliver_journal_watch(str(self.org.pk), str(first.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("1", mail.outbox[0].body)
        later = JournalWatchBatch.objects.get(immediate=False)
        self.assertGreater(later.send_after, timezone.now())
        deliver_journal_watch(str(self.org.pk), str(later.pk))
        self.assertEqual(len(mail.outbox), 1)
        batch = self.due(immediate=False)
        deliver_journal_watch(str(self.org.pk), str(batch.pk))
        deliver_journal_watch(str(self.org.pk), str(batch.pk))
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("3", mail.outbox[1].body)
        self.assertNotIn(self.student.get_full_name(), mail.outbox[1].body)
        self.assertIn(str(batch.pk), mail.outbox[1].extra_headers["Message-ID"])
        self.assertEqual(mail.outbox[1].to, [self.rec.email])

    def test_independent_routes_same_person_and_overlapping_subscriptions(self):
        second = JournalWatchRecipient.objects.create(
            organization=self.org, email="scores@example.test", verified_at=timezone.now()
        )
        self.watch(events=[WatchKind.ABSENT])
        self.watch(events=[WatchKind.SCORE], rec=second)
        self.watch(events=[WatchKind.SCORE], rec=second)
        self.watch(PersonKind.ACTOR, events=[WatchKind.SCORE], rec=second)
        with (
            patch("apps.monitoring.journal_watch_events._dispatch") as dispatch,
            self.captureOnCommitCallbacks(execute=True),
        ):
            # Only the outbox wakeup runs after persistence. Normal gradebook notifications
            # use a separate integration and do not contribute to journal-watch messages.
            self.mark(self.entry("absent"))
        dispatch.assert_called_once()
        _, _, when = dispatch.call_args.args
        self.assertLessEqual(when, timezone.now())
        self.mark(self.entry("present", 6))
        self.assertEqual(JournalWatchEvent.objects.count(), 2)
        self.assertEqual(
            list(
                JournalWatchMailItem.objects.order_by("event__created_at").values_list(
                    "recipient__email", "event__kind"
                )
            ),
            [(self.rec.email, "absent"), (second.email, "score")],
        )

    def test_student_target_event_type_and_unsubmitted_placeholders(self):
        self.watch(events=[WatchKind.CHANGE])
        self.assertEqual(JournalWatchEvent.objects.count(), 0)
        self.mark()
        other = enroll(self.offering, make_student(self.org))
        self.mark(self.entry("present"), self.entry("absent", enrollment=other))
        self.mark(self.entry("present", 5, enrollment=other))
        self.assertFalse(JournalWatchEvent.objects.exists())
        self.mark(self.entry("present", 9))
        self.assertEqual(JournalWatchEvent.objects.get().old_value, "iə")
        Lesson.objects.filter(pk=self.lesson.pk).update(is_passive=True)
        self.mark(self.entry("absent"))
        self.assertEqual(JournalWatchEvent.objects.count(), 1)

    def test_formal_correction_and_outer_rollback(self):
        self.watch()
        self.mark(self.entry("absent"))
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.mark(self.entry("present"))
            raise RuntimeError("synthetic rollback")
        self.assertEqual(JournalWatchEvent.objects.count(), 1)
        mark = LessonMark.objects.get(lesson=self.lesson, enrollment=self.enrollment)
        self.assertEqual(mark.status, "absent")
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            corrections.apply_correction(
                mark=mark,
                field="attendance",
                new_status="present",
                reason="other",
                note="Synthetic correction",
                document=SimpleUploadedFile("basis.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf"),
                by_user=self.teacher,
            )
        self.assertEqual(
            list(JournalWatchEvent.objects.order_by("created_at").values_list("old_value", "new_value")),
            [("—", "qb"), ("qb", "iə")],
        )

    def test_address_verification_replay_delivery_recovery_and_revocation(self):
        rec = rules.request_recipient(request=self.req, email="Test2@EXAMPLE.TEST")
        self.assertIsNone(rec.verified_at)
        with self.assertRaises(ValidationError):
            self.watch(rec=rec)
        with self.assertRaises(ValidationError):
            rules.request_recipient(request=self.req, email=rec.email)
        with patch.object(deliver_confirmation, "delay") as schedule_confirmation:
            recover_journal_watch_outbox()
            schedule_confirmation.assert_called_once_with(str(self.org.pk), str(rec.pk))
        deliver_confirmation(str(self.org.pk), str(rec.pk))
        deliver_confirmation(str(self.org.pk), str(rec.pk))
        self.assertEqual(len(mail.outbox), 1)
        url = mail.outbox[0].body.splitlines()[-1]
        endpoint, token = url.split("#")
        self.assertTrue(endpoint.endswith("/confirm/"))
        with self.assertRaises(ValidationError):
            rules.confirm_recipient(token=token + "invalid")
        rules.confirm_recipient(token=token)
        with self.assertRaises(ValidationError):
            rules.confirm_recipient(token=token)
        self.watch(rec=rec)
        self.mark(self.entry("present"))
        batch = self.due()
        rules.delete_recipient(request=self.req, recipient_id=rec.pk)
        deliver_journal_watch(str(self.org.pk), str(batch.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(JournalWatchEvent.objects.exists())

    def test_retry_backoff_and_cancel_disabled_route(self):
        watch = self.watch()
        self.mark(self.entry("absent"))
        batch = self.due()
        with (
            patch("apps.monitoring.journal_watch_mail.EmailMessage.send", side_effect=OSError("synthetic")),
            self.assertLogs("apps.monitoring.journal_watch_mail", level="ERROR"),
        ):
            deliver_journal_watch(str(self.org.pk), str(batch.pk))
        batch.refresh_from_db()
        self.assertEqual(batch.attempts, 1)
        self.assertGreater(batch.send_after, timezone.now())
        self.assertIsNone(batch.sent_at)
        self.due()
        with patch.object(deliver_journal_watch, "delay") as schedule:
            recover_journal_watch_outbox()
            schedule.assert_called_once_with(str(self.org.pk), str(batch.pk))
        watch.is_active = False
        watch.save(update_fields=["is_active"])
        deliver_journal_watch(str(self.org.pk), str(batch.pk))
        batch.refresh_from_db()
        self.assertIsNotNone(batch.cancelled_at)
        self.assertEqual(mail.outbox, [])

    def test_person_scope_role_scope_and_cross_tenant_recipient(self):
        second = make_org()
        foreign = make_student(second)
        self.assertEqual(rules.search_people(self.req, PersonKind.STUDENT, foreign.username), [])
        self.assertEqual(
            [p["id"] for p in rules.search_people(self.req, PersonKind.ACTOR, self.teacher.username)],
            [str(self.teacher.pk)],
        )
        self.assertEqual(rules.search_people(self.req, PersonKind.ACTOR, self.student.username), [])
        with self.assertRaises(ValidationError):
            self.watch(person=foreign)
        wrong = JournalWatchRecipient.objects.create(
            organization=second, email="elsewhere@example.test", verified_at=timezone.now()
        )
        with self.assertRaises(ValidationError):
            self.watch(rec=wrong)
        watch = self.watch()
        if connection.vendor == "postgresql":
            with self.assertRaises(IntegrityError), transaction.atomic():
                JournalWatchRoute.objects.create(organization=self.org, watch=watch, recipient=wrong)
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS jw_route_recipient_org IMMEDIATE")
        for user in (self.teacher, self.org.owner, foreign):
            self.req.user = user
            with self.assertRaises(PermissionDenied):
                rules.watch_context(self.req)
        self.req.user = self.head
        self.req.is_view_as = True
        with self.assertRaises(PermissionDenied):
            rules.delete_watch(request=self.req, watch_id=watch.pk)

    @override_settings(JOURNAL_WATCH_CONFIRMATION_HOURLY_LIMIT=1)
    def test_verification_budget_survives_address_removal_and_errors_do_not_log_addresses(self):
        rec = rules.request_recipient(request=self.req, email="limited@example.test")
        with (
            patch("apps.monitoring.journal_watch_mail.EmailMessage.send", side_effect=OSError(rec.email)),
            self.assertLogs("apps.monitoring.journal_watch_mail", level="ERROR") as logs,
        ):
            deliver_confirmation(str(self.org.pk), str(rec.pk))
        self.assertNotIn(rec.email, " ".join(logs.output))
        rec.refresh_from_db()
        self.assertEqual(rec.confirmation_attempts, 1)
        self.assertGreater(rec.confirmation_next_at, timezone.now())
        rules.delete_recipient(request=self.req, recipient_id=rec.pk)
        with self.assertRaises(ValidationError):
            rules.request_recipient(request=self.req, email="second@example.test")
        self.assertFalse(JournalWatchRecipient.objects.filter(email="second@example.test").exists())

    def test_restricted_postgres_tenant_cannot_read_or_write_foreign_watch_rows(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row-level security")
        second = make_org()
        foreign = JournalWatchRecipient.objects.create(organization=second, email="foreign@example.test")
        self.watch()
        self.mark(self.entry("absent"))
        with connection.cursor() as cur:
            cur.execute("SET LOCAL ROLE rls_app_role")
            try:
                cur.execute(
                    "SELECT set_config('app.bypass_rls','off',true), set_config('app.current_org_id',%s,true)",
                    [str(self.org.pk)],
                )
                self.assertTrue(JournalWatchRecipient.objects.filter(pk=self.rec.pk).exists())
                self.assertFalse(JournalWatchRecipient.objects.filter(pk=foreign.pk).exists())
                with self.assertRaises(DatabaseError), transaction.atomic():
                    JournalWatchRecipient.objects.create(organization=second, email="blocked@example.test")
                cur.execute("SELECT set_config('app.current_org_id',%s,true)", [str(second.pk)])
                self.assertFalse(JournalWatchEvent.objects.exists())
                self.assertFalse(JournalWatchBatch.objects.exists())
                self.assertFalse(JournalWatchMailItem.objects.exists())
            finally:
                cur.execute("RESET ROLE")
                cur.execute("SELECT set_config('app.bypass_rls','on',true)")

    def test_effective_and_actual_user_saved_on_behalf_of_another(self):
        actual = make_teacher(self.org, "actual")
        self.watch(kind=PersonKind.ACTOR, person=actual, events=[WatchKind.SCORE])
        self.req.is_view_as = True
        self.req.real_user = actual
        self.mark(self.entry("present", 8), request=self.req)
        event = JournalWatchEvent.objects.get()
        self.assertEqual((event.actor_id, event.real_actor_id), (self.teacher.pk, actual.pk))
        self.assertEqual(event.real_actor_label, actual.get_full_name())
        batch = JournalWatchBatch.objects.get()
        deliver_journal_watch(str(self.org.pk), str(batch.pk))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(UNIVERSITY_MODE=True)
    def test_real_profile_and_endpoints_require_the_official_role(self):
        from django.urls import reverse

        from apps.appeals.tests.test_creation import _assign_user_to_org
        from core.roles import ProfileRole

        viewer = make_user("observer")
        activate_member(self.org, viewer, "watch_observer", permissions=["system.monitoring.view"])
        self.watch()
        self.mark(self.entry("absent"))
        self.mark(self.entry("present", 8))
        endpoint = reverse("monitoring:journal_watch_people")
        config = reverse("monitoring:journal_watch_configure")
        profile = reverse("accounts:profile") + "?section=journal-watch"
        for user, role, name in (
            (self.head, ProfileRole.ORG_ADMIN, "ikt_rehber"),
            (viewer, ProfileRole.MEMBER, "watch_observer"),
            (self.teacher, ProfileRole.TEACHER, "teacher"),
            (self.student, ProfileRole.STUDENT, "student"),
        ):
            with self.subTest(role=name):
                _assign_user_to_org(user, self.org, role, name)
                self.client.force_login(user)
                session = self.client.session
                session["active_organization"] = self.org.slug
                session.save()
                page = self.client.get(profile)
                lookup = self.client.post(endpoint, {"kind": "actor", "q": self.teacher.username})
                if user == self.head:
                    self.assertContains(page, "data-jw-form")
                    self.assertContains(page, "q/b")
                    self.assertContains(page, "i/e · 8 bal")
                    self.assertContains(page, self.student.get_full_name())
                    self.assertEqual(lookup.status_code, 200)
                    self.assertEqual(lookup.json()["people"][0]["id"], str(self.teacher.pk))
                else:
                    self.assertNotIn(b"data-jw-form", page.content)
                    self.assertNotIn(b'data-section="journal-watch"', page.content)
                    self.assertEqual(lookup.status_code, 403)
                    denied = self.client.post(config, {"action": "remove_recipient", "recipient_id": self.rec.pk})
                    self.assertEqual(denied.status_code, 403)
        self.assertTrue(JournalWatchRecipient.objects.filter(pk=self.rec.pk).exists())

    def test_mailbox_link_prefetch_and_csrf_safe_confirmation(self):
        from django.test import Client
        from django.urls import reverse

        rec = rules.request_recipient(request=self.req, email="csrf@example.test")
        deliver_confirmation(str(self.org.pk), str(rec.pk))
        url = reverse("monitoring:journal_watch_confirm")
        token = mail.outbox[0].body.split("#")[-1].strip()
        anonymous = Client(enforce_csrf_checks=True)
        get = anonymous.get(url)
        self.assertEqual(get.status_code, 200)
        self.assertEqual(get["Referrer-Policy"], "same-origin")
        self.assertContains(get, 'name="referrer" content="same-origin"')
        self.assertNotIn(token.encode(), get.content)
        rec.refresh_from_db()
        self.assertIsNone(rec.verified_at)
        self.assertEqual(anonymous.post(url, {"token": token}).status_code, 403)
        data = {"token": token, "csrfmiddlewaretoken": anonymous.cookies["csrftoken"].value}
        self.assertEqual(anonymous.post(url, data, HTTP_ORIGIN="https://foreign.test").status_code, 403)
        self.assertEqual(anonymous.post(url, data, HTTP_ORIGIN="http://testserver").status_code, 200)
        rec.refresh_from_db()
        self.assertIsNotNone(rec.verified_at)
        self.assertEqual(anonymous.post(url, data, HTTP_ORIGIN="http://testserver").status_code, 400)
