"""Jurnal siyahısı (``page_contexts.journal_list_context``) üçün SQL-səviyyəli
süzgəc + seçim-siyahısı köməkçiləri (QA 2026-09-05 P2-18).

Əvvəllər bütün bu iş `page_contexts.py`-də BÜTÜN offering-ləri (11 124-ə qədər)
model instansiyası kimi yükləyib Python siyahısı üzərində süzürdü, seçim
siyahıları (müəllim/qrup/fakültə/kafedra) isə həmin tam dəst üzərində əl ilə
təkrarsızlaşdırılırdı — İKT rəhbəri görünüşündə 1.96 s / 32 sorğu. Burada
EYNİ NƏTİCƏ (eyni sətirlər, eyni sıra, eyni dropdown-lar) ORM səviyyəsində,
yalnız lazımi dəstlər üzərində alınır. Ayrıca moduldur ki, `page_contexts.py`
600-sətir büdcəsində qalsın (bax `scripts/check_module_size.py`)."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError

from core.search_text import tolerant_q

#: `schedule.season_label` ilə EYNİ ay-bölgüsü (SQL tərəfə güzgülənir).
SEASON_MONTHS: dict[str, tuple[int, ...]] = {
    "Payız semestri": (8, 9, 10, 11, 12),
    "Yaz semestri": (1, 2, 3, 4, 5),
    "Yay semestri": (6, 7),
}


def int_or_none(value) -> int | None:
    """``instructor_id`` (auth.User — tam ədəd PK) üçün fail-closed çevirmə."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def uuid_or_none(value):
    """``group_id`` (OrgUnit — UUID PK) üçün fail-closed çevirmə."""
    import uuid

    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _org_unit(organization, raw):
    """Seçilmiş id → təşkilatın bölməsi (tip məhdudiyyəti YOX — «məktəb»/«fakültə» adlandırması
    fərqi süzgəci boşaltmasın); pozuq / naməlum / başqa təşkilat → ``None``."""
    from core.http_ids import parse_uuid

    unit_id = parse_uuid(raw)
    if unit_id is None or organization is None:
        return None
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()


def apply_unit_filters(qs, organization, faculty_raw: str, department_raw: str):
    """«Fakültə» / «Kafedra» süzgəcləri → ``(qs, effektiv_fakültə, effektiv_kafedra)``.

    TƏRİFLƏR (``lessons_log_units`` ilə EYNİ mənbə — bax onun modul şərhi):

    * **Fakültə** — açılışın QRUPU fakültənin alt-ağacındadır (ara səviyyələr daxil).
    * **Kafedra** — açılışın kafedrası = fənnin TƏDRİS YÜKÜNÜN kafedrası (dərs yükü sətri →
      ``TeachingTask.chair``, yoxdursa ``Subject.chair_unit``; köçürülmüş açılışda fənnin yükü /
      qrup yolu / müəllimin ştat kafedrası) — tək tərif :mod:`apps.registrar.offering_chairs`-dədir.
      Köçürülmüş strukturda qrup kafedranın altında DEYİL (2026-10-24: yalnız qrup yolu boş
      verirdi); 2026-10-25: müəllimin istənilən kafedra üzvlüyü də YOX — saat hesabı ilə başqa
      kafedrada dərs deyən müəllimin bütün fənləri o kafedraya düşürdü («Mülki müdafiə»).
    * **Kaskad** — kafedra seçilmiş fakültənin alt-ağacında deyilsə (UI fakültə dəyişəndə
      kafedranı sıfırlayır), köhnə kafedra seçimi atılır — boş nəticə yox, fakültə nəticəsi.
    * Pozuq / naməlum id → boş nəticə (fail-closed, əvvəlki davranış).
    """
    from apps.registrar import lessons_log_units as units

    faculty = _org_unit(organization, faculty_raw) if faculty_raw else None
    department = _org_unit(organization, department_raw) if department_raw else None
    if (faculty_raw and faculty is None) or (department_raw and department is None):
        return qs.none(), faculty_raw, department_raw
    if faculty is not None and department is not None and not units.is_within(department, faculty):
        department, department_raw = None, ""
    if faculty is not None:
        qs = qs.filter(units.faculty_q(faculty, offering=""))
    if department is not None:
        qs = qs.filter(units.kafedra_offering_q(department, within=qs))
    return qs, faculty_raw, department_raw


def label_for_selection(kind: str, value: str) -> str:
    """Seçilmiş id-nin adı — dropdown siyahısında olmayan hallar üçün fallback.

    Kafedra/qrup üçün ``OrgUnit.name``, müəllim üçün tam ad (yoxdursa username).
    Etibarsız id səssizcə boş qaytarır — qutu ən pis halda placeholder göstərir.
    """
    if not value:
        return ""
    try:
        if kind == "unit":
            unit = django_apps.get_model("organizations", "OrgUnit").objects.filter(pk=value).only("name").first()
            return unit.name if unit else ""
        if kind == "teacher":
            user_model = django_apps.get_model("auth", "User")
            user = user_model.objects.filter(pk=value).only("first_name", "last_name", "username").first()
            return (user.get_full_name() or user.username).strip() if user else ""
    except (ValueError, TypeError, ValidationError):
        return ""
    return ""


def apply_kind_filter(qs, kind: str):
    """Keçirilmiş və planlaşdırılmış növlər üzrə SQL süzgəci; səhifələmə qorunur."""
    from .journal_planned_kinds import apply_kind_filter as apply

    return apply(qs, kind)


def apply_text_query(qs, query: str):
    """``q`` axtarışı — fənn kodu/adı + müəllim adı üzərində, KÖHNƏ Python
    davranışının (bitişik mətndə alt-sətir axtarışı) DB tərəfə eyni-eyni
    köçürülməsi: "CODE NAME MÜƏLLİM" birləşməsi üzərində ``core.search_text.tolerant_q``.

    Sərhəd keçən sorğular da (məs. kodun sonu + adın əvvəli) EYNİ nəticəni
    verir — ``Concat`` NULL-ları avtomatik boş mətnə çevirir (Django sənədi)."""
    from django.db.models import CharField, Value
    from django.db.models.functions import Coalesce, Concat, NullIf, Trim

    full_name = Coalesce(
        NullIf(
            Trim(Concat("instructor__first_name", Value(" "), "instructor__last_name", output_field=CharField())),
            Value(""),
        ),
        "instructor__username",
        Value(""),
        output_field=CharField(),
    )
    haystack = Concat("subject__code", Value(" "), "subject__name", Value(" "), full_name, output_field=CharField())
    # Dözümlü (sahib 2026-09-26): tokenlər VƏ; az/ing hərfləri qatlanır; fənn kodu kod rejimində.
    search_q = tolerant_q(query, ("_jl_search_haystack",), compact_fields=("subject__code",))
    if search_q is None:
        return qs
    return qs.annotate(_jl_search_haystack=haystack).filter(search_q)


def teacher_choices_for(base_qs) -> list[dict]:
    """Müəllim dropdown-u — offering-lərin təkrarsız müəllimləri (yüngül sorğu)."""
    from .journal_teacher_filters import teachers_for

    rows = teachers_for(base_qs).values_list("pk", "first_name", "last_name", "username")
    choices = []
    for uid, first, last, username in rows:
        full = f"{first or ''} {last or ''}".strip()
        label = full or username
        choices.append({"value": str(uid), "label": label})
    # `value` ikinci açardır: eyni adlı İKİ müəllim (ad toqquşması) arasında
    # `SELECT DISTINCT`-in özü sıra ZƏMANƏTİ vermir — yalnız etiketə görə sort
    # (Python-un stabil sort-u ilə belə) sorğu planına görə dəyişən sıra verərdi.
    choices.sort(key=lambda c: (c["label"].lower(), c["value"]))
    return choices


def group_choices_for(base_qs) -> list[dict]:
    """Qrup dropdown-u — offering-lərin təkrarsız qrupları (yüngül sorğu)."""
    from .journal_group_identity import choices_for_scope

    return choices_for_scope(base_qs)


def faculty_department_choices_for(base_qs) -> tuple[list[dict], list[dict]]:
    """Fakültə/kafedra dropdown-ları — qrupun ata-zəncirindən (``path``), YALNIZ
    offering-lərdə iştirak edən təkrarsız qruplar üçün. `organizations` statik
    idxal edilmir (``django_apps.get_model`` — modul-sərhəd dövrü yaranmasın,
    bax ``module_deps.py``: ``organizations → registrar`` onsuz da var)."""
    from core.constants import OrgUnitType

    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    group_rows = list(base_qs.exclude(group_id=None).values_list("group_id", "group__path").distinct())
    if not group_rows:
        return [], []

    referenced_ids: set[str] = set()
    for _group_id, path in group_rows:
        if path:
            referenced_ids.update(seg for seg in path.split("/") if seg)

    faculty_types = {OrgUnitType.FACULTY, OrgUnitType.DEANERY}
    dept_types = {OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT}
    ancestor_rows = org_unit_model.objects.filter(
        pk__in=referenced_ids, unit_type__in=faculty_types | dept_types
    ).values_list("id", "unit_type", "name")
    ancestor_map = {str(uid): (unit_type, name) for uid, unit_type, name in ancestor_rows}

    def _nearest(path, types):
        if not path:
            return None
        # Path kök→özü sırasındadır; `_ancestor_of` (əvvəlki Python versiya)
        # özündən yuxarı doğru gedirdi — ekvivalenti: TƏRSİNƏ gəzib İLK uyğunu tap.
        for seg in reversed(path.split("/")):
            info = ancestor_map.get(seg)
            if info and info[0] in types:
                return seg, info[1]
        return None

    seen_faculty: set[str] = set()
    seen_dept: set[str] = set()
    faculty_choices: list[dict] = []
    dept_choices: list[dict] = []
    for _group_id, path in group_rows:
        faculty = _nearest(path, faculty_types)
        if faculty is not None and faculty[0] not in seen_faculty:
            seen_faculty.add(faculty[0])
            faculty_choices.append({"value": faculty[0], "label": faculty[1]})
        department = _nearest(path, dept_types)
        if department is not None and department[0] not in seen_dept:
            seen_dept.add(department[0])
            dept_choices.append({"value": department[0], "label": department[1]})

    # Deterministik ikinci açar (bax `teacher_choices_for` şərhi) — eyni adlı
    # fakültə/kafedra olsa belə sıra sabit qalır.
    faculty_choices.sort(key=lambda c: (c["label"].lower(), c["value"]))
    dept_choices.sort(key=lambda c: (c["label"].lower(), c["value"]))
    return faculty_choices, dept_choices
