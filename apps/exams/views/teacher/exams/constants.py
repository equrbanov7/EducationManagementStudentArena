"""teacher exams paketi — constants.

M2 (2026-07-02): LIVE_ACTIVE_STATES buradan çıxarıldı — import-time
`apps.live_exam.models` asılılığı yaradırdı. Əvəzinə
`apps.exams.constants.get_live_active_states()` lazy accessor-u istifadə olunur.
"""

DETAIL_QUESTION_PAGE_SIZE = 20


DETAIL_QUESTION_MAX_PAGE_SIZE = 50
