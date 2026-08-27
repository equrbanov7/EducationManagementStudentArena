"""Sillabus domeninin audited mənbə kontraktları (J9 — sərbəst iş mövzuları).

Niyə ``field_contracts`` DEYİL: həmin modul artıq modul-ölçü qapısının sərt
600-sətir tavanındadır (``scripts/check_module_size.py``), qapının özünün
yazdığı yeganə çarə isə "əvvəlcə onu bölün"-dür.  Ona görə sillabus domeninin
kontraktları burada, öz modulunda yaşayır; forma, adlandırma və default-deny
proyeksiya semantikası ``field_contracts``-dakı ilə hərfi-hərfinə eynidir.

Gate qeydi
----------
``sillabus`` və ``sillabus_serbest_is`` plan-da ``design_gated``-dir, yəni HEÇ
BİR faza onları batch zəncirinə İDDİA ETMİR (``source_tables = ()``).  Gated
olmaq İDDİAya qadağa qoyur, OXUMAĞA yox — bax ``rehearsal_contracts`` seam
qeydi və ``rehearsal_journal_points_source``-dakı ``archive_gated`` presedenti.
Dizayn qərarı (sahib, 2026-08): sərbəst iş MÖVZULARI köçürülür, sərbəst iş
BALI isə köçürülmür (o, artıq J5-də ``AssessmentComponent(self_work)`` +
``ComponentScore`` kimi mövcuddur və mövzu-başına deyil, aqreqatdır).

Zəncir
------
``journals.sillabus_id → sillabus.id → sillabus.uniqid → sillabus_serbest_is.uniqid``

⚠️ ``sillabus_serbest_is.uniqid`` JURNAL uniqid-i DEYİL, SİLLABUS uniqid-idir.
Canlı ölçü (2026-08-27, rehearsal dump): 13,875 jurnaldan 12,979-unda
``sillabus_id`` doludur, 12,055-i real ``sillabus`` sətrinə düşür və 12,051-i
(87 %) ən azı bir sərbəst iş mövzusuna çatır.
"""

from __future__ import annotations

from .field_contracts import LegacySourceFieldContract

# ``journals``-ın ÜÇÜNCÜ, qəsdən kiçik kontraktı.  ``JOURNAL_FIELDS``-i
# genişlətmək onun barmaq izini — və beləliklə J1-J8-in yazdığı HƏR
# ``source_row_hash``-i — dəyişərdi; presedent ``STUDENT_STATUS_FIELDS``-dir.
# ``uniqid`` daxildir, çünki açılış (offering) indeksi məhz jurnal uniqid-i ilə
# açarlanır; ``sillabus_id`` isə zəncirin yeganə yeni sütunudur.
JOURNAL_SYLLABUS_FIELDS = LegacySourceFieldContract(
    source_table="journals",
    version="syllabus-v1",
    allowed_fields=("id", "uniqid", "sillabus_id"),
)

# ``sillabus`` yalnız KÖRPÜ kimi oxunur: ``id`` → ``uniqid``.  Başqa heç bir
# sütun yoxdur, çünki proyeksiya default-deny-dir: OXUNMAYAN sahə mənbədən heç
# vaxt çıxmamalıdır.  ``ders_saati`` (``journals.fenn_saati``-nin çarpaz-yoxlama
# mənbəyi, 10,631 müqayisədən 9,419-u üst-üstə düşür) QƏSDƏN kənardadır: onu
# oxuyan faza hələ yoxdur.  Lazım olanda AYRICA kiçik kontraktla açılmalıdır —
# bu kontraktı genişlətmək onun barmaq izini, deməli J9-un yazdığı bütün
# ``derivation_hash``-ləri dəyişər.  Kredensial/PII sütunları (dekan_id,
# kafedra_id, teacher_id, language, …) heç vaxt bu kontrakta girmir.
SILLABUS_FIELDS = LegacySourceFieldContract(
    source_table="sillabus",
    version="syllabus-v1",
    allowed_fields=("id", "uniqid"),
)

# Mövzu mətninin özü.  ``name`` HTML-entity daşıyır (``&uuml;``, ``&ccedil;``);
# ``legacy_text.clean_text`` onları üç keçidlə açır, sonra NFC + boşluq
# normallaşdırması edir — yəni ayrıca dekoder lazım deyil.
SILLABUS_SELF_WORK_FIELDS = LegacySourceFieldContract(
    source_table="sillabus_serbest_is",
    version="syllabus-v1",
    allowed_fields=("id", "uniqid", "name"),
)

__all__ = [
    "JOURNAL_SYLLABUS_FIELDS",
    "SILLABUS_FIELDS",
    "SILLABUS_SELF_WORK_FIELDS",
]
