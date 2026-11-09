"""A source timetable slot is covered only by the same teaching event."""


def slot_key(slot):
    return (
        slot.weekday,
        slot.start_time,
        slot.end_time,
        slot.room,
        slot.week_type,
        slot.kind,
        slot.instructor_id or slot.offering.instructor_id,
        slot.is_parked,
    )
