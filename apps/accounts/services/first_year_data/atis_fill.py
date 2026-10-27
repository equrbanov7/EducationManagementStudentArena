"""ATİS datası olmayan 1-ci kurs hesablarına ATİS ixracından FILL-ONLY doldurma (sahib 2026-10-27).

Köhnə sistem deltası (2026-10-23/25) ATİS idxalında olmayan və ya FİN-i ilə tanınmayan 2026 qəbulu tələbələrini
özü yaradıb — FİN, doğum tarixi, telefon, real e-poçt (placeholder var), vəsiqə, qəbul sahələri, ATİS id-si, tədris
dili boş qalıb. ``import_students_atis``-i yenidən işlətmək olmaz: tanınan FİN-ləri ötürür, qalanlara İKİNCİ hesab
yaradır. Bu modul yalnız MÖVCUD hesabın BOŞ sahələrini doldurur.

HƏDƏF: ``admission_year`` qəbulunun aktiv qeydi olan aktiv tələbə, qeydinin ``atis_id``-si boşdur.

TUTUŞDURMA (təxmin yoxdur):

1. **FİN** — hesabın FİN-i ATİS sətrinin FİN-i ilə eynidir;
2. **ad** (hesabda FİN yoxdur) — soyad + ad + ata adı açarı (registr/diakritik dözümlü, «oğlu/qızı» atılır) DƏQİQ
   eynidir; namizəd YALNIZ FİN-i heç bir hesabda olmayan ATİS sətirləridir; ATİS sətrinin proqramı tələbənin
   qeydi / qrupu ilə ziddiyyət təşkil etməməlidir (eyni proqram, eyni ixtisas vahidi — qrupun valideyni, və ya
   tələbənin proqramının rəsmi şifri yoxdur, məs. legacy «Dizayn Məktəbi»). Bir tələbəyə iki sətir və ya bir
   sətrə iki tələbə düşürsə — ``skip_ambiguous_name`` (heç biri yazılmır).

DOLDURMA — yalnız BOŞ sahə: profil (FİN, doğum tarixi, cins «təyin edilməyib»-dirsə, ata adı, telefon, vətəndaşlıq,
vəsiqə seriyası/nömrəsi, ünvan), hesabın e-poçtu YALNIZ placeholder-dirsə (``email_is_placeholder``) və ATİS
e-poçtu başqa hesabın e-poçtu / istifadəçi adı deyilsə, qeydin qəbul sahələri (ATİS id, bal, imtahan növü, xətt,
tur, tədris dili, məbləğ, tarixlər, qeyd, əlavə atributlar). Qrup, status, forma, maliyyələşmə DƏYİŞMİR.

ATİS sətri heç bir hesaba düşmürsə (FİN bazada yoxdur və ad ilə tutulmayıb) — hesab YARADILMIR, yalnız sayılır
(``import_students_atis --only-program …`` sonra yarada bilər).
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.db.models import Q

from core.audit import log_action
from core.constants import AuditAction

from ...identity import email_is_placeholder
from ..intake.admission import disambiguate_program, program_by_code
from .atis_rows import RECORD_FIELDS
from .scope import person_key

BATCH_RESOURCE = "accounts.first_year_atis_fill_batch"
SHOWN = (
    "atis_rows",
    "atis_rows_known_fin",
    "targets",
    "matched_fin",
    "matched_name",
    "students_filled",
    "students_already_full",
    "no_atis_row_for_fin",
    "no_atis_row_for_name",
    "atis_rows_without_account",
    "atis_rows_ambiguous",
)


def _empty(value) -> bool:
    # ``admission_extra``-nın DB defoltu JSON SƏTRİ «{}»-dir (``'"{}"'::jsonb``) — o da boş sayılır.
    if isinstance(value, str):
        return value.strip() in ("", "{}")
    return value is None or value == {} or value == []


class AtisFiller:
    """Tutuşdurma + plan; ``write()`` yazır. Saylar ``counts``-dadır (şəxsi data yoxdur)."""

    def __init__(self, organization, records, rows, counts: Counter):
        self.organization = organization
        self.records = records
        self.rows = rows
        self.counts = counts
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        self.known_fins = {
            fin.strip().upper(): user_id
            for fin, user_id in UserProfile.objects.exclude(fin=None).values_list("fin", "user_id")
            if fin and fin.strip()
        }
        self._programs: dict = {}
        self.matches: list = []  # [(record, row, how)]
        self.missing_by_form: Counter = Counter()
        self.missing_by_program: Counter = Counter()

    # ── tutuşdurma ──────────────────────────────────────────────────────
    def _program(self, row):
        cache_key = (row.program_code, row.language, row.speciality, row.specialization)
        if cache_key not in self._programs:
            program, status = program_by_code(self.organization, row.program_code)
            if status == "ambiguous":
                program = disambiguate_program(
                    self.organization,
                    row.program_code,
                    name=row.speciality,
                    sector=row.language,
                    specialization=row.specialization,
                )
            self._programs[cache_key] = program
        return self._programs[cache_key]

    def _compatible(self, record, row) -> str:
        """``""`` — uyğundur; əks halda ötürmə səbəbi."""

        program = self._program(row)
        if program is None:
            return "skip_program_unresolved"
        if program.pk == record.program_id:
            return ""
        units = {record.program.specialty_unit_id, getattr(record.group, "parent_id", None)} - {None}
        if program.specialty_unit_id in units or not (record.program.official_code or "").strip():
            return ""
        return "skip_program_mismatch"

    def match(self) -> None:
        self.counts["atis_rows"] += len(self.rows)
        by_fin: dict = defaultdict(list)
        for row in self.rows:
            if row.fin:
                by_fin[row.fin].append(row)
        duplicate_fins = {fin for fin, rows in by_fin.items() if len(rows) > 1}
        self.counts["skip_atis_fin_duplicate_in_file"] += sum(len(by_fin[fin]) for fin in duplicate_fins)
        by_name: dict = defaultdict(list)
        for row in self.rows:
            if row.fin in self.known_fins:
                self.counts["atis_rows_known_fin"] += 1
            elif row.fin and row.fin not in duplicate_fins and all(row.name_key):
                by_name[row.name_key].append(row)
        targets = [record for record in self.records if _empty(record.atis_id)]
        self.counts["targets"] += len(targets)
        matched_rows: set = set()
        name_claims: dict = defaultdict(list)
        for record in targets:
            profile = record.student.profile
            fin = (profile.fin or "").strip().upper()
            if fin:
                rows = by_fin.get(fin) or []
                if len(rows) != 1:
                    self.counts["no_atis_row_for_fin" if not rows else "skip_atis_fin_duplicate_target"] += 1
                    continue
                self.matches.append((record, rows[0], "fin"))
                matched_rows.add(rows[0].index)
                self.counts["matched_fin"] += 1
                continue
            key = person_key(record.student.last_name, record.student.first_name, profile.patronymic)
            if not all(key):
                self.counts["skip_name_incomplete"] += 1
                continue
            candidates = by_name.get(key) or []
            if not candidates:
                self.counts["no_atis_row_for_name"] += 1
            elif len(candidates) > 1:
                self.counts["skip_ambiguous_name"] += 1
            else:
                name_claims[candidates[0].index].append((record, candidates[0]))
        ambiguous_rows: set = set()
        for claims in name_claims.values():
            if len(claims) > 1:
                self.counts["skip_ambiguous_name"] += len(claims)
                ambiguous_rows.add(claims[0][1].index)
                continue
            record, row = claims[0]
            reason = self._compatible(record, row)
            if reason:
                self.counts[reason] += 1
                continue
            self.matches.append((record, row, "name"))
            matched_rows.add(row.index)
            self.counts["matched_name"] += 1
        for rows in by_name.values():
            if len(rows) > 1:
                ambiguous_rows.update(row.index for row in rows)
        for row in self.rows:
            if row.fin in self.known_fins or row.index in matched_rows:
                continue
            if row.index in ambiguous_rows:
                self.counts["atis_rows_ambiguous"] += 1
                continue
            self.counts["atis_rows_without_account"] += 1
            self.missing_by_form[row.education_form or "unknown"] += 1
            self.missing_by_program[row.program_code or "unknown"] += 1

    # ── doldurma ────────────────────────────────────────────────────────
    def _email_free(self, email: str, user_pk, seen: set) -> bool:
        User = django_apps.get_model("auth", "User")
        key = email.strip().lower()
        if key in seen:
            return False
        return not User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exclude(pk=user_pk).exists()

    def _fin_free(self, fin: str, profile_pk) -> bool:
        UserProfile = django_apps.get_model("accounts", "UserProfile")
        return bool(fin) and not UserProfile.objects.filter(fin=fin).exclude(pk=profile_pk).exists()

    def _plan_one(self, record, row, seen_emails: set) -> tuple[dict, dict, str]:
        profile = record.student.profile
        profile_values: dict = {}
        if _empty(profile.fin) and row.fin and self._fin_free(row.fin, profile.pk):
            profile_values["fin"] = row.fin
        if profile.birth_date is None and row.birth_date is not None:
            profile_values["birth_date"] = row.birth_date
        if (profile.gender or "unspecified") == "unspecified" and row.gender != "unspecified":
            profile_values["gender"] = row.gender
        for name, value in row.profile.items():
            if _empty(getattr(profile, name, None)) and value:
                profile_values[name] = value
        record_values = {
            name: row.record.get(name)
            for name in RECORD_FIELDS
            if _empty(getattr(record, name, None)) and not _empty(row.record.get(name))
        }
        email = ""
        current = record.student.email or ""
        if row.email and (not current.strip() or email_is_placeholder(current)):
            if self._email_free(row.email, record.student_id, seen_emails):
                email = row.email
                seen_emails.add(row.email.strip().lower())
            else:
                self.counts["skip_email_taken"] += 1
        return profile_values, record_values, email

    def write(self, *, actor, batch: str) -> None:
        seen_emails: set = set()
        manifest = []
        for record, row, how in self.matches:
            profile_values, record_values, email = self._plan_one(record, row, seen_emails)
            if not (profile_values or record_values or email):
                self.counts["students_already_full"] += 1
                continue
            try:
                with transaction.atomic():
                    self._save(record, profile_values, record_values, email)
            except IntegrityError:
                self.counts["skip_write_conflict"] += 1
                continue
            fields = sorted(profile_values) + sorted(f"record.{name}" for name in record_values)
            if email:
                fields.append("email")
            for name in fields:
                self.counts[f"field_{name.replace('record.', 'record_')}"] += 1
            self.counts["students_filled"] += 1
            manifest.append([record.student_id, how, fields])
        if manifest:
            log_action(
                action=AuditAction.UPDATE,
                user=actor,
                organization=self.organization,
                obj=self.organization,
                new_values={"counts": dict(sorted(self.counts.items())), "filled": manifest},
                reason=f"first_year_atis_fill {batch}",
                resource_type=BATCH_RESOURCE,
                resource_id=batch,
                resource_repr=batch,
            )

    @staticmethod
    def _save(record, profile_values: dict, record_values: dict, email: str) -> None:
        profile = record.student.profile
        if profile_values:
            for name, value in profile_values.items():
                setattr(profile, name, value)
            profile.save(update_fields=[*profile_values, "updated_at"])
        if record_values:
            for name, value in record_values.items():
                setattr(record, name, value)
            record.save(update_fields=[*record_values, "updated_at"])
        if email:
            user = record.student
            user.email = email
            user.save(update_fields=["email"])


__all__ = ["AtisFiller", "BATCH_RESOURCE", "SHOWN"]
