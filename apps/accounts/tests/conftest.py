"""The public source tree exercises FAQ streaming with anonymous fixture bytes."""

import pytest


@pytest.fixture(scope="session")
def faq_fixture_directory(tmp_path_factory):
    from apps.accounts.views.profile.faq_catalog import media_metadata

    folder = tmp_path_factory.mktemp("faq-sample")
    for key in media_metadata():
        (folder / (key + ".mp4")).write_bytes(b"\x00\x00\x00\x18ftypisom" + b"synthetic test payload" * 4)
        (folder / (key + ".vtt")).write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nTest\n")
    return folder


@pytest.fixture(autouse=True)
def faq_files_in_public_checkout(request, monkeypatch):
    if "faq" not in request.module.__name__:
        return
    from apps.accounts.views.profile import faq_media

    if (faq_media.BUILTIN_DIR / "login.mp4").is_file():
        return
    folder = request.getfixturevalue("faq_fixture_directory")
    monkeypatch.setattr(faq_media, "BUILTIN_DIR", folder)
    if hasattr(request.module, "BUILTIN_DIR"):
        monkeypatch.setattr(request.module, "BUILTIN_DIR", folder)
