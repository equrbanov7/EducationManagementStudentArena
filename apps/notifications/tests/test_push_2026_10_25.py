"""Sahib 2026-10-25: «bildiriş gələrkən telefonun notification-ında görünsün» — FCM push + cihaz API-si.

FCM HTTP v1 tamamilə saxtalaşdırılır (şəbəkə yoxdur): OAuth token ucu + ``messages:send``.
"""

from __future__ import annotations

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.notifications.models import InAppNotification, NotificationType, PushDevice
from apps.notifications.public import LText, create_notification, create_notification_for_users
from apps.notifications.push import config as push_config
from apps.notifications.push import dispatch
from apps.notifications.push.fcm import classify
from core.rls import bypass_rls

User = get_user_model()

ACTIVATION = "Profilini aktivləşdirdi: %(name)s"
ACTIVATION_CTX = "accounts.rim_activation"
TOKEN_A = "tok-android-" + "a" * 40
TOKEN_B = "tok-ios-" + "b" * 40


def _service_account() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "ems-test",
            "client_email": "push@ems-test.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


SERVICE_ACCOUNT = _service_account()


class _Response:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeFCM:
    """``requests.Session`` əvəzi: token ucu + ``messages:send``; ``responses[token]`` → (status, body)."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.sent = []
        self.token_requests = 0

    def __call__(self):  # requests.Session() kimi çağırılır
        return self

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        if url.endswith("/token"):
            self.token_requests += 1
            assert data["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            assert data["assertion"].count(".") == 2
            return _Response(200, {"access_token": "ya29.test", "expires_in": 3600})
        assert url == "https://fcm.googleapis.com/v1/projects/ems-test/messages:send"
        assert headers["Authorization"] == "Bearer ya29.test"
        message = json["message"]
        self.sent.append(message)
        return _Response(*self.responses.get(message["token"], (200, {"name": "projects/ems-test/messages/1"})))

    def close(self):
        pass


def _unregistered():
    return (
        404,
        {
            "error": {
                "code": 404,
                "status": "NOT_FOUND",
                "message": "Requested entity was not found.",
                "details": [
                    {"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}
                ],
            }
        },
    )


class _PushCase(TestCase):
    def setUp(self):
        cache.clear()
        push_config._load.cache_clear()
        self.addCleanup(push_config._load.cache_clear)
        self.user = User.objects.create_user("push_student", "push_student@qku.edu.az", "pw-12345-Abc!")

    def _device(self, token=TOKEN_A, user=None, **extra):
        with bypass_rls():
            return PushDevice.objects.create(user=user or self.user, token=token, platform="android", **extra)

    def _notify(self, **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return create_notification(
                recipient=self.user,
                title=LText(ACTIVATION, ACTIVATION_CTX, name="Test User"),
                link="/accounts/profile/?section=my-journal",
                notification_type=NotificationType.GRADE,
                **extra,
            )


class NoCredentialsTests(_PushCase):
    def test_without_credentials_push_is_a_noop(self):
        self._device()
        with mock.patch("apps.notifications.tasks.push_send_task.delay") as delay:
            notification = self._notify()
        delay.assert_not_called()
        self.assertFalse(push_config.is_configured())
        self.assertEqual(dispatch.deliver([notification.pk]), {"disabled": 1})

    @override_settings(FCM_SERVICE_ACCOUNT_JSON="not-json-and-not-a-file")
    def test_broken_credentials_are_treated_as_missing(self):
        self.assertFalse(push_config.is_configured())


@override_settings(FCM_SERVICE_ACCOUNT_JSON=SERVICE_ACCOUNT, SITE_URL="https://ems.example.az")
class DeliveryTests(_PushCase):
    def test_success_sends_to_every_active_device_in_device_language(self):
        self._device(TOKEN_A, language="ru-RU")
        self._device(TOKEN_B, language="")
        self._device("tok-old-" + "c" * 40, is_active=False)
        fake = FakeFCM()
        with mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            notification = self._notify()

        self.assertEqual(len(fake.sent), 2)
        by_token = {message["token"]: message for message in fake.sent}
        self.assertEqual(by_token[TOKEN_A]["notification"]["title"], "Профиль активирован: Test User")
        self.assertEqual(by_token[TOKEN_B]["notification"]["title"], "Profilini aktivləşdirdi: Test User")
        data = by_token[TOKEN_A]["data"]
        self.assertEqual(data["notification_id"], str(notification.pk))
        self.assertEqual(data["type"], "grade")
        self.assertEqual(data["link"], notification.link)
        self.assertTrue(data["url"].startswith("https://ems.example.az/"))
        self.assertTrue(all(isinstance(value, str) for value in data.values()))
        self.assertEqual(by_token[TOKEN_A]["apns"]["payload"]["aps"]["badge"], 1)
        self.assertEqual(fake.token_requests, 1)  # access token keşlənir
        with bypass_rls():
            self.assertEqual(PushDevice.objects.filter(last_success_at__isnull=False).count(), 2)

    def test_unregistered_token_is_deactivated(self):
        good = self._device(TOKEN_A)
        bad = self._device(TOKEN_B)
        fake = FakeFCM({TOKEN_B: _unregistered()})
        with mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            self._notify()
        with bypass_rls():
            good.refresh_from_db()
            bad.refresh_from_db()
        self.assertTrue(good.is_active)
        self.assertFalse(bad.is_active)
        self.assertEqual(bad.deactivated_reason, "unregistered")

    def test_transient_error_keeps_device_active(self):
        device = self._device(TOKEN_A)
        fake = FakeFCM({TOKEN_A: (503, {"error": {"status": "UNAVAILABLE"}})})
        with mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            self._notify()
        with bypass_rls():
            device.refresh_from_db()
        self.assertTrue(device.is_active)

    def test_muted_type_and_users_without_devices_are_skipped(self):
        self._device(TOKEN_A, muted_types=["grade"])
        other = User.objects.create_user("push_other", "push_other@qku.edu.az", "pw-12345-Abc!")
        fake = FakeFCM()
        with mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            with mock.patch("apps.notifications.tasks.push_send_task.delay", wraps=lambda ids: None) as delay:
                with self.captureOnCommitCallbacks(execute=True):
                    create_notification(recipient=other, title="Salam")  # cihazı yoxdur → növbə yoxdur
                delay.assert_not_called()
            self._notify()
        self.assertEqual(fake.sent, [])

    def test_bulk_notification_is_chunked(self):
        users = [User.objects.create_user(f"push_bulk{i}", f"push_bulk{i}@qku.edu.az", "pw") for i in range(5)]
        for index, user in enumerate(users):
            self._device(f"tok-bulk-{index}-" + "d" * 30, user=user)
        fake = FakeFCM()
        with override_settings(PUSH_SEND_CHUNK=2), mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            with mock.patch("apps.notifications.push.dispatch.deliver", wraps=dispatch.deliver) as deliver:
                with self.captureOnCommitCallbacks(execute=True):
                    create_notification_for_users(recipients=users, title="Elan")
        self.assertEqual(deliver.call_count, 3)  # 2 + 2 + 1
        self.assertEqual(len(fake.sent), 5)

    def test_read_or_deleted_notification_is_not_pushed(self):
        self._device(TOKEN_A)
        with mock.patch("apps.notifications.tasks.push_send_task.delay"):
            notification = self._notify()
        with bypass_rls():
            InAppNotification.objects.filter(pk=notification.pk).update(is_read=True)
        fake = FakeFCM()
        with mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            self.assertEqual(dispatch.deliver([notification.pk]), {"no_target": 1})
        self.assertEqual(fake.sent, [])

    def test_runtime_switch_disables_push(self):
        self._device(TOKEN_A)
        with mock.patch("core.runtime_settings_push.push_enabled_setting", return_value=False):
            with mock.patch("apps.notifications.tasks.push_send_task.delay") as delay:
                self._notify()
        delay.assert_not_called()


class ClassifyTests(TestCase):
    def test_fcm_error_classification(self):
        self.assertEqual(classify(200, {}).outcome, "ok")
        self.assertEqual(classify(*_unregistered()).outcome, "unregistered")
        invalid = {
            "error": {
                "status": "INVALID_ARGUMENT",
                "message": "The registration token is not a valid FCM registration token",
            }
        }
        self.assertEqual(classify(400, invalid).outcome, "invalid")
        self.assertEqual(
            classify(400, {"error": {"status": "INVALID_ARGUMENT", "message": "bad payload"}}).outcome, "error"
        )
        mismatch = {"error": {"details": [{"errorCode": "SENDER_ID_MISMATCH"}]}}
        self.assertEqual(classify(403, mismatch).outcome, "sender_mismatch")
        self.assertEqual(classify(429, {}).outcome, "retry")
        self.assertEqual(classify(401, {}).outcome, "auth")


class DeviceApiTests(_PushCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("notifications_api:devices")

    def _post(self, payload, client=None, method="post"):
        return getattr(client or self.client, method)(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

    def test_register_is_idempotent_and_token_moves_between_accounts(self):
        payload = {"token": TOKEN_A, "platform": "android", "app_version": "1.0.0", "language": "ru"}
        first = self._post(payload)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertNotIn(TOKEN_A, first.content.decode())  # token geri qaytarılmır
        second = self._post({**payload, "app_version": "1.0.1", "muted_types": ["system"]})
        self.assertEqual(second.status_code, 200)
        with bypass_rls():
            self.assertEqual(PushDevice.objects.count(), 1)
            device = PushDevice.objects.get()
        self.assertEqual((device.app_version, device.muted_types), ("1.0.1", ["system"]))

        other = User.objects.create_user("push_api_other", "push_api_other@qku.edu.az", "pw")
        other_client = Client()
        other_client.force_login(other)
        self.assertEqual(self._post(payload, client=other_client).status_code, 200)
        with bypass_rls():
            self.assertEqual(PushDevice.objects.get().user_id, other.pk)

    def test_logout_delete_deactivates_device(self):
        self._post({"token": TOKEN_A, "platform": "ios"})
        response = self._post({"token": TOKEN_A}, method="delete")
        self.assertEqual(response.json(), {"ok": True, "deactivated": 1})
        with bypass_rls():
            device = PushDevice.objects.get()
        self.assertFalse(device.is_active)
        self.assertEqual(device.deactivated_reason, "logout")
        listing = self.client.get(self.url).json()
        self.assertEqual(listing["devices"], [])
        self.assertEqual(listing["push"], {"configured": False, "enabled": False})

    def test_validation_and_auth(self):
        self.assertEqual(self._post({"token": "short", "platform": "android"}).json()["error"], "invalid_token")
        self.assertEqual(self._post({"token": TOKEN_A, "platform": "symbian"}).json()["error"], "invalid_platform")
        bad_mute = self._post({"token": TOKEN_A, "platform": "web", "muted_types": ["nope"]})
        self.assertEqual(bad_mute.status_code, 400)
        anonymous = Client().get(self.url)
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous.json()["error"], "auth_required")

    def test_csrf_is_enforced_for_writes(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(self._post({"token": TOKEN_A, "platform": "android"}, client=strict).status_code, 403)


class InboxApiTests(_PushCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)

    def test_list_is_localized_and_read_syncs(self):
        with mock.patch("apps.notifications.tasks.push_send_task.delay"):
            notification = self._notify()
        data = self.client.get(reverse("notifications_api:list"), {"lang": "ru"}).json()
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(data["results"][0]["title"], "Профиль активирован: Test User")
        self.assertEqual(data["results"][0]["id"], notification.pk)
        response = self.client.post(reverse("notifications_api:read", args=[notification.pk]))
        self.assertEqual(response.json(), {"ok": True, "changed": True, "unread_count": 0})
        stranger = User.objects.create_user("push_stranger", "push_stranger@qku.edu.az", "pw")
        other = Client()
        other.force_login(stranger)
        self.assertEqual(other.post(reverse("notifications_api:read", args=[notification.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("notifications_api:unread_count")).json()["unread_count"], 0)


@override_settings(FCM_SERVICE_ACCOUNT_JSON=SERVICE_ACCOUNT)
class TestPushEndpointTests(_PushCase):
    def test_only_superadmin_or_rim_can_send_test_push(self):
        url = reverse("notifications_api:device_test")
        client = Client()
        client.force_login(self.user)
        self.assertEqual(client.post(url).status_code, 403)

        admin = User.objects.create_user("push_admin", "push_admin@qku.edu.az", "pw", is_superuser=True)
        self._device(TOKEN_A, user=admin)
        client.force_login(admin)
        fake = FakeFCM()
        with mock.patch("apps.notifications.push.fcm.requests.Session", fake):
            report = client.post(url).json()["report"]
        self.assertEqual(report["devices"], 1)
        self.assertEqual(report["ok"], 1)
        self.assertEqual(fake.sent[0]["data"]["notification_id"], "0")
        with bypass_rls():
            self.assertFalse(InAppNotification.objects.filter(recipient=admin).exists())
