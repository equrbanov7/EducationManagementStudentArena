# 135 Sİ üzrə dəqiq mənbə bölgüsü

`repair_si135_legacy_roster` yalnız baxılmış ayrıca mənbə SHA256-sını qəbul edir:
`3369a1b8c4504ae390e331e86f292d1374f513868c3750a581290d797057913a`.
Köhnə `students.group_id` üzrə 932 → 23, 933 → 22 tələbədir; əsas 797 qrupunda
bir tələbə qalır. 46 hesabın hər biri dəqiq dəyişməz student/SAR mappingi ilə
yoxlanıb. Köhnə HTML entity-ləri yalnız şəxsiyyət mətninin standart açılışıdır;
hesab seçimi adla edilmir, xam mənbə ayrıca sübutda saxlanır.

Əmr TSPX ilə eyni kanonik tranzaksiya, canlı mənbə mappingi, hesab/üzvlük,
qeydiyyatlı parent/child, proqram, sektor, təhsil forması və akademik məzmun
qorumasından istifadə edir. İki ailə sabit müqavilələrlə məhduddur; TSPX-in
49 nəfəri və əvvəlki `c6eb7979…` fayl SHA-sı dəyişməyib. Başqa qrup və ya
ailənin manifest/receipt-i qəbul edilmir.

Workflow `repair_si135_legacy_roster`, `si135-roster-…` tagı və
`si135-roster.json.enc` assetini gözləyir. `batch` plaintext SHA256,
`row_subject` isə təzə dry-run baseline SHA256-sıdır. Backup və APPLY təsdiqi
qüvvədədir. Dry-run defoltdur, bütün paket atomikdir; təkrar apply no-op olur.
Sİ və TSPX audit receipt-lərinin resurs və batch namespace-ləri ayrıdır.

Əvvəlcədən qiymətli alt qrup qeydiyyatları olduqda ümumi reverse onları əsas
qrupa daşıya bilər. Buna görə dəyişməyən post-state yoxlamasına əlavə olaraq
bu undo açıq şəkildə bloklanır; ayrıca baxılmış kompensasiya tələb olunur.
Heç bir ingilis dili səviyyə/qonaq siyahısı bu əmrlə SAR qrupuna çevrilmir.
