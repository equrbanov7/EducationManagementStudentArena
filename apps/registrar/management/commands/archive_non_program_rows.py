"""İxtisas OLMAYAN «proqram» sətirlərini ARXİVLƏŞDİRİR (``is_active=False``).

Sahibin qərarı (2026-08-31)
---------------------------
«Lazımlıdırsa saxla» + «sistem magistr/doktorantura üçün də işlədiləcək» →
**SİLMƏ, arxivlə**: sətir seçicilərdə görünmür, amma ona bağlı tarixi qeydlər
(tələbə akademik qeydləri, tədris planları, qiymətlər) **toxunulmaz qalır**.

Hansı 8 sətir — ``_program_official_codes.NON_PROGRAM_ROWS``::

    MYEDU-61   Level                          İngilis dili mərkəzinin səviyyə qeydi
    MYEDU-65   aaa                            test sətri
    MYEDU-66   Dizayn Məktəbi                 fakültə adı
    MYEDU-36-M Magistratura və doktorantura   struktur bölməsi adı
    MYEDU-91   Lifelong                       davamlı təhsil mərkəzi
    MYEDU-91-M Lifelong                       eyni mərkəzin magistr dublikatı
    MYEDU-92   Kollec                         struktur bölməsi
    MYEDU-101  Kollec 2                       struktur bölməsi

«Magistratura və doktorantura» STRUKTUR bölməsidir, ixtisas deyil — real
magistr proqramları hədəfdə AYRICA sətirlərdir (``-M`` şəkilçili və
``MYEDU-<id>-M`` sətirləri), ona görə onu arxivləşdirmək magistratura
funksionallığını bağlamır.

Nə DƏYİŞMİR
-----------
* ``Program.code`` — köçürmə xəttinin şəxsiyyət açarıdır, toxunulmur.
* ``official_code`` — bu sətirlərdə onsuz da boşdur.
* Bağlı ``StudentAcademicRecord`` / ``Curriculum`` / ``Enrollment`` sətirləri —
  **BİRİ DƏ** dəyişmir, silinmir, deaktiv edilmir.  Komanda yalnız proqramın
  öz ``is_active`` bayrağını endirir.

Təhlükəsizlik
-------------
* **DEFOLT DRY-RUN** — ``--apply`` verilmədən heç nə yazılmır.
* **Fail-closed** — bazadakı ad gözlənilən adla uyuşmursa HEÇ NƏ yazılmır.
* **İdempotent** — artıq arxivlənmiş sətir keçilir.
* Bağlantı sayları (tələbə qeydi / tədris planı) hər icrada göstərilir ki,
  sahib arxivləşdirmənin nəyə toxunduğunu rəqəmlə görsün.
* Bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir.
* Hər yazı ``core.audit.log_action`` ilə audit izinə düşür.

İstifadə::

    python manage.py archive_non_program_rows                    # dry-run (defolt)
    python manage.py archive_non_program_rows --apply
    python manage.py archive_non_program_rows --apply --organization <uuid>
    python manage.py archive_non_program_rows --restore --apply  # geri qaytar
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from ...models import Program
from ._program_official_codes import NON_PROGRAM_ROWS

DOC = "docs/migration/IXTISAS_KODLARI_SAHIB_QERARI.md"
AUDIT_REASON = (
    "ixtisas olmayan sətir arxivləşdirildi (is_active=False) — sahibin 2026-08-31 qərarı; "
    "silinmədi, bağlı tarixi qeydlər toxunulmadı"
)
AUDIT_REASON_RESTORE = "ixtisas olmayan sətrin arxivi geri qaytarıldı (is_active=True) — əl ilə"


class Command(BaseCommand):
    help = "İxtisas olmayan 8 «proqram» sətrini arxivləşdirir (is_active=False). Defolt: dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument("--organization", dest="organization", default=None, help="yalnız bu təşkilatın (id)")
        parser.add_argument(
            "--restore",
            action="store_true",
            help="əks əməliyyat: həmin sətirləri yenidən aktiv et (is_active=True)",
        )

    # ── plan ────────────────────────────────────────────────────────────────

    def _build_plan(self, org_id, target_active: bool):
        """``(pending, already, blocked, missing)`` — kor UPDATE yoxdur."""

        programs = Program.objects.select_related("organization")
        if org_id:
            programs = programs.filter(organization_id=org_id)

        pending, already, blocked, missing = [], [], [], []
        for hold in NON_PROGRAM_ROWS:
            rows = list(programs.filter(code=hold.internal_code))
            if not rows:
                missing.append(hold)
                continue
            for row in rows:
                actual = (row.name or "").strip()
                if actual != hold.name:
                    blocked.append(
                        (
                            hold,
                            f"ad uyğun gəlmir: bazada «{actual}», gözlənilən «{hold.name}» "
                            f"(program id={row.pk}) — kor-koranə arxivlənmir",
                        )
                    )
                    continue
                if row.is_active == target_active:
                    already.append((row, hold))
                else:
                    pending.append((row, hold))
        return pending, already, blocked, missing

    def _attachments(self, row) -> dict:
        """Sətrə bağlı tarixi qeydlərin sayı — HEÇ BİRİ dəyişmir, sadəcə göstərilir."""

        return {
            "student_records": row.student_records.count(),
            "curricula": row.curricula.count(),
        }

    # ── hesabat ─────────────────────────────────────────────────────────────

    def _report(self, pending, already, blocked, missing, verb: str) -> None:
        write = self.stdout.write
        write(self.style.MIGRATE_HEADING(f"İxtisas olmayan sətirlər — {verb} planı ({len(NON_PROGRAM_ROWS)} namizəd)"))
        write("")
        for row, hold in pending:
            att = self._attachments(row)
            write(
                f"  {self.style.SUCCESS('→')} {hold.internal_code} «{hold.name}» — {hold.reason}\n"
                f"      bağlı (TOXUNULMUR): {att['student_records']} tələbə qeydi, "
                f"{att['curricula']} tədris planı"
            )
        for _row, hold in already:
            write(f"  {self.style.WARNING('=')} {hold.internal_code} «{hold.name}» — artıq {verb}")
        for hold in missing:
            write(f"  {self.style.WARNING('?')} {hold.internal_code} «{hold.name}» — bazada tapılmadı")
        for hold, reason in blocked:
            write(self.style.ERROR(f"  ✗ {hold.internal_code}: {reason}"))
        write("")
        write(f"Sənəd: {DOC} §4")

    # ── icra ────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        restore = options["restore"]
        target_active = bool(restore)
        verb = "aktivləşdirmə" if restore else "arxivləşdirmə"

        with rls_worker_atomic(), bypass_rls():
            pending, already, blocked, missing = self._build_plan(options["organization"], target_active)
            self._report(pending, already, blocked, missing, verb)

            if blocked:
                raise CommandError(
                    "Kimlik yoxlaması keçmədi — komanda fail-closed dayandı. Heç bir sətir dəyişdirilmədi."
                )

            if not options["apply"]:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING("DRY-RUN: heç nə yazılmadı (--apply ilə yazılır)."))
                return

            changed = self._apply(pending, target_active)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb.capitalize()}: {changed} sətir; {len(already)} artıq belə idi. "
                "Bağlı tarixi qeydlərin heç biri dəyişdirilmədi."
            )
        )

    def _apply(self, pending, target_active: bool) -> int:
        changed = 0
        with transaction.atomic():
            for row, hold in pending:
                old = row.is_active
                row.is_active = target_active
                row.save(update_fields=["is_active", "updated_at"])
                log_action(
                    action=AuditAction.UPDATE,
                    organization=row.organization,
                    obj=row,
                    old_values={"is_active": old},
                    new_values={"is_active": target_active},
                    changes={
                        "is_active": {"old": old, "new": target_active},
                        "internal_code_unchanged": row.code,
                        "why_not_a_program": hold.reason,
                        "attachments_untouched": self._attachments(row),
                    },
                    reason=AUDIT_REASON_RESTORE if target_active else AUDIT_REASON,
                    resource_type="registrar.Program",
                    resource_id=str(row.pk),
                    resource_repr=row.display_label,
                )
                changed += 1
        return changed
