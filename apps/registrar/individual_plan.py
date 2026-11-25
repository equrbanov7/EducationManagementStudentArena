"""«TƏLƏBƏNİN FƏRDİ TƏDRİS PLANI» — rəsmi DOCX sənədi (bütöv qrup / fərdi tələbə).

FORMAT UNİVERSİTETİN RƏSMİ NÜMUNƏSİNDƏN OLDUĞU KİMİDİR. Sahibin göndərdiyi
«235 QM fərdi plan.docx» nümunəsinin BİR tələbə bloku (başlıq paraqrafları,
iki semestr cədvəli, qeyd və imza sətirləri) `docx_templates/individual_plan.docx`
şablonudur; mətn yerlərində `{{TOKEN}}` yer tutucuları var. Sənəd python-docx ilə
YOX, XML səviyyəsində doldurulur — nümunənin şrifti, sərhədləri saxlanılır (2026-09-07).
Sahib 2026-11-26: nümunənin cədvəli A4-dən kənara çıxırdı (en 11484, girinti −998) — şablonda kənar boşluqlar
2/1 sm, cədvəl eni mətn sahəsinə bərabər (10205), cədvəl şrifti 11, başlıq sətri hər səhifədə təkrarlanır.

Məlumat mənbəyi:
  * tələbə / qrup / ixtisas / fakültə — `StudentAcademicRecord` + `OrgUnit` zənciri
    (fakültə = qrupun ən yaxın `faculty` əcdadı; ixtisas = `specialty` əcdadı,
    yoxdursa proqramın adı);
  * fənlər — tələbənin planının (`Curriculum`) I kursdan CARİ kursa qədər BÜTÜN semestrləri
    (sahib 2026-11-26), hər kurs öz başlığı ilə: payız = 2·k−1, yaz = 2·k. Kurs qrupun metadatasından (`course_year`),
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

from apps.organizations.public import group_meta

from . import individual_plan_sources as sources

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
class YearBlock:
    """Bir tədris ili (kurs): başlıq + payız/yaz semestrləri."""

    title: str
    semesters: list[SemesterBlock]


@dataclass
class StudentPlan:
    university: str
    faculty: str
    specialty: str
    group: str
    student: str
    study_year: str
    academic_year: str
    years: list[YearBlock]

    @property
    def semesters(self) -> list[SemesterBlock]:
        return [semester for year in self.years for semester in year.semesters]


# ── Məlumatın yığılması ──────────────────────────────────────────────────────


def _ancestor_named(unit, unit_type: str) -> str:
    node = unit
    while node is not None:
        if getattr(node, "unit_type", "") == unit_type:
            return node.name or ""
        node = getattr(node, "parent", None)
    return ""


def _start_year(academic_year: str) -> int:
    match = re.search(r"(\d{4})", academic_year or "")
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


def _season_of(name: str) -> str:
    name = (name or "").lower()
    if "pay" in name or "güz" in name or "fall" in name or "autumn" in name:
        return "fall"
    if "yaz" in name or "spring" in name or "bahar" in name:
        return "spring"
    return ""


def _season_periods(organization, academic_year: str) -> dict[str, list]:
    """Tədris ilinin dövrlərini fəslə görə ayır: `fall` (Payız) / `spring` (Yaz)."""
    return _periods_by_year(organization).get(_start_year(academic_year), {"fall": [], "spring": []})


def _periods_by_year(organization) -> dict[int, dict[str, list]]:
    """``başlanğıc ili → {fall, spring}`` — BÜTÜN tədris illərinin dövrləri bir sorğuda.

    ``academic_year`` sərbəst mətndir («2024/2025», «2024-2025», «2024») — ilk 4 rəqəmli il açardır.
    """
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    years: dict[int, dict[str, list]] = {}
    for period_id, name, academic_year in AcademicPeriod.objects.filter(organization=organization).values_list(
        "id", "name", "academic_year"
    ):
        season, start = _season_of(name), _start_year(academic_year)
        if season and start:
            years.setdefault(start, {"fall": [], "spring": []})[season].append(period_id)
    return years


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


_PATRONYMIC_SUFFIX_RE = re.compile(r"\s+(qızı|oğlu|qizi|oglu)\s*$", re.I)


def _az_title(text: str) -> str:
    """«SAHİL» → «Sahil» (Python-un ``.title()``-i «İ»-ni «i̇» edir, «I»-ni «i»)."""

    def word(part: str) -> str:
        lower = part.replace("İ", "i").replace("I", "ı").lower()
        return lower[:1].replace("i", "İ").replace("ı", "I").upper() + lower[1:] if lower else lower

    return " ".join(word(part) for part in text.split())


def _student_name(student) -> str:
    """«Ad Soyad Ata adı» — rəsmi nümunədəki kimi (sahib 2026-11-25); ata adının «qızı/oğlu» sonluğu yazılmır."""
    base = (student.get_full_name() or "").strip() or student.username
    profile = getattr(student, "profile", None)
    patronymic = _PATRONYMIC_SUFFIX_RE.sub("", (getattr(profile, "patronymic", "") or "").strip()).strip()
    if patronymic and patronymic.casefold() not in base.casefold():
        return f"{base} {_az_title(patronymic) if patronymic.isupper() else patronymic}"
    return base


def _row_hours(row) -> int:
    contact = int(row.lecture_hours or 0) + int(row.seminar_hours or 0) + int(row.lab_hours or 0)
    return contact if contact > 0 else int(row.total_hours or 0)


def _row_chair(row) -> str:
    chair = getattr(row, "teaching_chair", None) or getattr(row.subject, "chair_unit", None)
    return (getattr(chair, "name", "") or "").strip()


def _plan_row_hours(row, offering) -> int:
    """Auditoriya saatı: plan sətrinin mühazirə+seminar+lab cəmi; köhnə planlarda bu sahələr boşdur (yalnız ümumi iş
    yükü, məs. 150) — onda tələbənin həmin semestrdəki jurnalının saatı (sahib 2026-11-26: illər eyni formada)."""
    contact = int(row.lecture_hours or 0) + int(row.seminar_hours or 0) + int(row.lab_hours or 0)
    if contact > 0:
        return contact
    if offering is not None and int(offering.lesson_hours or 0) > 0:
        return int(offering.lesson_hours)
    return int(row.total_hours or 0)


def _semester_block(title: str, rows, teachers: dict, extra=(), offerings=None) -> SemesterBlock:
    """Plan sətirləri + (plan boşdursa / başqa qrupun jurnalı varsa) jurnal sətirləri (:mod:`.individual_plan_sources`).

    ``teachers``: ``subject_id → müəllim`` (tələbənin öz jurnalı, yoxdursa qrupun həmin semestrdəki açılışı);
    ``offerings``: ``subject_id → tələbənin jurnalı`` (kodu/saatı olmayan köhnə plan sətirləri üçün).
    """
    offerings = offerings or {}
    block = SemesterBlock(title=title)
    for index, row in enumerate(rows, start=1):
        block.rows.append(
            PlanRow(
                n=index,
                code=(row.row_code or "").strip() or sources.subject_code(row.subject),
                subject=(row.subject.name or "").strip(),
                hours=_plan_row_hours(row, offerings.get(row.subject_id)),
                credits=int(row.credits or 0),
                chair=_row_chair(row),
                teacher=teachers.get(row.subject_id, ""),
            )
        )
    for item in extra:
        block.rows.append(
            PlanRow(
                n=len(block.rows) + 1,
                code=item["code"],
                subject=item["subject"],
                hours=item["hours"],
                credits=item["credits"],
                chair=item["chair"],
                teacher=item["teacher"],
                note=item["note"],
            )
        )
    return block


def _year_label(start: int) -> str:
    return f"{start}-{start + 1}" if start else ""


def build_student_plan(
    organization,
    record,
    *,
    period,
    teachers_cache: dict | None = None,
    seasons_cache: dict | None = None,
    rows_cache: dict | None = None,
    context_group=None,
    plan_sources: sources.PlanSources | None = None,
) -> StudentPlan:
    """Bir tələbənin fərdi planı — I kursdan cari kursa qədər BÜTÜN tədris illəri (sahib 2026-11-26).

    Hər kurs bir blokdur: «I kurs — 2023-2024 tədris ili», altında payız (P-1) və yaz (Y-2) cədvəlləri.
    Kurs ``k``-nın tədris ili = cari ilin başlanğıcı − (cari kurs − k).

    Perf auditi 2026-09-13 F-03: qrup sənədində sorğu sayı tələbə sayından asılı olmamalıdır —
    ``seasons_cache`` (bütün illərin dövrləri, bir sorğu), ``teachers_cache`` ((qrup, il) üzrə),
    ``rows_cache`` (kurikulumun BÜTÜN sətirləri + (qrup, proqram) struktur adları) çağıran tərəfindən ötürülür.
    """
    CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
    academic_year = getattr(period, "year_display", None) or getattr(period, "academic_year", "") or ""
    raw_year = getattr(period, "academic_year", "") or ""
    current_start = _start_year(raw_year)
    group = record.group
    course = _course_year(group, record, raw_year)

    if seasons_cache is None:
        seasons_cache = {}
    if "by_year" not in seasons_cache:
        seasons_cache["by_year"] = _periods_by_year(organization)
    by_year = seasons_cache["by_year"]
    if teachers_cache is None:
        teachers_cache = {}
    if rows_cache is None:
        rows_cache = {}
    rows_key = ("rows", record.curriculum_id)
    if rows_key not in rows_cache:
        rows_cache[rows_key] = list(
            CurriculumSubject.objects.filter(curriculum_id=record.curriculum_id)
            .select_related("subject", "subject__chair_unit", "teaching_chair")
            .order_by("semester_number", "order", "row_code", "subject__name")
            if record.curriculum_id
            else []
        )
    all_rows = rows_cache[rows_key]
    if plan_sources is None:
        plan_sources = sources.PlanSources(
            organization, [pid for seasons in by_year.values() for pid in seasons["fall"] + seasons["spring"]]
        )
    home_group_id = getattr(group, "id", None)
    fallback_groups = [home_group_id, getattr(context_group, "id", None)]

    years: list[YearBlock] = []
    for year_course in range(1, course + 1):
        start = current_start - (course - year_course) if current_start else 0
        seasons = by_year.get(start, {"fall": [], "spring": []})
        teacher_key = (home_group_id, start)
        if teacher_key not in teachers_cache:
            teachers_cache[teacher_key] = _teacher_map(organization, group, seasons)
        group_teachers = teachers_cache[teacher_key]
        fall_no, spring_no = 2 * year_course - 1, 2 * year_course
        semesters = []
        for season, number, label in (("fall", fall_no, "Payız"), ("spring", spring_no, "Yaz")):
            season_rows = [row for row in all_rows if row.semester_number == number]
            teachers = {subject_id: name for (key, subject_id), name in group_teachers.items() if key == season}
            teachers.update(plan_sources.student_teachers(record.student_id, seasons[season]))
            # Sahib 2026-11-25: plan boşdursa jurnallar, başqa qrupun (əlavə / alt qrup) jurnalı varsa o da.
            # Keçmiş illərdə qrupun açılışları ehtiyat mənbə deyil (qrup o vaxt başqa kursda idi).
            extra = plan_sources.semester_extra_rows(
                record,
                period_ids=seasons[season],
                curriculum_subject_ids={row.subject_id for row in season_rows},
                home_group_id=home_group_id,
                fallback_groups=fallback_groups if start == current_start else [],
            )
            prefix = "P" if season == "fall" else "Y"
            offerings = plan_sources.student_offering_map(record.student_id, seasons[season])
            semesters.append(
                _semester_block(
                    f"{label} semestri ({prefix}-{number})", season_rows, teachers, extra, offerings=offerings
                )
            )
        roman = _ROMAN.get(year_course, str(year_course))
        title = f"{roman} kurs — {_year_label(start)} tədris ili" if start else f"{roman} kurs"
        years.append(YearBlock(title=title, semesters=semesters))

    program = record.program
    # Struktur adları (ixtisas/fakültə) `parent` zənciri ilə tapılır — zəncirin
    # `select_related`-dən kənar pillələri hər tələbə üçün təkrar sorğu olardı;
    # (qrup, proqram) cütü üzrə bir dəfə hesablanır (F-03).
    names_key = ("names", getattr(group, "id", None), getattr(program, "id", None))
    if names_key not in rows_cache:
        specialty = _ancestor_named(group, "specialty") if group is not None else ""
        if not specialty:
            specialty_unit = getattr(program, "specialty_unit", None)
            specialty = (getattr(specialty_unit, "name", "") or "").strip() or (program.name or "")
        faculty = _ancestor_named(group, "faculty") if group is not None else ""
        if not faculty:
            specialty_unit = getattr(program, "specialty_unit", None)
            faculty = _ancestor_named(specialty_unit, "faculty") if specialty_unit is not None else ""
        rows_cache[names_key] = (specialty, faculty)
    specialty, faculty = rows_cache[names_key]

    student = record.student
    return StudentPlan(
        university=az_upper(organization.name),
        faculty=faculty,
        specialty=specialty,
        group=(group.name if group is not None else ""),
        student=_student_name(student),
        study_year=_ROMAN.get(course, str(course)),
        academic_year=re.sub(r"\s*/\s*", "-", academic_year),  # nümunədəki kimi «2026-2027»
        years=years,
    )


def group_records(organization, group, *, record_id=None, period_ids=()):
    """Qrupun aktiv (qeydiyyatlı) tələbələri — sənəd sırası soyad/ad üzrədir.

    Sahib 2026-11-25: «Əlavə olaraq» üzvlər (öz qrupu başqadır, bu qrupun jurnalındadır) da — sonda.
    """
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    queryset = (
        StudentAcademicRecord.objects.filter(organization=organization, group=group, is_active=True)
        .select_related(
            "student", "student__profile", "program", "program__specialty_unit", "curriculum", "group", "group__parent"
        )
        .order_by("student__last_name", "student__first_name", "student__username")
    )
    if record_id:
        queryset = queryset.filter(pk=record_id)
    records = list(queryset)
    extras = sources.extra_member_records(organization, group, period_ids)
    if record_id:
        extras = [record for record in extras if str(record.pk) == str(record_id)]
    return records + [record for record in extras if record.pk not in {item.pk for item in records}]


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


def _paragraph_start(xml: str, token: str) -> int:
    return xml.rindex("<w:p ", 0, xml.index(token))


def _year_title_paragraph(sem_title_paragraph: str) -> str:
    """Semestr başlığı paraqrafından kurs başlığı: altdan xətt, bir az yuxarı boşluq, cədvəllə bir yerdə."""
    para = sem_title_paragraph.replace("{{SEM1_TITLE}}", "{{YEAR_TITLE}}")
    para = para.replace('w:before="120" w:after="60"', 'w:before="240" w:after="60"', 1)
    return para.replace("<w:b/>", '<w:b/><w:u w:val="single"/>')


def _fill_block(block_xml: str, plan: StudentPlan) -> str:
    """Tələbə bloku: başlıq + hər kurs üçün [kurs başlığı, payız cədvəli, yaz cədvəli] + qeyd/imzalar."""
    seg_start = _paragraph_start(block_xml, "{{SEM1_TITLE}}")
    tables = list(_TBL_RE.finditer(block_xml))
    seg_end = tables[1].end()
    head, segment, tail = block_xml[:seg_start], block_xml[seg_start:seg_end], block_xml[seg_end:]
    year_title = _year_title_paragraph(segment[: segment.index("</w:p>") + len("</w:p>")])
    seg_tables = _TBL_RE.findall(segment)

    parts = []
    for year in plan.years:
        filled = segment
        for tbl_xml, semester in zip(seg_tables, year.semesters):
            filled = filled.replace(tbl_xml, _fill_table(tbl_xml, semester), 1)
        filled = _sub(filled, {"SEM1_TITLE": year.semesters[0].title, "SEM2_TITLE": year.semesters[1].title})
        parts.append(_sub(year_title, {"YEAR_TITLE": year.title}) + filled)
    return _sub(
        head + "".join(parts) + tail,
        {
            "UNIVERSITY": plan.university,
            "FACULTY": plan.faculty,
            "SPECIALTY": plan.specialty,
            "GROUP": plan.group,
            "STUDENT": plan.student,
            "STUDY_YEAR": plan.study_year,
            "ACADEMIC_YEAR": plan.academic_year,
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
    raw_year = getattr(period, "academic_year", "") or ""
    by_year = _periods_by_year(organization)
    seasons_cache: dict = {"by_year": by_year}
    current = by_year.get(_start_year(raw_year), {"fall": [], "spring": []})
    year_periods = current["fall"] + current["spring"]
    records = group_records(organization, group, record_id=record_id, period_ids=year_periods)
    teachers_cache: dict = {}
    rows_cache: dict = {}
    all_periods = [pid for seasons in by_year.values() for pid in seasons["fall"] + seasons["spring"]]
    plan_sources = sources.PlanSources(organization, all_periods)
    plan_sources.prime([record.student_id for record in records])
    plans = [
        build_student_plan(
            organization,
            record,
            period=period,
            teachers_cache=teachers_cache,
            seasons_cache=seasons_cache,
            rows_cache=rows_cache,
            context_group=group,
            plan_sources=plan_sources,
        )
        for record in records
    ]
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
    "YearBlock",
    "az_upper",
    "build_group_document",
    "build_student_plan",
    "current_period",
    "group_records",
    "render_docx",
]
