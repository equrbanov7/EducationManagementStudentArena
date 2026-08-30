"""Proqramlara RƏSMİ dövlət ixtisas şifrini (``official_code``) yazır.

Nə üçün var (2026-08-30, sahibin sözü)
--------------------------------------
«İxtisasın yanında ixtisas kodları olsun gərək … İndiki ixtisas kodları
uydurmadı deyəsən.» Doğrudur: MyEdu köçürməsi ``Program.code`` sütununu
sətirlərin çoxunda YER TUTUCU ilə doldurub (``MYEDU-<id>``, ``<şifr>-M``,
``<şifr>-<id>``) və tələbəyə məhz o göstərilirdi.

``code`` DƏYİŞDİRİLMİR
----------------------
``Program.code`` daxili identifikatordur və köçürmə xətti ondan asılıdır
(``apps/legacy_import`` onu ``TargetRef.key`` və ``program_pk_index()`` açarı
kimi işlədir). Bu komanda YALNIZ ``official_code`` sütununa toxunur.

Nə YAZILIR
----------
* Düşmən doğrulayıcısının açıq «TƏTBİQ ET» hökmü olan **5** şifr.
* ``--adopt-clean-codes`` verilsə (DEFOLT DEYİL): daxili kodu artıq təmiz
  6-rəqəmli milli şifr olan sətirlərin şifri OLDUĞU KİMİ mənimsənilir —
  yeni iddia deyil, sadəcə əvvəldən göstərilən dəyərin köçürülməsi.

Nə YAZILMIR (qəsdən)
--------------------
* Doğrulayıcının RƏDD etdiyi hər şey (8 sətir).
* Dərin sayt axtarışının 21 namizədi — doğrulayıcı «mən tətbiq etmədim,
  sahibin təsdiqi üçün» dedi.
* İxtisas OLMAYAN 8 sətir («Level», «aaa», «Kollec» …).
* ``050624`` «Cihazqayırma mühəndisliyi» — daxili şifri YANLIŞdır (milli
  təsnifatda 050624 = «Mədən mühəndisliyi»), ona görə rəsmi şifri BOŞ qalır
  və ``--adopt-clean-codes`` da onu keçir.

Hamısı ``--holds`` hesabatında və
``docs/migration/IXTISAS_KODLARI_SAHIB_QERARI.md`` sənədində sadalanır.

Təhlükəsizlik
-------------
* **DEFOLT DRY-RUN** — ``--apply`` verilmədən heç nə yazılmır.
* **İdempotent** — ikinci icrada yazılmış sətirlər «artıq düzgündür» keçilir.
* **Fail-closed** — ad/pillə uyuşmursa VƏ YA sətirdə fərqli rəsmi şifr artıq
  varsa komanda HEÇ NƏ yazmadan dayanır. Səssiz üstünə yazma YOXDUR.
* Cədvəlin özü hər icrada 05/06 pillə qaydasından keçir.
* Bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir
  (request-dən kənar entry-point qaydası).
* Hər yazı ``core.audit.log_action`` ilə audit izinə düşür: köhnə → yeni,
  sübut səviyyəsi, hər iki mənbə.

İstifadə::

    python manage.py set_program_official_codes                      # dry-run (defolt)
    python manage.py set_program_official_codes --holds              # yalnız buraxılanlar
    python manage.py set_program_official_codes --table              # sahibin doldurulacaq cədvəli
    python manage.py set_program_official_codes --apply              # yazır
    python manage.py set_program_official_codes --apply --adopt-clean-codes
    python manage.py set_program_official_codes --apply --organization <uuid>
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...models import Program
from ._program_official_codes import (
    ASSIGNMENTS,
    CLEAN_CODE_RE,
    HELD_BACK,
    LEVEL_PREFIXES,
    NON_PROGRAM_ROWS,
    SITE_SEARCH_CANDIDATES,
    SOURCE_CONTRADICTIONS,
    WRONG_CODES,
    WritePlan,
    check_table_health,
)

EVIDENCE_VERIFIED = "doğrulanmış — iki müstəqil mənbə + düşmən doğrulayıcısının «TƏTBİQ ET» hökmü"
EVIDENCE_ADOPTED = "mənimsənilmiş — daxili kod artıq təmiz 6-rəqəmli milli şifrdir (yeni iddia deyil)"

AUDIT_REASON = "rəsmi ixtisas şifri yazıldı (official_code); daxili code toxunulmadı — 2026-08-30 doğrulaması"
DOC = "docs/migration/IXTISAS_KODLARI_SAHIB_QERARI.md"


class Command(BaseCommand):
    help = "Proqramlara rəsmi dövlət ixtisas şifrini (official_code) yazır. Defolt: dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument(
            "--adopt-clean-codes",
            action="store_true",
            dest="adopt",
            help=(
                "daxili kodu artıq təmiz 6-rəqəmli milli şifr olan sətirlərdə həmin dəyəri "
                "official_code kimi mənimsə (yanlış siyahıdakılar keçilir)"
            ),
        )
        parser.add_argument("--organization", dest="organization", default=None, help="yalnız bu təşkilatın (id)")
        parser.add_argument("--holds", action="store_true", help="yalnız buraxılanları göstər (DB sorğusu yoxdur)")
        parser.add_argument(
            "--table",
            action="store_true",
            help=f"bazadakı HƏR proqram üçün doldurulacaq markdown cədvəl sətri çap et ({DOC} üçün)",
        )

    # ── sətir kimliyinin təsdiqi ────────────────────────────────────────────

    def _identity_problem(self, row, expected_name: str, degree_level: str) -> str | None:
        """Sətrin həqiqətən gözlənilən sətir olduğunu təsdiqlə (kor UPDATE yoxdur)."""

        if (row.name or "").strip() != expected_name:
            return (
                f"ad uyğun gəlmir: bazada «{row.name}», gözlənilən «{expected_name}» "
                f"(program id={row.pk}) — kor-koranə yazılmır"
            )
        # Ad TƏK BAŞINA kifayət deyil: «Kompüter Mühəndisliyi» həm bakalavr,
        # həm magistr sətrində eyni addır — pillə ikisini ayıran yeganə əlamətdir.
        if row.degree_level != degree_level:
            return (
                f"təhsil pilləsi uyğun gəlmir: bazada «{row.degree_level}», "
                f"gözlənilən «{degree_level}» (program id={row.pk})"
            )
        return None

    # ── plan ────────────────────────────────────────────────────────────────

    def _build_plan(self, org_id, adopt: bool) -> WritePlan:
        plan = WritePlan()
        programs = Program.objects.all()
        if org_id:
            programs = programs.filter(organization_id=org_id)

        wrong_internal = {row.internal_code for row in WRONG_CODES}

        for item in ASSIGNMENTS:
            rows = list(programs.filter(code=item.internal_code))
            if not rows:
                plan.missing.append(item)
                continue
            for row in rows:
                problem = self._identity_problem(row, item.expected_name, item.degree_level)
                if problem:
                    plan.blocked.append((item, problem))
                    continue
                current = (row.official_code or "").strip()
                if current == item.official_code:
                    plan.already_done.append(item)
                elif current:
                    plan.blocked.append(
                        (
                            item,
                            f"sətirdə artıq FƏRQLİ rəsmi şifr var: «{current}» ≠ «{item.official_code}» "
                            f"(program id={row.pk}) — səssiz üstünə yazılmır",
                        )
                    )
                else:
                    plan.pending.append((row, item))

        for wrong in WRONG_CODES:
            rows = list(programs.filter(code=wrong.internal_code))
            if not rows:
                plan.missing.append(wrong)
                continue
            for row in rows:
                problem = self._identity_problem(row, wrong.expected_name, wrong.degree_level)
                if problem:
                    plan.blocked.append((wrong, problem))
                    continue
                current = (row.official_code or "").strip()
                if current:
                    plan.blocked.append(
                        (
                            wrong,
                            f"YANLIŞ şifrli sətirdə rəsmi şifr doldurulub («{current}») — "
                            f"əl ilə yoxlanmalıdır (program id={row.pk})",
                        )
                    )
                else:
                    plan.kept_blank.append((row, wrong))

        if adopt:
            plan.adoptions = self._build_adoptions(programs, wrong_internal)

        return plan

    def _build_adoptions(self, programs, wrong_internal: set[str]) -> list:
        """Daxili kodu artıq təmiz milli şifr olan sətirlər — dəyəri olduğu kimi mənimsə."""

        assigned = {item.internal_code for item in ASSIGNMENTS}
        adoptions: list = []
        for row in programs.filter(official_code=""):
            code = (row.code or "").strip()
            if not CLEAN_CODE_RE.match(code) or code in wrong_internal or code in assigned:
                continue
            expected = LEVEL_PREFIXES.get(row.degree_level)
            if expected and not code.startswith(expected):
                # 05/06 qaydasını pozur → mexaniki sağlamlıq yoxlaması onu SAXLAYIR.
                self.stdout.write(
                    self.style.WARNING(f"  keçildi (05/06 qaydası): {code} «{row.name}» — pillə «{row.degree_level}»")
                )
                continue
            adoptions.append((row, code))
        return adoptions

    # ── hesabatlar ──────────────────────────────────────────────────────────

    def _report_plan(self, plan: WritePlan, adopt: bool) -> None:
        write = self.stdout.write
        write("")
        write(self.style.MIGRATE_HEADING("RƏSMİ İXTİSAS ŞİFRİ — PLAN"))
        write(f"  Cədvəldəki doğrulanmış şifr    : {len(ASSIGNMENTS)}")
        write(f"  Yazılacaq (doğrulanmış)        : {len(plan.pending)}")
        write(
            f"  Mənimsəniləcək (təmiz daxili)  : {len(plan.adoptions)}" + ("" if adopt else "  [--adopt-clean-codes]")
        )
        write(f"  Qəsdən BOŞ saxlanılır          : {len(plan.kept_blank)}")
        write(f"  Artıq düzgündür (idempotent)   : {len(plan.already_done)}")
        write(f"  Bazada tapılmadı               : {len(plan.missing)}")
        write(f"  BLOKLU (fail-closed)           : {len(plan.blocked)}")

        if plan.pending:
            write("")
            write(self.style.MIGRATE_LABEL("Yazılacaq (doğrulanmış):"))
            for row, item in plan.pending:
                write(f"  «{row.name}»  official_code: «{row.official_code}» → «{item.official_code}»")
                write(f"        daxili code (dəyişmir): {row.code}")
                write(f"        sübut  : {EVIDENCE_VERIFIED}")
                write(f"        mənbə 1: {item.source_primary}")
                write(f"        mənbə 2: {item.source_secondary}")
                if item.note:
                    write(f"        qeyd   : {item.note}")

        if plan.adoptions:
            write("")
            write(self.style.MIGRATE_LABEL("Mənimsəniləcək (daxili kod artıq təmiz milli şifrdir):"))
            for row, code in plan.adoptions:
                write(f"  «{row.name}»  official_code: «» → «{code}»   ({EVIDENCE_ADOPTED})")

        if plan.kept_blank:
            write("")
            write(self.style.MIGRATE_LABEL("Qəsdən BOŞ saxlanılan (yanlış daxili şifr):"))
            for row, wrong in plan.kept_blank:
                write(f"  «{row.name}»  daxili code «{row.code}» → official_code «» (yazılmır)")
                write(f"        səbəb : {wrong.reason}")

        for item in plan.already_done:
            write(f"  = artıq düzgündür: «{item.expected_name}» → {item.official_code}")
        for item in plan.missing:
            write(f"  ? bazada yoxdur  : {item.internal_code} «{item.expected_name}»")

    def _report_held_back(self) -> None:
        write = self.stdout.write
        write("")
        write(self.style.MIGRATE_HEADING("YAZILMAYANLAR — SAHİBİN QƏRARINI GÖZLƏYİR"))
        write(f"Tam, doldurulacaq cədvəl: {DOC}")

        write("")
        write(self.style.MIGRATE_LABEL(f"Doğrulayıcı RƏDD etdi / model qüsuru ({len(HELD_BACK)}):"))
        for hold in HELD_BACK:
            write(f"  {hold.internal_code} «{hold.name}»")
            write(f"      səbəb : {hold.reason}")
            if hold.proposal:
                write(f"      təklif: {hold.proposal}")

        write("")
        write(self.style.MIGRATE_LABEL(f"Dərin sayt axtarışının namizədləri ({len(SITE_SEARCH_CANDIDATES)}):"))
        for cand in SITE_SEARCH_CANDIDATES:
            write(f"  {cand.internal_code} «{cand.name}» → namizəd {cand.candidate_code} ({cand.degree_level})")
            write(f"      mənbə : {cand.source}")
            if cand.note:
                write(f"      qeyd  : {cand.note}")

        write("")
        write(
            self.style.MIGRATE_LABEL(f"İxtisas OLMAYAN sətirlər ({len(NON_PROGRAM_ROWS)}) — şifr yox, silinmə də yox:")
        )
        for hold in NON_PROGRAM_ROWS:
            write(f"  {hold.internal_code} «{hold.name}» — {hold.reason}")

        write("")
        write(self.style.MIGRATE_LABEL(f"Mənbənin öz ziddiyyətləri ({len(SOURCE_CONTRADICTIONS)}) — düzəldilməyib:"))
        for line in SOURCE_CONTRADICTIONS:
            write(f"  · {line}")

    def _report_table(self, org_id) -> None:
        """Sahibin sənədi üçün HƏR proqramın bir markdown sətri.

        «Təsdiqlənmiş şifr» sütunu qəsdən BOŞDUR — sahib 1-ci gün onu doldurur.
        """

        known = {item.internal_code: (item.official_code, "TƏTBİQ OLUNDU") for item in ASSIGNMENTS}
        known.update({c.internal_code: (c.candidate_code, c.source) for c in SITE_SEARCH_CANDIDATES})
        known.update({h.internal_code: ("—", "doğrulayıcı RƏDD etdi") for h in HELD_BACK})
        known.update({n.internal_code: ("—", "ixtisas deyil") for n in NON_PROGRAM_ROWS})
        known.update({w.internal_code: ("—", "YANLIŞ şifr — boş qalır") for w in WRONG_CODES})

        programs = Program.objects.all()
        if org_id:
            programs = programs.filter(organization_id=org_id)

        self.stdout.write("| Daxili kod | Ad | Pillə | Hazırkı rəsmi şifr | Namizəd | Mənbə | **Təsdiqlənmiş şifr** |")
        self.stdout.write("|---|---|---|---|---|---|---|")
        for row in programs.order_by("name", "code"):
            candidate, source = known.get(row.code, ("", ""))
            self.stdout.write(
                f"| `{row.code}` | {row.name} | {row.degree_level} | "
                f"{row.official_code or '—'} | {candidate or ''} | {source} | ☐ |"
            )

    # ── icra ────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        problems = check_table_health()
        if problems:
            for line in problems:
                self.stderr.write(self.style.ERROR(f"  {line}"))
            raise CommandError(
                "Şifr cədvəli öz sağlamlıq yoxlamasından keçmədi — HEÇ NƏ yazılmadı. "
                "Köhnə nəsil təsnifatda bakalavr 05xxxx, magistr 06xxxx-dir."
            )

        if options["holds"]:
            self._report_held_back()
            return

        if options["table"]:
            with rls_worker_atomic(), bypass_rls():
                self._report_table(options["organization"])
            return

        adopt = options["adopt"]
        apply_changes = options["apply"]

        with rls_worker_atomic(), bypass_rls():
            plan = self._build_plan(options["organization"], adopt)
            self._report_plan(plan, adopt)

            if plan.blocked:
                self.stdout.write("")
                self.stdout.write(self.style.ERROR("BLOKLU — heç nə yazılmadı:"))
                for item, reason in plan.blocked:
                    self.stdout.write(self.style.ERROR(f"  {item.internal_code}: {reason}"))
                raise CommandError("Ziddiyyət tapıldı — komanda fail-closed dayandı. Heç bir sətir dəyişdirilmədi.")

            self._report_held_back()

            if not apply_changes:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING("DRY-RUN: heç nə yazılmadı (--apply ilə yazılır)."))
                return

            written, adopted = self._apply(plan)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Yazıldı: {written} doğrulanmış şifr, {adopted} mənimsənilmiş şifr; "
                f"{len(plan.kept_blank)} sətir qəsdən boş qaldı."
            )
        )

    def _apply(self, plan: WritePlan) -> tuple[int, int]:
        written = 0
        adopted = 0
        with transaction.atomic():
            for row, item in plan.pending:
                self._write(row, item.official_code, EVIDENCE_VERIFIED, item.source_primary, item.source_secondary)
                written += 1
            for row, code in plan.adoptions:
                self._write(row, code, EVIDENCE_ADOPTED, f"MyEdu daxili kodu «{code}»", "milli təsnifat formatı")
                adopted += 1
        return written, adopted

    def _write(self, row, official_code: str, evidence: str, source_primary: str, source_secondary: str) -> None:
        old = row.official_code
        row.official_code = official_code
        row.save(update_fields=["official_code", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            organization=row.organization,
            obj=row,
            old_values={"official_code": old},
            new_values={"official_code": official_code},
            changes={
                "official_code": {"old": old, "new": official_code},
                "internal_code_unchanged": row.code,
                "evidence": evidence,
                "source_primary": source_primary,
                "source_secondary": source_secondary,
            },
            reason=AUDIT_REASON,
            resource_type="registrar.Program",
            resource_id=str(row.pk),
            resource_repr=row.display_label,
        )
