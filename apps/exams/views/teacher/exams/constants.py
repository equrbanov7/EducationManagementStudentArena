"""teacher exams paketi — constants."""

from apps.live_exam.models import LiveSession

LIVE_ACTIVE_STATES = (
    LiveSession.STATE_LOBBY,
    LiveSession.STATE_QUESTION,
    LiveSession.STATE_REVEAL,
)


DETAIL_QUESTION_PAGE_SIZE = 20


DETAIL_QUESTION_MAX_PAGE_SIZE = 50
