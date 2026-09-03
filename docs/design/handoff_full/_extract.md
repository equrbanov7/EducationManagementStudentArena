### 00 Dizayn konstantlari.dc.html
size 62KB
props: preview 1240x1100
state: 
views: 
arrays: PRIMARY, NEUTRAL, SEMANTIC, EXTRA, ALIASES, MAPPING, STATUSES, TYPE, RADII, SHADOWS, HEIGHTS, SPACE, SCREENS, NAV, STEPS
h1: Dizayn konstantları
labels: " + s[0] + ", ÜMUMİ YÜK, TƏSDİQLƏNİB, GÖZLƏYİR, NORMADAN ARTIQ, Neytral, Məlumat, Təsdiq, Gözləyir, Rədd

### 01 Tedris shobesi - Universitet strukturu.dc.html
size 64KB
props: preview 1400x1150 · role:Tədris Şöbəsi müdiri|Tədris Şöbəsi əməkdaşı|Rektorat|Dekanlıq
state: loading, w, open, root, sel, q, qRaw, typeF, edit, heads, names, toast
views: 
arrays: UNITS, PEOPLE
h1: Universitetin strukturu
labels: Rektorat, Fakültə, Dekanlıq — fakültənin inzibati aparatı, Kafedra, İxtisas — akademik proqram, Tələbə qrupu, Mərkəz — fakültədən kənar struktur, Tədris laboratoriyası, İxtisas, Müəllim heyəti, Rəhbəri olmayan bölmə, Mərkəz / laboratoriya, Qrup sayı, Tələbə sayı

### 02 Tedris shobesi - Kafedra profili.dc.html
size 122KB
props: preview 1320x1180 · role:Tədris Şöbəsi müdiri|Tədris Şöbəsi əməkdaşı|Dekanlıq|Kafedra müdiri · normSet:Nazirlik normaları|Universitet normaları · dataState:Avtomatik|Skeleton|Xəta
state: loading, err, w, sel, tab, stage, railQ, railOpen, staffQ, staffQRaw, typeF, onlyOff, sort, sortOpen, sem, ownF, tsel, hourly, edit, openMeet, toast
views: 
arrays: FACS, RANK_ORDER, SORTS
h1: Kafedralar
labels: Yük riski, Yüklü, Normada, Boş tutum, Ştat: , Əvəzçilik: , Saathesabı: , Ştat vahidi cəmi: , normada, yüklü, risk, boş tutum, Qərbi Kaspi Universiteti, Müəllim heyəti

### 03 Tedris shobesi - Ixtisaslar.dc.html
size 129KB
props: role:Tədris Şöbəsi müdiri|Tədris Şöbəsi əməkdaşı|Dekanlıq|Kafedra müdiri · listState:Avtomatik|Skeleton|Boş|Xəta
state: loading, err, w, node, type, openFac, eng, eco, hum, railOpen, railQ, stage, q, qRaw, deg, form, onlyNoPlan, sort, sortOpen, sortQ, sel, tab, semF, blokF, deptF, deptOpen, deptQ, course, edit, arch, archReason, toast
views: 
arrays: FACS, PROGRAMS, SORTS
h1: İxtisaslar
labels: ⚠ Plan yoxdur, Qərbi Kaspi Universiteti, İxtisas kodu, Tam ad, Təhsil pilləsi, Təhsil forması, Tabe olduğu kafedra, Fakültə, Məzuniyyət üçün ECTS, Qayıb limiti, Vəziyyət, Qrup, Tələbə, Cari semestrdə açılmış fənn

### 04 Tedris shobesi - Fenn kataloqu.dc.html
size 98KB
props: preview 1360x1180 · role:Tədris Şöbəsi müdiri|Tədris Şöbəsi əməkdaşı|Dekanlıq|Kafedra müdiri · dataState:Avtomatik|Skeleton|Xəta
state: loading, err, w, sel, tab, railOpen, q, qRaw, dept, deptOpen, blok, sort, sortOpen, only, merge, edit, toast
views: 
arrays: DEPTS, BLOKS, CAT, SORTS, TEACHERS
h1: Fənn kataloqu
labels: Kredit, Planlarda istifadə, Prerekvizit, Sillabus, Reyestr kodu, Sahibi kafedra, Tədris dili, Qiymətləndirmə forması, Fənn blokları, Semestrlər, Vəziyyət, Mühazirə, Seminar, Laboratoriya

### 05 Tedris plani redaktoru.dc.html
size 97KB
props: preview 1240x1180 · planStatus:Qaralama|Kafedra baxışı|Fakültə şurası|Tədris şöbəsi|Təsdiqlənib · semTarget:30 · showAudit:true
state: tab, kurs, fSem, fBlok, fKaf, q, qApplied, openDd, ddQuery, tableState, focus, sortKey, sortDir, modal, target, dSifr, dName, dKredit, dSerbest, dMuh, dSem, dLab, dSemestr, dPre, dKaf, catQ, blokCode, blokName, cloneSrc, sendNote
views: 
arrays: BLOKS, ROWS, LATER, KATALOQ, GRAFIK, KURS
h1: Tədris planı redaktoru
labels: Plan sətri, Cəmi kredit (təkrarsız fənn), Ümumi saat, Auditoriya saatı, Açıq xəbərdarlıq, Cəmi kredit

### 06 Tedris shobesi - Qruplar.dc.html
size 96KB
props: preview 1360x1180 · role:Tədris Şöbəsi müdiri|Tədris Şöbəsi əməkdaşı|Dekanlıq|Kafedra müdiri|Kurator · dataState:Avtomatik|Skeleton|Xəta
state: loading, err, w, sel, tab, railOpen, q, qRaw, prog, progOpen, kurs, lang, stQ, stQRaw, stF, ssel, move, create, toast
views: 
arrays: GROUPS, AD_Q, AD_O, SOY, DAYS, SLOTS, KINDS, MOVE_KINDS
h1: Qruplar
labels: Bazar ertəsi, Çərşənbə axşamı, Çərşənbə, Cümə axşamı, Cümə, Qərbi Kaspi Universiteti, Tələbə sayı, Qrupun orta balı, Orta GPA, Dərsə gəlmə, Akademik borcu olanlar, İxtisas, Kafedra / fakültə, Təhsil pilləsi və forma

### 07 Tedris shobesi - Semestr acilishi.dc.html
size 76KB
props: preview 1400x1150 · role:Tədris Şöbəsi müdiri|Tədris Şöbəsi əməkdaşı|Dekanlıq|Kafedra müdiri
state: loading, w, view, q, qRaw, dept, deptOpen, stat, assigned, cancelled, journals, sent, selected, assign, gen, lock, locked, toast
views: 
arrays: GROUPS, TEACHERS
h1: Semestr açılışı
labels: Plandan açılış yaradıldı, Kafedraya göndərildi, Müəllim təyin olundu, Jurnal açıldı, Semestr kilidləndi, Açılış sətri, Müəllim təyin olunub, Müəllim gözləyir, Jurnalı açılıb, Semestr saatı, Bütün açılışlara müəllim təyin olunub, Açılışlar təsdiqlənmiş plandan gəlir, Elektron jurnallar açılıb

### 08 Telebe qebulu - ATIS ve qrup teyinati.dc.html
size 71KB
props: preview 1440x1150 · role:Tələbə Mərkəzi|Tədris Şöbəsi müdiri|Dekanlıq|Proqram koordinatoru
state: tab, q, qRaw, stage, fixed, impF, prog, progOpen, picked, assign, groups, newG, toast
views: 
arrays: AD_Q, AD_O, SOY
h1: Tələbə qəbulu
labels: Uyğundur, FİN təkrarlanır — eyni şəxs iki sətirdə, İxtisas kodu universitetdə tapılmadı, Attestatın surəti yüklənməyib, ATİS siyahısı yükləndi, Tədris şöbəsi yoxladı, Fakültələrə paylandı, Qruplara təyin edildi, Cəmi sətir, Yoxlamadan keçdi, Bloklayan xəta, Xəbərdarlıq

### 09 Telebe reyestri ve hereketi.dc.html
size 60KB
props: preview 1440x1150 · role:Tələbə Mərkəzi|Dekanlıq|Proqram koordinatoru
state: tab, q, qRaw, prog, progOpen, stat, form, moveF, card, move, toast, move, card, progOpen
views: 
arrays: AD_Q, AD_O, SOY
h1: Tələbə reyestri
labels: Qrupdan qrupa köçürmə, İxtisasdan ixtisasa köçürmə, Əyanidən qiyabiyə (və ya tərsi), Akademik məzuniyyət, Bərpa, Xaric etmə, Cəmi tələbə, Əyani / qiyabi, Riskdə olan, Xüsusi statuslu, Açıq hərəkət əmri, Statusu, Kurs, GPA (4 ballıq)

### 10 Telebe kabineti.dc.html
size 83KB
props: preview 1360x1100 · transcriptPolicy:request|download
state: 
views: syl, grade, att, req, ss
arrays: COURSES, DAYS, SLOTS, SCHED, DOCS, TICKETS, TERMS, NOTIF
h1: 
labels: Bazar ertəsi, Çərşənbə axşamı, Çərşənbə, Cümə axşamı, Cümə, Transkript sorğusu, Arayış sorğusu, Qiymətə etiraz, Şikayət, Tələbə hərəkəti, Təhsil haqqı, Texniki problem, Toplanmış bal, Gözlənilən GPA

### 11 Muracietler paneli.dc.html
size 62KB
props: preview 1400x1150 · role:Tələbə|Müəllim|Tələbə Mərkəzi|Dekanlıq|Kafedra müdiri|Tədris Şöbəsi
state: tab, sel, q, qRaw, stat, kind, kindOpen, replies, states, newT, fwd, toast, fwd, newT, kindOpen
views: 
arrays: TICKETS
h1: Müraciətlər
labels: Transkript sorğusu, Arayış sorğusu, Qiymətə etiraz, Şikayət, Tələbə hərəkəti, Təhsil haqqı, Təqdimat, Texniki problem, Açıq müraciətim, Məlumat gözlənilir, Cavablanıb, Orta cavab müddəti, Mənə gələn açıq, Yeni — baxılmayıb

### 12 Ders yuku - Tedris shobesi.dc.html
size 112KB
props: preview 1440x960
state: 
views: 
arrays: CAT
h1: {{ pageTitle }}
labels: 

### 13 Koordinator - Yuk vizasi.dc.html
size 42KB
props: preview 1440x960
state: view, reviewed, remarks, modal, target, remarkText, fYear, fSem, fGroup, fState, applied, year, sem, group, state
views: queue
arrays: ALL
h1: {{ pageTitle }}
labels: 

### 14 Kafedra mudiri - Yuk bolgusu.dc.html
size 64KB
props: preview 1500x980
state: 
views: dist, teachers, reports
arrays: ROWS, ACTS, TEACHERS
h1: {{ pageTitle }}
labels: Mühazirə, Seminar, Laboratoriya

### 15 Dekanliq - Yuk tesdiqi.dc.html
size 60KB
props: preview 1440x960
state: view, tab, reviewed, remarks, selected, modal, target, fYear, fSem, fSpec, fGroup, applied, year, sem, spec, group, remarkText, returnText
views: queue, summary, history
arrays: ALL
h1: {{ pageTitle }}
labels: 

### 16 Muellim - Shexsi yuk.dc.html
size 64KB
props: preview 1440x1024
state: 
views: load, plan, paid, notes
arrays: ROWS, PLAN, PAID, NOTES, REASONS
h1: {{ pageTitle }}
labels: Saat sayı düz deyil, Qrup/tələbə sayı səhvdir, Fənn ixtisasım deyil, Norma həddindən artıqdır, Mühazirə, Seminar, Laboratoriya, Digər iş

### 17 Rektor - Umumi baxish.dc.html
size 52KB
props: preview 1440x1024
state: 
views: overview, fac, dep, rep
arrays: DEPS, FACS, REPORTS
h1: {{ pageTitle }}
labels: Normadan az (< 90%), Normada (90–105%), Norma üstü (105–125%), Kritik yüklü (> 125%)

### 18 Muellim - Sillabuslar.dc.html
size 50KB
props: preview 1440x1120
state: 
views: table, minor, major, card
arrays: ORDER, DATA, BLOCKS, HIST
h1: Sillabuslar
labels: Qaralama, Təqdim edilib, Baxışdadır, Düzəliş tələb olunur, Təsdiqlənib, Rədd edilib, Arxivlənib, Cari il üzrə fənn, Təsdiq gözləyir, Sillabussuz fənn, Akademik il, Semestr, Kafedra, PDF yüklə

### 19 Muellim - Sillabus redaktoru.dc.html
size 93KB
props: preview 1480x1120 · viewState:normal|readonly|loading|permission · saveState:saved|saving|failed|offline|conflict|stale
state: 
views: 
arrays: SEC, RULE, METHODS, HIST
h1: Alqoritmlər və verilənlər strukturu
labels: Ümumi məlumat, Təsvir və məqsəd, Təlim nəticələri, Həftəlik mövzular, Tədris metodları, Qiymətləndirmə, Sərbəst iş, Ədəbiyyat, Preview, Təsdiqə göndərmə, Fənnin adı və kodu, Fakültə, Kafedra, Təhsil proqramı

### 20 Kafedra mudiri - Sillabus tesdiqi.dc.html
size 67KB
props: preview 1480x1080 · role:kafedra|dekan|noscope
state: 
views: 
arrays: SECS, DIFFS, AUDIT
h1: Sillabus təsdiqi
labels: Təqdim edilib, Baxışdadır, Düzəlişdə, Növbədə gözləyən, 10 gündən çox gözləyir, Çatışmayan bölməsi var, Orta gözləmə, Status, Sıralama, Təsdiq faizi, Təsdiqlənmiş, Baxışda, Gecikib, 2026/2027 payız

### 21 Muellim - Kecilmish dersler.dc.html
size 37KB
props: preview 1420x1150 · role:Müəllim|Kafedra müdiri|Dekanlıq|Tədris Şöbəsi müdiri
state: range, from, to, q, qRaw, course, courseOpen, kind, onlyFlagged, teacher, toast
views: 
arrays: TEACHERS, COURSES, GROUPS, SLOTS, WD, MON, RANGES
h1: Keçilmiş dərslər
labels: Vaxtında yazılıb, Gec yazılıb, Jurnal boşdur, Keçilmiş dərs, Auditoriya saatı, Orta iştirak, Jurnalı boş dərs, Gec yazılan qeyd