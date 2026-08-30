"""structure_views paketi — constants."""

from core.constants import OrgUnitType

KAFEDRA_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)


TEACHER_ROLE_NAMES = ("teacher", "assistant", "assistant_teacher", "instructor", "collaborator")


HEAD_CANDIDATE_MIN_LEVEL = 40


FACULTY_PAGE_SIZE = 9


KAFEDRA_PAGE_SIZE = 9


#: Kafedra kartında əvvəlcədən göstərilən müəllim sayı (avatar sırası) —
#: qalanı "+N daha" çipinə düşür ki, çox müəllimli kafedrada kart hündürlüyü
#: sabit qalsın (bax: "ətraflı görünüş" modalı tam siyahını göstərir).
TEACHER_PREVIEW_LIMIT = 4

#: "Ətraflı görünüş" modalında render olunan müəllim sətri limiti (müdafiə
#: xətti — real universitetlərdə kafedra/fakültə müəllim sayı bundan azdır,
#: amma limit olmasa patoloji halda modal patlaya bilər).
DETAIL_TEACHER_LIST_LIMIT = 300

#: "Ətraflı görünüş" modalında göstərilən fənn (kataloq) çipi limiti.
DETAIL_SUBJECT_PREVIEW_LIMIT = 40

#: "Tədris ili üzrə açılışlar" statistika blokunda göstərilən il sayı.
DETAIL_YEAR_BREAKDOWN_LIMIT = 5


_SORT_OPTIONS = {
    "name": ("name",),
    "-name": ("-name",),
    "newest": ("-created_at", "name"),
    "oldest": ("created_at", "name"),
}
