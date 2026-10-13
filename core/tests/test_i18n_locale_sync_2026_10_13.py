"""`scripts/i18n_locale_sync.py` — «de» kataloqunu AZ mənbəyi ilə sinxronlaşdıran alət (2026-10-13, gecə).

Orkestratorun birləşmə axını: başqa agentlər yeni mətni yalnız az/en/ru/tr-yə yazır →
``export`` əskik «de» girişlərini çıxarır → tərcümə → ``apply`` yazır. Bu test həmin axının
üç zəmanətini yoxlayır (DB-siz, müvəqqəti kataloqlarla):

* yeni AZ girişi ixrac olunur, mövcud (o cümlədən «Status» kimi eyni yazılan) tərcümələr
  ixraca DÜŞMÜR və ``apply`` zamanı SİLİNMİR;
* placeholder dəsti uyğun gəlməyən tərcümə rədd olunur (runtime ``KeyError`` riski);
* hədəf kataloq AZ-ın sırası ilə yazılır, AZ-da olmayan köhnə giriş atılır.
"""

import importlib.util
import json
import os
from types import SimpleNamespace

import polib

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tool(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "i18n_locale_sync", os.path.join(BASE, "scripts", "i18n_locale_sync.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = str(tmp_path)
    return module


def _write(tmp_path, lang, domain, entries):
    path = tmp_path / "locale" / lang / "LC_MESSAGES"
    path.mkdir(parents=True, exist_ok=True)
    po = polib.POFile()
    po.metadata = {"Content-Type": "text/plain; charset=UTF-8", "Language": lang}
    for ctx, msgid, msgstr in entries:
        po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
    po.save(str(path / f"{domain}.po"))


def _catalog(tmp_path, lang):
    po = polib.pofile(str(tmp_path / "locale" / lang / "LC_MESSAGES" / "django.po"))
    return [((e.msgctxt or ""), e.msgid, e.msgstr) for e in po]


def test_export_apply_roundtrip_keeps_existing_and_rejects_bad_placeholders(tmp_path):
    tool = _tool(tmp_path)
    _write(
        tmp_path,
        "az",
        "django",
        [
            ("x", "status", "Status"),
            ("x", "greeting", "Salam, %(name)s"),
            ("x", "new_key", "Yeni mətn"),
        ],
    )
    _write(
        tmp_path,
        "en",
        "django",
        [("x", "status", "Status"), ("x", "greeting", "Hello, %(name)s"), ("x", "new_key", "New text")],
    )
    _write(
        tmp_path,
        "de",
        "django",
        [("x", "status", "Status"), ("x", "greeting", ""), ("x", "stale_key", "Alt")],
    )
    for domain in ("djangojs",):
        for lang in ("az", "en", "de"):
            _write(tmp_path, lang, domain, [])

    batches, outputs = tmp_path / "batches", tmp_path / "out"
    outputs.mkdir()
    tool.cmd_export(SimpleNamespace(lang="de", out=str(batches), batch_size=50, include_identity=False))
    batch = json.loads((batches / "django_000.json").read_text(encoding="utf-8"))
    exported = {item["msgid"]: item_id for item_id, item in batch.items()}
    assert set(exported) == {"greeting", "new_key"}  # «Status» artıq doludur — ixrac olunmur

    (outputs / "django_000.json").write_text(
        json.dumps({exported["greeting"]: "Hallo, %(nam)s", exported["new_key"]: "Neuer Text"}), encoding="utf-8"
    )
    tool.cmd_apply(
        SimpleNamespace(
            lang="de", batches=str(batches), translations=str(outputs), show=5, rejected_out=str(tmp_path / "r.txt")
        )
    )
    assert _catalog(tmp_path, "de") == [
        ("x", "status", "Status"),
        ("x", "greeting", ""),  # placeholder uyğunsuzluğu → rədd, boş qalır
        ("x", "new_key", "Neuer Text"),
    ]
    assert "placeholder" in (tmp_path / "r.txt").read_text(encoding="utf-8")
