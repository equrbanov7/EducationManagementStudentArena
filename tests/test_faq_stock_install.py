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


def test_supplement_preserves_base_and_installs_only_verified_new_set(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from scripts.deploy import install_faq_stock as installer

    base = tmp_path / "apps/accounts/guide_media"
    base.mkdir(parents=True)
    base_video = base / "original.mp4"
    base_video.write_bytes(b"base")
    inode = base_video.stat().st_ino
    manifest = tmp_path / "inventory.json"
    extra = {"asset_id": 12, "encrypted": {"size": 50}, "files": {"lesson.vtt": entry(b"demo")}}
    manifest.write_text(json.dumps({"asset_id": 11, "files": {"original.mp4": entry(b"base")}, "supplements": [extra]}))
    monkeypatch.setattr(installer, "MANIFEST", manifest)
    monkeypatch.setenv("FAQ_STOCK_EXTRA_URLS", '{"12":"supplement-only"}')
    calls = []

    def fetch(package, work, stage, fallback):
        calls.append((package["asset_id"], fallback))
        parcel = Path(work) / "parcel.tar"
        archive(parcel, [("lesson.vtt", b"fail" if len(calls) == 1 else b"demo")])
        unpack(parcel, stage, package["files"])

    monkeypatch.setattr(installer, "fetch_package", fetch)
    with pytest.raises(ValueError, match="digest"):
        installer.install(tmp_path)
    assert not (base / "lesson.vtt").exists()
    assert base_video.read_bytes() == b"base"
    installer.install(tmp_path)
    installer.install(tmp_path)
    assert calls == [(12, "supplement-only"), (12, "supplement-only")]
    assert base_video.stat().st_ino == inode
    assert (base / "lesson.vtt").read_bytes() == b"demo"
