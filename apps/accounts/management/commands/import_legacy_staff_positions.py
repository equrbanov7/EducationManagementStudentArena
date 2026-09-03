"""Köhnə sistemin («myedudb») işçi vəzifə məlumatını hədəfə etiket kimi köçürür.

NİYƏ BU QƏDƏR DAR
-----------------
Mənbədə **ayrıca vəzifə cədvəli yoxdur**.  Vəzifəyə oxşar yeganə üç siqnal:

* ``workers.inzibati`` (0/1) — sütunun adı «inzibati»dir və data bunu təsdiqləyir
  (bax ``docs/migration/LEGACY_STAFF_POSITIONS.md``).  → ``İnzibati işçi`` etiketi.
* ``workers.teacher_type`` (1/2/3) — **NAMƏLUM**.  Sənədləşdirilməyib, datadan
  birmənalı ad çıxmır.  Bu əmr onu HEÇ BİR etiketə çevirmir; yalnız bölgünü
  hesabatda göstərir.
* ``workers_permits.permits`` içindəki ``dekan`` / ``kafedra`` tokenləri — bunlar
  köhnə sistemin **səhifə icazələridir**, vəzifə adı deyil (dekanlıq əməkdaşı da
  ala bilərdi).  Ona görə avtomatik YAZILMIR — sahibin əl ilə təsdiqi üçün
  siyahı kimi çap olunur.

TƏHLÜKƏSİZLİK
-------------
* Əmr **rol/üzvlük/icazə toxunmur** — yalnız ``UserProfile.staff_position``
  mətn sahəsini doldurur.  Bu sahə heç bir səlahiyyət vermir.
* **Additive**: yalnız BOŞ ``staff_position`` doldurulur, mövcud dəyər əzilmir.
* **Quru işləyiş defoltdur**; yazmaq üçün ``--apply`` tələb olunur.

MƏNBƏ FAYLI
-----------
JSON siyahısı; hər sətir::

    {"username": "n.novruzov", "legacy_worker_id": 1,
     "inzibati": 1, "teacher_type": 1, "permits": ["dekan", "kafedra"]}

Legacy dump-dan çıxarmaq üçün SQL sənəddədir
(``docs/migration/LEGACY_STAFF_POSITIONS.md``, §5).

İstifadə::

    python manage.py import_legacy_staff_positions --source workers.json
    python manage.py import_legacy_staff_positions --source workers.json --apply
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import translation
from django.utils.translation import pgettext

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.staff_position import LEGACY_STAFF_CATEGORY_ADMINISTRATIVE, legacy_staff_category_label

_CTX = "organizations.command.legacy_staff_positions"

#: Köhnə sistemin vəzifə-şübhəli səhifə icazələri — YALNIZ hesabat üçün.
_REVIEW_PERMITS = ("dekan", "kafedra")


def derive_staff_category(row):
    """Mənbə sətrindən vəzifə kateqoriyası — naməlumda ``None``.

    QƏSDƏN yalnız ``inzibati`` oxunur.  ``teacher_type`` naməlumdur və heç vaxt
    etiketə çevrilmir (bax modul başlığı).
    """

    try:
        inzibati = int(row.get("inzibati") or 0)
    except (TypeError, ValueError):
        return None
    return LEGACY_STAFF_CATEGORY_ADMINISTRATIVE if inzibati == 1 else None


def _load_rows(path):
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise CommandError(pgettext(_CTX, "Mənbə faylı oxunmadı: {path}").format(path=path)) from exc
    except json.JSONDecodeError as exc:
        raise CommandError(pgettext(_CTX, "Mənbə faylı düzgün JSON deyil: {path}").format(path=path)) from exc
    if not isinstance(payload, list):
        raise CommandError(pgettext(_CTX, "Mənbə faylı JSON siyahısı olmalıdır."))
    for index, row in enumerate(payload, start=1):
        if not isinstance(row, dict) or not str(row.get("username") or "").strip():
            raise CommandError(pgettext(_CTX, "Sətir {index}: «username» sahəsi tələb olunur.").format(index=index))
    return payload


class Command(BaseCommand):
    help = "Köhnə sistemin işçi vəzifə kateqoriyasını UserProfile.staff_position sahəsinə etiket kimi köçürür."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, metavar="FILE", help="Legacy JSON export path.")
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Write to the database. Without it the command only prints the plan.",
        )

    def handle(self, *args, **options):
        from ...models import UserProfile

        rows = _load_rows(options["source"])
        apply_changes = bool(options["apply"])

        by_username = {}
        teacher_type_counter = {}
        review = {permit: [] for permit in _REVIEW_PERMITS}

        for row in rows:
            username = str(row["username"]).strip()
            by_username[username] = row
            raw_type = row.get("teacher_type")
            key = str(raw_type) if raw_type is not None else "-"
            teacher_type_counter[key] = teacher_type_counter.get(key, 0) + 1
            permits = row.get("permits") or []
            if isinstance(permits, list):
                for permit in _REVIEW_PERMITS:
                    if permit in permits:
                        review[permit].append(username)

        matched = 0
        planned = 0
        already = 0
        written = 0

        with rls_worker_atomic(), bypass_rls():
            profiles = UserProfile.objects.select_related("user").filter(user__username__in=list(by_username))
            for profile in profiles:
                row = by_username.get(profile.user.username)
                if row is None:
                    continue
                matched += 1
                category = derive_staff_category(row)
                if category is None:
                    continue
                if (profile.staff_position or "").strip():
                    already += 1
                    continue
                planned += 1
                if apply_changes:
                    profile.staff_position = self._stored_label(category)
                    profile.save(update_fields=["staff_position", "updated_at"])
                    written += 1

        self._report(
            total=len(rows),
            matched=matched,
            planned=planned,
            already=already,
            written=written,
            apply_changes=apply_changes,
            teacher_type_counter=teacher_type_counter,
            review=review,
        )

    @staticmethod
    def _stored_label(category):
        """Bazaya yazılan etiket — HƏMİŞƏ təşkilatın əsas dilində.

        ``staff_position`` sərbəst mətndir; operator interfeysi rus dilində
        olanda qeyd rus dilində donmamalıdır, ona görə dil açıq şəkildə
        ``settings.LANGUAGE_CODE``-a bağlanır.
        """

        with translation.override(settings.LANGUAGE_CODE):
            return str(legacy_staff_category_label(category))

    def _report(self, *, total, matched, planned, already, written, apply_changes, teacher_type_counter, review):
        write = self.stdout.write
        write(pgettext(_CTX, "Mənbə sətri: {count}").format(count=total))
        write(pgettext(_CTX, "Uyğunlaşdırılan hesab: {count}").format(count=matched))
        write(pgettext(_CTX, "Hesabı tapılmayan sətir: {count}").format(count=total - matched))
        write(pgettext(_CTX, "Vəzifəsi onsuz da doldurulmuş: {count}").format(count=already))
        if apply_changes:
            write(pgettext(_CTX, "Vəzifə yazıldı: {count}").format(count=written))
        else:
            write(pgettext(_CTX, "Vəzifə yazılacaq: {count}").format(count=planned))
            write(pgettext(_CTX, "Quru işləyiş — heç nə yazılmadı (--apply ilə tətbiq edin)."))

        write("")
        write(pgettext(_CTX, "NAMƏLUM: «teacher_type» kodlarının mənası sənədləşdirilməyib — etiketə çevrilmədi."))
        for code in sorted(teacher_type_counter):
            write(
                pgettext(_CTX, "teacher_type={code}: {count} nəfər").format(code=code, count=teacher_type_counter[code])
            )

        headings = {
            "dekan": pgettext(_CTX, "ƏL İLƏ TƏSDİQ — köhnə sistemdə «dekanlıq» səhifəsinə girişi olanlar:"),
            "kafedra": pgettext(_CTX, "ƏL İLƏ TƏSDİQ — köhnə sistemdə «kafedra» səhifəsinə girişi olanlar:"),
        }
        for permit in _REVIEW_PERMITS:
            usernames = review.get(permit) or []
            if not usernames:
                continue
            write("")
            write(headings[permit])
            for username in sorted(usernames):
                write(f"  - {username}")

        write("")
        write(pgettext(_CTX, "Rol və icazələr DƏYİŞMİR — bu əmr yalnız mətn etiketi yazır."))
