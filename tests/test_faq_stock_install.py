"""A production media update must verify every file before replacing the current set."""

import hashlib
import io
import tarfile

import pytest

from scripts.deploy.install_faq_stock import unpack, valid


def entry(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def archive(path, items):
    with tarfile.open(path, "w") as out:
        for name, data in items:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            out.addfile(member, io.BytesIO(data))


@pytest.mark.parametrize(
    "items",
    [
        [("lesson.mp4", b"xxxx")],
        [("../lesson.mp4", b"demo")],
        [("lesson.mp4", b"demo"), ("lesson.mp4", b"demo")],
        [],
    ],
)
def test_invalid_stock_rejected(tmp_path, items):
    stage = tmp_path / "staging"
    stage.mkdir()
    path = tmp_path / "demo.tar"
    archive(path, items)
    with pytest.raises(ValueError):
        unpack(path, stage, {"lesson.mp4": entry(b"demo")})
    assert not (tmp_path / "lesson.mp4").exists()


def test_exact_media_contents_and_permissions(tmp_path):
    payload = b"demo"
    stage = tmp_path / "staging"
    stage.mkdir()
    path = tmp_path / "demo.tar"
    archive(path, [("lesson.mp4", payload)])
    unpack(path, stage, {"lesson.mp4": entry(payload)})
    assert valid(stage / "lesson.mp4", entry(payload))
    assert (stage / "lesson.mp4").stat().st_mode & 0o222 == 0
    alias = stage / "other.mp4"
    alias.symlink_to(stage / "lesson.mp4")
    assert not valid(alias, entry(payload))
