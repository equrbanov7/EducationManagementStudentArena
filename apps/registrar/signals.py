"""Registrar domen siqnalları — aşağı qatların (exams və s.) reyestr hadisələrinə
statik import olmadan abunə olması üçün.

2026-09-14 (W5 `w5left`, tapşırıq 3; W4 hesabatı «qalanlar» 4). Tələbənin
qrupu dəyişəndə (`transfer.transfer_student_group`) reyestr qrupuna təyin
olunmuş final/midterm imtahanların fərdi PIN-ləri yenilənməli idi. `exams`
onsuz da `registrar`-a bağlıdır; əks istiqamətdə (`registrar → exams`) import
`scripts/module_deps.py` üçün YENİ dövr yaradardı — ona görə registrar yalnız
siqnal göndərir, `exams` (`services/unit_pin_sync.py`) ona abunə olur.

PostgreSQL-də qrup yazısı ORM `save()` ilə deyil, DB funksiyası
(`registrar_begin_student_group_transfer`) ilə gedir → `post_save` işə düşmür;
bu siqnal həmin boşluğu bağlayır. Göndərilmə köçürmənin atomik blokunun
İÇİNDƏDİR — abunəçi `transaction.on_commit` ilə işləməlidir.
"""

from django.dispatch import Signal

#: Tələbənin cari akademik qeydinin qrupu dəyişdi.
#: kwargs: ``record`` (StudentAcademicRecord, yeni qrupla), ``old_group``
#: (OrgUnit | None), ``new_group`` (OrgUnit), ``organization``.
student_group_changed = Signal()

__all__ = ["student_group_changed"]
