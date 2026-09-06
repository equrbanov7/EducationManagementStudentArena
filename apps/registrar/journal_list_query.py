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
from django.db.models import Q

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


def path_segment_q(field: str, unit_id: str) -> Q:
    """``unit_id in path.split("/")`` şərtinin SQL güzgüsü.

    ``OrgUnit.path`` "/" ilə ayrılmış id zənciridir (kök → özü). Sərhədli
    LIKE variantları (tam, əvvəl, son, orta seqment) `unit_id`-nin path-ın
    HƏR HANSI seqmentinə (alt sətir kimi deyil) düşdüyünü tapır."""
    return (
        Q(**{field: unit_id})
        | Q(**{f"{field}__startswith": f"{unit_id}/"})
        | Q(**{f"{field}__endswith": f"/{unit_id}"})
        | Q(**{f"{field}__contains": f"/{unit_id}/"})
    )


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
    """Dərs tipi süzgəci — offering-in HƏR HANSI slotu/dərsi bu tipdədirmi.

    Əvvəllər `attach_kind_labels` tam dəst üçün hesablanıb Python-da
    `selected_kind in o.slot_kinds` yoxlanılırdı; indi iki subquery ilə eyni
    məntiq DB tərəfdə (join fan-out YOXDUR — `pk__in`, `Count` annotasiyasını
    təhrif etmir)."""
    from apps.registrar.models import Lesson, ScheduleSlot

    return qs.filter(
        Q(pk__in=ScheduleSlot.objects.filter(kind=kind).values_list("offering_id", flat=True))
        | Q(pk__in=Lesson.objects.filter(kind=kind).values_list("offering_id", flat=True))
    )


def apply_text_query(qs, query: str):
    """``q`` axtarışı — fənn kodu/adı + müəllim adı üzərində, KÖHNƏ Python
    davranışının (bitişik mətndə alt-sətir axtarışı) DB tərəfə eyni-eyni
    köçürülməsi: "CODE NAME MÜƏLLİM" birləşməsi üzərində ``icontains``.

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
    return qs.annotate(_jl_search_haystack=haystack).filter(_jl_search_haystack__icontains=query)


def teacher_choices_for(base_qs) -> list[dict]:
    """Müəllim dropdown-u — offering-lərin təkrarsız müəllimləri (yüngül sorğu)."""
    rows = (
        base_qs.exclude(instructor_id=None)
        .values_list("instructor_id", "instructor__first_name", "instructor__last_name", "instructor__username")
        .distinct()
    )
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
    rows = base_qs.exclude(group_id=None).values_list("group_id", "group__name").distinct()
    choices = [{"value": str(gid), "label": name} for gid, name in rows]
    # Eyni adlı qruplar (məs. "." kimi generic test adları) üçün DETERMİNİST
    # ikinci açar — bax `teacher_choices_for` şərhi.
    choices.sort(key=lambda c: (c["label"].lower(), c["value"]))
    return choices


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
