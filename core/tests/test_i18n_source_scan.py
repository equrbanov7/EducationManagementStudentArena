"""i18n mənbə skanerinin reqressiya testləri (frontend auditi 2026-09-13, F4).

Nəyi qoruyur
------------
`scripts/i18n_source_scan.py` Python-da ``pgettext(_CTX, "…")`` çağırışının
kontekstini yalnız string literal olanda oxuyurdu. Layihədə isə kontekst çox
yerdə modul sabitidir (``_CTX = "audit.section"``) — belə 564 (ctx, msgid) cütü
heç bir kataloqda yox idi, amma qapı (`check_i18n_catalogs.py`) onları görmədiyi
üçün yaşıl qalırdı. Nəticə: EN/RU/TR-də audit-log, groups-registry, org-members,
struktur reyestri, intake, imtahan balı importu qarışıq dilli.

Burada:
1. skaner sabit konteksti həll edir (modul səviyyəsi, sinif səviyyəsi, `AnnAssign`);
2. qeyri-müəyyən sabit (eyni ad, fərqli string) yanlış kontekst yazmaqdansa buraxılır;
3. real repo faylı (`apps/audit/views.py`) skanda görünür;
4. Python mənbəyində tapılan hər cüt ya AZ kataloqundadır, ya da doldurma
   skriptində (`scripts/i18n_fill_ctx_gap_2026_09_13.py`) — orkestrator skripti
   işlədənə qədər boşluq «görünməz» qalmasın;
5. auditin F1/F2/F3/F8/F9/F20/F22 msgstr düzəlişləri `.po`-da yerindədir
   (`.mo` runtime yoxlaması `tests/test_i18n_terminology.py`-dədir — o,
   `compilemessages`-dən sonra işləyir, burada `.po` özü oxunur).
"""

from __future__ import annotations

import importlib.util
import os
import textwrap

import polib
import pytest

from scripts.i18n_source_scan import SOURCE_ROOTS, _walk_files, python_msgids

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILL_SCRIPT = os.path.join(BASE, "scripts", "i18n_fill_ctx_gap_2026_09_13.py")


def _po(lang, domain="django"):
    return polib.pofile(os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po"))


def _msgstr(catalog, ctx, msgid):
    entry = catalog.find(msgid, msgctxt=ctx or None)
    assert entry is not None, (ctx, msgid)
    return entry.msgstr


# ── 1. sabit kontekstin həlli ────────────────────────────────────────────────


def test_module_constant_context_is_resolved():
    source = textwrap.dedent("""
        from django.utils.translation import pgettext

        _CTX = "audit.section"

        def labels():
            return {"a": pgettext(_CTX, "Son 30 gün"), "b": pgettext("literal.ctx", "Bu gün")}
        """)
    found = python_msgids(source)
    assert ("audit.section", "Son 30 gün") in found
    assert ("literal.ctx", "Bu gün") in found


def test_class_level_and_annotated_constants_are_resolved():
    source = textwrap.dedent("""
        from django.utils.translation import pgettext_lazy

        CTX_A: str = "organizations.registry"

        class Labels:
            CTX_B = "teacher_intake"
            x = pgettext_lazy(CTX_A, "Kafedralar")
            y = pgettext_lazy(CTX_B, "Ad")
        """)
    found = python_msgids(source)
    assert ("organizations.registry", "Kafedralar") in found
    assert ("teacher_intake", "Ad") in found


def test_ambiguous_constant_is_skipped_not_guessed():
    # Eyni ad iki fərqli string ilə — hansı kontekstin doğru olduğu bilinmir;
    # yanlış cüt yazmaq kataloqu zibilləyərdi, ona görə çağırış buraxılır.
    source = textwrap.dedent("""
        from django.utils.translation import pgettext

        CTX = "a.first"
        CTX = "a.second"
        label = pgettext(CTX, "Qrup")
        """)
    found = python_msgids(source)
    assert ("a.first", "Qrup") not in found
    assert ("a.second", "Qrup") not in found


def test_dynamic_context_is_still_ignored():
    # Funksiya parametri / f-string — statik deyil, əvvəlki kimi sükutla keçilir.
    source = textwrap.dedent("""
        from django.utils.translation import pgettext

        def label(context):
            return pgettext(context, "Qrup")

        def other(name):
            return pgettext(f"x.{name}", "Kod")
        """)
    assert python_msgids(source) == set()


# ── 2. real repo ─────────────────────────────────────────────────────────────


def test_audit_views_constant_context_is_visible_in_scan():
    path = os.path.join(BASE, "apps", "audit", "views.py")
    with open(path, encoding="utf-8") as handle:
        found = python_msgids(handle.read())
    assert ("audit.section", "Son 30 gün") in found
    assert ("audit.section", "Bütün icraçılar") in found


def _load_fill_entries():
    spec = importlib.util.spec_from_file_location("i18n_fill_ctx_gap", FILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ENTRIES


def test_every_python_constant_context_pair_is_in_catalog_or_fill_script():
    """Skanerin gördüyü hər Python cütü AZ kataloqunda VƏ YA doldurma skriptindədir.

    Orkestrator skripti işlədəndən sonra ikinci hissə boş çoxluğa çevrilir və test
    yalnız kataloqu yoxlayır — yəni bu test həm keçid dövrünü, həm sonranı qoruyur.
    """
    assert "apps" in SOURCE_ROOTS
    found = set()
    for path in _walk_files(BASE):
        if not path.endswith(".py"):
            continue
        with open(path, encoding="utf-8") as handle:
            found |= python_msgids(handle.read())
    az = {(entry.msgctxt or "", entry.msgid) for entry in _po("az") if not entry.obsolete}
    fill = {(ctx, msgid) for ctx, messages in _load_fill_entries()["django"].items() for msgid in messages}
    gap = sorted(pair for pair in found - az if pair not in fill)
    assert gap == [], f"kataloqsuz və doldurma skriptində olmayan {len(gap)} cüt: {gap[:10]}"


def test_fill_script_translations_are_complete_and_placeholder_safe():
    import re

    placeholder = re.compile(r"%\([^)]+\)[sd]|\{[a-zA-Z_][a-zA-Z0-9_]*\}|%[sd]")
    entries = _load_fill_entries()
    for domain, contexts in entries.items():
        for ctx, messages in contexts.items():
            for msgid, translations in messages.items():
                for lang in ("en", "ru", "tr"):
                    assert lang in translations, (domain, ctx, msgid, lang)
                    # Qapı `msgstr == msgid`-i tərcüməsiz sayır (identity ratchet).
                    assert translations[lang] != msgid, (domain, ctx, msgid, lang)
                    assert sorted(placeholder.findall(translations[lang])) == sorted(placeholder.findall(msgid)), (
                        domain,
                        ctx,
                        msgid,
                        lang,
                    )


# ── 3. semantik msgstr düzəlişləri (F1/F2/F3/F8/F9/F20/F22) ──────────────────

EXPECTED = {
    # F1 — modal bağlama düyməsi RU «открыть», TR «açık» idi (əks məna)
    ("exams.partial.exam_modals", "action_close"): {"ru": "Закрыть", "tr": "Kapat"},
    # F2 — «Seçimi sıfırla» RU/TR-də «Sil» kimi görünürdü
    ("exams.template.test_question_bank", "action_deselect_all"): {"ru": "Снять выделение", "tr": "Seçimi temizle"},
    # F3 — yoxlama linki 4 dildə «Geri/Back/Назад» idi
    ("exams.template.teacher_pending_attempts", "action_check"): {
        "az": "Yoxla",
        "en": "Check",
        "ru": "Проверить",
        "tr": "Kontrol et",
    },
    # F8 — mart ayı «Search/Поиск/Ara» idi
    ("abbrev. month", "March"): {"en": "March", "ru": "Март", "tr": "Mart"},
    ("alt. month", "March"): {"en": "March", "ru": "марта", "tr": "Mart"},
    # F9 — dublikat sayı kartı «Mövzu/Subject» adlanırdı
    ("exams.template.test_question_bank", "stat_duplicates"): {
        "az": "Dublikatlar",
        "en": "Duplicates",
        "ru": "Дубликаты",
        "tr": "Kopyalar",
    },
    # F20 — aria-label «Закрой это» (sən-forması)
    ("courses.partial.create_modal", "aria_close"): {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    ("courses.partial.topic_edit_modal", "aria_close"): {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    ("courses.partial.topic_modal", "aria_close"): {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    # F22 — sahə etiketi help_text-in kopiyası idi
    ("supervision.config.field", "enabled"): {"az": "Aktiv", "en": "Enabled", "ru": "Включено", "tr": "Etkin"},
}


@pytest.mark.parametrize("lang", ["az", "en", "ru", "tr"])
def test_semantic_msgstr_fixes_are_in_po(lang):
    catalog = _po(lang)
    for (ctx, msgid), per_lang in EXPECTED.items():
        if lang in per_lang:
            assert _msgstr(catalog, ctx, msgid) == per_lang[lang], (lang, ctx, msgid)
