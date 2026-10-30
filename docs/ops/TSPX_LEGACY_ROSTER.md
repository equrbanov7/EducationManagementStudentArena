# 135 TSPX mənbə bölgüsünün bərpası

`repair_tspx_legacy_roster` yalnız baxılmış MyEdu mənbəsinin 49 dəqiq
`student`/`student_record` uyğunluğunu qəbul edir: 23 nəfər birinci alt qrupa,
26 nəfər ikinci alt qrupa keçir; mənbədə əsas qrupda olan bir nəfər saxlanılır.
İngilis dili səviyyə və qonaq siyahıları bu əmrin əhatəsinə daxil deyil.

Şifrəli mənbə release tagı `tspx-roster-…`, asseti `tspx-roster.json.enc`-dir.
Workflow `batch` sahəsində baxılmış plaintext faylın SHA256-sını,
`row_subject` sahəsində təzə dry-run baseline SHA256-sını qəbul edir.
Standart backup və `APPLY` təsdiqi qüvvədədir. Terminal əmri də eyni
`--manifest`, `--manifest-sha256`, `--expected-baseline`, `--apply` arqumentlərindən istifadə edir.

Əmr aktiv superadmin, təşkilat, cari dövr, qeydiyyatlı parent/child münasibəti,
eyni proqram/sektor/form, aktiv hesab və üzvlük, dəqiq şəxsi məlumatlar,
dəyişməz mənbə mappingi və canlı SAR vəziyyətini yoxlayır. Əlavə tələbə,
başqa ailəyə keçid və ya mənbədən fərqli hesab uyğunluğu bütün paketi dayandırır.

Dry-run kanonik qrup köçürmələrini bir tranzaksiyada işlədib geri qaytarır.
Apply əvvəlki jurnal, qiymət, dərs, sillabus, paylaşım və əlaqə fingerprintlərini
qoruyur; əvvəlki əsas qrup qeydiyyatı silinmir, successor ilə tarixçədə qalır.
Tam əvvəl/sonra vəziyyəti audit receiptindədir. Eyni paket təkrar işləndikdə dəyişiklik yaratmır.

`--undo` yalnız dəyişməyən receipt vəziyyətində və əvvəlcədən mövcud aktiv
alt qrup qeydiyyatı olmadıqda birbaşa kanonik tərs əməli qəbul edir.
135 TSPX-in mövcud qiymətli alt qrup jurnalları səbəbindən prod undo
`tspx_undo_preexisting_child_roster_requires_reviewed_compensation` ilə dayanmalıdır.
Bu hal ayrıca baxılmış kompensasiya tələb edir; əvvəlki alt qrup dərslərini əsas
qrupa daşıyan ümumi reverse əməli təhlükəsiz geri qaytarma sayılmır.
