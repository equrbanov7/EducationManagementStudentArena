# QA / performans / təhlükəsizlik dalğası — 2026-10-17

Sahib: «bir neçə agenti işə sal, onlar sistemdə QA kimi işləsin … bir neçəsi performans, bir neçəsi security üçün».
Altı agent yalnız lokal QA klonunda işlədi (prod-a toxunulmadı, qa.* parolları dəyişmədi), sonra dörd düzəliş agenti
və hər paket üçün müstəqil yoxlayıcı agent. Ayrı-ayrı hesabatlar bu qovluqdadır:
`QA1_teacher_student.md`, `QA2_admin_roles.md`, `PERF1_backend.md`, `PERF2_frontend.md`, `SEC1_code_review.md`,
`SEC2_live_tests.md`.

Ümumi nəticə: **kritik və yüksək təhlükəli tapıntı yoxdur**. QA: 0 P0/P1, 12 P2, 23 P3. Security: 3 orta, 6 aşağı.
Yoxlayıcılar düzəlişlərdə daha 3 ciddi boşluq tapdı — hamısı commit-dən əvvəl bağlandı.

## 1. Monitorinq logları (sahibin şikayəti)

| Tapıntı | Düzəliş |
|---|---|
| 2026-10-11-dən prod-da log yazılmırdı. Promtail Docker-ə köhnə API 1.24 ilə müraciət edirdi, Docker 29 isə min 1.40 tələb edir. Server restartında promtail proxy-dən əvvəl qalxıb və bu versiyada ilişib qalıb. Lokalda təkrarlandı. | Promtail başlamazdan əvvəl proxy-nin cavab verməsini gözləyir. Prod-da yoxlanıldı: 200 min+ sətir Loki-yə çatıb, «Loglar» bölməsi son saniyələri göstərir. |

## 2. Təhlükəsizlik

| Tapıntı | Mənbə | Düzəliş |
|---|---|---|
| «Məlumatlarınızı tamamlayın»da başqasının FİN-ini sonsuz sınamaq olurdu (FİN «başqa hesabda var» deyirdi) | SEC-1 F1, SEC-2 | FİN yalnız digər xanalar düzgün olanda yoxlanılır, hesab başına saatda 8 cəhd |
| Özü yazdığı FİN rəsmi idxalı bloklaya bilərdi (başqasının FİN-ini yazan əsl sahibin hesabını yaradılmaz edirdi) | SEC-1 F2 | FİN «təsdiqlənməmiş» kimi saxlanılır; ATİS / kadr idxalı ad-soyad uyğun olsa təsdiqləyir, fərqli olsa FİN-i səhv hesabdan götürüb əsl sahibinə verir |
| Yükü olan müəllimin bloku avtomatik açılanda səbəbə baxılmırdı (təhlükəsizlik / intizam bloku da açılırdı) | SEC-1 F3 | Yalnız «Forma 7» idxalının bloku açılır; əl ilə bloklar ayrıca yoxlamaya düşür |
| prod əməliyyat workflow-unda input yoxlaması yeni sətirli dəyəri buraxırdı; logda müəllim adları çap olunurdu | SEC-1 F7 | Bütöv dəyər yoxlanılır, logda yalnız parametr adları |
| Tələbənin şəxsi e-poçtu ictimai profildə əhatədən kənar dekana və HR-a görünürdü | QA-2 F-04 | Yalnız tələbənin özünə, superadmin-ə və onu əhatəsində olana |
| HR (tələbə kataloqu ona bağlıdır) tələbə məlumatına bir çox yoldan çatırdı: qrup çekmecəsi + DOCX, RİM mərkəzi, «Struktur üzvləri» + kart + CSV, «Rol təyin et», «Rolları idarə et», tələbə təşkilat idarəsi, başlıq axtarışı, starosta adı və idarəsi | QA-2 F-03 + 2 yoxlama | Vahid qayda (`apps/organizations/student_privacy.py`): tələbə səlahiyyəti olmayan rol tələbəni heç yerdə görmür; cavab «tapılmadı» ilə eynidir |
| **Yoxlayıcı tapdı:** «Rol təyin et»də HR tələbənin istifadəçi ID-si ilə onun rolunu dəyişə bilirdi | review | Bağlandı (gizli tələbə = tapılmadı) |
| «Semestr açılışı» və «Tədris planı»nı dekan / kafedra müdiri bütün fakültələr üzrə görürdü (yazı məhdud idi) | QA-2 F-01/F-02 | Oxu da əhatəyə görə; «Yeni plan» yalnız redaktə əhatəsində |
| İmtahan qrupu üçün istifadəçi axtarışı istənilən müəllimə bütün istifadəçi siyahısını verirdi | SEC-2 | 2+ hərf, səhifə ≤ 20, ümumi ≤ 200 |
| **Yoxlayıcı tapdı:** cədvəl redaktorunda kafedra müdiri başqa kafedranın fənni üçün 403-dən əvvəl bazaya yazı edə bilirdi | review | Səlahiyyət yazıdan ƏVVƏL yoxlanılır |
| Başqa fakültənin dərsini redaktə cəhdi 500 verirdi | review | 403; fənn dəyişikliyi aydın 409 |

## 3. Funksional (QA-1 / QA-2)

| Tapıntı | Düzəliş |
|---|---|
| Profili natamam tələbə `/exams/` imtahan siyahısına çata bilmirdi | Tələbənin imtahan siyahısı profil qapısından keçir |
| «Qrupu dəyiş» səhv edilsə geri qaytarılmırdı (409) | Son köçürmənin dəqiq geri qaytarılması (A→B→A); heç nə silinmir |
| Kafedra müdiri / tyutor «Cədvəl idarəetməsi»ni görürdü, amma redaktor boş idi | Kafedra öz fənləri olan qrupları, tyutor öz qruplarını görür |
| Başlıqda bal 10, detallarda 9,55 | «Cəm: 9,55 → 10» |
| «Mənim dərs yüküm», «Statistika», «Fənlərim» legendi başqa dildə azərbaycanca qalırdı | Tərcümə + dil üzrə göstərmə |
| Dərs modalında otaq siyahısında axtarış yox idi, eyni korpusda iki «102» | Axtarış + fərqləndirmə |
| Azad edilən fənn tələbənin cədvəlində görünürdü | Gizlənir (qrup cədvəlinə toxunulmur) |
| Jurnal tarixçəsində «iə/qb» | «i/e», «q/b» |
| Mobil kabinet menyusu hər yükləmədə açılıb-yanırdı | Düzəldildi |

## 4. Performans (PERF-1 / PERF-2)

| Səhifə | Əvvəl → sonra |
|---|---|
| İmtahan monitoru (30 s-də bir yenilənir) | aktiv bilet başına sorğu → sabit (~71 → ~16) |
| «Fənlərim» | 51 → 44 sorğu |
| Jurnal «Yekun» | 77 → 61 (557 tələbəli jurnalda 85 → 69) |
| «Cədvəlim» | 30 → 20 (fənn sayından asılı deyil) |
| Cədvəl redaktoru «Uyğun vaxtlar» | 361 → ~148 ms |
| Staff kabinet bölməsi | 22 → 19 |
| RİM axtarışı | sətir başına sorğu → bir sorğu |
| Bütün staff səhifələri | Google Fonts render-bloklaması silindi |

## 5. Sahibin bu gün əlavə istədikləri

- Telefon xanasında operator seçimi (050, 051, 055, 099, 070, 077, 010, 060, «Xarici nömrə»), placeholder «məs: 123 45 67».
- Seçicinin yanında aşağı ox (giriş səhifələrində görünmürdü).
- Login və profil səhifələrində lazımsız yuxarı-aşağı scroll silindi.
- «Hələlik keç»: bu girişdə davam, məlumat doldurulana qədər hər girişdə yenə gəlir; RİM söndürə bilər.
- Qəyyumlar Şurası üzvü: bütün oxu səlahiyyətləri (yazma yoxdur).

## 6. Qalan / sahibin qərarı

- HR «Rol təyin et»də hələ üzv olmayan müraciətçilərin e-poçtunu görür; tələbə qoşulma müraciətləri bölməsi HR-dadır.
- PERF-2: avatarlar yükləmədə kiçildilmir; staff bölmələrində imtahan modal paketi (79 KB gzip) hər yerdə yüklənir;
  `bootstrap_select.js` menyuları dərhal qurur (böyük jurnalda DOM şişir); build/minify addımı yoxdur.
- PERF-1 aşağı prioritetli 8 tapıntı (F-08…F-17), canlı imtahan sorğu keşi.
- Dev klonda Microsoft Clarity işləyir (klonda real adlar var) — lokalda söndürmək tövsiyə olunur.
