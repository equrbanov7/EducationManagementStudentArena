"""Kabinet bölmələri üzrə suallar və uzun videolardakı keçidlər."""

from .faq_extra_academic import ACADEMIC
from .faq_extra_administration import ADMINISTRATION
from .faq_extra_cabinet import CABINET
from .faq_extra_teaching import TEACHING

EXTRA = {**CABINET, **ADMINISTRATION, **TEACHING, **ACADEMIC}
