"""Universitet saytındakı «Tədris planı» PDF-lərini QARALAMA plana çevirir.

Sahib (2026-09-09): «burdakı tədris planlarını yükləyib hər ixtisasa əlavə et».
Mənbə siyahısı repodadır: ``apps/registrar/data/ixtisas/plan_sources.tsv``
(ixtisas adı · köhnə şifr · sənəd adı · URL) — saytdan bir dəfə yığılıb ki,
icra zamanı şəbəkə lazım olmasın və mənbə nəzərdən keçirilə bilsin.

ÜÇ ADDIM
--------
1. ``--fetch``  — PDF-ləri ``--dir`` qovluğuna endirir (YEGANƏ şəbəkə addımı).
2. (defolt)     — parse edir və HESABAT verir: neçə sətir tanındı, neçəsi
                  fənn kataloqunda tapıldı, neçəsi seçmə blokdur, neçəsi
                  tapılmadı. Bazaya heç nə yazılmır.
3. ``--apply``  — YALNIZ tanınmış tək fənn sətirlərini QARALAMA (`DRAFT`)
                  plana yazır.

NİYƏ QARALAMA
-------------
Plan dərs yükünü, jurnalı və məzuniyyət yoxlamasını idarə edir. Qaralama plan
heç nəyə təsir etmir: o, mövcud təsdiq zəncirindən (kafedra → şura → tədris
şöbəsi) keçməyincə işə düşmür. Yəni idxal insanın nəzərdən keçirməsini ƏVƏZ
ETMİR, ona hazırlıq verir.

NƏ YAZILMIR (qəsdən)
--------------------
* **seçmə bloklar** — «I blok: 1. Sosiologiya 2. AR Konstitusiyası …» bir xanada
  bir neçə fənndir; tək `CurriculumSubject` deyil (planın ~34%-i);
* **kataloqda tapılmayan fənn** — sistem fənn UYDURMUR, siyahı ilə göstərir;
* planı onsuz da olan ixtisas — `--force` olmadan toxunulmur.

İstifadə::

    python manage.py import_curriculum_plans --fetch --dir /tmp/plans
    python manage.py import_curriculum_plans --dir /tmp/plans            # hesabat
    python manage.py import_curriculum_plans --dir /tmp/plans --apply --year 2023
"""

from __future__ import annotations

import csv
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.registrar.models import Curriculum, CurriculumSubject, PlanStatus, Program, Subject
from apps.registrar.plan_import import extract_any, match_rows, normalize
from core.rls_pooling import rls_worker_atomic

SOURCES = Path(__file__).resolve().parents[2] / "data" / "ixtisas" / "plan_sources.tsv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
}


#: Ardıcıl sorğular arasında fasilə — sayt sürətli seriyada HTML səhv səhifəsi verir.
FETCH_PAUSE = 0.8
RETRY_PAUSE = 3.0
RETRIES = 3


def _is_pdf(path: Path) -> bool:
    """Fayl həqiqətən PDF-dir? (HTML səhv səhifəsi də 200 ilə gəlir.)"""
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"%PDF"
    except OSError:  # pragma: no cover — oxunmayan fayl onsuz da yenidən endirilir
        return False


def _quote(url: str) -> str:
    """URL yolunu təhlükəsiz kodlaşdırır — İDEMPOTENT.

    ⚠️ Mənbə cədvəlindəki URL-lərin bir hissəsi saytdan ARTIQ faiz-kodlanmış
    şəkildə yığılıb (`…/050405%20%C4%B0qtisadiyyat%202023.pdf`). Sadə `quote`
    onları İKİNCİ dəfə kodlayır (`%20` → `%2520`) və sayt 200 ilə HTML səhv
    səhifəsi qaytarır — 11 plan məhz buna görə «PDF deyil» olurdu. Ona görə
    əvvəlcə `unquote`, sonra `quote`.
    """
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def load_sources() -> list[dict]:
    if not SOURCES.exists():  # pragma: no cover — repo faylı
        raise CommandError(f"Mənbə siyahısı tapılmadı: {SOURCES}")
    with SOURCES.open(encoding="utf-8") as handle:
        body = [line for line in handle if not line.startswith("#")]
    return [dict(row) for row in csv.DictReader(body, delimiter="\t")]


class Command(BaseCommand):
    help = "Sayt «Tədris planı» PDF-lərini qaralama plana çevirir (defolt: hesabat)."

    def add_arguments(self, parser):
        parser.add_argument("--org", dest="org_slug", default="", help="Təşkilat slug-ı.")
        parser.add_argument("--dir", dest="directory", required=True, help="PDF qovluğu.")
        parser.add_argument("--fetch", action="store_true", help="PDF-ləri endir (şəbəkə).")
        parser.add_argument("--apply", action="store_true", help="Qaralama plan YARAT.")
        parser.add_argument("--year", type=int, default=2023, help="Qəbul ili (defolt 2023).")
        parser.add_argument("--force", action="store_true", help="Planı olan ixtisası da idxal et.")

    def handle(self, *args, **options):
        sources = load_sources()
        directory = Path(options["directory"])
        directory.mkdir(parents=True, exist_ok=True)

        if options["fetch"]:
            self._fetch(sources, directory)
            return

        organization = self._organization(options.get("org_slug"))
        catalogue = {}
        for subject in Subject.objects.filter(organization=organization):
            catalogue.setdefault(normalize(subject.name), subject)
        # ⚠️ Uyğunluq fayl adındakı 050XXX şifri ilə QURULMUR. Saytdakı şifrlərin
        # bir hissəsi səhvdir (bax `_program_official_codes.py`) — sınaqda o yol
        # Psixologiya planını Regionşünaslığa, İqtisadiyyatı «Sənayenin təşkili»nə
        # bağlayırdı. Mənbə cədvəlindəki HƏLL EDİLMİŞ `proqram` sütunu işlədilir.
        programs = {
            (program.degree_level, normalize(program.name)): program
            for program in Program.objects.filter(organization=organization)
        }

        totals = {"rows": 0, "matched": 0, "electives": 0, "unknown": 0, "written": 0, "plans": 0}
        unmatched_names: list[str] = []

        for source in sources:
            path = directory / (source.get("senet") or "").strip()
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"  fayl yoxdur: {source['sayt_adi']} → {path.name}"))
                continue
            try:
                # Düzüm ÖZÜ seçilir: bakalavr cədvəli, alınmasa magistr cədvəli.
                rows, layout = extract_any(str(path))
            except Exception as exc:  # noqa: BLE001 — pozuq PDF axını dayandırmasın
                self.stdout.write(self.style.ERROR(f"  oxunmadı: {source['sayt_adi']} ({exc.__class__.__name__})"))
                continue

            result = match_rows(rows, catalogue)
            totals["rows"] += len(rows)
            totals["matched"] += len(result["matched"])
            totals["electives"] += len(result["electives"])
            totals["unknown"] += len(result["unknown"])
            unmatched_names.extend(row["name"] for row in result["unknown"])

            resolved = (source.get("proqram") or "").strip()
            program = programs.get((source.get("seviyye") or "", normalize(resolved))) if resolved else None
            flag = " ⚠ az sətir" if result["low_yield"] else ""
            target = program.name if program else self.style.WARNING("ixtisas ƏL İLƏ həll edilməlidir")
            self.stdout.write(
                f"  {len(rows):3d} sətir → {len(result['matched']):3d} uyğun · "
                f"{len(result['electives']):2d} blok · {len(result['unknown']):3d} tapılmadı{flag}  "
                f"{source['sayt_adi'][:32]:34} → {target}"
            )

            if options["apply"] and program is not None and result["matched"]:
                written = self._write_plan(
                    organization,
                    program,
                    result["matched"],
                    year=options["year"],
                    force=options["force"],
                    source=source,
                )
                totals["written"] += written
                totals["plans"] += 1 if written else 0

        self.stdout.write(self.style.MIGRATE_HEADING("\nYEKUN"))
        self.stdout.write(
            f"  sətir {totals['rows']} · uyğun {totals['matched']} · seçmə blok "
            f"{totals['electives']} · tapılmadı {totals['unknown']}"
        )
        if options["apply"]:
            self.stdout.write(f"  yazıldı: {totals['written']} sətir / {totals['plans']} qaralama plan")
        else:
            self.stdout.write(self.style.NOTICE("  HESABAT rejimi — heç nə yazılmadı (`--apply` ilə yazılır)."))
        if unmatched_names:
            self.stdout.write("\n  Kataloqda tapılmayan fənn adları (ilk 25):")
            for name in sorted(set(unmatched_names))[:25]:
                self.stdout.write(f"    · {name[:88]}")

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def _organization(self, slug):
        queryset = Organization.objects.filter(is_active=True)
        if slug:
            queryset = queryset.filter(slug=slug)
        organization = queryset.first()
        if organization is None:
            raise CommandError("Təşkilat tapılmadı.")
        return organization

    def _fetch(self, sources, directory):
        """PDF-ləri endirir. ⚠️ Yalnız HTTP 200 YETƏRLİ DEYİL.

        Sayt ardıcıl sorğuda bəzən 200 ilə HTML səhv səhifəsi qaytarır (~48 KB).
        Köhnə yoxlama «fayl var və >1000 bayt» idi, ona görə həmin HTML «endirilmiş»
        sayılır, `--fetch` onu bir daha çəkmir və parser 11 planda `FileDataError`
        verirdi. İndi məzmun `%PDF` imzası ilə yoxlanılır, alınmayan fayl SİLİNİR
        və sorğular arasında qısa fasilə verilir.
        """
        done, failed = 0, []
        for source in sources:
            path = directory / (source.get("senet") or "").strip()
            if path.exists() and _is_pdf(path):
                continue
            for attempt in range(RETRIES):
                if attempt:
                    time.sleep(RETRY_PAUSE)
                try:
                    request = urllib.request.Request(_quote(source["url"]), headers=HEADERS)
                    payload = urllib.request.urlopen(request, timeout=60).read()
                except Exception as exc:  # noqa: BLE001 — bir fayl bütün axını dayandırmasın
                    error = str(exc)
                    continue
                if not payload.startswith(b"%PDF"):
                    error = f"PDF deyil ({len(payload)} bayt)"
                    continue
                path.write_bytes(payload)
                done += 1
                break
            else:
                path.unlink(missing_ok=True)  # yalançı «endirilmiş» qalmasın
                failed.append(f"{source['sayt_adi'][:40]} ({error})")
            time.sleep(FETCH_PAUSE)

        self.stdout.write(self.style.SUCCESS(f"Endirildi: {done} fayl → {directory}"))
        for line in failed:
            self.stdout.write(self.style.ERROR(f"  endirilmədi: {line}"))

    def _write_plan(self, organization, program, matched, *, year, force, source=None):
        """QARALAMA plan yaradır və tanınmış sətirləri yazır; sətir sayını qaytarır.

        ⚠️ KREDİTSİZ sətir YAZILMIR. Magistr cədvəlində kredit sütunu ad sütunu
        ilə həmişə üst-üstə düşmür; parser belə halda krediti `None` saxlayır
        (taxmin etmir). `credits or 0` yazsaydıq, planda 0 kreditli fənn qalar
        və məzuniyyət yoxlaması sükutla səhv işləyərdi.
        """
        rows = [row for row in matched if row.get("credits")]
        if not rows:
            return 0
        existing = Curriculum.objects.filter(organization=organization, program=program, admission_year=year).first()
        if existing is not None and not force:
            return 0
        skipped = len(matched) - len(rows)
        note = self._provenance(source, total=len(matched), written=len(rows), skipped=skipped)
        with rls_worker_atomic():
            plan = Curriculum.objects.create(
                organization=organization,
                program=program,
                admission_year=year,
                name=f"{program.name} · {year}",
                status=PlanStatus.DRAFT,
                version=(existing.version + 1) if existing else 1,
                previous_version=existing,
                last_reason=note,
            )
            CurriculumSubject.objects.bulk_create(
                [
                    CurriculumSubject(
                        organization=organization,
                        curriculum=plan,
                        subject=row["subject"],
                        semester_number=self._semester(row["semester"]),
                        credits=row["credits"],
                        total_hours=row["total_hours"] or 0,
                        row_code=(row.get("code") or "")[:32],
                        order=index,
                    )
                    for index, row in enumerate(rows, start=1)
                ]
            )
        return len(rows)

    @staticmethod
    def _provenance(source, *, total, written, skipped):
        """Planın haradan gəldiyini plan qeydində saxlayır (təsdiq edən görsün)."""
        source = source or {}
        parts = [
            "Universitet saytındakı rəsmi «Tədris planı» sənədindən AVTOMATİK "
            "qaralama kimi idxal edildi (insan təsdiqi tələb olunur).",
            f"Mənbə: {source.get('sayt_adi', '—')} · {source.get('senet', '—')}",
            f"URL: {source.get('url', '—')}",
            f"Tanınmış sətir: {total} · yazıldı: {written} · krediti oxunmadığı üçün buraxıldı: {skipped}",
        ]
        if (source.get("seviyye") or "") == "master":
            parts.append(
                "⚠️ Magistr sənədində semestr bölgüsü YOXDUR — bütün sətirlər 1-ci "
                "semestrə qoyulub, təsdiqdən əvvəl əl ilə bölünməlidir."
            )
        return "\n".join(parts)

    @staticmethod
    def _semester(value: str) -> int:
        """«payız-3» / «yaz-4» → 3 / 4; oxunmasa 1."""
        digits = re.findall(r"\d+", value or "")
        return int(digits[-1]) if digits else 1
