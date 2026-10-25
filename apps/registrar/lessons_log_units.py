"""«Keçilmiş dərslər» — «Fakültə» və «Kafedra» filtrləri (sahib, 2026-09-25).

TƏRİFLƏR — kodun qalanı ilə EYNİ mənbələr:

* **Fakültə** — dərsin QRUPUNUN struktur əcdadı (``FACULTY``/``DEANERY``): jurnal siyahısının
  «Fakültə» filtri (``journal_list_query.faculty_department_choices_for`` + qrup yolu) və
  ``journal.roster`` / RİM əhatəsi (qrupun ``OrgUnit.path`` alt-ağacı) ilə eyni qayda.
* **Kafedra** — dərsin AÇILIŞININ kafedrası = fənnin tədris yükünün aid olduğu kafedra
  (dərs yükü sətri → ``TeachingTask.chair``, yoxdursa ``Subject.chair_unit``, köçürülmüş açılışda
  fənnin yükü / qrup yolu / müəllimin ştat kafedrası). Tərif TƏKDİR və
  :mod:`apps.registrar.offering_chairs`-dədir — jurnal siyahısı ``/jurnal/`` də onu işlədir. Müəllimin
  başqa kafedradakı (saat hesabı) üzvlüyü dərsi o kafedraya KEÇİRMİR (sahib, 2026-10-25: «Mülki
  müdafiə» Proqramlaşdırma süzgəcində çıxırdı).
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

from . import offering_chairs

FACULTY_TYPES = (OrgUnitType.FACULTY, OrgUnitType.DEANERY)
CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
#: Seçim siyahılarının tavanı (bölmənin digər seçiciləri ilə eyni).
OPTION_CAP = 300


def _org_units():
    return django_apps.get_model("organizations", "OrgUnit").objects


def _kafedra_types(organization):
    from apps.organizations.public import kafedra_unit_types

    return kafedra_unit_types(organization) if organization is not None else CHAIR_TYPES


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


def kafedra_lesson_q(unit, *, within=None) -> Q:
    """Dərs kafedraya aiddir: açılışının kafedrası ``unit``-in alt-ağacındadır (``offering_chairs``).

    ``within`` — süzüləcək dərs queryset-i (həll yalnız onun açılışları üçün; ``None`` → təşkilat)."""
    return offering_chairs.kafedra_q(unit, offering="offering__", within=within)


def kafedra_offering_q(unit, *, offering="", within=None) -> Q:
    """Açılış kafedraya aiddir (``offering_chairs`` tərifi).

    ``offering`` — sahə prefiksi: ``""`` birbaşa ``CourseOffering`` queryset-i üçün (jurnal
    siyahısının «Kafedra» filtri — ``journal_list_query.apply_unit_filters``), ``"offering__"``
    slot / dərs kimi açılışa FK daşıyan modellər üçün."""
    return offering_chairs.kafedra_q(unit, offering=offering, within=within)


def kafedra_slot_q(unit, *, within=None) -> Q:
    """Cədvəl slotu kafedraya aiddir (slotun açılışının kafedrası)."""
    return offering_chairs.kafedra_q(unit, offering="offering__", within=within)


def _in_scopes(path, unit_id, scopes) -> bool:
    for scope in scopes:
        if unit_id in {str(uid) for uid in scope.unit_ids}:
            return True
        if any((path or "").startswith(f"{scope_path}/") for scope_path in scope.unit_paths):
            return True
    return False


def _unit_candidates(option_source, organization) -> tuple[dict, dict]:
    """``({fakültə_id: (ad, yol)}, {kafedra_id: (ad, yol)})`` — dörd sabit sorğu, sətir sayından asılı deyil."""
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

    offerings = django_apps.get_model("registrar", "CourseOffering").objects.filter(
        pk__in=option_source.order_by().values("offering_id")
    )
    chairs = offering_chairs.chair_candidates(offerings, organization.pk)
    return faculties, chairs


def _options(units, *, scopes=None, under=None) -> list:
    rows = []
    for uid, (name, path) in units.items():
        if scopes is not None and not _in_scopes(path, uid, scopes):
            continue
        if under is not None and not (uid == str(under.pk) or (path or "").startswith(f"{under.path}/")):
            continue
        rows.append({"value": uid, "label": name or uid})
    rows.sort(key=lambda row: (row["label"].casefold(), row["value"]))
    return rows[:OPTION_CAP]


def unit_options(option_source, organization, *, faculty=None, scopes=None) -> tuple[list, list]:
    """``(fakültə seçimləri, kafedra seçimləri)`` — dörd sabit sorğu, sətir sayından asılı deyil.

    ``scopes`` — struktur əhatəli nəzarətçinin ``UnitScope`` siyahısı (org-wide / müəllim → ``None``)."""
    if scopes is not None and any(scope.is_org_wide for scope in scopes):
        scopes = None
    faculties, chairs = _unit_candidates(option_source, organization)
    # Kafedra siyahısı əhatəyə görə YOX, görünən dərslərin kafedralarına görədir (dərslər onsuz da
    # əhatəlidir): dekanın qruplarına başqa fakültənin kafedrası da dərs keçir («Mülki müdafiə»).
    return _options(faculties, scopes=scopes), _options(chairs, under=faculty)


def _settle(organization, unit, raw, options, types, *, scoped, lockable=True) -> tuple:
    """Bir seçicinin effektiv bölməsi: ``(bölmə, kilidli?, etibarsız?)`` (sahib, 2026-10-14).

    Əhatəli aktorda (kafedra müdiri, dekan, müəllim) TƏK seçim varsa o, avtomatik seçilir və
    sahə gizlənir — URL-dəki başqa id SƏSSİZ nəzərə alınmır. Əhatədən kənar id (siyahıda yoxdur)
    «etibarsız» sayılır → nəticə boşdur və bölmənin adı açılmır. Org-wide aktorda dəyişiklik yoxdur.
    ``lockable=False`` — tək seçim avtomatik seçilmir (kafedra: görünən dərslər bir neçə kafedranındır).
    """
    if not scoped:
        return unit, False, bool(raw and unit is None)
    if lockable and len(options) == 1:
        if unit is not None and str(unit.pk) == options[0]["value"]:
            return unit, True, False
        return resolve_unit(organization, options[0]["value"], types), True, False
    if unit is not None and str(unit.pk) not in {option["value"] for option in options}:
        return None, False, True
    return unit, False, bool(raw and unit is None)


def filter_state(user, organization, option_source, *, supervisor, faculty_raw="", kafedra_raw="", with_options=True):
    """Seçilmiş fakültə/kafedra + (istəyə görə) seçim siyahıları — bölmə VƏ CSV üçün TƏK qayda.

    Qaytarır: ``faculty``/``kafedra`` (bölmə və ya ``None``), ``faculty_value``/``kafedra_value``
    (effektiv query dəyəri), ``invalid`` (seçilib, amma tapılmayıb və ya əhatədən kənardır → nəticə
    boş olmalıdır), ``faculty_locked``/``kafedra_locked`` (əhatədə tək seçim — avtomatik seçilib,
    sahə gizlədilir), ``faculty_options``/``kafedra_options``.

    Əhatəli aktorda siyahılar ``with_options=False`` (CSV) olsa da qurulur — kilid və əhatə
    yoxlaması bölmə ilə EYNİ olsun."""
    faculty = resolve_unit(organization, faculty_raw, FACULTY_TYPES) if faculty_raw else None
    kafedra_types = _kafedra_types(organization)
    kafedra = resolve_unit(organization, kafedra_raw, kafedra_types) if kafedra_raw else None
    scopes = None
    if supervisor:
        from apps.registrar.lessons_log import _supervision_scopes

        scopes = _supervision_scopes(user, organization)
        if any(scope.is_org_wide for scope in scopes):
            scopes = None
    scoped = not supervisor or scopes is not None
    faculty_options: list = []
    kafedra_options: list = []
    faculty_locked = kafedra_locked = False
    faculty_invalid = bool(faculty_raw and faculty is None)
    kafedra_invalid = bool(kafedra_raw and kafedra is None)
    candidates = _unit_candidates(option_source, organization) if (with_options or scoped) else None
    if candidates is not None:
        faculty_options = _options(candidates[0], scopes=scopes)
        faculty, faculty_locked, faculty_invalid = _settle(
            organization, faculty, faculty_raw, faculty_options, FACULTY_TYPES, scoped=scoped
        )
    dropped = False
    if faculty is not None and kafedra is not None and not is_within(kafedra, faculty):
        # Kaskad: fakültə dəyişəndə ona aid olmayan köhnə kafedra seçimi atılır (boş nəticə olmasın).
        kafedra, dropped, kafedra_invalid = None, True, False
    if candidates is not None:
        # Kafedra siyahısı = görünən dərslərin kafedraları (əhatə süzgəci yox — bax ``unit_options``).
        # Kilid yalnız aktorun BÜTÜN dərsləri bir kafedranındırsa: fakültə ilə daralmış tək seçim
        # (dekanın fakültəsində bir kafedra) başqa kafedraların dərslərini gizlətməsin.
        kafedra_options = _options(candidates[1], under=faculty)
        lockable = len(candidates[1]) == 1
        if not dropped:
            kafedra, kafedra_locked, kafedra_invalid = _settle(
                organization, kafedra, kafedra_raw, kafedra_options, kafedra_types, scoped=scoped, lockable=lockable
            )
        elif scoped and lockable and len(kafedra_options) == 1:
            kafedra = resolve_unit(organization, kafedra_options[0]["value"], kafedra_types)
            kafedra_locked = True

    def _value(unit, raw, invalid):
        return str(unit.pk) if unit is not None else (raw if invalid else "")

    return {
        "faculty": faculty,
        "kafedra": kafedra,
        "faculty_value": _value(faculty, faculty_raw, faculty_invalid),
        "kafedra_value": _value(kafedra, kafedra_raw, kafedra_invalid),
        "invalid": bool(faculty_invalid or kafedra_invalid),
        "dropped": dropped,
        "faculty_locked": faculty_locked,
        "kafedra_locked": kafedra_locked,
        "faculty_options": faculty_options if with_options else [],
        "kafedra_options": kafedra_options if with_options else [],
    }


__all__ = [
    "CHAIR_TYPES",
    "FACULTY_TYPES",
    "OPTION_CAP",
    "faculty_q",
    "filter_state",
    "is_within",
    "kafedra_lesson_q",
    "kafedra_offering_q",
    "kafedra_slot_q",
    "resolve_unit",
    "unit_options",
]
