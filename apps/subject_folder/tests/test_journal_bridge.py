"""Jurnal körpüsü müqaviləsi: hook yoxdur → pending; rədd → blocked + mesaj; ok → synced; istisna → pending."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command

import pytest

from apps.subject_folder import public
from apps.subject_folder.services import journal

pytestmark = pytest.mark.django_db


class Hook:
    def __init__(self, result=(True, ""), error=None):
        self.result, self.error, self.calls = result, error, []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def accepted(ready, monkeypatch):
    """Hook-suz qəbul edilmiş göndəriş (pending)."""
    monkeypatch.setattr(journal, "resolve_journal_hook", lambda: None)
    row = public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[0], text="iş")
    row = public.accept(row, by_user=ready.teacher, points="4")
    public.sync_submission_to_journal(row)
    row.refresh_from_db()
    return row


def test_missing_hook_leaves_points_pending_with_message(accepted):
    assert accepted.journal_sync_status == "pending"
    assert "aktiv deyil" in accepted.journal_sync_message
    assert accepted.journal_synced_at is None


def test_hook_ok_marks_synced_and_receives_the_contract(accepted, ready):
    hook = Hook((True, "yazıldı"))
    result = public.sync_submission_to_journal(accepted, hook=hook)
    accepted.refresh_from_db()
    assert result["status"] == "synced" and accepted.journal_sync_status == "synced"
    assert accepted.journal_synced_at is not None
    (call,) = hook.calls
    assert call["offering"] == ready.offering and call["enrollment"] == ready.enrollments[0]
    assert (call["slot_index"], call["slot_title"]) == (1, ready.slot1.title)
    assert (call["points"], call["max_points"]) == (Decimal("4.0"), Decimal("5.0"))
    assert call["source_ref"] == f"subject_folder.submission:{accepted.pk}" and call["by_user"] == ready.teacher
    assert accepted.events.filter(kind="journal_synced").exists()
    # Təkrar çağırış artıq yazılmış balı yenidən göndərmir.
    public.sync_submission_to_journal(accepted, hook=hook)
    assert len(hook.calls) == 1


def test_hook_refusal_blocks_with_reason(accepted):
    result = public.sync_submission_to_journal(accepted, hook=Hook((False, "Jurnal bağlıdır")))
    accepted.refresh_from_db()
    assert result == {"status": "blocked", "message": "Jurnal bağlıdır"}
    assert accepted.journal_sync_status == "blocked" and accepted.journal_sync_message == "Jurnal bağlıdır"
    assert accepted.events.filter(kind="journal_blocked").exists()
    assert accepted.status == "accepted" and accepted.points == Decimal("4.0")  # bal itmir


def test_hook_exception_stays_pending_for_retry(accepted):
    result = public.sync_submission_to_journal(accepted, hook=Hook(error=RuntimeError("db down")))
    accepted.refresh_from_db()
    assert result["status"] == "pending" and "RuntimeError" in accepted.journal_sync_message
    assert accepted.journal_sync_attempts >= 2


def test_hook_is_resolved_from_registrar_public_services(monkeypatch):
    import apps.registrar.public_services as services

    monkeypatch.setattr(journal, "HOOK_MODULES", ("apps.registrar.public_services", "apps.registrar.public"))
    hook = Hook()
    monkeypatch.setattr(services, "selfwork_points", SimpleNamespace(record_points=hook), raising=False)
    assert journal.resolve_journal_hook() is hook
    monkeypatch.setattr(services, "selfwork_points", hook, raising=False)
    assert journal.resolve_journal_hook() is hook


def test_homework_is_never_sent_to_the_journal(ready):
    row = public.submit(task=ready.homework, assignment=ready.assignment, student=ready.students[0], text="ev")
    row = public.check_homework(row, by_user=ready.teacher)
    hook = Hook()
    assert public.sync_submission_to_journal(row, hook=hook)["status"] == "none" and hook.calls == []


def test_accept_triggers_sync_on_commit(ready, monkeypatch, django_capture_on_commit_callbacks):
    hook = Hook((True, ""))
    monkeypatch.setattr(journal, "resolve_journal_hook", lambda: hook)
    row = public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[1], text="iş")
    with django_capture_on_commit_callbacks(execute=True):
        public.accept(row, by_user=ready.teacher, points="5")
    row.refresh_from_db()
    assert row.journal_sync_status == "synced" and len(hook.calls) == 1


def test_retry_command_dry_run_and_apply(accepted, monkeypatch):
    out = StringIO()
    call_command("subject_folder_sync_journal", stdout=out)
    assert "DRY-RUN" in out.getvalue() and "'candidates': 1" in out.getvalue()
    accepted.refresh_from_db()
    assert accepted.journal_sync_status == "pending"
    hook = Hook((False, "Semestr bağlıdır"))
    monkeypatch.setattr(journal, "resolve_journal_hook", lambda: hook)
    call_command("subject_folder_sync_journal", "--apply", stdout=StringIO())
    accepted.refresh_from_db()
    assert accepted.journal_sync_status == "blocked"
    # blocked yalnız --include-blocked ilə yenidən yoxlanır.
    hook.result = (True, "")
    call_command("subject_folder_sync_journal", "--apply", stdout=StringIO())
    accepted.refresh_from_db()
    assert accepted.journal_sync_status == "blocked"
    call_command("subject_folder_sync_journal", "--apply", "--include-blocked", stdout=StringIO())
    accepted.refresh_from_db()
    assert accepted.journal_sync_status == "synced"


def test_celery_task_wrapper(accepted, monkeypatch):
    from apps.subject_folder.tasks import sync_journal_pending

    monkeypatch.setattr(journal, "resolve_journal_hook", lambda: Hook((True, "")))
    summary = sync_journal_pending()
    accepted.refresh_from_db()
    assert summary["synced"] == 1 and accepted.journal_sync_status == "synced"


def test_preview_includes_optional_journal_side(ready, monkeypatch):
    import apps.registrar.public_services as services

    row = public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[0], text="iş")
    assert public.journal_preview(row, points="4")["journal"] is None  # hook yoxdur
    seen = []

    def preview(**kwargs):
        seen.append(kwargs)
        return {"blocked": True, "reason": "Jurnal bağlıdır"}

    monkeypatch.setattr(journal, "HOOK_MODULES", ("apps.registrar.public_services",))
    monkeypatch.setattr(services, "selfwork_points", SimpleNamespace(preview=preview), raising=False)
    result = public.journal_preview(row, points="4")
    assert result["journal"] == {"blocked": True, "reason": "Jurnal bağlıdır"}
    assert seen[0]["slot_index"] == 1 and seen[0]["points"] == Decimal("4")

    def broken(**kwargs):
        raise RuntimeError("yarımçıq")

    monkeypatch.setattr(services, "selfwork_points", SimpleNamespace(preview=broken), raising=False)
    assert public.journal_preview(row, points="4")["journal"] is None  # baxış heç vaxt sınmır
