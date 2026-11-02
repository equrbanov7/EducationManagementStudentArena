"""Every history template msgid is present in all five source/runtime catalogs."""

import gettext
from pathlib import Path

import polib
import pytest

from scripts.i18n_source_scan import template_msgids

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "apps/registrar/templates/registrar/journal_own_history.html"
LOCALES = ("az", "en", "ru", "tr", "de")


@pytest.mark.parametrize("lang", LOCALES)
def test_required_locales_include_scanned_history_messages_and_runtime_mo(lang):
    keys = template_msgids(TEMPLATE.read_text(), origin=str(TEMPLATE))
    assert ("", "Daxil edən şəxs məlum deyil") in keys
    folder = ROOT / "locale" / lang / "LC_MESSAGES"
    po = polib.pofile(folder / "django.po")
    with (folder / "django.mo").open("rb") as stream:
        runtime = gettext.GNUTranslations(stream)
    for ctx, msgid in keys:
        entry = po.find(msgid, msgctxt=ctx or None)
        assert entry is not None and entry.msgstr and "fuzzy" not in entry.flags, (lang, msgid)
        assert runtime.gettext(msgid) == entry.msgstr, (lang, msgid)
    if lang != "az":
        assert runtime.gettext("Daxil edən şəxs məlum deyil") != "Daxil edən şəxs məlum deyil"
        assert runtime.gettext("Öz daxil etdiyiniz qeyd") != "Öz daxil etdiyiniz qeyd"


@pytest.mark.parametrize("lang", LOCALES)
def test_prior_history_badge_context_is_scanned_and_compiled(lang):
    msgid = "Əvvəlki jurnal qeydləri mövcuddur"
    context = "registrar.journal_history"
    for name in ("_journal_teacher_record.html", "_journal_teaching_heading.html"):
        template = ROOT / "apps/registrar/templates/registrar/partials" / name
        assert (context, msgid) in template_msgids(template.read_text(), origin=str(template))
    folder = ROOT / "locale" / lang / "LC_MESSAGES"
    entry = polib.pofile(folder / "django.po").find(msgid, msgctxt=context)
    assert entry is not None and entry.msgstr and "fuzzy" not in entry.flags
    with (folder / "django.mo").open("rb") as stream:
        runtime = gettext.GNUTranslations(stream)
    assert runtime.pgettext(context, msgid) == entry.msgstr
    if lang != "az":
        assert entry.msgstr != msgid
