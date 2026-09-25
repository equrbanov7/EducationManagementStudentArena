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

#: RİM-in toplu bağlaması (``journal_close.close_journals``) HƏQİQƏTƏN jurnal
#: bağladı. Tranzaksiya commit olunduqdan SONRA (``on_commit``, robust) göndərilir.
#: kwargs: ``organization``, ``period``, ``unit`` (OrgUnit | None — əhatə),
#: ``offering_ids`` (YENİ bağlanan açılışlar), ``by_user``.
#: Abunəçi: ``apps.surveys`` (dövrün anonim sorğu kampaniyasını açır). Abunə
#: ``apps.registrar.public.journal_close.journal_closed`` ilə (public səth).
journal_closed = Signal()

__all__ = ["journal_closed", "student_group_changed"]
