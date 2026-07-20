"""Rəsmi "DAVAMİYYƏT BALININ HESABLANMASI" cədvəlinin regres testləri.

Cədvəlin altındakı qayda: bir q/b = 2 akademik saat, bal = 10 × (1 − buraxılmış_saat
/ dərs_saatı) 2 onluğa AŞAĞI yuvarlanır (floor); auditoriya saatlarının 25%-dən çoxu
buraxılanda imtahana buraxılmır. Aşağıdakı gözləntilər rəsmi çap cədvəlinin (Elvin
göndərib) yüksək-etibarlı, parlaq xanalarından götürülüb — dəyərlər dəyişməsin deyə
kilidlənir.
"""

from decimal import Decimal

import pytest

from apps.registrar import attendance


def D(x):
    return Decimal(str(x))


@pytest.mark.parametrize(
    "lesson_hours,qb,expected",
    [
        # 10 saat
        (10, 0, D("10")),
        (10, 1, D("8")),
        # 15 saat
        (15, 1, D("8.66")),
        # 20 saat
        (20, 1, D("9")),
        (20, 2, D("8")),
        # 25 saat
        (25, 1, D("9.2")),
        (25, 2, D("8.4")),
        (25, 3, D("7.6")),
        # 30 saat
        (30, 1, D("9.33")),
        (30, 2, D("8.66")),
        (30, 3, D("8")),
        # 45 saat — floor sübutu: 9.5556 → 9.55 (round olsaydı 9.56 olardı)
        (45, 1, D("9.55")),
        (45, 5, D("7.77")),
        # 60 saat — floor sübutu: 9.6667 → 9.66
        (60, 1, D("9.66")),
        (60, 7, D("7.66")),
        # 90 saat — floor sübutu: 9.7778 → 9.77
        (90, 1, D("9.77")),
        (90, 11, D("7.55")),
        # 120 saat / 15 q/b = tam 25% (30 saat) → hələ buraxılır, bal 7.50
        (120, 15, D("7.5")),
    ],
)
def test_official_table_cells(lesson_hours, qb, expected):
    score, barred = attendance.attendance_score_from_count(lesson_hours, qb)
    assert barred is False
    assert score == expected


@pytest.mark.parametrize(
    "lesson_hours,qb",
    [
        (10, 2),  # 4 saat > 2.5 (25%)
        (15, 2),  # 4 > 3.75
        (20, 3),  # 6 > 5
        (25, 4),  # 8 > 6.25
        (30, 4),  # 8 > 7.5
        (45, 6),  # 12 > 11.25
        (60, 8),  # 16 > 15
        (90, 12),  # 24 > 22.5
        (120, 16),  # 32 > 30 (15 q/b tam 25%-də buraxılır, 16 keçir)
    ],
)
def test_barred_beyond_25_percent(lesson_hours, qb):
    score, barred = attendance.attendance_score_from_count(lesson_hours, qb)
    assert barred is True
    assert score is None


def test_exactly_25_percent_is_admitted_not_barred():
    # 120 saat, 30 buraxılmış saat = tam 25% → strict ">" olduğu üçün buraxılır.
    score, barred = attendance.attendance_score(120, 30)
    assert barred is False
    assert score == Decimal("7.5")
    # 30.01 saat (bir az çox) → buraxılmır.
    score2, barred2 = attendance.attendance_score(120, Decimal("30.01"))
    assert barred2 is True
    assert score2 is None


def test_hours_based_generalizes_beyond_two_hour_lessons():
    # Qeyri-standart dərs saatı: 60 saatlıq fəndə 10 saat qayıb (2-saatlıq deyil).
    # 10 × (1 − 10/60) = 8.3333 → floor 8.33; 10 < 15 (25%) → buraxılır.
    score, barred = attendance.attendance_score(60, 10)
    assert barred is False
    assert score == Decimal("8.33")


def test_zero_lesson_hours_gives_full_score():
    score, barred = attendance.attendance_score(0, 0)
    assert barred is False
    assert score == Decimal("10.00")


def test_no_absence_is_full_score():
    score, barred = attendance.attendance_score(45, 0)
    assert barred is False
    assert score == Decimal("10")


def test_score_is_floored_not_rounded():
    # 45 saat / 2 saat qayıb → 9.5556; floor=9.55, round olsaydı 9.56.
    score, _ = attendance.attendance_score(45, 2)
    assert score == Decimal("9.55")
