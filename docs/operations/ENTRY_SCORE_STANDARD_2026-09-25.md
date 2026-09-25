# 2026/2027 giriş balı standartı

Midterm rejimində giriş balı eyni kanonik hesabdan gəlir:

| Hissə | Qayda | Tavan |
|---|---|---|
| Davamiyyət | Buraxılışın eyni saatı, tələbənin proqram həddi və idmançı istisnası | 10 |
| Aktivlik | Balı olan seminar/laboratoriya dərslərinin ədədi ortası, 2 onluq yarım-yuxarı | 10 |
| Midterm | Komponent balı; balı olan köhnə kollokvium qalığı varsa cəmə daxildir | 20 |
| Sərbəst iş | Jurnalın kanonik sərbəst iş balı; SELF_WORK komponentli açılışlar | 10 |

Cəm sxemin `entry_score_max` həddinə kəsilir və tam ədədə yarım-yuxarı yuvarlaqlaşdırılır.
Buraxılmayan tələbənin davamiyyət hissəsi 0-dır. Təkrar imtahan giriş balını artırmır.
İdmançı istisnası buraxılış məhdudiyyətini aradan qaldırır, qayıbın bala təsirini yox.
Balı olmayan dərslər aktivlik ortasına daxil deyil; dərs balı yoxdursa aktivlik 0-dır.
Davamiyyət saatı məlum deyilsə mövcud kanonik qaydanın 10 balı saxlanılır.

Rejim `interim_assessment` tərəfindən dövrə və təşkilat ayarına görə seçilir.
Kollokvium rejimli əvvəlki illərin düsturu və ekran sütunları saxlanılır.
Yeni migration və ya saxlanmış balların kütləvi yenilənməsi tələb olunmur.

## Yoxlama sübutu

`entry_standard_baseline.json`: keçiddən əvvəlki koddan 2026-09-25 tarixində alınmış
fikstura nəticələri və PostgreSQL sorğu sayları. `test_entry_standard_parity.py`
köhnə dövrlərin bütün güzgülərdə bu nəticələrə bərabərliyini yoxlayır.

Yeni fikstura nümunələri:

- 9.33 davamiyyət + 8.50 aktivlik + 17 Midterm + 9 sərbəst iş → **44**.
- Qayıb həddi keçilib: 0 + 10 + 20 + 10 → **40**, təkrar imtahan balından asılı deyil.
- İdmançı: 7.33 + 6.50 + min(18+3, 20) + 2.50 → **36**.
- Dərssiz, giriş tavanı 35: 10 + 0 + 20 + 10 → **35**.

Tək/toplu jurnal, yekun, transkript, tələbə kabineti, dashboard, cədvəl modalı,
analitika və akademik xülasə eyni rəqəmlərlə yoxlanılır. Sorğu büdcəsi əvvəlki
snapshot-dan artmamalıdır. Qrid və Yekun artıq oxuduğu dərs işarələrini paylaşır;
analitika iki komponent cəmini bir SQL aqreqasiyasında oxuyur. Qrupun ümumi qayıb
həddi yalnız həqiqətən istənəndə yüklənir; sətirlər tələbənin öz həddindən istifadə edir.

Müəllimin Yekun cədvəli və tələbənin Fənlərim/Nəticələrim/jurnal detalları dörd
hissəni göstərir. Keçmiş illərdə köhnə görünüş qalır. Yeni mətnlər az/en/ru/tr
kataloqlarına `scripts/i18n_add_entrystd_2026_09_25.py` ilə əlavə edilir.

## İcra edilmiş yoxlamalar (2026-09-25)

- PostgreSQL: bütün registrar testləri, akademik nəticə/xülasə/dashboard və URL
  icazə yoxlamaları — **2 089 keçdi** (migrasiya və paralel yazı testləri daxil).
- PostgreSQL: subject_folder, timetable, surveys və yeni müəllim/tələbə ekranları —
  **309 keçdi** (RLS və paralel yazı testləri daxil). Cəmi **2 398 test**, xəta yoxdur.
- Black, isort, flake8, modul ölçüsü, modul sərhədi, public API, kontekst və
  worker-transaction qapıları, i18n kataloqları — keçdi.
- `manage.py check` problemsizdir; `makemigrations --check --dry-run` dəyişiklik tapmadı.
- Lokal brauzerdə əvvəlki ilin Yekun cədvəli və yeni qovluq/yoxlama səhifələri açılır.
  Server yeni kodla yenidən başladılıb. Kod üçün production deploy bu yoxlamanın hissəsi deyil.
