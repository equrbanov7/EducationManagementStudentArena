"""Kabinetin cari mətnlərindən və anonim nümunə rol əhatələrindən oflayn FAQ modelini yığır.

Layihənin Python mühitində python -m tools.tutorials.export_faq işlədin.
Sonra node tools/tutorials/build-library.cjs hədəf-qovluq əmri pleyeri və media fayllarını köçürür.
"""

import json
import os
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parent


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    django.setup()
    from apps.accounts.views.profile.faq_catalog import GUIDES, media_metadata
    from apps.accounts.views.profile.faq_extra import EXTRA
    from apps.accounts.views.profile.faq_visibility import guide_allowed

    examples = json.loads((ROOT / "scenarios/faq-role-examples.json").read_text())
    roles = {"all": {"label": "Bütün mövzular", "ids": [guide.key for guide in GUIDES]}}
    for key, example in examples.items():
        sections = set(example["sections"])
        capabilities = set(example["capabilities"])
        roles[key] = {
            "label": example["label"],
            "ids": [guide.key for guide in GUIDES if guide_allowed(guide, sections, dict.fromkeys(capabilities, True))],
        }

    guides = []
    for guide in GUIDES:
        row = {
            key: getattr(guide, key)
            for key in ("key", "title", "topic", "steps", "aliases", "video", "start", "section", "flags")
        }
        source = EXTRA.get(guide.section)
        if guide.key.startswith("section-") and source and source[3]:
            row.update(long=source[3], longStart=source[4])
        guides.append(row)

    model = {"roles": roles, "guides": guides, "media": media_metadata()}
    dest = ROOT / "out/faq-model.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
