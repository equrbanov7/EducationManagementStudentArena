"""Heyət yerləşdirmə auditi — «kim hansı kafedradadır» (sahib 2026-10-25).

Mənbələr: «Forma 7» (kafedra → müəllim, ştat), struktur/heyət siyahısı (bölmə → şəxs, vəzifə) və kafedraların
dərs yükü faylları. Tutuşdurma Forma 7 qaydasıdır (``teacher_roster.matching``) — yeni ad qaydası icad edilmir.

* ``sources`` — faylları oxuyur (DB-siz) → :class:`sources.Evidence` siyahısı;
* ``plan`` — hesablarla tutuşdurur, ştat kafedrası / üzvlüklər / yük / jurnal faktlarını yığır, düzəliş planı qurur;
* ``apply`` — planı mövcud servislərlə yazır (``workload.join_chair_as_teacher``, üzvlüyün əsaslığı, deaktivasiya),
  manifest audit jurnalındadır, ``undo`` onu geri qaytarır;
* ``report`` — adlı Markdown/CSV hesabatı (şəxsi məlumat — yalnız 0600 lokal fayl).
"""
