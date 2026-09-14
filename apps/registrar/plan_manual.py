"""Əl ilə köçürülmüş plan mənbələri + kataloqda olmayan fənnin yaradılması.

Bu modul `import_curriculum_plans` komandasının İKİ əlavə rejimini daşıyır.
Məntiq komandadan ayrılıb ki, komanda faylı modul ölçü büdcəsini
(`scripts/check_module_size.py`) aşmasın.

1. ``--manual`` — SKAN PDF-lər
------------------------------
Saytdakı planların bir hissəsi mətn qatı OLMAYAN skandır (məs. «Ekologiya
mühəndisliyi» sənədi: hər səhifədə 0 simvol) — `extract_rows` onlardan 0 sətir
qaytarır. Belə sənədin cədvəli insan tərəfindən oxunub
``data/ixtisas/manual_plans.json``-a köçürülüb. Fayl DATA-dır: növbəti skan
sənəd üçün kod dəyişmir, yalnız JSON genişlənir. Sətirlər PDF-dən gələnlərlə
EYNİ `match_rows` süzgəcindən keçir — əl ilə köçürülməyə heç bir güzəşt yoxdur.

2. ``--create-subjects`` — kataloqda olmayan fənn
-------------------------------------------------
Rəsmi planda olan, amma bizim `Subject` kataloqumuzda olmayan ~160 sətir var.
Sahib (2026-09-10): «əsas məsələ onların burada olmasıdır». Bu rejim həmin
sətirləri kataloqa yazır ki, plan onları göstərə bilsin.

⚠️ NƏ YARADILMIR (təhlükəsizlik qatı)
    * **seçmə bloklar** («I blok: 1. Sosiologiya 2. …») — bir xanada bir neçə
      fənn; tək fənn deyil;
    * **yer tutucular** («Ali məktəb tərəfindən müəyyən edilən fənn») — konkret
      fənn deyil, sonradan doldurulan yerdir.

Hər ikisi `match_rows`-da AYRI səbətlərə düşür və `unknown`-a heç vaxt çatmır,
bu modul isə YALNIZ `unknown` səbətinə toxunur. Yəni kataloqa uydurma fənn
düşmür: yalnız sənəddə ADI OLAN sətirlər yazılır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from apps.registrar.models import Subject
from apps.registrar.plan_import import normalize
from core.rls_pooling import rls_worker_atomic

#: Əl ilə köçürülmüş planlar (skan PDF-lər).
MANUAL_PLANS = Path(__file__).resolve().parent / "data" / "ixtisas" / "manual_plans.json"

#: Saytdan gələn yeni fənlərin kod prefiksi.
#: ⚠️ `Subject.code` təşkilat daxilində UNİKALDIR (`uniq_subject_code_per_org`).
#: Mövcud kataloqun 2501 kodunun HAMISI `MYEDU-…` prefiksindədir, ona görə
#: `SAYT-…` fəzası boşdur; həm də ayrı prefiks yeni fənnin haradan gəldiyini
#: koda baxan adama dərhal göstərir.
SITE_CODE_PREFIX = "SAYT"

#: Bir fənn üçün ağlabatan yuxarı kredit həddi. Sənəddəki kredit sütunu bəzən
#: sürüşür (saat sütunu oxunur) — 240 kreditli «fənn» kataloqu sükutla korlayar,
#: ona görə hədd aşılanda sətrin krediti yox, modelin defaultu işlədilir.
MAX_SANE_ECTS = 60

_NAME_MAX = Subject._meta.get_field("name").max_length


def load_manual_plans(path: Path | None = None) -> list[dict]:
    """`manual_plans.json`-u oxuyur; sətirləri PDF sətirləri ilə EYNİ formaya salır.

    Əl ilə köçürülmüş cədvəldə `total_hours`/`semester` sütunu yoxdur (skan
    sənəddə saat və semestr bölgüsü oxunmur) — açarlar boş dəyərlə tamamlanır
    ki, axının qalan hissəsi mənbənin PDF, yoxsa əl işi olduğunu BİLMƏSİN.
    """
    path = path or MANUAL_PLANS
    if not path.exists():  # pragma: no cover — repo faylı
        raise FileNotFoundError(f"Əl ilə köçürülmüş plan faylı tapılmadı: {path}")
    entries = json.loads(path.read_text(encoding="utf-8"))
    for entry in entries:
        entry["rows"] = [{"total_hours": None, "semester": "", **row} for row in entry.get("rows") or []]
    return entries


def clean_subject_name(name: str) -> str:
    """Kataloqa yazılacaq ad: boşluq sadələşir, haşiyə ulduzu atılır, sahəyə sığır."""
    text = re.sub(r"\s+", " ", (name or "")).strip()
    return text.rstrip("*").strip()[:_NAME_MAX]


def _description(source: dict | None) -> str:
    """Fənnin PROVENANSI — kataloqa baxan adam onun haradan gəldiyini görsün."""
    source = source or {}
    return "\n".join(
        [
            "Universitet saytındakı rəsmi «Tədris planı» sənədində olan, lakin fənn "
            "kataloqunda olmayan fənn kimi AVTOMATİK yaradıldı "
            "(`import_curriculum_plans --create-subjects`).",
            f"Mənbə: {source.get('sayt_adi', '—')} · {source.get('senet', '—')}",
            f"URL: {source.get('url', '—')}",
        ]
    )


class SubjectCreator:
    """`unknown` sətirlərini kataloqa yazır və onları `matched`-ə keçirir.

    `dry_run` (defolt) rejimində obyektlər QURULUR, amma YAZILMIR — komandanın
    hesabat rejimi neçə fənn yaradılacağını göstərə bilsin. Yazma yalnız
    `--apply` ilə (`dry_run=False`) baş verir.
    """

    def __init__(self, organization, catalogue: dict, *, dry_run: bool = True):
        self.organization = organization
        #: ``{normalize(ad): Subject}`` — komandanın kataloq lüğəti. YERİNDƏ
        #: yenilənir ki, eyni icrada növbəti planlar yeni fənni TAPSIN və
        #: təkrar yaratmasın.
        self.catalogue = catalogue
        self.dry_run = dry_run
        self.created: list[Subject] = []
        self._number = self._first_free_number()

    def _first_free_number(self) -> int:
        """Növbəti boş `SAYT-####` nömrəsi — mövcud kodla toqquşmasın."""
        prefix = f"{SITE_CODE_PREFIX}-"
        highest = 0
        codes = Subject.objects.filter(organization=self.organization, code__startswith=prefix)
        for code in codes.values_list("code", flat=True):
            tail = (code or "")[len(prefix) :]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return highest + 1

    def _next_code(self) -> str:
        code = f"{SITE_CODE_PREFIX}-{self._number:04d}"
        self._number += 1
        return code

    def _build(self, row: dict, source: dict | None) -> Subject:
        """Bir sətirdən `Subject` qurur (hələ yazmır)."""
        credits = row.get("credits")
        fields = {
            "organization": self.organization,
            "code": self._next_code(),
            "name": clean_subject_name(row["name"]),
            "description": _description(source),
        }
        # Kredit yoxdursa və ya ağlabatan həddi aşırsa — modelin defaultu qalır.
        if credits and 0 < credits <= MAX_SANE_ECTS:
            fields["ects"] = credits
        return Subject(**fields)

    def absorb(self, result: dict, source: dict | None = None) -> int:
        """`unknown` sətirləri üçün fənn yaradır, onları `matched`-ə keçirir.

        Qaytarır: bu mənbədə YENİ yaradılan fənn sayı. Eyni ad bir neçə planda
        təkrarlanırsa, kataloq lüğəti sayəsində yalnız BİR dəfə yaradılır.
        """
        unknown = result["unknown"]
        if not unknown:
            return 0
        fresh: list[Subject] = []
        for row in unknown:
            key = normalize(row["name"])
            subject = self.catalogue.get(key)
            if subject is None:
                subject = self._build(row, source)
                self.catalogue[key] = subject
                fresh.append(subject)
            result["matched"].append({**row, "subject": subject})
        result["unknown"] = []
        if fresh and not self.dry_run:
            with rls_worker_atomic():
                Subject.objects.bulk_create(fresh)
        self.created.extend(fresh)
        return len(fresh)


__all__ = [
    "MANUAL_PLANS",
    "MAX_SANE_ECTS",
    "SITE_CODE_PREFIX",
    "SubjectCreator",
    "clean_subject_name",
    "load_manual_plans",
]
