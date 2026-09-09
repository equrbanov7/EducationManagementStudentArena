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


def _quote(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, urllib.parse.quote(parts.path), parts.query, ""))


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
                    organization, program, result["matched"], year=options["year"], force=options["force"]
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
        done = 0
        for source in sources:
            path = directory / (source.get("senet") or "").strip()
            if path.exists() and path.stat().st_size > 1000:
                continue
            try:
                request = urllib.request.Request(_quote(source["url"]), headers=HEADERS)
                path.write_bytes(urllib.request.urlopen(request, timeout=60).read())
                done += 1
            except Exception as exc:  # noqa: BLE001 — bir fayl bütün axını dayandırmasın
                self.stdout.write(self.style.ERROR(f"  endirilmədi: {source['sayt_adi'][:34]} ({exc})"))
        self.stdout.write(self.style.SUCCESS(f"Endirildi: {done} fayl → {directory}"))

    def _write_plan(self, organization, program, matched, *, year, force):
        """QARALAMA plan yaradır və tanınmış sətirləri yazır; sətir sayını qaytarır."""
        existing = Curriculum.objects.filter(organization=organization, program=program, admission_year=year).first()
        if existing is not None and not force:
            return 0
        with rls_worker_atomic():
            plan = Curriculum.objects.create(
                organization=organization,
                program=program,
                admission_year=year,
                name=f"{program.name} · {year}",
                status=PlanStatus.DRAFT,
                version=(existing.version + 1) if existing else 1,
                previous_version=existing,
            )
            CurriculumSubject.objects.bulk_create(
                [
                    CurriculumSubject(
                        organization=organization,
                        curriculum=plan,
                        subject=row["subject"],
                        semester_number=self._semester(row["semester"]),
                        credits=row["credits"] or 0,
                        total_hours=row["total_hours"] or 0,
                        order=index,
                    )
                    for index, row in enumerate(matched, start=1)
                ]
            )
        return len(matched)

    @staticmethod
    def _semester(value: str) -> int:
        """«payız-3» / «yaz-4» → 3 / 4; oxunmasa 1."""
        digits = re.findall(r"\d+", value or "")
        return int(digits[-1]) if digits else 1
