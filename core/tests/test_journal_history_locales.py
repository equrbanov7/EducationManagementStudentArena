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
