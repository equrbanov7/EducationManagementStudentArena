# examphoto — imtahan ekranında tələbənin öz şəkli (2026-10-13, gecə)

Sahib: «test imtahanı zamanı solda ya da sağda nəsə tələbənin öz şəklinin görünməsi. onu da əlavə et
UX/UI skill qoşaraq. ordakı performans və təhlükəsizlik problemlərinə bax.»

İstifadə olunan skill-lər: `design:design-critique`, `design:accessibility-review` (WCAG 2.1 AA).

## 1. Kimlik kartı (YENİ)

| Ekran | Nə görünür |
|---|---|
| ≥1280 px | Sağda ayrıca 208 px sütun; kart `position: fixed` (top/left `auto` → sual kartı ilə bir xəttdə, sürüşmədə yerində qalır). Şəkil 160×200 (4:5), ad, Qrup, Tələbə №, İstifadəçi adı. Başlıq çipinin şəkli gizlənir (təkrar olmasın). |
| 1025–1279 px | Kart sol sütunda, sual paletinin üstündə (adi axın). |
| ≤1024 px | Kart gizli, başlıqdakı yığcam çip (36–40 px şəkil) qalır — sual sahəsi daralmır. |
| Kodlaşdırma imtahanı | Kart sol sütunun (`.coding-question-sidebar`) başında, ≥1025 px. |

* Fayllar: `apps/exams/templates/exams/student/partials/_proctor_id_card.html`,
  `apps/exams/static/exams/css/take_exam/id_card.css`, `apps/exams/static/exams/js/take_exam/identity_photo.js`.
* Şəkil yoxdursa / yüklənmirsə: baş hərflər + «Şəkil yüklənməyib — nəzarətçiyə şəxsiyyət vəsiqənizi göstərin»
  (inline `onerror` yox — sənəd səviyyəsində `error` dinləyicisi, CSP-yə uyğun).
* Mənbə: `UserProfile.avatar` — sistemdə ayrıca «rəsmi kimlik şəkli» sahəsi YOXDUR (yalnız avatar).
* `sticky` niyə yox: `main.css`-də html + body `overflow-x: hidden` body-ni scroll konteynerinə çevirir,
  səhifədəki bütün sticky-lər ölüdür. Kart `fixed`; `.exam-shell` giriş animasiyasının `fill-mode: both`
  qalıcı `transform`-u fixed-i bağlayırdı → bu səhifədə `backwards` (görünüş eyni).

### Əlçatanlıq (WCAG AA) — ölçülmüş kontrast
kicker 7.58 · etiket (neutral-100 fonda) 6.92 · dəyər 13.35 · ad 14.63 · baş hərflər 5.49 · şəkil halqası 4.76 (≥3).
Kart `section[aria-label]` + `dl/dt/dd`; şəklin `alt=""` (ad dərhal altında mətn kimi). Kart interaktiv deyil
(fokus sırası dəyişmir). 375 px-də üfüqi sürüşmə yoxdur.

### Brauzerdə yoxlanılıb (sandbox DB, 100 suallıq test)
1920×1000, 1440×900, 1366×640 (sürüşmədə y=119 sabit), 1100×800, 375×812; şəkil 404 → baş hərflərə keçid;
konsolda CSP xətası yoxdur; 3 səhifə yükləməsində şəkil serverə 1 dəfə gəldi (private keş).

## 2. Performans

| Mövzu | Status |
|---|---|
| Kimlik sorğuları | **Düzəldi**: `{% proctor_identity %}` valideyn şablonda bir dəfə (2 sorğu); çip + kart eyni `ident`. Test: profil sorğusu 1. |
| Gizli slayd şəkilləri | **Düzəldi**: sual/variant şəkilləri 2-ci slayddan `loading="lazy" decoding="async"` — 100 şəkilli imtahan ilk açılışda 100 sorğu etmirdi. |
| Şəkil marşrutu | **Düzəldi**: `If-Modified-Since` → 304 (icazə yoxlamasından SONRA), `Vary: Cookie`. |
| Autosave | Artıq OK: dəyişən suallar (`changed_questions[]`), test 1 s / yazılı 3 s debounce, in-flight qoruyucu, backoff, OCC revision. |
| JS/CSS | Skriptlər body sonunda; yeni: 1 CSS (≈5 KB) + 1 JS (≈1.5 KB). |

## 3. Təhlükəsizlik

| Mövzu | Status |
|---|---|
| Şəkil IDOR | Artıq OK (`can_view_student_photo`): tələbə yalnız özünü; test əlavə edildi (sinif yoldaşı → 404, 304 sızmır). |
| SVG / qeyri-raster | **Düzəldi**: yalnız jpeg/png/webp/gif; `Content-Security-Policy: default-src 'none'; sandbox`. |
| Cavab endpoint-ləri | Artıq OK: POST/question-seen/status/heartbeat hamısı `user=request.user` + aktiv cəhd yoxlaması. |
| Cavab açarı | Artıq OK: variant dəyəri token (EX28-01), vaxtlı sual strict delivery; test: HTML-də `is_correct`/xam id yox. |
| Taymer | Artıq OK: `deadline_at` + `expire_if_write_window_closed` serverdə. |
| CSP | Inline yoxdur (`check_inline_assets.py` ✅). |

Qeyd (sahib üçün): ümumi `accounts:profile_avatar` istənilən daxil olmuş istifadəçiyə açıqdır (profil
avatarları interfeysdə başqalarına göstərilir) — bu, imtahan marşrutundan ayrı, köhnə dizayn qərarıdır.

## Testlər
`apps/exams/tests/test_examphoto_2026_10_13.py` (13 test) + `test_proc_2026_10_01_monitor.py`.
i18n: `scripts/i18n_fill_examphoto_2026_10_13.py` (4 sətir × az/en/ru/tr). Miqrasiya yoxdur.
