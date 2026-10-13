# Alman dili (`de`) — 2026-10-13 (gecə)

Sahib: «yeni dil əlavəsi etsin alman dili. select option-da görünsün. başqa hər yerdə də işləsin,
tərcümədə o da olsun.»

## Nə edildi

| Sahə | Dəyişiklik |
|---|---|
| Dil siyahısı | `config/settings/components/i18n_static.py` — `("de", "Deutsch")`. Giriş/portal səhifəsinin select-i bu siyahını göstərir → «Deutsch» görünür. |
| Ümumi dil seçicisi | `templates/partials/_language_switcher.html` — «DE» düyməsi + `language/name_de` (az «Alman dili», en «German», ru «Немецкий», tr «Almanca», de «Deutsch»). |
| Kataloq | `locale/de/LC_MESSAGES/django.po` (18 897 giriş) və `djangojs.po` (797) — AZ-ın msgctxt/msgid dəsti ilə eyni, hamısı tərcümə olunub, `.mo` kompilyasiya olunub. |
| i18n qapısı | `scripts/check_i18n_catalogs.py` `LOCALES`-ə `de`; `scripts/i18n_baseline.json`-a de bölməsi. `de` tr/ru ilə eyni ratchet qaydasındadır. |
| Sinxron aləti | `scripts/i18n_locale_sync.py export/apply --lang de` — AZ-da olub de-də olmayan mətnləri JSON partiyalarına çıxarır, tərcüməni placeholder/HTML yoxlaması ilə geri yazır. Mövcud tərcümələrə toxunmur. |
| JS kataloqu | `core/jsi18n.py` `settings.LANGUAGES`-dən oxuyur → `?l=de` avtomatik verilir. |
| Canlı imtahan | Aparıcının «Dil» ayarında «DE» (`SESSION_LANGUAGES`, `LANGUAGE_KEYS`); oyunçu ekranında sıra «1.», rəqəm «9.100». |
| İcazə redaktoru | `permission_editor/labels_de.js` (labels.js 600 sətir həddinə görə ayrıca fayl), `labels.js` əlavə dilləri qoşur. |
| AI | Gemini/AI xülasə/qiymətləndirmə/sual generasiyası/kurs planlayıcısı: `de → German`; köməkçidə alman dilinin aşkarlanması (ä/ß + söz nümunələri). |
| SEO | `core/context_processors.py` — almanca meta təsvir; hreflang siyahısı `LANGUAGES`-dən avtomatik. |
| Ölkə adı | Qeydiyyat formasında Azərbaycan → «Aserbaidschan». |

## Qəsdən dəyişdirilməyənlər (sahibin qərarı lazımdır)

* **İmtahan MƏZMUN dilləri** (`apps/exams/constants.py` `EXAM_LANGUAGE_CHOICES`, sual bankı dili) — bu
  interfeys dili deyil, sualların yazıldığı dildir. «de» əlavə etmək miqrasiya (choices) və imtahan
  axınının yoxlanmasını tələb edir; alman sektoru (`student_groups` → `de`) üçün almanca imtahan
  variantı lazımdırsa ayrıca iş kimi edilməlidir.
* **Final imtahan zalı dil zolağı** (`FEXC_UI_LANGUAGES` = az/en/ru) — tr də orada yoxdur; imtahan
  zalının UI-si eyni saxlanıldı.
* **Blog kateqoriya adları** (`name_az/en/ru/tr` model sahələri) — de üçün `en`-ə qayıdır (mövcud fallback).
* **Söyüş filtri** (`core/moderation/wordlist.py`) — alman siyahısı yoxdur.
* `apps/live_exam/static/js/player/utils.js` dəyişdi, amma `?v=` versiyası qaldırılmadı: 13 ES-modul
  importunu birlikdə dəyişməmək üçün (fərqli versiya = modulun iki nüsxəsi riski). Növbəti canlı imtahan
  versiya artımında avtomatik gedəcək; dəyişiklik yalnız de üçün kosmetikdir.

## Başqa agentlərin yeni mətnləri (birləşmə axını)

Gecə agentlərinin `i18n_fill_*` skriptləri yalnız az/en/ru/tr-yə yazır. Birləşmədən sonra qapı
`django/de: missing_vs_source 0 → N` göstərəcək. Həll:

```bash
venv/bin/python scripts/i18n_locale_sync.py export --lang de --out /tmp/de_new --batch-size 500
# /tmp/de_new/*.json → /tmp/de_out/<eyni ad>.json  ({"<id>": "Deutsch"}; plural → ["tək", "cəm"])
venv/bin/python scripts/i18n_locale_sync.py apply --lang de --batches /tmp/de_new --translations /tmp/de_out
venv/bin/python manage.py compilemessages -l de -i .claude -i venv
venv/bin/python scripts/check_i18n_catalogs.py
```

## Yoxlama

* `check_i18n_catalogs.py` — keçir. de: django `missing 0 / untranslated 0 / bad_placeholder 0 /
  identity 102`, djangojs `0 / 0 / 0 / 4`. Identity-lər alman dilində də eyni yazılan sözlərdir
  (Status, Seminar, Rektor, Dekan, Telefon, ECTS, PIN, Python…).
* Azərbaycan hərfi (ə/ğ/ı/ş) sızması: 2 giriş, ikisi də qəsdən (nümunə ad «Əliyev…», «FİN»).
  «du/dein» (qeyri-rəsmi müraciət) — 0.
* Testlər: `core/tests/test_german_language_2026_10_13.py` (select-də «Deutsch», setlang → almanca
  səhifə → geri az, dil seçicisi, JS kataloqu, canlı imtahan dili), `test_i18n_locale_sync_2026_10_13.py`;
  `test_i18n_no_fallback_smoke`, `test_profile_i18n_role_matrix`, `organizations/test_i18n_smoke`-a de əlavə olundu.

## Səhər yoxlanmalı

* Giriş səhifəsində dil select-indən «Deutsch» seçib kabineti açmaq; sidebar, jurnal, imtahan siyahısı.
* Terminologiya seçimləri: Kafedra → «Lehrstuhl», Kollokvium/Aralıq → «Zwischenprüfung», Apellyasiya →
  «Einspruch», Jurnal → «Journal», Payız semestri → «Herbstsemester» (istəsəniz «Wintersemester»).
