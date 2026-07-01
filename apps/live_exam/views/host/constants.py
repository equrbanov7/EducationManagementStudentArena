"""live_exam host paketi — constants."""

from apps.live_exam.models import LiveSession

LIVE_ACTIVE_STATES = (
    LiveSession.STATE_LOBBY,
    LiveSession.STATE_QUESTION,
    LiveSession.STATE_REVEAL,
)
