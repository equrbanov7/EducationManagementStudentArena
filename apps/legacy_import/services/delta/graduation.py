"""``graduation`` fazası — cari semestrin jurnallarında OLMAYAN və proqram müddəti bitmiş tələbələrin rəsmi «Məzun etmə» əmri.

Sahib 2026-10-25: «Əgər bu ilin jurnalında onların adı yoxdursa — MƏZUN ET; yoxsa ola bilər kimsə kəsilib,
bitirməyib — onu məzun etmə.» Köçürmədə bütün qeydlər ``enrolled`` qaldı (köhnə sistem məzunu ayırmırdı), ona görə
reyestrdə ~4 250 «aktiv» tələbə heç bir cari jurnalda yoxdur.

NAMİZƏD (hamısı birlikdə):

* akademik qeyd ``enrolled``;
* YENİ sistemdə tələbənin cari və ya gələcək (aktiv) dövrdə HEÇ BİR qeydiyyatı yoxdur (status fərq etmir);
* KÖHNƏ sistemin cari semestr jurnallarında (paketin ``journals`` bölməsi, ``is_current`` + ``full_semesters``)
  yoxdur — tutuşdurula bilməyən legacy sətrinin FİN-i və ya adı eyni olan hesab da «yoxlanmalı»dır;
* köhnə sistemdə azad edilməyib (``azadedildi=1`` → xaric — ``registry_sync``-in işidir, məzun deyil);
* cutover-dən sonra yeni sistemdə əl ilə hərəkət/status/köçürmə izi yoxdur (RİM/dekanlıq qalibdir);
* **proqram müddəti bitib**: qəbul ili + ceil(ECTS / 60) ≤ cari tədris ilinin başlanğıcı (2026/2027 → 2026; yəni
  2026-nın yayına qədər bitirməli idi). Bakalavr 240 ECTS → 4 il, magistr 120 → 2 il;
* **son kursa çatıb**: yeni sistemdəki SON jurnal semestri proqramın son tədris ilindədir və ya ondan sonradır
  (məs. 2022 bakalavr → 2025/2026). Daha əvvəl kəsilən (2022 qəbulu, son jurnal 2022/2023 Yaz) — «kəsilib,
  bitirməyib» ola bilər. Jurnal tarixçəsi köçürülmüş ilk tədris ilindən (2021/2022) sonra bitməli olub heç
  jurnalı olmayan da yoxlanmalıdır; tarixçədən əvvəl bitənlər (2017–2019 qəbulu) bu yoxlamadan azaddır;
* qrupu «silinməli» / «xaric olan» / «test» qabı deyil.

Müddəti bitməyənlər (məs. 2023 qəbulu bakalavr, jurnalda yoxdur — kəsilib / akademik məzuniyyət ola bilər) və qəbul
ili bilinməyənlər (köçürmə sentineli 1950) MƏZUN EDİLMİR — adlı «yoxlanmalı» siyahısına düşür (qrup, qəbul ili,
yeni sistemdə son jurnal semestri).

Əmr: ``MZN-SINX-2026``, tarix sabit ``2026-07-01`` (2025/2026 tədris ilinin sonu); səbəb ``registry_sync`` ilə eyni
prefiksdədir (``SYNC_REASON``) — sinxronun öz izi «əl ilə dəyişiklik» sayılmır. Rəsmi servis
(``registrar.movements.create_movement(kind=graduation)``): status ``graduated``, açıq qeydiyyatlar dondurulur, giriş
bağlanır (başqa aktiv qeydi olan istisna). Geri qaytarma — hər tələbə üçün «Bərpa» əmri. Bildiriş GETMİR.
İdempotentdir: ikinci qaçışda məzunlar artıq ``graduated`` — 0 yazı.

Sahibin 2026-10-25 ikinci qərarı (paketin ``snapshot``-unda opt-in bayraqlar, ``graduation_owner.py``):
``graduate_year_unknown`` (qəbul ili bilinməyənlər → məzun), ``leave_unfinished`` (bitirməyib, jurnalda yoxdur →
akademik məzuniyyət ``AM-SINX-2026``), ``deactivate_emptied_groups`` (boşalan qrupların arxivlənməsi).
"""

from __future__ import annotations

import datetime

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery

from .graduation_owner import YEAR_UNKNOWN_REASON, OwnerDecisions
from .registry_sync import SYNC_REASON, RegistrySync, _junk
from .resolve import person_key, text

ORDER_NUMBER = "MZN-SINX-2026"
ORDER_DATE = datetime.date(2026, 7, 1)
REASON = f"{SYNC_REASON}: məzun — cari semestr jurnallarında yoxdur, proqram müddəti başa çatıb"
#: Köçürmənin «qəbul ili bilinmir» sentineli (``legacy_import`` ARCHIVE_FALLBACK_ADMISSION_YEAR) və ondan aşağısı.
UNKNOWN_ADMISSION_YEAR = 1950
#: Bu ildən əvvəlki qəbul ili etibarsız sayılır (sentinel / «Silinməlidir» qabındakı 2000) — yoxlanmalı.
MIN_PLAUSIBLE_YEAR = 2001
_DEFAULT_ECTS = {"master": 120}


def sync_graduation(run) -> None:
    """Fazanın giriş nöqtəsi (``DeltaRun.run``)."""

    GraduationSync(run).execute()


def study_years(program) -> int:
    """Proqramın müddəti (il): ceil(ECTS / 60); ECTS yoxdursa dərəcəyə görə (bakalavr 4, magistr 2)."""

    ects = int(getattr(program, "ects_total", 0) or 0) or _DEFAULT_ECTS.get(getattr(program, "degree_level", ""), 240)
    return (ects + 59) // 60


def academic_year_start(period, today=None) -> int:
    """Tədris ili sentyabrda başlayır: cari dövrün başlanğıcı (yoxdursa bu gün) → il."""

    when = getattr(period, "start_date", None) or today or datetime.date.today()
    return when.year if when.month >= 9 else when.year - 1


class GraduationSync:
    def __init__(self, run):
        self.run = run
        self.org = run.organization
        self.Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        self.Enrollment = django_apps.get_model("registrar", "Enrollment")
        self.period = self.org.academic_periods.filter(is_current=True, is_active=True).first()
        self.cutoff_year = academic_year_start(self.period)
        first = self.org.academic_periods.exclude(start_date__isnull=True).order_by("start_date").first()
        #: Yeni sistemdə jurnal tarixçəsinin başladığı tədris ili (köçürmə 2021/2022-dən).
        self.history_start = academic_year_start(first) if first is not None else self.cutoff_year

    # ── köhnə sistem ──────────────────────────────────────────────────────
    def _legacy_current_ids(self) -> set:
        """Köhnə sistemin CARİ semestr jurnallarındakı legacy tələbə id-ləri (fake/aktiv fərq etmir — ehtiyat)."""

        from .extract import parse_id_list

        snapshot = self.run.bundle.get("snapshot") or {}
        current = {int(row["id"]) for row in self.run.bundle.get("periods") or [] if str(row.get("is_current")) == "1"}
        current |= {int(value) for value in snapshot.get("full_semesters") or []}
        ids: set = set()
        for journal in self.run.bundle.get("journals") or []:
            if int(journal.get("semestr") or 0) in current:
                ids.update(parse_id_list(journal.get("students_id")))
        return ids

    def _legacy_evidence(self):
        """``(cari jurnaldakı user_id-lər, azad edilmiş user_id-lər, tutuşmayan FİN-lər, tutuşmayan ad açarları)``."""

        rows = {row["id"]: row for row in self.run.bundle.get("students") or []}
        in_journal, unresolved_fins, unresolved_names = set(), set(), set()
        for legacy_id in sorted(self._legacy_current_ids()):
            user_id, _outcome = self.run.students.resolve(legacy_id, create=False)
            if user_id is not None:
                in_journal.add(user_id)
                continue
            self.run.count("graduation.legacy_journal_unresolved")
            row = rows.get(legacy_id) or {}
            fin = str(row.get("fincode") or "").strip().upper()
            if fin:
                unresolved_fins.add(fin)
            key = _name_key(row.get("last_name"), row.get("first_name"))
            if key:
                unresolved_names.add(key)
        return in_journal, self._legacy_expelled(), unresolved_fins, unresolved_names

    def _legacy_expelled(self) -> set:
        """Köhnə sistemdə azad edilmiş (``azadedildi=1``) hesablar — ``registry_sync`` ilə eyni güclü sübutla
        (cutover ledger-i, ``institutional_identifier``, FİN); ad tutuşdurması yoxdur."""

        from .resolve import ledger_map

        rows = [
            row
            for row in list(self.run.bundle.get("students") or [])
            + list(self.run.bundle.get("expelled_students") or [])
            if int(row.get("azadedildi") or 0) == 1
        ]
        if not rows:
            return set()
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        ids = [str(row["id"]) for row in rows]
        ledger = ledger_map(self.org, "student", ids)
        by_inst = dict(
            UserProfile.objects.filter(institutional_identifier__in=ids).values_list(
                "institutional_identifier", "user_id"
            )
        )
        fins = sorted({str(row.get("fincode") or "").strip().upper() for row in rows} - {""})
        by_fin = {
            fin.upper(): user_id
            for fin, user_id in UserProfile.objects.filter(fin__in=fins).values_list("fin", "user_id")
            if fin
        }
        out = set()
        for row in rows:
            key = str(row["id"])
            fin = str(row.get("fincode") or "").strip().upper()
            user_id = int(ledger[key]) if key in ledger else by_inst.get(key) or by_fin.get(fin)
            if user_id is not None:
                out.add(user_id)
        return out

    # ── yeni sistem ───────────────────────────────────────────────────────
    def _open_period_users(self) -> set:
        today = datetime.date.today()
        open_period = Q(offering__period__is_active=True) & (
            Q(offering__period__is_current=True) | Q(offering__period__start_date__gt=today)
        )
        return set(
            self.Enrollment.objects.filter(open_period, organization=self.org)
            .values_list("student_id", flat=True)
            .distinct()
        )

    def _candidates(self, open_users):
        last = self.Enrollment.objects.filter(organization=self.org, student_id=OuterRef("student_id")).order_by(
            "-offering__period__start_date"
        )
        return (
            self.Record.objects.filter(organization=self.org, status="enrolled")
            .exclude(student_id__in=list(open_users))
            .select_related("student", "student__profile", "program", "group")
            .annotate(
                last_year=Subquery(last.values("offering__period__academic_year")[:1]),
                last_name_period=Subquery(last.values("offering__period__name")[:1]),
            )
            .order_by("pk")
        )

    # ── əsas axın ─────────────────────────────────────────────────────────
    def execute(self) -> None:
        in_journal, expelled, fins, names = self._legacy_evidence()
        open_users = self._open_period_users()
        self.run.count(
            "graduation.untouched.in_journal",
            self.Record.objects.filter(
                organization=self.org, status="enrolled", student_id__in=list(open_users)
            ).count(),
        )
        records = list(self._candidates(open_users))
        touched = RegistrySync(self.run)._manually_changed({record.pk for record in records})
        self.run.count("graduation.info.cutoff_year", self.cutoff_year)
        self.run.count("graduation.info.history_start_year", self.history_start)
        owner = OwnerDecisions(self)
        for record in records:
            kind = self._decide(record, in_journal, expelled, fins, names, touched)
            action = owner.action_for(kind)
            if action and _legacy_unresolved_match(record, fins, names):
                kind, action = "review.legacy_unresolved_match", ""
            if action == "graduate":
                if self._graduate(record, reason=YEAR_UNKNOWN_REASON, names_kind="graduation_graduated_year_unknown"):
                    self.run.count("graduation.graduated_year_unknown")
                    owner.graduated(record)
                continue
            if action == "leave":
                owner.leave(record, kind)
                continue
            if kind != "graduate":
                self.run.count(f"graduation.{kind}")
                if kind.startswith("review."):
                    self.run.names(f"graduation_{kind}", _person(record), self._label(record))
                continue
            self._graduate(record)
        owner.finish()

    def _decide(self, record, in_journal, expelled, fins, names, touched) -> str:
        if record.student_id in in_journal:
            return "untouched.in_legacy_journal"
        if record.student_id in expelled:
            return "untouched.legacy_expelled"
        if record.pk in touched:
            return "review.system_changed"
        if _junk(getattr(record.group, "name", "")):
            return "review.junk_group"
        year = int(record.admission_year or 0)
        if year <= UNKNOWN_ADMISSION_YEAR or year < MIN_PLAUSIBLE_YEAR:
            return "review.year_unknown"
        if year + study_years(record.program) > self.cutoff_year:
            return "review.period_not_ended"
        final_year = year + study_years(record.program) - 1
        last = _year_start(record.last_year)
        if last is None and final_year >= self.history_start:
            return "review.no_journal_history"
        if last is not None and last < final_year:
            return "review.left_before_final_year"
        # Köhnə sistemin cari jurnalında tutuşdurula bilməyən sətrin FİN-i / adı bu adamla eynidir — o ola bilər.
        if _legacy_unresolved_match(record, fins, names):
            return "review.legacy_unresolved_match"
        return "graduate"

    def _graduate(self, record, *, reason: str = REASON, names_kind: str = "graduation_graduated") -> bool:
        from apps.registrar.public import movements

        try:
            with transaction.atomic():
                movements.create_movement(
                    record=record,
                    kind=movements.MovementKind.GRADUATION,
                    order_number=ORDER_NUMBER,
                    order_date=ORDER_DATE,
                    reason=reason,
                    actor=self.run.actor,
                )
        except (movements.MovementError, ValidationError) as error:
            code = getattr(error, "code", "") or error.__class__.__name__
            self.run.count("graduation.failed")
            self.run.names("graduation_failed", _person(record), f"{self._label(record)} · {code}")
            return False
        self.run.count("graduation.graduated")
        self.run.count(f"graduation.graduated.{record.program.degree_level}.year_{record.admission_year}")
        self.run.count("written.student_movements")
        self.run.names(names_kind, _person(record), self._label(record))
        return True

    # ``OwnerDecisions`` (``graduation_owner``) üçün açıq adlar.
    def person(self, record) -> str:
        return _person(record)

    def label(self, record) -> str:
        return self._label(record)

    def _label(self, record) -> str:
        group = getattr(record.group, "name", "") or "—"
        years = study_years(record.program)
        last = " ".join(part for part in (record.last_year or "", record.last_name_period or "") if part) or "—"
        return (
            f"{group} · qəbul {record.admission_year} · {record.program.degree_level} {years} il"
            f" · son jurnal: {last}"
        )


def _year_start(academic_year):
    """«2025/2026» → 2025; tanınmırsa ``None``."""

    head = str(academic_year or "")[:4]
    return int(head) if head.isdigit() else None


def _legacy_unresolved_match(record, fins, names) -> bool:
    """Köhnə sistemin cari jurnalında tutuşdurula bilməyən sətrin FİN-i / adı bu adamla eynidir — o ola bilər."""

    profile = getattr(record.student, "profile", None)
    fin = str(getattr(profile, "fin", "") or "").strip().upper()
    return bool(fin and fin in fins) or _name_key(record.student.last_name, record.student.first_name) in names


def _name_key(last_name, first_name) -> str:
    last, first = person_key(last_name), person_key(first_name)
    return f"{last}|{first}" if last and first else ""


def _person(record) -> str:
    student = record.student
    return text(student.get_full_name() or student.username)


__all__ = [
    "ORDER_DATE",
    "ORDER_NUMBER",
    "REASON",
    "GraduationSync",
    "academic_year_start",
    "study_years",
    "sync_graduation",
]
