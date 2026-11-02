import base64
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.accounts.services import reviewed_targeted_credentials as op
from apps.workload.tests.factories import activate_member, make_org, make_structure


class TargetedPendingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.pem = cls.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        der = cls.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        cls.fingerprint = hashlib.sha256(der).hexdigest()

    def setUp(self):
        self.org = make_org("targeted-private")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.user = get_user_model().objects.create_user(
            "targeted-private-teacher", first_name="First", last_name="Last", password="old-private"
        )
        self.other = get_user_model().objects.create_user("unrelated-private", password="unchanged-private")
        activate_member(self.org, self.user, "teacher")
        self.user.profile.organization = self.org
        self.user.profile.patronymic = "Father"
        self.user.profile.access_state = "active"
        self.user.profile.email_verified = False
        self.user.profile.password_change_required = True
        self.user.profile.save()
        self.patches = [
            patch.object(op, "ORG", str(self.org.pk)),
            patch.object(op, "FINGERPRINT", self.fingerprint),
            patch.dict(
                op.BATCHES, {"staff-seven": [(self.user.pk, self.user.username, "First", "Last", "Father")]}, clear=True
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.public = Path(self.directory.name) / "public.pem"
        self.public.write_bytes(self.pem)
        self.output = Path(self.directory.name) / "result.enc.json"

    def run_op(self, **kwargs):
        return op.issue(organization=self.org, actor=self.actor, batch="staff-seven", **kwargs)

    def test_dry_is_readonly_and_has_no_identity_password(self):
        before = self.user.password
        result = self.run_op()
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, before)
        self.assertEqual(result["eligible"], 1)
        self.assertNotIn(self.user.username, json.dumps(result))
        self.assertFalse(self.output.exists())

    def test_apply_encrypted_csv_only_exact_target_and_stale_repeat_refused(self):
        unrelated = self.other.password
        dry = self.run_op()
        result = self.run_op(apply=True, baseline=dry["baseline"], public_key=self.public, output=self.output)
        self.assertEqual(result["issued"], 1)
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.other.password, unrelated)
        self.assertFalse(self.user.check_password("old-private"))
        envelope = json.loads(self.output.read_bytes())
        metadata = {k: envelope[k] for k in ("format", "cipher", "key_sha256")}
        key = self.key.decrypt(
            base64.b64decode(envelope["wrapped_key"]),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        payload = json.loads(
            AESGCM(key).decrypt(
                base64.b64decode(envelope["nonce"]),
                base64.b64decode(envelope["ciphertext"]),
                json.dumps(metadata, sort_keys=True).encode(),
            )
        )
        password = payload["csv"].splitlines()[1].split(",")[-1]
        self.assertTrue(self.user.check_password(password))
        self.assertNotIn(password, self.output.read_text())
        self.assertNotIn(password, json.dumps(result))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            self.run_op(
                apply=True,
                baseline=dry["baseline"],
                public_key=self.public,
                output=Path(self.directory.name) / "second",
            )

    def test_activated_skipped_no_rotation(self):
        self.user.profile.email_verified = True
        self.user.profile.password_change_required = False
        self.user.profile.save()
        result = self.run_op()
        self.assertEqual((result["eligible"], result["skipped"]), (0, 1))

    def test_archived_skipped_never_restored(self):
        self.user.profile.access_state = "archived"
        self.user.profile.save()
        result = self.run_op()
        self.assertEqual(result["eligible"], 0)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.access_state, "archived")

    def test_username_id_and_full_identity_are_required(self):
        self.user.first_name = "Other"
        self.user.save(update_fields=["first_name"])
        with self.assertRaises(ValueError):
            self.run_op()

    def test_changed_live_hash_blocks_apply(self):
        dry = self.run_op()
        self.user.set_password("new-other-secret")
        self.user.save(update_fields=["password"])
        with self.assertRaises(ValueError):
            self.run_op(apply=True, baseline=dry["baseline"], public_key=self.public, output=self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_key_and_existing_output_do_not_change_password(self):
        before = self.user.password
        dry = self.run_op()
        self.public.write_text("invalid")
        with self.assertRaises(ValueError):
            self.run_op(apply=True, baseline=dry["baseline"], public_key=self.public, output=self.output)
        self.public.write_bytes(self.pem)
        self.output.write_text("existing-ciphertext")
        with self.assertRaises(FileExistsError):
            self.run_op(apply=True, baseline=dry["baseline"], public_key=self.public, output=self.output)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, before)
        self.assertEqual(self.output.read_text(), "existing-ciphertext")

    def test_race_activation_refusal_rolls_back(self):
        before = self.user.password
        with patch.object(op.Issuer, "_issue", return_value=[]), self.assertRaises(ValueError):
            self.run_op(apply=True, baseline=self.run_op()["baseline"], public_key=self.public, output=self.output)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, before)

    def test_cross_tenant_actor_refused(self):
        self.actor.profile.organization = None
        self.actor.profile.save(update_fields=["organization"])
        with self.assertRaises(ValueError):
            self.run_op()

    def test_student_current_master_code_group_and_pending_guard(self):
        from apps.registrar.models import Curriculum, StudentAcademicRecord

        structure = make_structure(self.org, code="TARGETMASTER")
        structure["program"].degree_level = "master"
        structure["program"].save(update_fields=["degree_level"])
        structure["group"].name = "510/6BİEO"
        structure["group"].save(update_fields=["name"])
        curriculum = Curriculum.objects.create(organization=self.org, program=structure["program"], admission_year=2026)
        activate_member(self.org, self.user, "student")
        self.user.profile.institutional_identifier = "10127"
        self.user.profile.save(update_fields=["institutional_identifier"])
        record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.user,
            program=structure["program"],
            curriculum=curriculum,
            group=structure["group"],
            admission_year=2026,
        )
        with patch.dict(
            op.BATCHES,
            {"staff-seven": [(self.user.pk, self.user.username, "First", "Last", "Father", "10127")]},
            clear=True,
        ):
            self.assertEqual(self.run_op()["eligible"], 1)
            record.status = "leave"
            record.save(update_fields=["status"])
            with self.assertRaises(ValueError):
                self.run_op()

    def test_behruz_leave_case_credentials_only_academic_state_unchanged(self):
        from apps.registrar.models import Curriculum, StudentAcademicRecord

        structure = make_structure(self.org, code="TARGETLEAVE")
        structure["program"].name = "İqtisadiyyatın tənzimlənməsi"
        structure["program"].save(update_fields=["name"])
        structure["group"].name = "404/5IHT"
        structure["group"].save(update_fields=["name"])
        curriculum = Curriculum.objects.create(organization=self.org, program=structure["program"], admission_year=2024)
        activate_member(self.org, self.user, "student")
        self.user.profile.institutional_identifier = "9622"
        self.user.profile.save(update_fields=["institutional_identifier"])
        record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.user,
            program=structure["program"],
            curriculum=curriculum,
            group=structure["group"],
            admission_year=2024,
            status="academic_leave",
        )
        before = StudentAcademicRecord.objects.filter(pk=record.pk).values().get()
        pin = [(self.user.pk, self.user.username, "First", "Last", "Father", "9622")]
        with patch.dict(op.BATCHES, {"behruz-one": pin}, clear=True):
            dry = op.issue(organization=self.org, actor=self.actor, batch="behruz-one")
            self.assertEqual((dry["eligible"], dry["academic_review_required"]), (1, 1))
            applied = op.issue(
                organization=self.org,
                actor=self.actor,
                batch="behruz-one",
                apply=True,
                baseline=dry["baseline"],
                public_key=self.public,
                output=self.output,
            )
            self.assertEqual(applied["issued"], 1)
            self.assertEqual(StudentAcademicRecord.objects.filter(pk=record.pk).values().get(), before)

    def turkan_op(self, **kwargs):
        pin = [(self.user.pk, self.user.username, "First", "Last", "Father")]
        with patch.dict(op.BATCHES, {"turkan-one": pin}, clear=True):
            return op.issue(organization=self.org, actor=self.actor, batch="turkan-one", **kwargs)

    def test_turkan_pending_encrypted_only_and_old_baseline_cannot_rotate_again(self):
        # Reuse the complete authenticated decrypt, unrelated-user and stale-repeat assertions.
        with patch.object(self, "run_op", self.turkan_op):
            self.test_apply_encrypted_csv_only_exact_target_and_stale_repeat_refused()

    def test_turkan_requires_never_personally_configured_account(self):
        from django.utils import timezone

        changes = [
            ("email_verified", True),
            ("password_change_required", False),
            ("profile_completed_at", timezone.now()),
        ]
        for field, value in changes:
            with self.subTest(field=field):
                profile = self.user.profile
                before = getattr(profile, field)
                setattr(profile, field, value)
                profile.save(update_fields=[field])
                self.assertEqual(self.turkan_op()["eligible"], 0)
                setattr(profile, field, before)
                profile.save(update_fields=[field])
        self.user.last_login = timezone.now()
        self.user.save(update_fields=["last_login"])
        self.assertEqual(self.turkan_op()["eligible"], 0)

    def test_turkan_personal_activation_after_dry_changes_guard_without_issuance(self):
        from django.utils import timezone

        dry = self.turkan_op()
        before = self.user.password
        self.user.last_login = timezone.now()
        self.user.save(update_fields=["last_login"])
        with self.assertRaises(ValueError):
            self.turkan_op(apply=True, baseline=dry["baseline"], public_key=self.public, output=self.output)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, before)
        self.assertFalse(self.output.exists())

    def test_turkan_teacher_membership_required_assistant_only_not_sufficient(self):
        from django.apps import apps

        Membership = apps.get_model("organizations.Membership")
        Membership.objects.filter(user=self.user, organization=self.org).update(is_active=False)
        activate_member(self.org, self.user, "assistant")
        self.assertEqual(self.turkan_op()["eligible"], 0)

    def test_turkan_fixed_id_refuses_other_same_name_account(self):
        pin = [(7099, self.user.username, "First", "Last", "Father")]
        with patch.dict(op.BATCHES, {"turkan-one": pin}, clear=True), self.assertRaises(ValueError):
            op.issue(organization=self.org, actor=self.actor, batch="turkan-one")
