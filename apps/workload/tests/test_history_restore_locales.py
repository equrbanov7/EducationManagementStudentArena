"""All restore template strings exist in source and runtime catalogs."""

import gettext
from pathlib import Path

import polib
import pytest

from scripts.i18n_source_scan import template_msgids

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("lang", ("az", "de", "en", "ru", "tr"))
def test_restore_template_strings_have_compiled_translations(lang):
    keys = set()
    for relative in (
        "apps/workload/templates/workload/history_restore.html",
        "apps/registrar/templates/registrar/partials/_journal_history_restore.html",
    ):
        path = ROOT / relative
        keys.update(template_msgids(path.read_text(), origin=relative))
    folder = ROOT / "locale" / lang / "LC_MESSAGES"
    po = polib.pofile(folder / "django.po")
    with (folder / "django.mo").open("rb") as stream:
        runtime = gettext.GNUTranslations(stream)
    assert keys
    for context, msgid in keys:
        entry = po.find(msgid, msgctxt=context or None)
        assert entry is not None and entry.msgstr and "fuzzy" not in entry.flags
        assert runtime.pgettext(context, msgid) == entry.msgstr
