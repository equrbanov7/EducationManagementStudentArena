"""A load test must not measure protected work after a failed login."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def scenario(monkeypatch):
    # Keep Locust's global gevent patch out of Django/PostgreSQL test threads.
    monkeypatch.setenv("LOCUST_SKIP_MONKEY_PATCH", "1")
    spec = importlib.util.spec_from_file_location("capacity_locust_contract", Path(__file__).with_name("locustfile.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(status=200, text="", headers=None, error=None):
    value = Mock(status_code=status, text=text, headers=headers or {}, error=error)
    value.__enter__ = Mock(return_value=value)
    value.__exit__ = Mock(return_value=False)
    return value


def user_with(get, post, cookies=None):
    client = Mock(cookies=cookies or {})
    client.get.return_value = get
    client.post.return_value = post
    return SimpleNamespace(client=client, host="https://localhost")


@pytest.mark.parametrize("status,text,error", [(503, "", None), (200, "no token", None), (0, "", "ReadTimeout")])
def test_failed_login_get_never_posts_or_enters_authenticated_work(scenario, status, text, error):
    page = response(status, text, error=error)
    user = user_with(page, response(302))
    with pytest.raises(scenario.StopUser):
        scenario._login(user, "[test]")
    user.client.post.assert_not_called()
    page.failure.assert_called_once()
    assert str(error) in page.failure.call_args.args[0]


@pytest.mark.parametrize(
    "status,location,cookies",
    [
        (200, "", {}),
        (302, "/accounts/login/telebe/", {"sessionid": "session"}),
        (302, "/accounts/profile/", {}),
        (0, "", {}),
    ],
)
def test_failed_login_post_stops_user(scenario, status, location, cookies):
    page = response(text='<input name="csrfmiddlewaretoken" value="token">')
    post = response(status, headers={"Location": location}, error="ReadTimeout" if status == 0 else None)
    user = user_with(page, post, cookies)
    with pytest.raises(scenario.StopUser):
        scenario._login(user, "[test]")
    post.failure.assert_called_once()
    if status == 0:
        assert "ReadTimeout" in post.failure.call_args.args[0]


def test_authenticated_redirect_with_session_passes(scenario):
    page = response(text='<input name="csrfmiddlewaretoken" value="token">')
    post = response(303, headers={"Location": "/accounts/profile/"})
    user = user_with(page, post, {"sessionid": "session"})
    scenario._login(user, "[test]")
    post.success.assert_called_once()


def test_worker_shard_never_wraps_into_another_workers_accounts(scenario, monkeypatch):
    monkeypatch.setattr(scenario, "_USER_PREFIX", "stress_")
    monkeypatch.setattr(scenario, "_USER_COUNT", 100)
    monkeypatch.setattr(scenario, "_USER_OFFSET", 50)
    monkeypatch.setattr(scenario, "_USER_SHARD_COUNT", 2)
    monkeypatch.setattr(scenario, "_user_cursor", iter(range(50, 55)))
    assert scenario._next_credentials()[0] == "stress_0051"
    assert scenario._next_credentials()[0] == "stress_0052"
    with pytest.raises(scenario.StopUser):
        scenario._next_credentials()


def test_fixture_exhaustion_is_reported_as_generator_failure(scenario, monkeypatch):
    monkeypatch.setattr(scenario, "_next_credentials", Mock(side_effect=scenario.StopUser))
    user = user_with(response(), response())
    user.environment = Mock()
    with pytest.raises(scenario.StopUser):
        scenario._login(user, "[test]")
    user.client.get.assert_not_called()
    user.environment.events.request.fire.assert_called_once()
    assert user.environment.events.request.fire.call_args.kwargs["request_type"] == "FIXTURE"
