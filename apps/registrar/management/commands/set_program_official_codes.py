"""Proqramlara HƏR İKİ rəsmi dövlət ixtisas şifrini yazır.

Nə üçün var (sahibin sözü)
--------------------------
«İxtisasın yanında ixtisas kodları olsun gərək, bunu hər kəs görə bilməlidi;
indiki ixtisas kodları uydurmadı deyəsən.» → «Burda yeni və köhnə kodlar var,
bunları da əlavə et.»

Doğrudur: MyEdu köçürməsi ``Program.code`` sütununu yer tutucu ilə doldurmuşdu
(``MYEDU-<id>``, ``<şifr>-M``) və rəqəmli görünən 28 şifrin **25-i tamam başqa
ixtisası göstərirdi** (``050620`` «Kompüter Mühəndisliyi» əslində «Dəniz
naviqasiyası mühəndisliyi»dir). Bu komanda hər iki nəslin şifrini rəsmi
kataloqdan yazır.

İKİ sütun yazılır
-----------------
``official_code``
    CARİ təsnifat (NK 503, 02.12.2024) — ``6XXXXXX``/``7XXXXXX``.
``legacy_official_code``
    ƏVVƏLKİ nəsil — ``050XXX``/``060XXX``. Köhnə tələbələrin diplomundakı şifr.

``code`` (daxili ``MYEDU-*`` açarı) DƏYİŞDİRİLMİR — ``apps/legacy_import`` onu
``TargetRef.key`` və ``program_pk_index()`` açarı kimi işlədir.

Nə YAZILMIR (qəsdən)
--------------------
* **şübhəli (7 sətir)** — bir neçə real namizəd var, seçim SAHİBİNDİR.
* **tapılmadı (8 sətir)** — sətir ixtisas DEYİL («Level», «aaa», «Kollec» …);
  şifr verilmir, silinmə də olmur.
* Yeni təsnifatda ləğv olunmuş ixtisasda ``official_code`` boş qalır (yalnız
  köhnə yazılır); yeni ixtisasda ``legacy_official_code`` boş qalır.

Hamısı ``--holds`` hesabatında və ``docs/migration/IXTISAS_KODLARI.md``-dədir.

Təhlükəsizlik
-------------
* **DEFOLT DRY-RUN** — ``--apply`` verilmədən heç nə yazılmır.
* **İdempotent** — ikinci icrada yazılmış sətirlər «artıq düzgündür» keçilir.
  Repetisiya bazası yenidən qurulanda təkrar işlədilə bilər.
* **Fail-closed** — data faylı kataloq yoxlamasından keçmirsə, ad/pillə
  uyuşmursa, VƏ YA sətirdə FƏRQLİ şifr artıq varsa komanda HEÇ NƏ yazmadan
  dayanır. Səssiz üstünə yazma YOXDUR (``--force`` istisna).
* Bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir.
* Hər yazı ``core.audit.log_action`` ilə audit izinə düşür.

İstifadə::

    python manage.py set_program_official_codes                 # dry-run (defolt)
    python manage.py set_program_official_codes --holds         # yalnız buraxılanlar
    python manage.py set_program_official_codes --table         # sahibin cədvəli
    python manage.py set_program_official_codes --apply         # yazır
    python manage.py set_program_official_codes --apply --force # fərqli şifri əvəz et
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
    MAPPING_FILE,
    WritePlan,
    load_rows,
    non_program_rows,
    owner_decision_rows,
    validate,
    writable_rows,
)

AUDIT_REASON = (
    "rəsmi ixtisas şifrləri yazıldı (official_code + legacy_official_code); "
    "daxili code toxunulmadı — NK 503/2024 + e-qanun 16051/21781 kataloqları"
)
DOC = "docs/migration/IXTISAS_KODLARI.md"
EVIDENCE = "rəsmi kataloqda şifr+ad üzrə təsdiqlənib (apps/registrar/data/ixtisas/)"

#: Yazılan sahələr: model sahəsi → :class:`CodeRow` atributu.
FIELDS = (("official_code", "current_code"), ("legacy_official_code", "legacy_code"))


class Command(BaseCommand):
    help = "Proqramlara rəsmi dövlət ixtisas şifrlərini (cari + köhnə) yazır. Defolt: dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument(
            "--force",
            action="store_true",
            help="sətirdə artıq FƏRQLİ şifr varsa da üstünə yaz (defolt: fail-closed dayanır)",
        )
        parser.add_argument("--organization", dest="organization", default=None, help="yalnız bu təşkilatın (id)")
        parser.add_argument("--holds", action="store_true", help="yalnız buraxılanları göstər (DB sorğusu yoxdur)")
        parser.add_argument("--table", action="store_true", help=f"hər proqram üçün markdown sətri ({DOC} üçün)")

    # ── plan ────────────────────────────────────────────────────────────────

    def _identity_problem(self, row, code_row) -> str | None:
        """Sətrin həqiqətən gözlənilən sətir olduğunu təsdiqlə (kor UPDATE yoxdur)."""
        if (row.name or "").strip() != code_row.expected_name:
            return (
                f"ad uyğun gəlmir: bazada «{row.name}», gözlənilən «{code_row.expected_name}» "
                f"(program id={row.pk}) — kor-koranə yazılmır"
            )
        # Ad TƏK BAŞINA kifayət deyil: «Kompüter Mühəndisliyi» həm bakalavr,
        # həm magistr sətrində eyni addır — pillə ikisini ayıran yeganə əlamətdir.
        if row.degree_level != code_row.degree_level:
            return (
                f"təhsil pilləsi uyğun gəlmir: bazada «{row.degree_level}», "
                f"gözlənilən «{code_row.degree_level}» (program id={row.pk})"
            )
        return None

    def _build_plan(self, org_id, force: bool) -> WritePlan:
        plan = WritePlan()
        programs = Program.objects.all()
        if org_id:
            programs = programs.filter(organization_id=org_id)

        writable = {code_row.internal_code: code_row for code_row in writable_rows()}
        held = {code_row.internal_code: code_row for code_row in (*owner_decision_rows(),)}
        held.update({code_row.internal_code: code_row for code_row in load_rows() if code_row.is_not_a_program})

        for code_row in writable.values():
            rows = list(programs.filter(code=code_row.internal_code))
            if not rows:
                plan.missing.append(code_row)
                continue
            for row in rows:
                problem = self._identity_problem(row, code_row)
                if problem:
                    plan.blocked.append((code_row, problem))
                    continue
                changes = self._diff(row, code_row, force, plan)
                if changes is None:
                    continue
                if changes:
                    plan.pending.append((row, code_row, changes))
                else:
                    plan.already_done.append((row, code_row))

        for code_row in held.values():
            for row in programs.filter(code=code_row.internal_code):
                plan.held.append((row, code_row))

        return plan

    def _diff(self, row, code_row, force: bool, plan: WritePlan) -> dict | None:
        """Yazılacaq sahələr; ziddiyyət varsa ``None`` (və ``plan.blocked``-a düşür)."""
        changes: dict[str, tuple[str, str]] = {}
        for field_name, attr in FIELDS:
            wanted = getattr(code_row, attr)
            current = (getattr(row, field_name) or "").strip()
            if not wanted or current == wanted:
                # Kataloqda şifr yoxdursa mövcud dəyər SİLİNMİR — sahibin əl ilə
                # yazdığı şifri komanda boşaltmamalıdır.
                continue
            if current and not force:
                plan.blocked.append(
                    (
                        code_row,
                        f"sətirdə artıq FƏRQLİ «{field_name}» var: «{current}» ≠ «{wanted}» "
                        f"(program id={row.pk}) — səssiz üstünə yazılmır (--force)",
                    )
                )
                return None
            changes[field_name] = (current, wanted)
        return changes

    # ── hesabatlar ──────────────────────────────────────────────────────────

    def _report_plan(self, plan: WritePlan) -> None:
        write = self.stdout.write
        write("")
        write(self.style.MIGRATE_HEADING("RƏSMİ İXTİSAS ŞİFRLƏRİ — PLAN"))
        write(f"  Data faylındakı sətir          : {len(load_rows())}  ({MAPPING_FILE.name})")
        write(f"  Yazıla bilən (dəqiq + yüksək)  : {len(writable_rows())}")
        write(f"  Yazılacaq                      : {len(plan.pending)}")
        write(f"  Artıq düzgündür (idempotent)   : {len(plan.already_done)}")
        write(f"  Qəsdən BOŞ (sahib/ixtisas deyil): {len(plan.held)}")
        write(f"  Bazada tapılmadı               : {len(plan.missing)}")
        write(f"  BLOKLU (fail-closed)           : {len(plan.blocked)}")

        if plan.pending:
            write("")
            write(self.style.MIGRATE_LABEL("Yazılacaq:"))
            for row, code_row, changes in plan.pending:
                write(f"  «{row.name}»  (daxili code dəyişmir: {row.code})")
                for field_name, (old, new) in changes.items():
                    write(f"        {field_name}: «{old}» → «{new}»")
                write(f"        əminlik: {code_row.confidence}   sübut: {EVIDENCE}")
                if code_row.note:
                    write(f"        qeyd   : {code_row.note}")

        for row, _code_row in plan.already_done:
            write(f"  = artıq düzgündür: «{row.name}» → {row.official_code_pair or '—'}")
        for code_row in plan.missing:
            write(f"  ? bazada yoxdur  : {code_row.internal_code} «{code_row.expected_name}»")

    def _report_held_back(self) -> None:
        write = self.stdout.write
        owner = owner_decision_rows()
        non_programs = non_program_rows()

        write("")
        write(self.style.MIGRATE_HEADING("YAZILMAYANLAR"))
        write(f"Tam siyahı və namizədlər: {DOC}")

        write("")
        write(self.style.MIGRATE_LABEL(f"SAHİBİN QƏRARINI gözləyir — «şübhəli» ({len(owner)}):"))
        for code_row in owner:
            write(f"  {code_row.internal_code} «{code_row.expected_name}» ({code_row.degree_level})")
            write(f"      namizədlər: {code_row.note}")

        write("")
        write(self.style.MIGRATE_LABEL(f"İxtisas OLMAYAN sətirlər ({len(non_programs)}) — şifr yox, silinmə də yox:"))
        for hold in non_programs:
            write(f"  {hold.internal_code} «{hold.name}» — {hold.reason}")

    def _report_table(self, org_id) -> None:
        known = {code_row.internal_code: code_row for code_row in load_rows()}
        programs = Program.objects.all()
        if org_id:
            programs = programs.filter(organization_id=org_id)

        self.stdout.write("| Daxili kod | Ad | Pillə | Cari şifr | Köhnə şifr | Əminlik | Qeyd |")
        self.stdout.write("|---|---|---|---|---|---|---|")
        for row in programs.order_by("name", "code"):
            code_row = known.get(row.code)
            self.stdout.write(
                f"| `{row.code}` | {row.name} | {row.degree_level} | "
                f"{row.official_code_current or '—'} | {row.official_code_legacy or '—'} | "
                f"{code_row.confidence if code_row else '—'} | {code_row.note if code_row else ''} |"
            )

    # ── icra ────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        problems = validate()
        if problems:
            for line in problems:
                self.stderr.write(self.style.ERROR(f"  {line}"))
            raise CommandError(
                f"«{MAPPING_FILE.name}» rəsmi kataloq yoxlamasından keçmədi — HEÇ NƏ yazılmadı. "
                "Hər şifr kataloqda mövcud olmalı, adı üst-üstə düşməli və pilləyə uyğun olmalıdır."
            )

        if options["holds"]:
            self._report_held_back()
            return

        if options["table"]:
            with rls_worker_atomic(), bypass_rls():
                self._report_table(options["organization"])
            return

        with rls_worker_atomic(), bypass_rls():
            plan = self._build_plan(options["organization"], options["force"])
            self._report_plan(plan)

            if plan.blocked:
                self.stdout.write("")
                self.stdout.write(self.style.ERROR("BLOKLU — heç nə yazılmadı:"))
                for code_row, reason in plan.blocked:
                    self.stdout.write(self.style.ERROR(f"  {code_row.internal_code}: {reason}"))
                raise CommandError("Ziddiyyət tapıldı — komanda fail-closed dayandı. Heç bir sətir dəyişdirilmədi.")

            self._report_held_back()

            if not options["apply"]:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING("DRY-RUN: heç nə yazılmadı (--apply ilə yazılır)."))
                return

            written = self._apply(plan)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Yazıldı: {written} proqram; {len(plan.already_done)} artıq düzgün idi; "
                f"{len(plan.held)} sətir qəsdən boş qaldı."
            )
        )

    def _apply(self, plan: WritePlan) -> int:
        written = 0
        with transaction.atomic():
            for row, code_row, changes in plan.pending:
                self._write(row, code_row, changes)
                written += 1
        return written

    def _write(self, row, code_row, changes: dict) -> None:
        for field_name, (_old, new) in changes.items():
            setattr(row, field_name, new)
        row.save(update_fields=[*changes, "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            organization=row.organization,
            obj=row,
            old_values={name: old for name, (old, _new) in changes.items()},
            new_values={name: new for name, (_old, new) in changes.items()},
            changes={
                **{name: {"old": old, "new": new} for name, (old, new) in changes.items()},
                "internal_code_unchanged": row.code,
                "confidence": code_row.confidence,
                "evidence": EVIDENCE,
                # str(): audit JSONField-inə lazy proxy sızmasın.
                "note": str(code_row.note),
            },
            reason=AUDIT_REASON,
            resource_type="registrar.Program",
            resource_id=str(row.pk),
            resource_repr=row.display_label_full,
        )
