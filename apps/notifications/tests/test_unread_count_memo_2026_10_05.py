"""Navbar oxunmamış bildiriş sayğacı sorğu daxilində bir dəfə hesablanır (tutum testi 2026-10-05)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.notifications.templatetags import notification_tags

User = get_user_model()


class UnreadCountMemoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("memo_user", email="memo@example.com")
        self.other = User.objects.create_user("memo_other", email="memo-other@example.com")
        self.request = RequestFactory().get("/")
        self.request.user = self.user

    def test_two_calls_in_one_request_query_once(self):
        context = {"request": self.request}
        with mock.patch.object(notification_tags, "get_unread_count", return_value=3) as counter:
            first = notification_tags.user_unread_notification_count(context, self.user)
            second = notification_tags.user_unread_notification_count(context, self.user)
        self.assertEqual((first, second), (3, 3))
        counter.assert_called_once_with(user=self.user)

    def test_other_user_is_not_served_from_request_memo(self):
        context = {"request": self.request}
        with mock.patch.object(notification_tags, "get_unread_count", side_effect=[3, 7]) as counter:
            notification_tags.user_unread_notification_count(context, self.user)
            other = notification_tags.user_unread_notification_count(context, self.other)
        self.assertEqual(other, 7)
        self.assertEqual(counter.call_count, 2)
