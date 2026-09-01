"""İmtahana buraxılış (``barred``) statusunun **TƏK MƏNBƏYİ**.

Niyə bu modul var
-----------------
2026-08-31 auditinə qədər «tələbə imtahana buraxılırmı?» sualı **doqquz ayrı
yerdə** müstəqil hesablanırdı (``services``, ``analytics``, ``journal_extras``,
``page_contexts``, ``gradebook``×2, ``transcript``, ``accounts.academic_records``,
``public``).  Düstur eyni idi, amma **məxrəc üç fərqli yerdən götürülürdü** —
nəticədə eyni tələbə müəllimin ekranında «Kəsilir», öz kabinetində «Buraxılır ✓»
görürdü (ölçülüb: 1,599 yazılış).  Dağınıqlıq problemin özü idi; bu modul onu
bir qapıya yığır.

İki rejim
---------
``resolve()`` iki fərqli suala cavab verir, hansının işlədiyini ``frozen``
açarı müəyyən edir:

* **CANLI** (``frozen=False``) — mövcud rəsmi qayda: üzrsüz qayıb saatı
  auditoriya saatlarının ``limit_percent``-ini (defolt 25%) **keçirsə**
  (strict ``>``) tələbə imtahana buraxılmır.
* **DONMUŞ** (``frozen=True``) — köçürülmüş və jurnalı bağlanmış tarixi
  semestr.  Buraxılış statusu **HEÇ HESABLANMIR**; köhnə sistemin faktiki
  nəticəsi göstərilir.

Niyə donmuş rejimdə «heç nə etməmək» = «köhnə sistemin nəticəsini göstərmək»
----------------------------------------------------------------------------
Köhnə sistemin sxemində «imtahana buraxılır/buraxılmır» sütunu **heç vaxt
olmayıb** (``yekun`` cədvəli: ``girish, imtahanda, yekun, kesr, …`` — buraxılış
sahəsi yoxdur; ``kesr`` isə kəsr bayrağıdır, buraxılış deyil: ``kesr=1``
olanların 88.5%-i imtahana GİRİB).  Köhnə sistemin yeganə müşahidə oluna bilən
izi **imtahan balının yazılıb-yazılmamasıdır**, və köçürmə həmin balı artıq
kanonik ``FinalGrade.exam_score``-a yazıb.

Ona görə tarixi rejimdə **yeni oxuma yolu lazım deyil**: ``barred`` susduqda
mövcud qiymət zənciri (``finals.compute_final_result`` / ``analytics._evaluate``)
köhnə balı oxuyub keçib/kəsilib qərarını ÖZÜ verir — yəni köhnə sistemdə
imtahana girmiş tələbə ekranda da girmiş görünür.  ``LegacyGradeFact``
hesablamaya QOŞULMUR: o, dəyişməz, append-only sübut qatıdır (İmtahan
Mərkəzinin yoxlaması üçün) — bax :mod:`apps.registrar.legacy_grade_read`.

⚠️ **Heç bir saxlanmış dəyər dəyişmir.**  Bu qat ``barred`` sütunu yaratmır,
miqrasiya yazmır, köhnə balı düzəltmir.  Status **oxu vaxtı** həll olunur.
Sahibin qırmızı xətti: «biz köhnə datanı dəyişmirik, sadəcə yeni sistemə
köçürürük».

Donma meyarı (KOMPOZİT — iki şərt birdən)
-----------------------------------------
::

    dondurulub(offering) := jurnal BAĞLIDIR  AND  offering KÖÇÜRÜLÜB

* **Jurnal bağlıdır** — ``AssessmentScheme.is_published`` və ya
  ``approval_status='approved'`` (``gradebook.journal_is_locked`` ilə eyni
  tərif; bax :data:`_LOCKED_STATUSES`).  Bu, RİM-in **açıq, auditli, geri
  qaytarıla bilən** inzibati aktıdır (``journal_close``) — sürüşən tarix deyil.
* **Köçürülüb** — ``legacy_import.LegacyEntityMap`` möhürü
  (``entity_type='course_offering'``, ``state='migrated'``).

Niyə hər ikisi birdən — və rədd edilən namizədlər (hamısı sübut bazasında ölçülüb):

* ``AcademicPeriod.is_current`` **YARARSIZ**: köçürmə onu qəsdən heç vaxt
  yazmır, ona görə 13 dövrün **heç birində** ``True`` deyil.  Meyar
  ``not is_current`` olsaydı gələcək semestrlər də «tarixi» sayılardı.
* ``AcademicPeriod.is_past`` **TƏHLÜKƏLİ**: sürüşən tarixdir və gələcək
  semestrlərə də işləyir.  Konkret sübut: canlı 2025/2026 Yay dilimi
  2026-08-31-də bitir, yəni 2026-09-01-də ``is_past=True`` olur — halbuki
  həmin dilimin 10 açılışının hamısı hələ DRAFT jurnaldır.  Təkbaşına
  ``is_past`` meyarı **heç bir insan qərarı olmadan** canlı jurnalda
  hesablamanı söndürərdi.
* Təkbaşına **jurnal kilidi YETMİR**: RİM gələcək semestrləri də bağlayacaq,
  onda yeni qayda oraya da yayılardı (köçürülmüşlük möhürü olmayacaq → canlı
  hesablama qalır).
* Təkbaşına **köçürülmüşlük YETMİR**: import canlı 2025/2026 Yay dövrünü də
  yaradıb (kilid olmayacaq → canlı hesablama qalır).

Kəsişmə tam olaraq nəzərdə tutulan çoxluqdur.  Sübut bazasında ölçü: 6,906
«barred» yazılışın **6,906-sı (100%)** hər iki şərti ödəyir; canlı Yay
diliminin (10 açılış, 59 yazılış) **0**-ı ödəyir.

Sərhəd halları
--------------
Hər biri :mod:`apps.registrar.tests.test_exam_eligibility_frozen`-də test edilib:

1. **Sübut sətri olmayan yazılış** (6,188 hal) — donmuş rejimdə ``barred=False``
   olur, amma imtahan balı da yoxdur → nə «keçib», nə «kəsilib».  Bu, sübutun
   YOXLUĞUdur, «buraxılmayıb» sübutu DEYİL: köhnə sistem onlar üçün nəticə
   yazmayıb.  Boş buraxmaq əvəzinə GÖRÜNƏN etiket verilir —
   :data:`STATUS_LEGACY_NO_RESULT` / :data:`NO_LEGACY_RESULT_LABEL`.
   ⚠️ Bu yazılışların kreditləri **əvvəl də** heç bir sütuna düşmürdü
   (``barred`` → ``failed`` → nə ``earned``, nə ``in_progress``), yəni qərar
   kredit toplamasını PİSLƏŞDİRMİR — sadəcə statusu dürüst adlandırır.
2. **İmtahan balı 0** (33 hal) — «buraxılıb, amma gəlməyib / sıfır alıb»
   deməkdir, çünki köhnə sistemdə ``yekun`` sətrinin ÖZÜ yaranıb.
   ``0`` heç vaxt «buraxılmayıb» demək deyil; ``graded=True`` qalır və normal
   kəsr yolundan (``exam25``) keçir.
3. **Məxrəcsiz yazılış** (``lesson_hours=0``, 25,314 hal) — canlı rejimdə də,
   donmuş rejimdə də ``barred=False``: sıfır məxrəclə heç bir qərar verilə
   bilməz.  :func:`resolve` bunu ``hours_known=False`` ilə AÇIQ bildirir ki,
   çağıran «buraxılır ✓» kimi göstərməsin.  Canlı semestrdə bu, konfiqurasiya
   xətasıdır (dərs saatı təyin olunmayıb), tarixi semestrdə isə itmiş datadır.
   ⚠️ Tarixi dilimlərdə dərs-cəmi məxrəci ilə **BURAXILIŞ QƏRARI vermək**
   QADAĞANDIR: saat semantikası 2023/2024 Yaz-dan sürüşüb (1 saat → 1 cüt),
   ona görə iki eyni dərəcədə müdafiə oluna bilən məxrəc **2,176 qərarda**
   fərqlənir (6,906 → 9,082).  Qadağa qüvvədədir və pozulmur — donmuş dilimdə
   qərar ümumiyyətlə verilmir.  Həmin cəm yalnız davamiyyət balının MİQYASI
   kimi işlədilir (bax :func:`lesson_hours_for`), qərar kimi yox.

Çıxışın TAMLIĞI (2026-08-31 düşmən baxışı)
------------------------------------------
İlk versiyada resolver yalnız ``barred``-ı verirdi, qalan görünən sahələri
(davamiyyət balı, istisna, kəsr səbəbi) hər çağıran ÖZÜ hesablayırdı — və
dərhal ayrıldılar:

* **Davamiyyət balı** — müəllimin «yekun bölgü» tabı ``attendance_score``-u
  istisnasız çağırırdı (25% keçilmişsə ``None`` = boş xana), tələbənin kabineti
  isə donmuş dilimdə ``exempt=True`` ilə YENİDƏN oxuyurdu (7.00).  Eyni sətir,
  iki ekran, iki bal.  İndi bal :func:`resolve`-dan çıxır (``attendance_score``)
  və qayda birdir: **bal yalnız ``barred`` olduqda gizlənir**.
* **Məxrəc** — tələbə tərəfi onu tələbənin ÖZ işarələrindən yığırdı
  (``sum(m.lesson.hours for m in marks)``), müəllim tərəfi isə açılışın bütün
  dərslərindən.  İşarəsi olmayan tələbədə bu, məxrəci kiçildib balı süni
  şəkildə qaldırırdı.  İndi hər iki tərəf :func:`lesson_hours_for` işlədir.
* **İdmançı istisnası** — yalnız iki səthdə ötürülürdü; ``analytics`` onu
  QƏSDƏN ötürmürdü («yoxsa iki mühərrik ayrılar» şərhi ilə), amma nəticədə
  ayrılan məhz o oldu.  İndi hər səth istisnanı ötürür; toplu səthlər
  :func:`exempt_student_ids` (tək sorğu) ilə.
* **Kəsr səbəbi** — :func:`fail_reason_code` tək tərifdir (q/b ≠ imtahan25).

Aqreqat dürüstlüyü (ÜOMG)
-------------------------
:func:`uomg_from` — «ÜOMG hesablana bilmir» halı ilə «ÜOMG sıfırdır» halını
AYIRIR.  Kredit məxrəci sıfır olanda ``(None, False)`` qaytarılır; çağıran
sıfır çap etmək əvəzinə :data:`UOMG_UNAVAILABLE_LABEL` göstərməlidir.  Səbəb:
donmuş dilimlərdə köhnə sistemin nəticə yazmadığı 6,188 sətir nə keçmiş, nə
kəsilmiş sayılır — 231 tələbənin ÜOMG-daşıyan BÜTÜN sətirləri belədir və
onların transkriptində ``0.00`` «sıfır bal aldı» kimi oxunurdu.  Rəsmi sənəddə
bu, tələbənin ziyanına yanlış faktdır.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps as django_apps
from django.utils.translation import pgettext_lazy

from apps.registrar import attendance
from apps.registrar.models import AssessmentScheme, StudentAcademicRecord

#: Buraxılış statusunun mənbəyi — UI bunu «niyə hesablanmadı»nı izah etmək üçün oxuyur.
SOURCE_LIVE = "live"
SOURCE_LEGACY = "legacy"

#: Donmuş yazılışın nəticə vəziyyəti (``status_code`` üçün).
STATUS_LIVE = "live"
STATUS_LEGACY = "legacy"
STATUS_LEGACY_NO_RESULT = "legacy_no_result"

#: Defolt buraxılış həddi — ``Program.absence_limit_percent`` boş olduqda.
DEFAULT_LIMIT_PERCENT = 25

# ── Şəffaflıq mətnləri (dörd dilə) ───────────────────────────────────────────
FROZEN_BADGE = pgettext_lazy("registrar.eligibility", "Köhnə sistemdən")

FROZEN_NOTICE = pgettext_lazy(
    "registrar.eligibility",
    "Bu semestr köhnə sistemdən köçürülüb və jurnalı bağlanıb. İmtahana buraxılış "
    "statusu yenidən hesablanmır — köhnə sistemin faktiki nəticəsi göstərilir.",
)

NO_LEGACY_RESULT_LABEL = pgettext_lazy("registrar.eligibility", "Köhnə sistemdə nəticə yazılmayıb")

NO_LEGACY_RESULT_NOTICE = pgettext_lazy(
    "registrar.eligibility",
    "Köhnə sistem bu fənn üzrə imtahan nəticəsi yazmayıb. Ona görə status nə "
    "«keçib», nə «kəsilib» kimi göstərilir — məlumat mövcud deyil.",
)

UNKNOWN_HOURS_NOTICE = pgettext_lazy(
    "registrar.eligibility",
    "Fənnin auditoriya saatı təyin olunmayıb — buraxılış statusu hesablana bilmir.",
)

#: Aqreqat göstərici (ÜOMG / orta bal) hesablana bilməyəndə göstərilən etiket.
#: ⚠️ Bu ``0.00`` DEYİL: sıfır «pis nəticə», bu isə «məlumat yoxdur» deməkdir.
UOMG_UNAVAILABLE_LABEL = pgettext_lazy("registrar.eligibility", "Hesablana bilmir")

UOMG_UNAVAILABLE_NOTICE = pgettext_lazy(
    "registrar.eligibility",
    "ÜOMG hesablana bilmir: qəti nəticəsi olan (keçilmiş və ya kəsilmiş) fənn "
    "yoxdur. Köhnə sistem bu semestrlər üçün imtahan nəticəsi yazmayıb — bu, "
    "sıfır bal demək DEYİL.",
)

#: :func:`fail_reason_code` kodları — KƏSİLMƏ səbəbinin TƏK tərifi.
FAIL_REASON_BARRED = "qb"  # davamiyyət həddi → imtahana buraxılmayıb
FAIL_REASON_EXAM = "exam25"  # imtahana girib, keçə bilməyib → 25% təkrar imtahan
FAIL_REASON_TOTAL = "total"  # nadir/qeyri-müəyyən (imtahan qeyd olunmayıb)

# Jurnalı donduran YEGANƏ vəziyyət: RİM-in bağladığı jurnal.  ``gradebook``-un
# ``_CLOSED_STATUSES``-i ilə eyni tərif — orada re-eksport olunur ki, iki
# tərif heç vaxt bir-birindən sürüşməsin (bax :func:`gradebook.journal_is_locked`).
_LOCKED_STATUSES = frozenset({"approved"})

#: ``LegacyEntityMap``-dəki köçürülmüşlük möhürünün açarları.
_MIGRATED_ENTITY_TYPE = "course_offering"
_MIGRATED_STATE = "migrated"

#: Offering nümunəsində sorğu-daxili memo (per-request obyekt → təbii scope).
_FROZEN_ATTR = "_ems_eligibility_frozen"


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


# ── Donma meyarı ─────────────────────────────────────────────────────────────


def _locked_offering_ids(offering_ids) -> set:
    """Verilmiş açılışlardan jurnalı BAĞLI olanlar (tək sorğu).

    ``gradebook.journal_is_locked`` sxemi yoxdursa YARADIR (``get_or_create``);
    burada isə oxu yoludur — sxemi olmayan açılış sadəcə bağlı sayılmır.
    Nəticə eynidir: təzə yaradılan sxem heç vaxt ``is_published`` olmur.
    """
    rows = AssessmentScheme.objects.filter(offering_id__in=offering_ids).values_list(
        "offering_id", "is_published", "approval_status"
    )
    return {oid for oid, published, status in rows if published or status in _LOCKED_STATUSES}


def _migrated_offering_ids(offering_ids) -> set:
    """Köçürmə möhürü olan açılışlar (tək sorğu).

    ``apps.registrar`` ``apps.legacy_import``-u **statik import ETMİR** (modul
    sərhəd qapısı: ``scripts/module_deps.py``) — ona görə model runtime-da
    ``django_apps.get_model`` ilə alınır.  ``legacy_import`` quraşdırılmayıbsa
    (məs. minimal test konfiqurasiyası) heç nə donmur: fail-open DEYİL, sadəcə
    mövcud canlı davranış qalır.
    """
    try:
        entity_map = django_apps.get_model("legacy_import", "LegacyEntityMap")
    except LookupError:  # pragma: no cover — legacy_import quraşdırılmayıb
        return set()
    # ``target_pk`` mətn sahəsidir (opaque key), UUID-lər str kimi saxlanılır.
    wanted = {str(oid): oid for oid in offering_ids}
    rows = entity_map.objects.filter(
        entity_type=_MIGRATED_ENTITY_TYPE,
        state=_MIGRATED_STATE,
        target_pk__in=list(wanted),
    ).values_list("target_pk", flat=True)
    return {wanted[pk] for pk in rows if pk in wanted}


def frozen_offering_ids(offering_ids) -> frozenset:
    """Buraxılış statusu **DONDURULMUŞ** açılışların id dəsti — iki sabit sorğu.

    Bu, isti yollar (jurnal qridi, cədvəl modalı, transkript) üçün nəzərdə
    tutulmuş **toplu** primitivdir: per-enrollment ``LegacyEntityMap`` sorğusu
    N+1 fəlakətidir.  Tək açılış üçün :func:`is_frozen` işlədin.

    ``offering_ids`` həm hazır kolleksiya, həm də **queryset** ola bilər (məs.
    ``qs.values("id")``) — ``analytics.build_evaluation_maps_for`` universitet
    miqyaslı icmalda məhz belə ötürür ki, Django ``IN (SELECT …)`` alt-sorğusu
    yazsın və 100 000+ elementli parametr siyahısı ümumiyyətlə yaranmasın.
    Ona görə giriş BURADA materiallaşdırılmır.

    Ardıcıllıq qəsdən belədir — əvvəl kilid, sonra köçürmə möhürü: ikinci sorğu
    yalnız KİLİDLİ açılışlarla məhdudlaşır (donma onsuz da onların alt çoxluğudur),
    yəni ``LegacyEntityMap``-ə heç vaxt bütün girişdən böyük siyahı getmir.
    Möhür sorğusu mətn açarla (``target_pk``) işlədiyi üçün alt-sorğu ilə
    birləşdirilə bilmir — bu ardıcıllıq həmin məhdudiyyəti ucuz saxlayır.
    """
    if offering_ids is None:
        return frozenset()
    if isinstance(offering_ids, (list, tuple, set, frozenset)):
        offering_ids = [oid for oid in offering_ids if oid is not None]
        if not offering_ids:
            return frozenset()
    locked = _locked_offering_ids(offering_ids)
    if not locked:
        return frozenset()
    return frozenset(_migrated_offering_ids(locked))


def lesson_hours_map(offering_ids) -> dict:
    """offering_id → keçirilmiş dərslərin saat cəmi — **tək aqreqat sorğu**.

    :func:`lesson_hours_for`-un toplu fallback mənbəyi.  Döngüdə çağıran hər
    səth (kabinet, transkript, analitika, cədvəl modalı) bunu BİR dəfə qurub
    ötürməlidir; əks halda ``lesson_hours=0`` olan 25,314 köçürülmüş yazılışda
    sətir başına bir sorğu yaranır.
    """
    from django.db.models import Sum

    from apps.registrar.models import Lesson

    if offering_ids is None:
        return {}
    # ``frozen_offering_ids`` ilə eyni müqavilə: giriş QUERYSET ola bilər
    # (``qs.values("offering_id")``) — o zaman materiallaşdırılmır, Django
    # ``IN (SELECT …)`` alt-sorğusu yazır (universitet miqyaslı icmal).
    if isinstance(offering_ids, (list, tuple, set, frozenset)):
        offering_ids = [oid for oid in offering_ids if oid is not None]
        if not offering_ids:
            return {}
    rows = Lesson.objects.filter(offering_id__in=offering_ids).values("offering_id").annotate(total=Sum("hours"))
    return {r["offering_id"]: r["total"] or 0 for r in rows}


def lesson_hours_for(offering, lessons=None, *, hours_map=None) -> Decimal:
    """Fənnin auditoriya saatı — MƏXRƏCİN tək tərifi.

    ``offering.lesson_hours`` kanonikdir; təyin olunmayıbsa (0/None) açılışın
    **bütün** dərslərinin saat cəmi götürülür — hazır ``lessons`` siyahısından,
    ya da :func:`lesson_hours_map` nəticəsindən (``hours_map``).  İkisi də
    verilməyibsə tək sorğu edilir, amma YALNIZ ``lesson_hours`` boş olduqda və
    açılış yazılmışsa (pk-siz obyekt DB-yə getmir).

    ⚠️ İki qayda:

    1. Məxrəc HEÇ VAXT tələbənin öz işarələrindən yığılmır — işarəsi olmayan
       tələbədə bu, məxrəci kiçildib balı süni qaldırır və eyni sətri müəllim
       ekranından ayırır (2026-08-31 düşmən baxışı, 2-ci bloker).
    2. Dərs-cəmi fallback-i əvvəllər YALNIZ jurnal səthlərində vardı
       (``gradebook``, ``journal_extras``), ``services``/``analytics``/``finals``
       isə xam ``lesson_hours``-a baxırdı — yəni ``lesson_hours=0`` olan açılışda
       müəllim qridi «kəsilir», kabinet «buraxılır» deyirdi.  İndi hamısı bu
       funksiyadan keçir.  Bu, modul docstring-indəki «tarixi məxrəci bərpa
       etmə» qadağası ilə ziddiyyət təşkil ETMİR: donmuş dilimdə heç bir
       buraxılış qərarı verilmir, məxrəc yalnız davamiyyət balının miqyasıdır.
    """
    hours = _as_decimal(getattr(offering, "lesson_hours", 0) or 0)
    if hours > 0:
        return hours
    if lessons is not None:
        return _as_decimal(sum(int(getattr(item, "hours", 0) or 0) for item in lessons))
    offering_id = getattr(offering, "id", None)
    if offering_id is None:
        return hours
    if hours_map is not None:
        return _as_decimal(hours_map.get(offering_id, 0))
    return _as_decimal(lesson_hours_map([offering_id]).get(offering_id, 0))


def exempt_student_ids(organization, student_ids) -> frozenset:
    """Rəsmi idmançı-tələbə istisnası olan tələbələr — **tək sorğu**.

    Roster səthləri (jurnal qridi, «yekun bölgü») üçün; tək tələbəlik səthlərdə
    ``record.national_athlete_exemption`` onsuz da əldədir.
    """
    ids = [sid for sid in student_ids if sid is not None]
    if not ids or organization is None:
        return frozenset()
    return frozenset(
        StudentAcademicRecord.objects.filter(
            organization=organization, student_id__in=ids, national_athlete_exemption=True
        ).values_list("student_id", flat=True)
    )


def is_frozen(offering) -> bool:
    """Tək açılış üçün donma yoxlaması; nəticə obyekt üzərində memolanır.

    Memo sorğu-daxilidir (model nümunəsi hər sorğuda təzədən yüklənir), ona görə
    RİM jurnalı yenidən açanda növbəti sorğu artıq canlı hesablamaya qayıdır.

    Pk-siz (yaddaşda qurulmuş, hələ yazılmamış) açılış heç vaxt donmuş sayılmır
    və **DB-yə getmir** — donma köçürmə möhürünə söykənir, möhür isə yalnız
    yazılmış sətirdə ola bilər.
    """
    offering_id = getattr(offering, "id", None) if offering is not None else None
    if offering_id is None:
        return False
    cached = getattr(offering, _FROZEN_ATTR, None)
    if cached is None:
        cached = offering_id in frozen_offering_ids([offering_id])
        setattr(offering, _FROZEN_ATTR, cached)
    return cached


# ── Kanonik cavab ────────────────────────────────────────────────────────────


def resolve(
    *,
    absence_hours,
    lesson_hours=None,
    allowed_hours=None,
    limit_percent=DEFAULT_LIMIT_PERCENT,
    exempt=False,
    resit_done=False,
    frozen=False,
):
    """«Bu yazılış imtahana buraxılırmı?» — sistemin YEGANƏ cavabı.

    :param absence_hours: üzrsüz buraxılmış saat (``Enrollment.absence_hours``
        və ya jurnal qridində işarələrdən toplanan eyni kəmiyyət).
    :param lesson_hours: fənnin auditoriya saatı (``CourseOffering.lesson_hours``).
    :param allowed_hours: icazəli qayıb saatı, əvvəlcədən hesablanıbsa
        (``gradebook._allowed_absence_hours`` kimi).  Verilibsə ``lesson_hours``
        və ``limit_percent`` yenidən vurulmur — çağıranın məxrəci olduğu kimi
        qalır, yəni bu qat mövcud CANLI davranışı dəyişmir.
    :param limit_percent: ``Program.absence_limit_percent`` (tenant/proqram üzrə).
    :param exempt: rəsmi idmançı-tələbə istisnası (milli yığma;
        ``StudentAcademicRecord.national_athlete_exemption``).  Saatlar olduğu
        kimi qalır, yalnız ``barred`` qalxmır.
    :param resit_done: tamamlanmış təkrar imtahan buraxılış qadağasını qaldırır
        (``finals.compute_final_result`` və ``analytics._evaluate`` güzgüsü).
    :param frozen: :func:`is_frozen` / :func:`frozen_offering_ids` nəticəsi.
    :returns: sabit açarlı dict — bütün çağırış nöqtələri EYNİ dicti oxuyur.
        ``attendance_score`` = rəsmi 10-luq davamiyyət balı (``None`` = göstərmə).
        Çağıran onu YENİDƏN hesablamamalıdır: ``attendance.attendance_score``
        birbaşa çağırılsa istisna/təkrar-imtahan/donma qaydası ikinci dəfə
        yazılmış olur və iki ekran ayrılır (2026-08-31 düşmən baxışı, 2-ci bloker).

    Donmuş rejimdə ``barred`` və ``over_limit`` **hər ikisi** ``False`` qaytarılır:
    xam müqayisə də etibarsızdır (§ modul docstring, 3-cü sərhəd halı), ona görə
    heç bir səth ona təsadüfən söykənə bilməsin.  ``allowed_hours`` isə
    hesablanmağa davam edir — o, qərar deyil, davamiyyət zolağının miqyasıdır.

    ⚠️ **Məxrəc barədə:** sistemdə hazırda üç fərqli məxrəc dolaşır (xam
    ``offering.lesson_hours``; ``… or sum(lesson.hours)`` fallback-i; tələbənin
    öz işarələrinin saat cəmi) və CANLI semestrlərdə bir-birini təkzib edir.
    Bu qat həmin uyğunsuzluğu **qəsdən düzəltmir** — çağıranın məxrəcini olduğu
    kimi qəbul edir ki, mövcud canlı davranış dəyişməsin.  Tarixi datada isə
    məsələ öz-özünə bağlanır: ölçülmüş 1,599 ziddiyyətin hamısı donmuş
    dilimlərdədir, orada isə məxrəc heç oxunmur.  Canlı məxrəcin vahidləşdirilməsi
    AYRICA qərardır (bax modul docstring, 3-cü sərhəd halı: eyni-ölçü məxrəcə
    keçid 2,176 qərarı dəyişir).
    """
    absent = _as_decimal(absence_hours)
    percent = _as_decimal(limit_percent if limit_percent is not None else DEFAULT_LIMIT_PERCENT)
    hours = _as_decimal(lesson_hours)
    if allowed_hours is None:
        allowed = hours * percent / Decimal(100)
    else:
        allowed = _as_decimal(allowed_hours)
    # ``hours_known`` = «məxrəc yararlıdır».  Qapı MƏXRƏCƏ (``allowed``) qoyulur,
    # xam saata yox: ``lesson_hours=0`` da, ``limit_percent=0`` da eyni nəticə
    # verir — hədd deqenerativdir, qərar verilmir.  Bu, altı səthdən beşinin
    # (``gradebook``×2, ``journal_extras``, ``page_contexts``) artıq işlətdiyi
    # konvensiyadır; ``services``/``analytics`` xam saata baxırdı, yəni
    # ``limit_percent=0`` halında onlar bar qoyurdu, digərləri qoymurdu.
    # İndi altısı da eyni cavabı verir (``test_call_sites_agree`` bunu kilidləyir).
    # Praktikada fərq yaranmır: ``Program.absence_limit_percent`` defolt 25-dir.
    hours_known = allowed > 0

    if frozen:
        over_limit = False
        barred = False
        source = SOURCE_LEGACY
        notice = FROZEN_NOTICE
    else:
        # Strict ``>``: tam 25% hələ buraxılır (rəsmi davamiyyət cədvəli ilə eyni).
        over_limit = hours_known and absent > allowed
        barred = over_limit and not exempt and not resit_done
        source = SOURCE_LIVE
        notice = None if hours_known else UNKNOWN_HOURS_NOTICE

    # ── Davamiyyət balı (10-luq) — burada, bir dəfə ───────────────────────────
    # ``attendance.attendance_score`` kanonik DÜSTURdur və toxunulmur; onun
    # ikinci qaytarma dəyəri (``barred``) artıq heç yerdə oxunmur — qərar
    # buranındır.  Ona görə düstur həmişə ``exempt=True`` ilə («gizlətmə,
    # hesabla») çağırılır və bal SONRA, yalnız ``barred`` olduqda gizlədilir.
    # Məxrəc yoxdursa bal da yoxdur: düstur orada 10.00 qaytarır, onu göstərmək
    # «tam davamiyyət» yalanı olardı (25,314 yazılış).
    raw_score = None
    if hours > 0:
        raw_score, _ = attendance.attendance_score(hours, absent, limit_percent=percent, exempt=True)

    return {
        "barred": barred,
        # Davamiyyət balı (0..10) və ya ``None`` = göstərmə (buraxılmayıb / məxrəc yoxdur).
        "attendance_score": None if barred else raw_score,
        "over_limit": over_limit,
        "exempt": bool(exempt),
        "resit_done": bool(resit_done),
        "frozen": bool(frozen),
        "source": source,
        "hours_known": hours_known,
        "absence_hours": absence_hours,
        "lesson_hours": lesson_hours,
        "allowed_hours": allowed,
        "limit_percent": limit_percent,
        "notice": notice,
        "frozen_badge": FROZEN_BADGE if frozen else None,
    }


#: ``status_code`` → istifadəçiyə göstərilən qısa etiket.
STATUS_LABELS = {
    STATUS_LEGACY: FROZEN_BADGE,
    STATUS_LEGACY_NO_RESULT: NO_LEGACY_RESULT_LABEL,
}

#: ``status_code`` → «niyə belədir» izahı (tooltip).
STATUS_NOTICES = {
    STATUS_LEGACY: FROZEN_NOTICE,
    STATUS_LEGACY_NO_RESULT: NO_LEGACY_RESULT_NOTICE,
}


def status_label(code):
    """Etiket mətni; canlı status üçün ``None`` (adi keçdi/kəsildi göstərilir)."""
    return STATUS_LABELS.get(code)


def status_notice(code):
    """Tooltip izahı; canlı status üçün ``None``."""
    return STATUS_NOTICES.get(code)


def status_code(eligibility, *, graded) -> str:
    """Nəticə vəziyyətinin kodu — UI etiketi üçün.

    * ``"live"``              — canlı semestr, adi qayda işləyir.
    * ``"legacy"``            — tarixi semestr, köhnə sistemin nəticəsi var.
    * ``"legacy_no_result"``  — tarixi semestr, köhnə sistem nəticə YAZMAYIB
      (6,188 yazılış).  Bu, «kəsilib» DEYİL — boşluğun dürüst adıdır.
    """
    if not eligibility.get("frozen"):
        return STATUS_LIVE
    return STATUS_LEGACY if graded else STATUS_LEGACY_NO_RESULT


def fail_reason_code(result) -> str:
    """Bir KƏSİLMİŞ nəticənin səbəb kodu — q/b ≠ imtahan25.  TƏK tərif.

    * :data:`FAIL_REASON_BARRED` — DAVAMİYYƏTDƏN kəsilib (imtahana buraxılmayıb)
      → fənn yenidən tədris olunmalıdır.
    * :data:`FAIL_REASON_EXAM` — imtahana GİRİB, keçə bilməyib → bir dəfə
      təkrar imtahan hüququ (fənn haqqının 25%-i).
    * :data:`FAIL_REASON_TOTAL` — imtahan qeyd olunmayıb (qeyri-müəyyən).

    Donmuş dilimdə ``barred`` heç vaxt qalxmadığı üçün köhnə sistemin imtahana
    buraxdığı sətir avtomatik ``exam25``-ə düşür — «q/b» damğası vurulmur.
    """
    if result.get("barred"):
        return FAIL_REASON_BARRED
    if result.get("graded") and not result.get("passed"):
        return FAIL_REASON_EXAM
    return FAIL_REASON_TOTAL


def uomg_from(quality_points, credits):
    """ÜOMG (100 bal) = Σ(bal × kredit) / Σ(kredit) — aqreqatın TƏK düsturu.

    :returns: ``(dəyər, hesablana_bildi)``.  Kredit məxrəci sıfırdırsa
        ``(None, False)`` — ``Decimal("0.00")`` **DEYİL**.

    Niyə ``None`` (2026-08-31 düşmən baxışı, 1-ci bloker): donmuş dilimlərdə
    köhnə sistemin nəticə yazmadığı sətirlər nə «keçib», nə «kəsilib» sayılır,
    yəni ÜOMG məxrəcinə düşmür.  231 tələbənin ÜOMG-daşıyan BÜTÜN sətirləri
    belədir — onlarda köhnə ``0.00`` fallback-i rəsmi transkriptdə «sıfır bal
    aldı» kimi oxunurdu.  Çağıran indi :data:`UOMG_UNAVAILABLE_LABEL` göstərir.
    """
    if not credits:
        return (None, False)
    value = _as_decimal(quality_points) / Decimal(credits)
    return (value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), True)


__all__ = [
    "DEFAULT_LIMIT_PERCENT",
    "FAIL_REASON_BARRED",
    "FAIL_REASON_EXAM",
    "FAIL_REASON_TOTAL",
    "UOMG_UNAVAILABLE_LABEL",
    "UOMG_UNAVAILABLE_NOTICE",
    "exempt_student_ids",
    "fail_reason_code",
    "lesson_hours_for",
    "lesson_hours_map",
    "uomg_from",
    "FROZEN_BADGE",
    "FROZEN_NOTICE",
    "NO_LEGACY_RESULT_LABEL",
    "NO_LEGACY_RESULT_NOTICE",
    "SOURCE_LEGACY",
    "SOURCE_LIVE",
    "STATUS_LEGACY",
    "STATUS_LEGACY_NO_RESULT",
    "STATUS_LIVE",
    "UNKNOWN_HOURS_NOTICE",
    "frozen_offering_ids",
    "is_frozen",
    "resolve",
    "STATUS_LABELS",
    "STATUS_NOTICES",
    "status_code",
    "status_label",
    "status_notice",
]
