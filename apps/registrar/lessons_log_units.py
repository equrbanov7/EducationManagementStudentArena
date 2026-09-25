"""«Keçilmiş dərslər» — «Fakültə» və «Kafedra» filtrləri (sahib, 2026-09-25).

TƏRİFLƏR — kodun qalanı ilə EYNİ mənbələr:

* **Fakültə** — dərsin QRUPUNUN struktur əcdadı (``FACULTY``/``DEANERY``): jurnal siyahısının
  «Fakültə» filtri (``journal_list_query.faculty_department_choices_for`` + qrup yolu) və
  ``journal.roster`` / RİM əhatəsi (qrupun ``OrgUnit.path`` alt-ağacı) ilə eyni qayda.
* **Kafedra** — dərsi keçən MÜƏLLİMİN kafedrası: aktiv ``Membership.scope_unit`` (``CHAIR`` /
  ``DEPARTMENT`` və ya onun alt-bölməsi) — dərs yükünün «kafedra müəllimləri» qaydası
  (``workload/services/people.py``) və sillabus müəllifinin kafedrası
  (``syllabus/services/units.author_chair_unit``) ilə eyni mənbə; ƏLAVƏ olaraq fənnin aparıcı
  kafedrası (``Subject.chair_unit``). Köçürülmüş strukturda qrup kafedranın altında DEYİL
  (ixtisas birbaşa fakültəyə bağlıdır) — ona görə kafedra qrup yolundan yox, müəllim + fəndən
  gəlir. Dərsin müəllimi ``Lesson.instructor``, boşdursa açılışın müəllimidir (``scoped_lessons``).
* **Kaskad** — fakültə seçiləndə kafedra siyahısı həmin fakültənin alt-ağacındakı kafedralarla
  daralır (fakültəyə uyğun gəlməyən köhnə kafedra seçimi atılır); fənn / qrup / müəllim
  siyahıları seçilmiş fakültə və kafedraya görə daralır.
* **Əhatə** — seçim siyahıları aktorun GÖRƏ BİLDİYİ dərslərdən qurulur; struktur əhatəli
  nəzarətçidə (kafedra müdiri, dekan) yalnız öz alt-ağacındakı bölmələr göstərilir, org-wide
  aktorda (RİM, rektor) bütün təşkilat. Siyahılar sabit sayda sorğu ilə qurulur (sətir-sətir yox).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from core.constants import OrgUnitType
from core.http_ids import parse_uuid

FACULTY_TYPES = (OrgUnitType.FACULTY, OrgUnitType.DEANERY)
CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
#: Seçim siyahılarının tavanı (bölmənin digər seçiciləri ilə eyni).
OPTION_CAP = 300


def _org_units():
    return django_apps.get_model("organizations", "OrgUnit").objects


def _memberships():
    return django_apps.get_model("organizations", "Membership").objects


def resolve_unit(organization, raw_id, types):
    """Seçilmiş id → təşkilatın bu tipdən bölməsi; pozuq / naməlum / başqa tip → ``None``."""
    unit_id = parse_uuid(raw_id)
    if unit_id is None or organization is None:
        return None
    return (
        _org_units()
        .filter(organization=organization, pk=unit_id, unit_type__in=types)
        .only("id", "name", "path", "unit_type", "organization_id")
        .first()
    )


def _subtree(field, unit) -> Q:
    """``field`` bölməsi ``unit``-in özü və ya törəməsidir (``OrgUnit.path`` materialized path)."""
    return Q(**{f"{field}_id": unit.pk}) | Q(**{f"{field}__path__startswith": f"{unit.path}/"})


def is_within(unit, ancestor) -> bool:
    return unit.pk == ancestor.pk or (unit.path or "").startswith(f"{ancestor.path}/")


def faculty_q(unit, *, offering="offering__") -> Q:
    """Qrupu fakültənin alt-ağacında olan dərslər / slotlar (``offering`` — sahə prefiksi)."""
    return _subtree(f"{offering}group", unit)


def _chair_teacher_ids(unit):
    """Kafedranın (və alt-bölmələrinin) aktiv üzvləri — alt-sorğu (``IN (SELECT …)``)."""
    return (
        _memberships()
        .filter(organization_id=unit.organization_id, is_active=True)
        .filter(_subtree("scope_unit", unit))
        .values("user_id")
    )


def kafedra_lesson_q(unit) -> Q:
    """Dərs kafedraya aiddir: müəllimi kafedranın üzvüdür VƏ YA fənni kafedranındır."""
    teachers = _chair_teacher_ids(unit)
    return (
        Q(instructor_id__in=teachers)
        | Q(instructor__isnull=True, offering__instructor_id__in=teachers)
        | _subtree("offering__subject__chair_unit", unit)
    )


def kafedra_slot_q(unit) -> Q:
    """Cədvəl slotu kafedraya aiddir (slotun müəllimi açılışın müəllimidir)."""
    return Q(offering__instructor_id__in=_chair_teacher_ids(unit)) | _subtree("offering__subject__chair_unit", unit)


def _in_scopes(path, unit_id, scopes) -> bool:
    for scope in scopes:
        if unit_id in {str(uid) for uid in scope.unit_ids}:
            return True
        if any((path or "").startswith(f"{scope_path}/") for scope_path in scope.unit_paths):
            return True
    return False


def unit_options(option_source, organization, *, faculty=None, scopes=None) -> tuple[list, list]:
    """``(fakültə seçimləri, kafedra seçimləri)`` — dörd sabit sorğu, sətir sayından asılı deyil.

    ``scopes`` — struktur əhatəli nəzarətçinin ``UnitScope`` siyahısı (org-wide / müəllim → ``None``)."""
    if scopes is not None and any(scope.is_org_wide for scope in scopes):
        scopes = None
    paths = [
        path
        for path in option_source.order_by()
        .values_list("offering__group__path", flat=True)
        .distinct()[: OPTION_CAP * 5]
        if path
    ]
    segment_ids = {str(parsed) for path in paths for seg in path.split("/") if (parsed := parse_uuid(seg))}
    faculties: dict = {}
    if segment_ids:
        found = {
            str(uid): (name, path)
            for uid, name, path in _org_units()
            .filter(organization=organization, pk__in=segment_ids, unit_type__in=FACULTY_TYPES)
            .values_list("id", "name", "path")
        }
        for path in paths:
            nearest = next((seg for seg in reversed(path.split("/")) if seg in found), None)
            if nearest is not None:
                faculties[nearest] = found[nearest]

    chairs: dict = {}
    teacher_ids = Q(user_id__in=option_source.values("instructor_id")) | Q(
        user_id__in=option_source.values("offering__instructor_id")
    )
    for uid, name, path in (
        _memberships()
        .filter(organization=organization, is_active=True, scope_unit__unit_type__in=CHAIR_TYPES)
        .filter(teacher_ids)
        .values_list("scope_unit_id", "scope_unit__name", "scope_unit__path")
        .distinct()[:OPTION_CAP]
    ):
        chairs[str(uid)] = (name, path)
    for uid, name, path in (
        option_source.exclude(offering__subject__chair_unit__isnull=True)
        .order_by()
        .values_list(
            "offering__subject__chair_unit_id",
            "offering__subject__chair_unit__name",
            "offering__subject__chair_unit__path",
        )
        .distinct()[:OPTION_CAP]
    ):
        chairs.setdefault(str(uid), (name, path))

    def _options(units, *, under=None):
        rows = []
        for uid, (name, path) in units.items():
            if scopes is not None and not _in_scopes(path, uid, scopes):
                continue
            if under is not None and not (uid == str(under.pk) or (path or "").startswith(f"{under.path}/")):
                continue
            rows.append({"value": uid, "label": name or uid})
        rows.sort(key=lambda row: (row["label"].casefold(), row["value"]))
        return rows[:OPTION_CAP]

    return _options(faculties), _options(chairs, under=faculty)


def filter_state(user, organization, option_source, *, supervisor, faculty_raw="", kafedra_raw="", with_options=True):
    """Seçilmiş fakültə/kafedra + (istəyə görə) seçim siyahıları — bölmə VƏ CSV üçün TƏK qayda.

    Qaytarır: ``faculty``/``kafedra`` (bölmə və ya ``None``), ``faculty_value``/``kafedra_value``
    (effektiv query dəyəri), ``invalid`` (seçilib, amma tapılmayıb → nəticə boş olmalıdır),
    ``faculty_options``/``kafedra_options``."""
    faculty = resolve_unit(organization, faculty_raw, FACULTY_TYPES) if faculty_raw else None
    kafedra = resolve_unit(organization, kafedra_raw, CHAIR_TYPES) if kafedra_raw else None
    invalid = bool((faculty_raw and faculty is None) or (kafedra_raw and kafedra is None))
    dropped = False
    if faculty is not None and kafedra is not None and not is_within(kafedra, faculty):
        # Kaskad: fakültə dəyişəndə ona aid olmayan köhnə kafedra seçimi atılır (boş nəticə olmasın).
        kafedra, dropped = None, True
    state = {
        "faculty": faculty,
        "kafedra": kafedra,
        "faculty_value": str(faculty.pk) if faculty is not None else ("" if not faculty_raw else faculty_raw),
        "kafedra_value": (
            str(kafedra.pk) if kafedra is not None else ("" if dropped or not kafedra_raw else kafedra_raw)
        ),
        "invalid": invalid,
        "dropped": dropped,
        "faculty_options": [],
        "kafedra_options": [],
    }
    if with_options:
        scopes = None
        if supervisor:
            from apps.registrar.lessons_log import _supervision_scopes

            scopes = _supervision_scopes(user, organization)
        state["faculty_options"], state["kafedra_options"] = unit_options(
            option_source, organization, faculty=faculty, scopes=scopes
        )
    return state


__all__ = [
    "CHAIR_TYPES",
    "FACULTY_TYPES",
    "OPTION_CAP",
    "faculty_q",
    "filter_state",
    "is_within",
    "kafedra_lesson_q",
    "kafedra_slot_q",
    "resolve_unit",
    "unit_options",
]
