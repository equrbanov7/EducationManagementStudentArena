"""«TƏLƏBƏNİN FƏRDİ TƏDRİS PLANI» — rəsmi DOCX sənədi (bütöv qrup / fərdi tələbə).

FORMAT UNİVERSİTETİN RƏSMİ NÜMUNƏSİNDƏN OLDUĞU KİMİDİR. Sahibin göndərdiyi
«235 QM fərdi plan.docx» nümunəsinin BİR tələbə bloku (başlıq paraqrafları,
iki semestr cədvəli, qeyd və imza sətirləri) `docx_templates/individual_plan.docx`
şablonudur; mətn yerlərində `{{TOKEN}}` yer tutucuları var. Sənəd python-docx ilə
YOX, XML səviyyəsində doldurulur — nümunənin şrifti (Times New Roman 12),
sütun enləri, sərhədləri və A4 səhifə parametrləri bir bayt belə dəyişmir
(«kənara çıxma — rəsmi sənədin formatı odur», 2026-09-07).

Məlumat mənbəyi:
  * tələbə / qrup / ixtisas / fakültə — `StudentAcademicRecord` + `OrgUnit` zənciri
    (fakültə = qrupun ən yaxın `faculty` əcdadı; ixtisas = `specialty` əcdadı,
    yoxdursa proqramın adı);
  * fənlər — tələbənin planının (`Curriculum`) cari tədris ilinə düşən iki semestri:
    payız = 2·kurs−1, yaz = 2·kurs. Kurs qrupun metadatasından (`course_year`),
    boşdursa qəbul ili ilə cari tədris ilinin fərqindən;
  * müəllim — həmin semestrin `CourseOffering`-i (qrup + fənn) varsa `instructor`;
  * «Fənnin kodu» — YALNIZ `CurriculumSubject.row_code` (plan şifri). Daxili
    `MYEDU-*` `subject.code` sənədə HEÇ VAXT düşmür (köçürmə artefaktıdır).
  * «Saat» — mühazirə+seminar+lab cəmi, üçü də 0-dırsa ümumi saat.

Nümunədə semestr başlığı «Payız semestri (P-7)» / «Yaz semestri (Y-8)» idi;
biz mötərizədə planın semestr NÖMRƏSİNİ yazırıq (I kurs → P-1 / Y-2).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from django.apps import apps as django_apps

from apps.organizations.groups_registry import group_meta

TEMPLATE_PATH = Path(__file__).resolve().parent / "docx_templates" / "individual_plan.docx"

_BLOCK_RE = re.compile(r"<!--STUDENT_BLOCK_START-->(.*?)<!--STUDENT_BLOCK_END-->", re.S)
_TBL_RE = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
_TR_RE = re.compile(r"<w:tr[ >].*?</w:tr>", re.S)
_PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
MAX_COURSE_YEAR = 6

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def az_upper(text: str) -> str:
    """Azərbaycan əlifbası üçün böyük hərf: `i` → `İ` (Python-un `.upper()`-i bunu bilmir)."""
    return (text or "").replace("i", "İ").upper()


@dataclass
class PlanRow:
    n: int
    code: str
    subject: str
    hours: int
    credits: int
    chair: str
    teacher: str
    note: str = ""


@dataclass
class SemesterBlock:
    title: str
    rows: list[PlanRow] = field(default_factory=list)

    @property
    def total_hours(self) -> int:
        return sum(row.hours for row in self.rows)

    @property
    def total_credits(self) -> int:
        return sum(row.credits for row in self.rows)


@dataclass
class StudentPlan:
    university: str
    faculty: str
    specialty: str
    group: str
    student: str
    study_year: str
    academic_year: str
    semesters: list[SemesterBlock]


# ── Məlumatın yığılması ──────────────────────────────────────────────────────


def _ancestor_named(unit, unit_type: str) -> str:
    node = unit
    while node is not None:
        if getattr(node, "unit_type", "") == unit_type:
            return node.name or ""
        node = getattr(node, "parent", None)
    return ""


def _start_year(academic_year: str) -> int:
    match = re.match(r"\s*(\d{4})", academic_year or "")
    return int(match.group(1)) if match else 0


def _course_year(group, record, academic_year: str) -> int:
    meta = group_meta(group) if group is not None else {"course_year": 0}
    course = int(meta.get("course_year") or 0)
    if course <= 0:
        start = _start_year(academic_year)
        admission = int(getattr(record, "admission_year", 0) or 0)
        course = (start - admission + 1) if start and admission else 1
    return max(1, min(MAX_COURSE_YEAR, course))


def current_period(organization):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    queryset = AcademicPeriod.objects.filter(organization=organization)
    return queryset.filter(is_current=True).first() or queryset.order_by("-start_date").first()


def _season_periods(organization, academic_year: str) -> dict[str, list]:
    """Tədris ilinin dövrlərini fəslə görə ayır: `fall` (Payız) / `spring` (Yaz)."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    seasons: dict[str, list] = {"fall": [], "spring": []}
    for period in AcademicPeriod.objects.filter(organization=organization, academic_year=academic_year):
        name = (period.name or "").lower()
        if "pay" in name or "güz" in name or "fall" in name or "autumn" in name:
            seasons["fall"].append(period.id)
        elif "yaz" in name or "spring" in name or "bahar" in name:
            seasons["spring"].append(period.id)
    return seasons


def _teacher_map(organization, group, seasons) -> dict[tuple[str, object], str]:
    """(fəsil, subject_id) → müəllimin adı — qrupun həmin dövrdəki açılışından."""
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    period_ids = seasons["fall"] + seasons["spring"]
    if group is None or not period_ids:
        return {}
    mapping: dict[tuple[str, object], str] = {}
    offerings = (
        CourseOffering.objects.filter(organization=organization, group=group, period_id__in=period_ids)
        .select_related("instructor")
        .order_by("created_at")
    )
    for offering in offerings:
        season = "fall" if offering.period_id in seasons["fall"] else "spring"
        instructor = offering.instructor
        if instructor is None:
            continue
        name = (instructor.get_full_name() or "").strip() or instructor.username
        mapping.setdefault((season, offering.subject_id), name)
    return mapping


def _row_hours(row) -> int:
    contact = int(row.lecture_hours or 0) + int(row.seminar_hours or 0) + int(row.lab_hours or 0)
    return contact if contact > 0 else int(row.total_hours or 0)


def _row_chair(row) -> str:
    chair = getattr(row, "teaching_chair", None) or getattr(row.subject, "chair_unit", None)
    return (getattr(chair, "name", "") or "").strip()


def _semester_block(title: str, rows, season: str, teachers) -> SemesterBlock:
    block = SemesterBlock(title=title)
    for index, row in enumerate(rows, start=1):
        block.rows.append(
            PlanRow(
                n=index,
                code=(row.row_code or "").strip(),
                subject=(row.subject.name or "").strip(),
                hours=_row_hours(row),
                credits=int(row.credits or 0),
                chair=_row_chair(row),
                teacher=teachers.get((season, row.subject_id), ""),
            )
        )
    return block


def build_student_plan(organization, record, *, period, teachers_cache: dict | None = None) -> StudentPlan:
    """Bir tələbənin fərdi planı — sənədin bir səhifəsi."""
    CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
    academic_year = getattr(period, "year_display", None) or getattr(period, "academic_year", "") or ""
    raw_year = getattr(period, "academic_year", "") or ""
    group = record.group
    course = _course_year(group, record, raw_year)
    fall_no, spring_no = 2 * course - 1, 2 * course

    seasons = _season_periods(organization, raw_year)
    if teachers_cache is None:
        teachers_cache = {}
    key = getattr(group, "id", None)
    if key not in teachers_cache:
        teachers_cache[key] = _teacher_map(organization, group, seasons)
    teachers = teachers_cache[key]

    rows = list(
        CurriculumSubject.objects.filter(curriculum=record.curriculum, semester_number__in=(fall_no, spring_no))
        .select_related("subject", "subject__chair_unit", "teaching_chair")
        .order_by("semester_number", "order", "row_code", "subject__name")
    )
    fall_rows = [row for row in rows if row.semester_number == fall_no]
    spring_rows = [row for row in rows if row.semester_number == spring_no]

    program = record.program
    specialty = _ancestor_named(group, "specialty") if group is not None else ""
    if not specialty:
        specialty_unit = getattr(program, "specialty_unit", None)
        specialty = (getattr(specialty_unit, "name", "") or "").strip() or (program.name or "")
    faculty = _ancestor_named(group, "faculty") if group is not None else ""
    if not faculty:
        specialty_unit = getattr(program, "specialty_unit", None)
        faculty = _ancestor_named(specialty_unit, "faculty") if specialty_unit is not None else ""

    student = record.student
    student_name = (student.get_full_name() or "").strip() or student.username
    return StudentPlan(
        university=az_upper(organization.name),
        faculty=faculty,
        specialty=specialty,
        group=(group.name if group is not None else ""),
        student=student_name,
        study_year=_ROMAN.get(course, str(course)),
        academic_year=academic_year,
        semesters=[
            _semester_block(f"Payız semestri (P-{fall_no})", fall_rows, "fall", teachers),
            _semester_block(f"Yaz semestri (Y-{spring_no})", spring_rows, "spring", teachers),
        ],
    )


def group_records(organization, group, *, record_id=None):
    """Qrupun aktiv (qeydiyyatlı) tələbələri — sənəd sırası soyad/ad üzrədir."""
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    queryset = (
        StudentAcademicRecord.objects.filter(organization=organization, group=group, is_active=True)
        .select_related("student", "program", "program__specialty_unit", "curriculum", "group", "group__parent")
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    if record_id:
        queryset = queryset.filter(pk=record_id)
    return list(queryset)


# ── XML doldurma ─────────────────────────────────────────────────────────────


def _sub(xml: str, values: dict[str, object]) -> str:
    for token, value in values.items():
        xml = xml.replace("{{" + token + "}}", escape(str(value if value is not None else "")))
    return xml


def _fill_table(tbl_xml: str, block: SemesterBlock) -> str:
    rows = _TR_RE.findall(tbl_xml)
    header, data, total = rows[0], rows[1], rows[-1]
    body_rows = block.rows or [PlanRow(n=1, code="", subject="", hours=0, credits=0, chair="", teacher="")]
    body = "".join(
        _sub(
            data,
            {
                "N": row.n,
                "CODE": row.code,
                "SUBJECT": row.subject,
                "HOURS": row.hours or "",
                "CREDITS": row.credits or "",
                "CHAIR": row.chair,
                "TEACHER": row.teacher,
                "NOTE": row.note,
            },
        )
        for row in body_rows
    )
    total_xml = _sub(total, {"TOTAL_HOURS": block.total_hours or "", "TOTAL_CREDITS": block.total_credits or ""})
    head = tbl_xml[: tbl_xml.index(header)]
    return head + header + body + total_xml + "</w:tbl>"


def _fill_block(block_xml: str, plan: StudentPlan) -> str:
    tables = _TBL_RE.findall(block_xml)
    out = block_xml
    for tbl_xml, semester in zip(tables, plan.semesters):
        out = out.replace(tbl_xml, _fill_table(tbl_xml, semester), 1)
    return _sub(
        out,
        {
            "UNIVERSITY": plan.university,
            "FACULTY": plan.faculty,
            "SPECIALTY": plan.specialty,
            "GROUP": plan.group,
            "STUDENT": plan.student,
            "STUDY_YEAR": plan.study_year,
            "ACADEMIC_YEAR": plan.academic_year,
            "SEM1_TITLE": plan.semesters[0].title,
            "SEM2_TITLE": plan.semesters[1].title,
        },
    )


def render_docx(plans: list[StudentPlan]) -> bytes:
    """Şablonu tələbə blokları ilə doldurub DOCX baytlarını qaytarır (hər tələbə yeni səhifə)."""
    with zipfile.ZipFile(TEMPLATE_PATH) as template:
        document = template.read("word/document.xml").decode("utf-8")
        match = _BLOCK_RE.search(document)
        if match is None:
            raise ValueError("individual_plan.docx: STUDENT_BLOCK markerləri tapılmadı")
        block = match.group(1)
        filled = _PAGE_BREAK.join(_fill_block(block, plan) for plan in plans) if plans else ""
        document = document[: match.start()] + filled + document[match.end() :]

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
            for item in template.infolist():
                if item.filename == "word/document.xml":
                    out.writestr(item.filename, document.encode("utf-8"))
                else:
                    out.writestr(item, template.read(item.filename))
    return buffer.getvalue()


def build_group_document(organization, group, *, record_id=None) -> tuple[str, bytes, int]:
    """(fayl adı, DOCX baytları, tələbə sayı) — bütöv qrup və ya tək tələbə üçün."""
    period = current_period(organization)
    records = group_records(organization, group, record_id=record_id)
    cache: dict = {}
    plans = [build_student_plan(organization, record, period=period, teachers_cache=cache) for record in records]
    safe_group = re.sub(r"[^\w\-]+", "-", group.name or "qrup", flags=re.U).strip("-") or "qrup"
    if record_id and plans:
        safe_student = re.sub(r"[^\w\-]+", "-", plans[0].student, flags=re.U).strip("-")
        filename = f"ferdi-tedris-plani-{safe_group}-{safe_student}.docx"
    else:
        filename = f"ferdi-tedris-plani-{safe_group}.docx"
    return filename, render_docx(plans), len(plans)


__all__ = [
    "DOCX_CONTENT_TYPE",
    "PlanRow",
    "SemesterBlock",
    "StudentPlan",
    "az_upper",
    "build_group_document",
    "build_student_plan",
    "current_period",
    "group_records",
    "render_docx",
]
