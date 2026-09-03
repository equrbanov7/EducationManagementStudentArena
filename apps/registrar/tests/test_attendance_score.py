"""Rəsmi «DAVAMİYYƏT BALININ HESABLANMASI» cədvəlinin tam, cədvəl-idarəli testi.

Cədvəlin altındakı qayda (sahib həll edib, 23/23 çap olunmuş dəyər uyğun gəlir)::

    davamiyyət = 10 × (N − Σ buraxılmış_saat) / N        # 2 onluğa AŞAĞI (floor)
    imtahana buraxılmır ⟺ Σ buraxılmış_saat > 0.25 × N   # STRICT ">"

``N`` = fənnin auditoriya saatı, çap olunmuş cədvəldə hər q/b = 2 akademik saat
(standart cüt).  Bizdə ``Lesson.hours`` REAL dəyər daşıyır (1, 2 və ya 3 saat),
ona görə kanonik funksiya qayıb SAYI deyil, qayıb SAATI ilə işləyir —
:func:`test_hours_and_count_paths_agree_on_every_cell` hər xanada iki yolun
eyniliyini, yəni ümumiləşdirmənin cədvələ SADİQ olduğunu sübut edir.

``_OFFICIAL_GRID`` cədvəlin 12 sətri × 17 sütununun (q/b 0..16) tam açılışıdır;
``None`` = qırmızı xana («İmtahana buraxılmır»).  ``_OWNER_VERIFIED_CELLS``
sahibin çap nüsxə ilə bir-bir tutuşdurduğu lövbərlərdir — qrid onlardan
ayrılsa test qırmızı olur.

⚠️ TARİXİ DATA.  Bu qayda **gələcək semestrlər** üçündür.  Köçürülmüş tarixi
semestrlərdə köhnə sistemin dəyərləri olduğu kimi qalır; burada heç bir test
tarixi yazılışa blok tətbiq etmir.
"""

from decimal import Decimal

import pytest

from apps.registrar import attendance

# Cədvəlin sətirləri (fənn saatı) və sütunları (q/b sayı).
_ROWS = (10, 15, 20, 25, 30, 45, 60, 75, 90, 105, 120, 135)
_COLS = tuple(range(0, 17))

# Sətir → hər q/b sütunu üçün gözlənilən bal; ``None`` = imtahana buraxılmır.
_OFFICIAL_GRID = {
    10: ("10.00", "8.00", None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
    15: ("10.00", "8.66", None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
    20: ("10.00", "9.00", "8.00", None, None, None, None, None, None, None, None, None, None, None, None, None, None),
    25: ("10.00", "9.20", "8.40", "7.60", None, None, None, None, None, None, None, None, None, None, None, None, None),
    30: ("10.00", "9.33", "8.66", "8.00", None, None, None, None, None, None, None, None, None, None, None, None, None),
    45: (
        "10.00",
        "9.55",
        "9.11",
        "8.66",
        "8.22",
        "7.77",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
    60: (
        "10.00",
        "9.66",
        "9.33",
        "9.00",
        "8.66",
        "8.33",
        "8.00",
        "7.66",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
    75: (
        "10.00",
        "9.73",
        "9.46",
        "9.20",
        "8.93",
        "8.66",
        "8.40",
        "8.13",
        "7.86",
        "7.60",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
    90: (
        "10.00",
        "9.77",
        "9.55",
        "9.33",
        "9.11",
        "8.88",
        "8.66",
        "8.44",
        "8.22",
        "8.00",
        "7.77",
        "7.55",
        None,
        None,
        None,
        None,
        None,
    ),
    105: (
        "10.00",
        "9.80",
        "9.61",
        "9.42",
        "9.23",
        "9.04",
        "8.85",
        "8.66",
        "8.47",
        "8.28",
        "8.09",
        "7.90",
        "7.71",
        "7.52",
        None,
        None,
        None,
    ),
    120: (
        "10.00",
        "9.83",
        "9.66",
        "9.50",
        "9.33",
        "9.16",
        "9.00",
        "8.83",
        "8.66",
        "8.50",
        "8.33",
        "8.16",
        "8.00",
        "7.83",
        "7.66",
        "7.50",
        None,
    ),
    135: (
        "10.00",
        "9.85",
        "9.70",
        "9.55",
        "9.40",
        "9.25",
        "9.11",
        "8.96",
        "8.81",
        "8.66",
        "8.51",
        "8.37",
        "8.22",
        "8.07",
        "7.92",
        "7.77",
        "7.62",
    ),
}

# Sahibin çap nüsxə ilə bir-bir yoxladığı lövbərlər (brifdən).
_OWNER_VERIFIED_CELLS = (
    (135, 2, "9.70"),
    (90, 1, "9.77"),
    (90, 9, "8.00"),
    (45, 5, "7.77"),
    (30, 3, "8.00"),
    (10, 1, "8.00"),
)

# Sahibin yoxladığı hədd sətirləri: sətir → SON icazəli q/b.
_OWNER_VERIFIED_LAST_ALLOWED = {90: 11, 60: 7, 30: 3, 120: 15}

_ALL_CELLS = tuple((n, q, _OFFICIAL_GRID[n][q]) for n in _ROWS for q in _COLS)
_SCORED_CELLS = tuple((n, q, e) for (n, q, e) in _ALL_CELLS if e is not None)
_BARRED_CELLS = tuple((n, q) for (n, q, e) in _ALL_CELLS if e is None)


def _ids(cells):
    return [f"{n}h-{q}qb" for (n, q, *_rest) in cells]


# ── Qridin özünün bütövlüyü ──────────────────────────────────────────────────


def test_grid_covers_every_official_row_and_column():
    assert set(_OFFICIAL_GRID) == set(_ROWS)
    for n in _ROWS:
        assert len(_OFFICIAL_GRID[n]) == len(_COLS), n
    assert len(_ALL_CELLS) == 12 * 17


@pytest.mark.parametrize("lesson_hours,qb,expected", _OWNER_VERIFIED_CELLS)
def test_owner_verified_anchors_are_in_the_grid(lesson_hours, qb, expected):
    """Lövbərlər qridin İÇİNDƏN oxunur — qrid sürüşsə bu test onu tutur."""
    assert _OFFICIAL_GRID[lesson_hours][qb] == expected


@pytest.mark.parametrize("lesson_hours,last_allowed", sorted(_OWNER_VERIFIED_LAST_ALLOWED.items()))
def test_owner_verified_thresholds_are_in_the_grid(lesson_hours, last_allowed):
    row = _OFFICIAL_GRID[lesson_hours]
    assert row[last_allowed] is not None, "son icazəli xana qırmızı olmamalıdır"
    assert row[last_allowed + 1] is None, "növbəti xana qırmızı olmalıdır"


# ── Cədvəlin hər xanası (12 × 17 = 204) ──────────────────────────────────────


@pytest.mark.parametrize("lesson_hours,qb,expected", _SCORED_CELLS, ids=_ids(_SCORED_CELLS))
def test_every_scored_cell_matches_the_official_table(lesson_hours, qb, expected):
    score, barred = attendance.attendance_score_from_count(lesson_hours, qb)
    assert barred is False
    assert score == Decimal(expected)


@pytest.mark.parametrize("lesson_hours,qb", _BARRED_CELLS, ids=_ids(_BARRED_CELLS))
def test_every_red_cell_is_barred(lesson_hours, qb):
    score, barred = attendance.attendance_score_from_count(lesson_hours, qb)
    assert barred is True
    assert score is None


@pytest.mark.parametrize("lesson_hours,qb,expected", _ALL_CELLS, ids=_ids(_ALL_CELLS))
def test_hours_and_count_paths_agree_on_every_cell(lesson_hours, qb, expected):
    """ÜMUMİLƏŞDİRMƏNİN SÜBUTU: saat əsaslı kanonik funksiya, hər dərs 2 saat
    olanda (Σ = 2 × q/b) rəsmi cədvəli EYNİLƏ verir."""
    by_hours = attendance.attendance_score(lesson_hours, 2 * qb)
    by_count = attendance.attendance_score_from_count(lesson_hours, qb)
    assert by_hours == by_count
    if expected is None:
        assert by_hours == (None, True)
    else:
        assert by_hours == (Decimal(expected), False)


def test_every_admitted_cell_is_at_least_seven_and_a_half():
    """Köçürmə doğrulamasının müstəqil tapıntısı: `dav < 7.5` ⟺ kəsr bayrağı
    (649,032 sətrin 99.61 %-i).  Qrid bunu struktur olaraq təsdiqləyir."""
    for _n, _q, expected in _SCORED_CELLS:
        assert Decimal(expected) >= Decimal("7.5")


# ── Ümumiləşdirmə: qeyri-standart dərs saatları (J11-dən sonrakı real data) ──


@pytest.mark.parametrize(
    "lesson_hours,absent_hours,expected",
    [
        # 1-saatlıq dərslər (185,781 sətir): tək saatlar cədvəldə sütun yoxdur,
        # amma düstur onları düzgün ölçür.
        (60, 1, "9.83"),
        (60, 5, "9.16"),
        (60, 15, "7.50"),  # tam 25% → hələ buraxılır
        # 3-saatlıq dərslər (30 sətir).
        (90, 3, "9.66"),
        (90, 21, "7.66"),
        # Qarışıq: 2×2h + 1×1h + 1×3h = 8 saat.
        (45, 8, "8.22"),
    ],
)
def test_real_lesson_hours_mixes(lesson_hours, absent_hours, expected):
    score, barred = attendance.attendance_score(lesson_hours, absent_hours)
    assert barred is False
    assert score == Decimal(expected)


# ── Hədd: STRICT ">" (rəsmi mətnlə eyni) ─────────────────────────────────────


def test_exactly_at_the_limit_is_admitted():
    score, barred = attendance.attendance_score(120, 30)  # tam 25%
    assert (score, barred) == (Decimal("7.5"), False)


def test_a_hair_over_the_limit_is_barred():
    score, barred = attendance.attendance_score(120, Decimal("30.01"))
    assert (score, barred) == (None, True)


@pytest.mark.parametrize("lesson_hours", _ROWS)
def test_limit_is_strictly_greater_on_every_row(lesson_hours):
    allowed = Decimal(lesson_hours) * Decimal("0.25")
    assert attendance.attendance_score(lesson_hours, allowed)[1] is False
    assert attendance.attendance_score(lesson_hours, allowed + Decimal("0.01"))[1] is True


# ── Yuvarlaqlaşdırma: floor, round DEYİL ─────────────────────────────────────


@pytest.mark.parametrize(
    "lesson_hours,absent_hours,floored,rounded",
    [
        (45, 2, "9.55", "9.56"),  # 9.5555…
        (90, 2, "9.77", "9.78"),  # 9.7777…
        (60, 2, "9.66", "9.67"),  # 9.6666…
        (15, 2, "8.66", "8.67"),  # 8.6666…
    ],
)
def test_score_is_floored_not_rounded(lesson_hours, absent_hours, floored, rounded):
    score, _ = attendance.attendance_score(lesson_hours, absent_hours)
    assert score == Decimal(floored)
    assert score != Decimal(rounded)


# ── Kənar hallar ─────────────────────────────────────────────────────────────


def test_zero_lesson_hours_gives_full_score_and_never_bars():
    assert attendance.attendance_score(0, 0) == (Decimal("10.00"), False)
    assert attendance.attendance_score(0, 40) == (Decimal("10.00"), False)


def test_no_absence_is_full_score_on_every_row():
    for lesson_hours in _ROWS:
        assert attendance.attendance_score(lesson_hours, 0) == (Decimal("10"), False)


def test_configurable_limit_percent_is_honoured():
    # Proqram 20%-ə keçirsə 120/26 saat artıq həddi keçir (24 icazəlidir).
    assert attendance.attendance_score(120, 26, limit_percent=20)[1] is True
    assert attendance.attendance_score(120, 24, limit_percent=20)[1] is False


# ── İdmançı-tələbə istisnası (milli yığma) ───────────────────────────────────


def test_athlete_exemption_lifts_the_bar_but_not_the_score():
    """Rəsmi istisna BURAXILIŞ qərarını ləğv edir, balı QALDIRMIR."""
    barred_score, barred = attendance.attendance_score(90, 30)
    assert (barred_score, barred) == (None, True)

    score, exempt_barred = attendance.attendance_score(90, 30, exempt=True)
    assert exempt_barred is False
    assert score == Decimal("6.66")  # 10 × (90 − 30) / 90 — real qayıba görə


def test_exemption_does_not_change_anything_below_the_limit():
    for lesson_hours, qb, expected in _SCORED_CELLS:
        assert attendance.attendance_score_from_count(lesson_hours, qb, exempt=True) == (
            Decimal(expected),
            False,
        )


def test_exemption_defaults_to_false():
    assert attendance.attendance_score(90, 30) == (None, True)
    assert attendance.attendance_score_from_count(90, 15) == (None, True)
