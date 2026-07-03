# PR3 audit — `!important` inventarı (FAZA 3B)

**Tarix:** 2026-07-04
**Status:** Audit tamamlandı, kod dəyişikliyi TƏXİRƏ salındı (visual verification tələb edir)

## Xülasə

CSS `!important` istifadələri: **195 halda, 55 faylda**. `docs/CODEX_PROMPT_FRONTEND_REFACTOR.md` PR3 spec-i açıq deyir: **"Do not bulk-strip. Visually verify."**

Bu, proctored exam platformasıdır — səhv çıxarılan `!important` layout regressiyasına səbəb ola bilər. Ona görə PR3 dizayn-review PR-larına bölünüb, hər biri müvafiq səhifədə vizual smoke ilə edilməlidir.

## Top offender fayllar (say)

| # | Fayl | Say |
|---|------|----:|
| 1 | `apps/courses/static/courses/css/course_dashboard_redesign.css` | 29 |
| 2 | `apps/exams/static/exams/css/teacher_view_attempt.css` | 13 |
| 3 | `apps/labs/static/labs/css/lab_detail.css` | 11 |
| 4 | `apps/accounts/static/accounts/css/profile/sections/my_courses.css` | 9 |
| 5 | `apps/accounts/static/accounts/css/profile/sections/courses.css` | 9 |
| 6 | `apps/exams/static/exams/css/coding_exam/_part1.css` | 8 |
| 7 | `apps/exams/static/exams/css/student_exam_history.css` | 7 |
| 8 | `static/css/language-switcher.css` | 6 |
| 9 | `apps/live_exam/static/css/wait_room/_part1.css` | 6 |
| 10 | `apps/live_exam/static/css/join/_part1.css` | 6 |

Qalıq siyahı: `/tmp/important_inventory.txt` (55 fayl).

## Təhlükəsiz-çıxarma kateqoriyaları (dizayn PR-da tətbiq)

### Kateqoriya A — Duplicate declaration (yüksək əminlik)
Eyni selektor daxilində iki dəfə eyni property elan olunubsa (`.x { color: red; color: red !important; }`), sonuncudakı `!important` sadəcə şumluqdur. **Say:** ~0-5 (adətən nadirdir).

### Kateqoriya B — Vendor override (mümkün üçün yoxla)
`.bootstrap-select .btn { color: X !important; }` kimi Bootstrap-override üçün istifadə olunanlar — Bootstrap yükləmə sırasını dəyişəndə yoxa çıxa bilir. **Say:** ~40+ (əsasən course_dashboard_redesign.css və language-switcher.css).

### Kateqoriya C — State override (utility class)
`.hidden { display: none !important; }` — spec-in yerinə uyğun (utility-class deyilib `!important` istifadə etmək qanunidir). **Toxunma.** **Say:** ~30.

### Kateqoriya D — Non-obvious cascade (mən vizual review olmadan toxunmuram)
Qalan hər şey (~120). Vizual smoke olmadan çıxarmaq təhlükəlidir. **Bir PR = bir səhifə** yanaşması ilə bölünməlidir.

## Icra planı (dizayn review-da)

1. **Sprint A** (Kateqoriya A): duplicate declaration-ları avtomatik aşkarla və sil. Risk: sıfır.
2. **Sprint B** (Kateqoriya B, prioritet 1 fayl): `course_dashboard_redesign.css` — Bootstrap override-ları yenidən şəkilləndir və specificity ilə əvəz et. Vizual smoke: student dashboard.
3. **Sprint C** (Kateqoriya B/D, live_exam, wait_room, join): live exam vizual smoke test tələb edir.
4. **Sprint D**: qalan fayllar, bir-bir.

## Ratchet

Modul ölçüsü budcəsinin analoqu olaraq `scripts/check_important_budget.py` (gələcək iş) əlavə oluna bilər — CI-də yeni `!important` əlavəsini bloklayır (yalnız kiçilmə).
