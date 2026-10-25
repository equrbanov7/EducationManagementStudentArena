"""Köhnə bildirişlərə dil-müstəqil deskriptor əlavə edir — sahib 2026-10-25 «bildirişlərin dili hərəsi bir cür».

Səbəb: bildiriş mətni yaradılan anda hazır sətir kimi, TETİKLƏYƏNİN dilində saxlanırdı (məs. «Профиль активирован:
…», «Profilini etkinleştirdi: …», «Profilini aktivləşdirdi: …» eyni siyahıda). Yeni bildirişlər ``metadata["i18n"]``
ilə yaranır (bax ``apps/notifications/i18n.py``); bu əmr eyni deskriptoru KÖHNƏ sətirlər üçün kataloqun ters
axtarışı ilə tapıb əlavə edir — siyahı onları oxuyanın dilində göstərir.

QAYDA:

* Yalnız ``metadata`` içinə ``i18n`` açarı əlavə olunur; ``title`` / ``message`` / ``link`` / oxunma vəziyyəti
  DƏYİŞMİR. Heç nə silinmir.
* Mənbə dili bilinmir — mətn bütün dillərin kataloqlarına qarşı yoxlanır; yalnız TƏK mənalı uyğunluq yazılır
  (qeyri-müəyyən / istifadəçi mətni / tanınmayan sətir olduğu kimi qalır).
* DEFOLT DRY-RUN; ``--apply`` ilə yazır. İdempotent: ``i18n`` artıq olan sətir keçilir, ikinci işə salınma heç nə
  tapmır (tanınmayanlar hər dəfə yenidən yoxlanır, amma yazılmır).
* Stdout-a YALNIZ saylar (ad yoxdur).

Nümunə::

    python manage.py backfill_notification_i18n
    python manage.py backfill_notification_i18n --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import translation
from django.utils.translation import pgettext

from apps.notifications.i18n import META_KEY, all_languages, describe
from apps.notifications.models import InAppNotification
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

_FIELDS = ("title", "message")

#: «Profilini aktivləşdirdi» (``metadata.kind == "profile_activated"``) mətninin kontekst və növ etiketləri
#: (``apps/accounts/services/rim/activation.py``). Köhnə sətirlərdə mətn mürəkkəb halda yığılıb:
#: «<növ> · @istifadəçi. <yekun> — <növlər üzrə>.» — hissələrə ayrılıb ayrı-ayrılıqda tanınır.
_ACTIVATION_CTX = "accounts.rim_activation"
_ACTIVATION_KINDS = ("Tələbə", "Müəllim", "Əməkdaş")


def _describe_kind_label(text: str, languages) -> dict | None:
    for lang in languages:
        with translation.override(lang):
            for msgid in _ACTIVATION_KINDS:
                if pgettext(_ACTIVATION_CTX, msgid) == text:
                    return {"m": msgid, "c": _ACTIVATION_CTX, "l": lang}
    return None


def describe_activation_message(text: str, languages) -> dict | None:
    """Köhnə «profile_activated» mesajının mürəkkəb deskriptoru (tanınmasa ``None``)."""
    head, sep, rest = (text or "").partition(". ")
    if not sep:
        return None
    summary, sep, kinds = rest.rpartition(" — ")
    if not sep or not kinds.endswith("."):
        return None
    summary_desc = describe(summary, languages=languages)
    kinds_desc = describe(kinds[:-1], languages=languages)
    if not (summary_desc and kinds_desc):
        return None
    label, sep, username = head.rpartition(" · ")
    if sep:
        label_desc = _describe_kind_label(label, languages)
        if label_desc is None:
            return None
        head_desc = {"t": "{0} · {1}", "a": [label_desc, username]}
    else:
        head_desc = {"t": "{0}", "a": [head]}
    return {"t": "{0}. {1} — {2}.", "a": [head_desc, summary_desc, kinds_desc]}


def describe_row(title: str, message: str, metadata: dict) -> dict:
    """Sətir üçün ``{sahə: deskriptor}`` (tapılanlar)."""
    languages = all_languages()
    metadata = metadata or {}
    found = {}
    for field, text in (("title", title), ("message", message), ("link_label", metadata.get("link_label"))):
        descriptor = describe(text, languages=languages) if text else None
        if descriptor is None and field == "message" and metadata.get("kind") == "profile_activated":
            descriptor = describe_activation_message(text, languages)
        if descriptor:
            found[field] = descriptor
    return found


class Command(BaseCommand):
    help = (
        "Köhnə bildirişlərə metadata['i18n'] deskriptoru əlavə edir (oxuyanın dilində göstərmək üçün). Defolt dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (verilməsə dry-run).")
        parser.add_argument("--batch-size", type=int, default=1000, help="Bir dəstədə sətir sayı (defolt 1000).")

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        batch_size = max(int(options["batch_size"]), 1)
        stats = {"scanned": 0, "updated": 0, "title_ok": 0, "title_missed": 0, "message_ok": 0, "message_missed": 0}
        last_pk = 0
        while True:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                rows = list(
                    InAppNotification.objects.filter(pk__gt=last_pk)
                    .order_by("pk")[:batch_size]
                    .only("pk", "title", "message", "metadata")
                )
                if not rows:
                    break
                last_pk = rows[-1].pk
                changed = []
                for row in rows:
                    metadata = row.metadata if isinstance(row.metadata, dict) else {}
                    if META_KEY in metadata:
                        continue
                    stats["scanned"] += 1
                    found = describe_row(row.title, row.message, metadata)
                    for field in _FIELDS:
                        text = getattr(row, field)
                        if text:
                            stats[f"{field}_ok" if field in found else f"{field}_missed"] += 1
                    if found:
                        row.metadata = {**metadata, META_KEY: found}
                        changed.append(row)
                stats["updated"] += len(changed)
                if apply and changed:
                    InAppNotification.objects.bulk_update(changed, ["metadata"], batch_size=500)

        mode = "APPLY" if apply else "DRY-RUN (heç nə yazılmadı)"
        self.stdout.write(f"{mode}: " + " · ".join(f"{key}={value}" for key, value in stats.items()))
