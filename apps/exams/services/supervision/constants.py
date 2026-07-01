"""supervision paketi — constants."""

VIOLATION_EVENT_TYPES = frozenset(
    {
        "fullscreen_exited",
        "tab_switched",
        "window_blurred",
        "keyboard_shortcut",
        "grace_period_expired",
    }
)


NON_COUNTING_EVENT_TYPES = frozenset(
    {
        "copy_attempt",
        "paste_attempt",
        "cut_attempt",
        "right_click_attempt",
        "text_select_attempt",
    }
)


EVENT_SEVERITY_MAP = {
    "fullscreen_exited": "high",
    "fullscreen_restored": "info",
    "tab_switched": "high",
    "window_blurred": "medium",
    "window_focused": "info",
    "copy_attempt": "medium",
    "paste_attempt": "medium",
    "cut_attempt": "medium",
    "right_click_attempt": "low",
    "keyboard_shortcut": "medium",
    "text_select_attempt": "low",
    "suspicious_repeated": "high",
    "grace_period_expired": "critical",
    "auto_locked": "critical",
    "auto_submitted": "critical",
    "resume_window_expired": "critical",
    "teacher_resumed": "info",
    "teacher_granted_chance": "info",
    "exam_started_supervised": "info",
    "student_acknowledged": "info",
}
