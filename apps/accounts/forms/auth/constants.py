"""accounts auth forms paketi — constants."""

from django.contrib.auth import get_user_model
from django.utils.translation import get_language

from core.constants import OrganizationType

User = get_user_model()


_AZERBAIJAN_DISPLAY_NAMES = {
    "az": "Azərbaycan",
    "tr": "Azerbaycan",
    "ru": "Азербайджан",
}


def _country_display_name(country):
    if country.code != "AZ":
        return country.name

    language_code = (get_language() or "").split("-", 1)[0]
    return _AZERBAIJAN_DISPLAY_NAMES.get(language_code, country.name)


STUDENT_JOIN_ORG_TYPE_MAP = {
    "school_student": OrganizationType.SCHOOL,
    "university_student": OrganizationType.UNIVERSITY,
    "course_student": OrganizationType.COURSE_CENTER,
}


TEACHER_JOIN_ORG_TYPE_MAP = {
    "school_teacher": OrganizationType.SCHOOL,
    "university_teacher": OrganizationType.UNIVERSITY,
    "course_teacher": OrganizationType.COURSE_CENTER,
}


STAFF_JOIN_ORG_TYPE_MAP = {
    "school_staff": OrganizationType.SCHOOL,
    "university_staff": OrganizationType.UNIVERSITY,
    "course_staff": OrganizationType.COURSE_CENTER,
}


ORGANIZATION_CREATOR_TYPES = {
    OrganizationType.SCHOOL,
    OrganizationType.UNIVERSITY,
    OrganizationType.COURSE_CENTER,
}


JOIN_ORG_TYPE_MAP = {
    **STUDENT_JOIN_ORG_TYPE_MAP,
    **TEACHER_JOIN_ORG_TYPE_MAP,
    **STAFF_JOIN_ORG_TYPE_MAP,
}


JOIN_SIGNUP_MODES = {"student_join", "teacher_join", "staff_join"}


ORGANIZATION_SELECTION_REQUIRED_MESSAGE = "Zəhmət olmasa siyahıdan təşkilatı (universitet/məktəb/kurs mərkəzi) seçin."
