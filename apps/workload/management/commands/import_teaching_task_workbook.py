"""``import_teaching_task_workbook`` — rəsmi TAPŞIRIQ kitabçasını (kafedra
başına bir vərəq) 2026/2027 tədris ilinə idxal edir.

Sahibin qərarı (2026-09-19): kitabçadakı hər sətir kafedranın tapşırıq sənədinə
düşür; fənn kataloqda yoxdursa YARADILIR; qrup yoxdursa ixtisas altında YARADILIR;
müəllim sütunu olan vərəqdə (Proqramlaşdırma) müəllimlər tapılır (yoxdursa
YARIM MƏLUMATLA yaradılır), bölgü təsdiqlənir → ``CourseOffering`` + tələbə
qeydiyyatları yaranır ki, müəllim dərhal sillabus yazıb jurnal apara bilsin.

Dry-run DEFOLTDUR; ``--apply`` yazır. İdempotentdir: mövcud sətir/təyinat/açılış
təkrarlanmır. Hesabat CSV ``--report`` qovluğuna yazılır (sirr yoxdur).

    manage.py import_teaching_task_workbook --file scripts/data/qku_tapsiriq_2026_2027.xlsx \\
        --org qku --year 2026/2027 --actor superadmin --report /tmp/tapsiriq
    ... --apply
"""

from __future__ import annotations

import difflib
import re
import secrets
from collections import Counter
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.accounts.services.username_repair import slug_name
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import CourseOffering, StudentAcademicRecord, Subject
from apps.registrar.services import enroll_student_in_subject
from apps.workload.constants import ACTIVITY_TOTAL_FIELD, TEACHING_ACTIVITIES, RowKind, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services.assignments import assign_teacher
from apps.workload.services.distribution import confirm_distribution
from apps.workload.services.imports import normalize
from apps.workload.services.people import chair_teacher_memberships
from apps.workload.services.scoping import resolve_actor
from apps.workload.services.tasks import resolve_specialty_and_faculty
from core.constants import OrgUnitType
from core.export_safety import safe_csv_writer
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

#: Vərəq adı (prefiks) → kafedra adı (OrgUnit chair). Kitabça vərəq adlarını qısaldır.
SHEET_TO_CHAIR = {
    "xarici dil": "Xarici dillər",
    "ekologiya": "Ekologiya",
    "tebiet elml": "Təbiət elmləri",
    "mexanika": "Mexanika və riyaziyyat",
    "proqramlasdirma": "Proqramlaşdırma və informasiya təhlükəsizliyi",
    "informasiya texnolog": "İnformasiya texnologiyaları",
}
#: İxtisas sütunundakı qısaltmalar → ixtisas (OrgUnit specialty) adı.
SPECIALTY_ALIASES = {
    "psixologiya": "Psixologiya",
    "teh sos ps x": "Təhsildə sosial psixoloji xidmət",
    "tehsos": "Təhsildə sosial psixoloji xidmət",
    "sosial is": "Sosial Iş",
    "komp muh": "Kompüter Mühəndisliyi",
    "kompmuh": "Kompüter Mühəndisliyi",
    "inform teh": "İnformasiya Təhlükəsizliyi",
    "informteh": "İnformasiya Təhlükəsizliyi",
    "komp elm": "Kompüter elmləri",
    "kompelm": "Kompüter elmləri",
    "mexat ve rob": "Mexatronika və robototexnika mühəndisliyi",
    "mexatverob": "Mexatronika və robototexnika mühəndisliyi",
    "inform tex": "İnformasiya Texnologiyaları",
    "informtex": "İnformasiya Texnologiyaları",
    "cihaz muh": "Cihaz Mühəndisliyi",
    "cihazmuh": "Cihaz Mühəndisliyi",
    "biologiya": "Biologiya",
    "ekologiya": "Ekologiya",
    "mesecilik": "Meşəçilik",
    "ekolog muh": "Ekologiya Mühəndisliyi",
    "ekologmuh": "Ekologiya Mühəndisliyi",
    "iqtisadiyyat": "İqtisadiyyat",
    "maliyye": "Maliyyə",
    "muhasibat": "Mühasibat",
    "marketinq": "Marketinq",
    "biznesin idare edilmesi": "Biznesin idarə edilməsi",
    "turizm": "Turizm işi",
    "filologiya azerbaycan dili ve edebiyyati": "Azərbaycan dili və ədəbiyyatı",
    "filologiya ingilis dili ve edebiyyati": "Filologiya (İngilis dili və ədəbiyyatı)",
    "qida muh": "Qida mühəndisliyi",
    "qidamuh": "Qida mühəndisliyi",
    "su bioehtiyyatlari": "Su Bioehtiyyatları və Akvakultura",
    "genetika": "Genetika",
    "malekulyar biologiya": "Malekulyar biologiya",
    "molekulyar biologiya": "Malekulyar biologiya",
    "beynelxalq munasibetler": "Beynəlxalq münasibətlər",
    "regionsunasliq": "Regionşünaslıq",
    "dov beled id": "Dövlət və bələdiyyə idarəetməsi",
    "dovbeledid": "Dövlət və bələdiyyə idarəetməsi",
    "qrafik dizayn": "Dizayn (Qrafik)",
    "interyer dizayn": "Dizayn (İnteryer)",
    "felsefe": "Fəlsəfə",
    "tarix": "Tarix",
    "yer qur ve kad": "Yer quruluşu və kadastr",
    "yerqurvekad": "Yer quruluşu və kadastr",
    "biotex": "Biotexnologiya",
    "biotexnolog": "Biotexnologiya",
    "bioekologiya": "Bioekologiya",
    "etraf muh": "Ətraf mühitin mühafizə və bərpa metodları",
}
#: Qrup kodu → sektor sözləri (qrup adının sonunda) — «az» defoltdur, DB-də bəzən yazılmır.
SECTOR_WORDS = ("az", "ing", "rus", "AZ", "ING", "İNG", "RUS", "Az", "Ing")
#: Qrup kodundakı ixtisas hərfləri (İxtisas sütunu boş/uyğunsuz olanda ehtiyat).
GROUP_CODE_SPECIALTY = {
    "K": "Kompüter Mühəndisliyi",
    "KE": "Kompüter elmləri",
    "İ": "İnformasiya Təhlükəsizliyi",
    "IT": "İnformasiya Texnologiyaları",
    "İT": "İnformasiya Texnologiyaları",
    "MRM": "Mexatronika və robototexnika mühəndisliyi",
    "CM": "Cihaz Mühəndisliyi",
    "BİO": "Biologiya",
    "BIO": "Biologiya",
    "SBİO": "Su Bioehtiyyatları və Akvakultura",
    "SBIO": "Su Bioehtiyyatları və Akvakultura",
    "EKO": "Ekologiya",
    "EM": "Ekologiya Mühəndisliyi",
    "M": "Meşəçilik",
    "QM": "Qida mühəndisliyi",
    "Bİ": "Biznesin idarə edilməsi",
    "BI": "Biznesin idarə edilməsi",
    "ML": "Maliyyə",
    "MU": "Mühasibat",
    "MRK": "Marketinq",
    "TSPX": "Təhsildə sosial psixoloji xidmət",
    "Sİ": "Sosial Iş",
    "SI": "Sosial Iş",
    "BM": "Beynəlxalq münasibətlər",
    "R": "Regionşünaslıq",
    "G": "Genetika",
    "MB": "Malekulyar biologiya",
    "E": "Ekologiya",
    "F": "Azərbaycan dili və ədəbiyyatı",
    "T": "Turizm işi",
    "TB": "Turizm bələdçiliyi",
}
SEASONS = {"payiz": "fall", "yaz": "spring"}
PERIODS = {
    "fall": ("Payız", date(2026, 9, 15), date(2027, 1, 31)),
    "spring": ("Yaz", date(2027, 2, 1), date(2027, 6, 30)),
}
_SPLIT_RE = re.compile(r"[\n|;,]+|\s{3,}")
_BLOCK_CHOSEN_RE = re.compile(r"^\s*\d+[.)]?\s*(.+?)\s*\+\s*$")
_ITEM_RE = re.compile(r"^\s*\d+[.)]\s*")
_QKU_CODE_RE = re.compile(r"^QKU-(\d+)$")


class _DryRunRollback(Exception):
    """Dry-run: transaction-ı geri almaq üçün daxili siqnal."""


def _title_az(word: str) -> str:
    """«MİNAYƏ» → «Minayə» (Python title() «İ»-ni pozur)."""
    word = _text(word)
    if not word:
        return ""
    lower = "".join("i" if ch == "İ" else "ı" if ch == "I" else ch.lower() for ch in word[1:])
    return word[0] + lower


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _int(value) -> int:
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def _sum_numbers(value) -> int:
    return sum(int(part) for part in re.findall(r"\d+", _text(value)))


def _key(value) -> str:
    """Qrup/ad açarı: boşluqsuz, kiçik hərf, İ/I fərqsiz, apostrofsuz."""
    text = _text(value).replace("İ", "i").replace("I", "i").replace("ı", "i")
    return re.sub(r"[\s'’`.\-_()]+", "", text).lower()


_GROUP_BOUNDARY_RE = re.compile(r"\s+(?=\d{2,4}(?:/\d+)?\s*[A-Za-zİƏÖÜĞŞÇ])")


def split_tokens(value) -> list[str]:
    """«036\\n3/336 F», «235 K     235 İT», «336 F1,2», «233 K ing 233 İT ing» → ayrı qrup adları."""
    raw = _text(value)
    match = re.match(r"^(\S+\s+\D+?)(\d)\s*,\s*(\d)\s*$", raw)
    if match:
        return [f"{match.group(1)}{match.group(2)}", f"{match.group(1)}{match.group(3)}"]
    tokens = []
    for part in _SPLIT_RE.split(raw):
        for piece in _GROUP_BOUNDARY_RE.split(part.strip()):
            piece = re.sub(r"\s+", " ", piece.strip().strip("'’"))
            if not piece or piece in SECTOR_WORDS or (piece.isdigit() and len(piece) < 3):
                continue
            tokens.append(piece)
    return tokens


def is_block(raw: str) -> bool:
    slug = slug_name(raw)
    return "blok" in slug or "secme" in slug or "sesme" in slug or re.match(r"^\s*(ATMF|SF\b|S\.F)", raw) is not None


def block_chosen_subject(raw: str) -> str:
    """Seçmə bloku → seçilən fənn: «+» ilə işarələnən; tək bənd; və ya «ATMF: X» formasında X."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for line in lines:
        match = _BLOCK_CHOSEN_RE.match(line)
        if match:
            return match.group(1).strip(" +")
    items = [_ITEM_RE.sub("", line).strip(" +") for line in lines if _ITEM_RE.match(line)]
    if len(items) == 1:
        return items[0]
    if not items:
        head = re.sub(r"^\s*(ATMF|SF|S\.F)[^:]*:\s*", "", " ".join(lines)).strip()
        if head and head != " ".join(lines):
            return head
    return ""


def _special_row_kind(record: dict) -> str:
    """Kontakt saatı olmayan xüsusi sətirlər: təcrübə / buraxılış-dissertasiya / dissertant."""
    if record["lecture_total"] or record["seminar_total"] or record["lab_total"]:
        return ""
    slug = slug_name(record["subject_text"])
    if "tecrube" in slug:
        return RowKind.PRACTICE
    if "buraxilis" in slug or "dissertasiya" in slug or "magistr" in slug:
        return RowKind.THESIS
    if "doktorant" in slug or "dissertant" in slug:
        return RowKind.POSTGRAD
    return ""


def clean_subject_name(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return " ".join(lines)[:255]


def parse_sheet(ws) -> tuple[str, list[dict]]:
    """Vərəq → sətir dict-ləri. İki düzülüş: tam (21 sütun) və qısa (Proqramlaşdırma)."""
    compact = ws.max_column <= 13
    records = []
    for index, row in enumerate(ws.iter_rows(values_only=True), 1):
        if index < 11:
            continue
        season = SEASONS.get(slug_name(row[0]))
        subject = _text(row[2]) if len(row) > 2 else ""
        if not season or not subject:
            continue

        def get(i, row=row):
            return row[i] if i < len(row) else None

        record = {
            "sheet": ws.title,
            "line": index,
            "season": season,
            "groups_text": _text(get(1)),
            "subject_text": subject,
            "specialty_text": _text(get(3)),
            "student_count_text": _text(get(4)),
            "student_count": _sum_numbers(get(4)),
        }
        if compact:
            record.update(
                union_count=1,
                subgroup_count=1,
                lecture_total=_int(get(5)),
                seminar_total=_int(get(6)),
                lab_total=_int(get(7)),
                teacher_text=_text(get(8)),
                total_hours=_int(get(9)),
                credits="",
            )
        else:
            record.update(
                union_count=max(_int(get(5)), 1),
                subgroup_count=max(_int(get(6)), 1),
                lecture_plan=_int(get(7)),
                lecture_total=_int(get(8)),
                seminar_plan=_int(get(9)),
                seminar_total=_int(get(10)),
                lab_plan=_int(get(11)),
                lab_total=_int(get(12)),
                consult_hours=_int(get(13)),
                exam_hours=_int(get(14)),
                thesis_hours=_int(get(15)),
                postgrad_hours=_int(get(16)),
                practice_research_hours=_int(get(17)),
                practice_production_hours=_int(get(18)),
                total_hours=_int(get(19)),
                credits=_text(get(20)),
                teacher_text="",
            )
        records.append(record)
    return ws.title, records


class Importer:
    def __init__(self, *, organization, year: str, actor_user, apply: bool, stdout):
        self.org = organization
        self.year = year
        self.actor_user = actor_user
        self.actor = resolve_actor(actor_user, organization)
        self.apply = apply
        self.stdout = stdout
        self.report_rows: list[dict] = []
        self.counters: Counter = Counter()
        self.subject_index = {normalize(s.name): s for s in Subject.objects.filter(organization=organization)}
        self.subject_names = list(self.subject_index.keys())
        self.group_index: dict[str, OrgUnit] = {}
        for unit in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True):
            self.group_index.setdefault(_key(unit.name), unit)
        self.specialty_index = {
            normalize(u.name): u
            for u in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.SPECIALTY, is_active=True)
        }
        self.chairs = {
            normalize(u.name): u
            for u in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.CHAIR, is_active=True)
        }
        codes = [
            int(m.group(1))
            for c in Subject.objects.filter(organization=organization).values_list("code", flat=True)
            for m in [_QKU_CODE_RE.match(c or "")]
            if m
        ]
        self.next_code = (max(codes) if codes else 0) + 1
        self.periods: dict[str, AcademicPeriod] = {}
        self.teacher_cache: dict[tuple, tuple] = {}
        self.created_specialties: list[str] = []
        self.created_groups: list[str] = []
        self.created_subjects: list[str] = []
        self.created_teachers: list[str] = []
        self.ambiguous_teachers: list[str] = []

    # ── köməkçilər ────────────────────────────────────────────────────────
    def note(self, **fields):
        self.report_rows.append(fields)

    def ensure_periods(self):
        for season, (name, start, end) in PERIODS.items():
            period = AcademicPeriod.objects.filter(organization=self.org, name=name, academic_year=self.year).first()
            if period is None:
                self.counters["period_created"] += 1
                if self.apply:
                    period = AcademicPeriod.objects.create(
                        organization=self.org,
                        name=name,
                        period_type="semester",
                        academic_year=self.year,
                        start_date=start,
                        end_date=end,
                        is_current=(season == "fall"),
                        is_active=True,
                    )
            elif season == "fall" and not period.is_current and self.apply:
                period.is_current = True
                period.save(update_fields=["is_current", "updated_at"])
            self.periods[season] = period

    def chair_for_sheet(self, title: str):
        slug = slug_name(title)
        for prefix, chair_name in SHEET_TO_CHAIR.items():
            if slug.startswith(slug_name(prefix)):
                return self.chairs.get(normalize(chair_name))
        return None

    def resolve_specialty(self, text: str, group_token: str, chair=None):
        text_norm = normalize(text)
        if text_norm:
            if text_norm in self.specialty_index:
                return self.specialty_index[text_norm]
            for alias, name in SPECIALTY_ALIASES.items():
                if text_norm.startswith(normalize(alias)) or normalize(alias) in text_norm:
                    unit = self.specialty_index.get(normalize(name))
                    if unit is not None:
                        return unit
            close = difflib.get_close_matches(text_norm, list(self.specialty_index), n=1, cutoff=0.85)
            if close:
                return self.specialty_index[close[0]]
        code = re.sub(r"^[\d/]+\s*", "", group_token)
        code = re.sub(r"\s*(az|ing|rus|AZ|ING|RUS|İNG|-?\d)$", "", code).strip()
        name = GROUP_CODE_SPECIALTY.get(code)
        unit = self.specialty_index.get(normalize(name)) if name else None
        if unit is not None or chair is None:
            return unit
        # Kataloqda olmayan ixtisas (məs. «Biotexnologiya», «Yer quruluşu və kadastr») —
        # sahibin qərarı: yaradılır (kafedranın fakültəsi altında), hesabatda görünür.
        full_name = ""
        for alias, alias_name in SPECIALTY_ALIASES.items():
            if text_norm and (text_norm.startswith(normalize(alias)) or normalize(alias) in text_norm):
                full_name = alias_name
                break
        if not full_name:
            return None
        faculty = chair.parent if chair.parent is not None and chair.parent.unit_type == OrgUnitType.FACULTY else None
        if faculty is None:
            return None
        unit = OrgUnit(organization=self.org, parent=faculty, unit_type=OrgUnitType.SPECIALTY, name=full_name)
        if self.apply:
            unit.save()
        self.specialty_index[normalize(full_name)] = unit
        self.counters["specialty_created"] += 1
        self.created_specialties.append(full_name)
        return unit

    def resolve_subject(self, raw: str, chair, credits: str, special_kind: str = "") -> tuple:
        """→ (Subject|None, action, resolved_name). Xüsusi sətir (təcrübə/buraxılış) fənn YARATMIR."""
        candidates = [raw]
        block = is_block(raw)
        chosen = block_chosen_subject(raw) if block else ""
        if chosen:
            candidates.insert(0, chosen)
        single = clean_subject_name(raw)
        candidates += [single, re.sub(r"\s*\(.*?\)\s*", " ", single).strip(), _ITEM_RE.sub("", single)]
        for candidate in candidates:
            key = normalize(candidate)
            if key and key in self.subject_index:
                return self.subject_index[key], "matched", self.subject_index[key].name
        for candidate in candidates[:2]:
            key = normalize(candidate)
            close = difflib.get_close_matches(key, self.subject_names, n=1, cutoff=0.9)
            if (
                close
                and close[0][:5] == key[:5]
                and (key[-1:].isdigit() == close[0][-1:].isdigit())
                and (not key[-1:].isdigit() or key[-1:] == close[0][-1:])
            ):
                return self.subject_index[close[0]], "fuzzy", self.subject_index[close[0]].name
        if block and not chosen:
            return None, "block_unresolved", ""
        if special_kind:
            return None, "special_row", ""
        name = chosen or single
        ects = _int(credits) or 5
        subject = Subject(
            organization=self.org, code=f"QKU-{self.next_code}", name=name, ects=min(max(ects, 1), 30), chair_unit=chair
        )
        self.next_code += 1
        if self.apply:
            subject.save()
        self.subject_index[normalize(name)] = subject
        self.subject_names.append(normalize(name))
        self.counters["subject_created"] += 1
        self.created_subjects.append(name)
        return subject, "created", name

    def resolve_group(self, token: str, specialty) -> list[tuple]:
        """→ [(OrgUnit, action), ...] — «533 T» kimi ad alt-qruplara («533T1», «533T2») açıla bilər."""
        bare = re.sub(r"\s+(az|AZ|Az)$", "", token)
        sector_only = re.sub(r"^(\S+)\s+\S+\s+(ing|rus|ING|RUS|İNG)$", r"\1 \2", token)  # «435 R ing» → «435 ing»
        for variant in (token, f"{token} az", bare, token.replace(" ", ""), f"{bare}-1", sector_only, f"3/{token}"):
            unit = self.group_index.get(_key(variant))
            if unit is not None:
                return [(unit, "matched")]
        base_key = _key(bare)
        subgroups = [
            unit
            for key, unit in self.group_index.items()
            if key.startswith(base_key) and re.fullmatch(r"\d(az)?", key[len(base_key) :])
        ]
        if subgroups:
            return [(unit, "matched_subgroup") for unit in sorted(subgroups, key=lambda u: u.name)]
        if specialty is None:
            return [(None, "no_specialty")]
        if not specialty.pk:  # dry-run-da yaradılmış ixtisas — qrup da yalnız planlanır
            self.counters["group_created"] += 1
            self.created_groups.append(token)
            return [(None, "created")]
        unit = OrgUnit(organization=self.org, parent=specialty, unit_type=OrgUnitType.GROUP, name=token)
        if self.apply:
            try:
                with transaction.atomic():
                    unit.save()
            except IntegrityError:
                unit.slug = f"{slug_name(token)}-{secrets.token_hex(2)}"
                unit.save()
        self.group_index[_key(token)] = unit
        self.counters["group_created"] += 1
        self.created_groups.append(token)
        return [(unit, "created")]

    def _teacher_candidates(self, token: str, chair) -> list:
        """Ad (böyük hərflə, bəzən soyad inisialı ilə) → kafedra, sonra təşkilat üzrə müəllimlər."""
        parts = token.replace("I", "İ").split()
        first = slug_name(parts[0]) if parts else ""
        initial = slug_name(parts[1])[:1] if len(parts) > 1 else ""
        if not first:
            return []

        def pick(memberships):
            seen = {}
            for membership in memberships:
                user = membership.user
                if user is None or not user.is_active or user.pk in seen:
                    continue
                if slug_name(user.first_name) != first:
                    continue
                if initial and slug_name(user.last_name)[:1] != initial:
                    continue
                seen[user.pk] = user
            return list(seen.values())

        found = pick(chair_teacher_memberships(self.org, chair, include_unscoped=False))
        if found:
            return found
        org_wide = Membership.objects.filter(
            organization=self.org, is_active=True, role__name__in=("teacher", "assistant"), role__is_active=True
        ).select_related("user")
        return pick(org_wide)

    def resolve_teacher(self, token: str, chair) -> tuple:
        """→ (User|None, action). Eyni ad-soyadlı dublikatlar ən köhnə hesaba yığılır."""
        token = token.strip()
        cache_key = (slug_name(token), chair.pk)
        if cache_key in self.teacher_cache:
            return self.teacher_cache[cache_key]
        candidates = self._teacher_candidates(token, chair)
        by_full = {}
        for user in candidates:
            by_full.setdefault(f"{slug_name(user.first_name)}.{slug_name(user.last_name)}", []).append(user)
        result: tuple
        if len(by_full) > 1:
            # Eyni ad, fərqli soyad: keçən illərdə bu kafedranın fənlərini kim aparıb?
            preferred = self._prefer_by_history(chair, [users for users in by_full.values()])
            if preferred is not None:
                by_full = {k: v for k, v in by_full.items() if preferred in v}
        if len(by_full) == 1:
            users = self._order_duplicates(next(iter(by_full.values())))
            result = (users[0], "matched" if len(users) == 1 else "matched_duplicate_accounts")
        elif len(by_full) > 1:
            result = (None, "ambiguous:" + " / ".join(sorted(by_full)))
            self.ambiguous_teachers.append(f"{token} → {' / '.join(sorted(by_full))}")
        else:
            result = (self._create_teacher(token, chair), "created")
        if (
            result[0] is not None
            and result[0].pk
            and not chair_teacher_memberships(self.org, chair).filter(user=result[0]).exists()
        ):
            self.counters["membership_added"] += 1
            if self.apply:
                role = Role.objects.get(organization=self.org, name="teacher")
                Membership.objects.get_or_create(
                    organization=self.org,
                    user=result[0],
                    role=role,
                    scope_unit=chair,
                    defaults={"is_active": True, "assigned_by": self.actor_user},
                )
            result = (result[0], result[1] + "+chair_membership")
        self.teacher_cache[cache_key] = result
        return result

    def _order_duplicates(self, users):
        """Dublikat hesablar: RİM rəhbəri üzvlüyü / son giriş / e-poçt olan hesab önə."""

        def rank(user):
            is_head = Membership.objects.filter(
                organization=self.org, user=user, is_active=True, role__name="ikt_rehber"
            ).exists()
            return (not is_head, user.last_login is None, not bool(user.email), user.pk)

        return sorted(users, key=rank)

    def _prefer_by_history(self, chair, groups_of_users):
        """Fərqli soyadlı namizədlərdən kafedranın fənlərini əvvəl aparanı seçir (yeganə olsa)."""
        scores = []
        for users in groups_of_users:
            count = CourseOffering.objects.filter(
                organization=self.org, instructor__in=users, subject__chair_unit=chair
            ).count()
            scores.append((count, users[0]))
        scores.sort(key=lambda item: -item[0])
        if scores and scores[0][0] > 0 and (len(scores) == 1 or scores[1][0] == 0):
            return scores[0][1]
        return None

    def _create_teacher(self, token: str, chair):
        User = get_user_model()
        first = _title_az(token.replace("I", "İ").split()[0])
        base = slug_name(first) or "muellim"
        username, suffix = base, 2
        while User.objects.filter(username__iexact=username).exists():
            username, suffix = f"{base}{suffix}", suffix + 1
        self.counters["teacher_created"] += 1
        self.created_teachers.append(f"{first} ({username})")
        if not self.apply:
            return User(username=username, first_name=first, is_active=True)
        user = User.objects.create_user(
            username=username, email="", password=secrets.token_urlsafe(12), first_name=first
        )
        profile = getattr(user, "profile", None)
        if profile is not None:
            profile.organization = self.org
            profile.password_change_required = True
            profile.email_verified = False
            profile.save(update_fields=["organization", "password_change_required", "email_verified", "updated_at"])
        role = Role.objects.get(organization=self.org, name="teacher")
        Membership.objects.create(
            organization=self.org, user=user, role=role, scope_unit=chair, is_active=True, assigned_by=self.actor_user
        )
        return user

    # ── əsas axın ─────────────────────────────────────────────────────────
    def import_sheet(self, title: str, records: list[dict]):
        chair = self.chair_for_sheet(title)
        if chair is None:
            self.stdout.write(f"  ! «{title}» vərəqi üçün kafedra tapılmadı — ötürüldü")
            self.counters["sheet_skipped"] += 1
            return
        if not records:
            self.stdout.write(f"  · «{title}» ({chair.name}): sətir yoxdur — ötürüldü")
            return
        task = TeachingTask.objects.filter(organization=self.org, chair=chair, academic_year=self.year).first()
        if task is None:
            self.counters["task_created"] += 1
            if self.apply:
                task = TeachingTask.objects.create(
                    organization=self.org,
                    chair=chair,
                    academic_year=self.year,
                    created_by=self.actor_user,
                    status=TaskStatus.DRAFT,
                )
        existing = set()
        if task is not None and task.pk:
            existing = set(task.rows.values_list("season", "subject_text", "groups_text"))
        rows_to_assign: list[tuple] = []
        for record in records:
            special_kind = _special_row_kind(record)
            subject, subject_action, subject_name = self.resolve_subject(
                record["subject_text"], chair, record["credits"], special_kind
            )
            tokens = split_tokens(record["groups_text"])
            spec_tokens = [t for t in _SPLIT_RE.split(record["specialty_text"]) if t.strip()]
            groups, group_actions = [], []
            for position, token in enumerate(tokens):
                spec_text = (
                    spec_tokens[position] if position < len(spec_tokens) else (spec_tokens[0] if spec_tokens else "")
                )
                specialty = self.resolve_specialty(spec_text, token, chair)
                for unit, action in self.resolve_group(token, specialty):
                    group_actions.append(f"{unit.name if unit is not None else token}:{action}")
                    if unit is not None and unit.pk:
                        groups.append(unit)
            teacher_tokens = [t for t in re.split(r"\s*[-–]\s*", record["teacher_text"]) if t.strip()]
            teachers = []
            for token in teacher_tokens:
                user, action = self.resolve_teacher(token, chair)
                teachers.append((token, user, action))
            specialty_unit, faculty = (groups[0].parent, None) if groups else (None, None)
            if specialty_unit is not None:
                specialty_unit, faculty = resolve_specialty_and_faculty(self.org, specialty_unit.pk)
            key = (record["season"], record["subject_text"][:255], record["groups_text"][:255])
            row_action = "exists" if key in existing else "created"
            row = None
            if row_action == "created":
                self.counters["row_created"] += 1
                if self.apply:
                    row = TeachingTaskRow(
                        organization=self.org,
                        task=task,
                        season=record["season"],
                        row_kind=special_kind or RowKind.TEACHING,
                        period=self.periods[record["season"]],
                        subject=subject if subject is not None and subject.pk else None,
                        subject_text=record["subject_text"][:255],
                        specialty=specialty_unit,
                        specialty_text=record["specialty_text"][:255],
                        faculty=faculty,
                        groups_text=record["groups_text"][:255],
                        student_count=record["student_count"],
                        student_count_text=record["student_count_text"][:100],
                        union_count=record["union_count"],
                        subgroup_count=record["subgroup_count"],
                        lecture_plan=record.get("lecture_plan", 0),
                        lecture_total=record["lecture_total"],
                        seminar_plan=record.get("seminar_plan", 0),
                        seminar_total=record["seminar_total"],
                        lab_plan=record.get("lab_plan", 0),
                        lab_total=record["lab_total"],
                        consult_hours=record.get("consult_hours", 0),
                        exam_hours=record.get("exam_hours", 0),
                        thesis_hours=record.get("thesis_hours", 0),
                        postgrad_hours=record.get("postgrad_hours", 0),
                        practice_research_hours=record.get("practice_research_hours", 0),
                        practice_production_hours=record.get("practice_production_hours", 0),
                        credits=record["credits"][:20],
                        credits_value=_int(record["credits"]),
                    )
                    row.total_hours = record["total_hours"] or row.computed_total_hours
                    row.save()
                    if groups:
                        row.groups.set(groups)
            elif task is not None:
                row = task.rows.filter(season=key[0], subject_text=key[1], groups_text=key[2]).first()
            if teachers and row is not None:
                rows_to_assign.append((row, teachers))
            elif teachers:
                self.counters["assignment_planned"] += 1
            self.note(
                sheet=title,
                line=record["line"],
                season=record["season"],
                subject_raw=clean_subject_name(record["subject_text"]),
                subject_action=subject_action,
                subject_resolved=subject_name,
                groups_raw=record["groups_text"].replace("\n", " | "),
                groups=" ; ".join(group_actions),
                teacher_raw=record["teacher_text"],
                teachers=" ; ".join(
                    f"{t}:{a}:{(u.get_full_name() or u.username) if u else ''}" for t, u, a in teachers
                ),
                row=row_action,
            )
        assigned = 0
        if self.apply and task is not None:
            assigned = self._assign_rows(task, rows_to_assign)
            if assigned and task.status in (TaskStatus.DRAFT, TaskStatus.DISTRIBUTING):
                self._confirm_and_enroll(task)
        self.stdout.write(
            f"  · «{title}» → {chair.name}: {len(records)} sətir, təyinat {assigned or len(rows_to_assign)} sətirdə"
        )

    def _assign_rows(self, task, rows_to_assign) -> int:
        assigned_rows = 0
        for row, teachers in rows_to_assign:
            if TeacherAssignment.objects.filter(row=row).exists():
                self.counters["assignment_exists"] += 1
                continue
            users = [u for _, u, _ in teachers if u is not None and u.pk]
            plan = []
            for index, activity in enumerate(TEACHING_ACTIVITIES):
                hours = int(getattr(row, ACTIVITY_TOTAL_FIELD[activity], 0) or 0)
                if not hours:
                    continue
                # «A-B» cütü: mühazirə birinciyə, seminar/lab ikinciyə; tək müəllim hamısını alır.
                user = (users[0] if index == 0 or len(users) == 1 else users[-1]) if users else None
                plan.append((activity, hours, user))
            for activity, hours, user in plan:
                try:
                    assign_teacher(
                        row=row,
                        actor=self.actor,
                        activity=str(activity),
                        teacher_id=user.pk if user else None,
                        hours=hours,
                        note="TAPŞIRIQ kitabçası idxalı 2026/2027" if user else "Vakant — idxalda müəllim tapılmadı",
                    )
                    self.counters["assignment_created" if user else "assignment_vacant"] += 1
                except Exception as exc:  # noqa: BLE001 — bir sətrin xətası bütün idxalı dayandırmasın
                    self.counters["assignment_failed"] += 1
                    self.note(sheet=task.chair.name, line=0, subject_raw=row.subject_label, teachers=f"XƏTA: {exc}")
            assigned_rows += 1
        return assigned_rows

    def _confirm_and_enroll(self, task):
        # Bölgüsüz qalan dərs sətirləri «Vakant» ilə doldurulur ki, təsdiq keçsin
        # (jurnal sahibi sonra «Fənn təhvili»/düzəlişlə təyin olunur).
        from apps.workload.services.assignments import remaining_hours

        for row in task.rows.all():
            for activity in TEACHING_ACTIVITIES:
                left = remaining_hours(row, str(activity))
                if left > 0:
                    assign_teacher(
                        row=row, actor=self.actor, activity=str(activity), teacher_id=None, hours=left, note="Vakant"
                    )
                    self.counters["assignment_vacant"] += 1
        result = confirm_distribution(task=task, actor=self.actor, allow_vacant=True)
        self.counters["offering_created"] += result["sync"]["created"]
        self.counters["offering_updated"] += result["sync"]["updated"]
        self.counters["offering_instructor_blocked"] += result["sync"]["instructor_blocked"]
        for offering in CourseOffering.objects.filter(pk__in=result["sync"]["offering_ids"]).select_related("group"):
            records = StudentAcademicRecord.objects.filter(
                organization=self.org, group=offering.group, is_active=True, status="enrolled"
            ).select_related("student")
            for record in records:
                _, created = enroll_student_in_subject(
                    record=record, subject=offering.subject, period=offering.period, kind="mandatory"
                )
                self.counters["enrollment_created" if created else "enrollment_exists"] += 1


class Command(BaseCommand):
    help = "TAPŞIRIQ kitabçasını (kafedra vərəqləri) tədris ilinə idxal edir — dry-run defolt."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--org", default="qku")
        parser.add_argument("--year", default="2026/2027")
        parser.add_argument("--actor", required=True, help="Bölgünü təsdiqləyən superadmin istifadəçi adı")
        parser.add_argument("--report", default="", help="Hesabat CSV qovluğu")
        parser.add_argument("--sheet", action="append", default=[], help="Yalnız bu vərəq(lər) (prefiks)")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        from openpyxl import load_workbook

        path = Path(options["file"])
        if not path.is_file():
            raise CommandError(f"file_not_found: {path}")
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheets = [parse_sheet(ws) for ws in workbook.worksheets]
        workbook.close()
        wanted = [slug_name(s) for s in options["sheet"]]
        if wanted:
            sheets = [(t, r) for t, r in sheets if any(slug_name(t).startswith(w) for w in wanted)]

        # Bütün idxal BİR transaction-dadır: dry-run sonda geri alınır, --apply-də
        # istənilən xəta hər şeyi geri qaytarır (yarımçıq idxal qalmır).
        try:
            self._run(sheets, options)
        except _DryRunRollback:
            pass
        self._write_report(options)

    def _run(self, sheets, options):
        with transaction.atomic(), rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=options["org"]).first()
            if organization is None:
                raise CommandError(f"organization_not_found: {options['org']}")
            actor_user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if actor_user is None or not actor_user.is_superuser:
                raise CommandError("actor_must_be_active_superuser")
            importer = Importer(
                organization=organization,
                year=options["year"],
                actor_user=actor_user,
                apply=options["apply"],
                stdout=self.stdout,
            )
            importer.ensure_periods()
            self.stdout.write(f"Təşkilat: {organization.name} · il {options['year']} · vərəq: {len(sheets)}")
            for title, records in sheets:
                importer.import_sheet(title, records)
            self.importer = importer
            if not options["apply"]:
                raise _DryRunRollback()

    def _write_report(self, options):
        importer = self.importer
        if options["report"]:
            out = Path(options["report"])
            out.mkdir(parents=True, exist_ok=True)
            fields = [
                "sheet", "line", "season", "subject_raw", "subject_action", "subject_resolved",
                "groups_raw", "groups", "teacher_raw", "teachers", "row",
            ]  # fmt: skip
            with (out / "tapsiriq_import.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = safe_csv_writer(handle)
                writer.writerow(fields)
                for item in importer.report_rows:
                    writer.writerow([item.get(f, "") for f in fields])
            self.stdout.write(f"Hesabat: {out / 'tapsiriq_import.csv'}")
        summary = " · ".join(f"{k}={v}" for k, v in sorted(importer.counters.items()))
        self.stdout.write(summary)
        for label, items in (
            ("Yaradılan ixtisaslar", importer.created_specialties),
            ("Yaradılan qruplar", importer.created_groups),
            ("Yaradılan fənlər", importer.created_subjects),
            ("Yaradılan müəllimlər", importer.created_teachers),
            ("Qeyri-müəyyən müəllim (vakant qaldı, ambiguous)", importer.ambiguous_teachers),
        ):
            if items:
                self.stdout.write(f"{label} ({len(items)}): " + " | ".join(sorted(set(items)))[:4000])
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY-RUN — heç nə yazılmadı (--apply ilə yazılır)."))
