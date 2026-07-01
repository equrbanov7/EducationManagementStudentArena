# Qalan Böyük Fayllar — Yeni Fazalar (2026-07)

Python + HTML content + böyük CSS artıq bölünüb (bax `docs/BOYUK_FAYLLAR_BOLGU_PLANI.md`).
Bu sənəd **yalnız qalan 17 donmuş faylı** əhatə edir və işi icra mühitinə görə ayırır:

- **CLAUDE (sandbox)** edə bilər: byte-təhlükəsiz, template-compile/pytest ilə doğrulanan iş.
- **CODEX (host)** etməli: JS davranışı — **real brauzer + E2E (Playwright) doğrulaması MƏCBURİ**,
  çünki sandbox-da brauzer yoxdur və JS-də IIFE-closure / `let/const` script-scope xətaları
  yalnız icra zamanı görünür.

Guard (`scripts/check_module_size.py`) bu 17 faylı **dondurub** — böyüyə bilməzlər, ona görə
bölgü təcili deyil, mərhələ-mərhələ aparıla bilər.

---

## 🔴 FAZA 7 — JS modulyarizasiya (CODEX icra edir, brauzer/E2E MƏCBURİ)

**Ümumi metod (hər fayl üçün):**
1. Faylın strukturunu təyin et: IIFE-wrapped, yoxsa top-level `const/let`, yoxsa `EMSReady`-callback.
2. **ES modul** yolu (tövsiyə olunan): faylı `import`/`export`-lu modullara böl, şablonda
   `<script type="module" src="...">` ilə yüklə. `let/const` script-scope problemi ES modulda yoxdur.
3. **Və ya global-namespace** yolu (legacy uyğunluq lazımsa): xüsusiyyətləri ayrı fayllara çıxar,
   `window.EMS_X = {...}` ilə expose et, ardıcıl `<script>`-lərlə yüklə.
4. **Hər addımdan sonra:** `./scripts/claude_pg_sandbox.sh` (və ya host) → **real brauzerdə səhifəni aç**,
   konsol xətası yoxla + **Playwright E2E** işlət. `check_module_size.py --update` ilə baseline yenilə.

### FAZA 7A — IIFE-wrapped (ən çətin; daxili funksiya çıxarışı)
Bunlar tək `(function(){ ... })()` bağlamasındadır — daxili funksiyaları modula çıxar, IIFE-ni nazik
orkestrator saxla (yaxud tam ES modula çevir).

| Fayl | Sətir | Qeyd |
|------|-------|------|
| `exams/js/coding_exam.js` | 2087 | Kod-editor + runner + test-nəticə + UI; feature modul-lara (editor/runner/ui/api) |
| `exams/js/exam_create_edit_modal.js` | 809 | `window._EXAM_CREATE_ED...` guard — modal state/validation/submit ayrı |
| `exams/js/exam_live_monitor.js` | 675 | `"use strict"` IIFE; chart + poll + render modul-ları (json_script DOM oxuyur) |

### FAZA 7B — top-level `const`-ağır (ES modul MƏCBURİ)
Bunlarda çoxlu top-level `const` var (`const $ = id => ...`) — ayrı `<script>`-lərə bölmək SINDIRA
bilər (const script-scope paylaşılmır). **Yalnız ES modul** (`export`/`import`) ilə böl.

| Fayl | Sətir | Qeyd |
|------|-------|------|
| `live_exam/js/host_lobby.js` | 2181 | ~89 top-level decl; WebSocket-state / render / event / avatar modul-ları |
| `live_exam/js/player.js` | 1558 | ~77 top-level decl; join / question / reaction / render modul-ları |

### FAZA 7C — orta (feature-modul split)
`EMSReady`-callback və ya modul-vari struktur; feature üzrə böl.

| Fayl | Sətir | Qeyd |
|------|-------|------|
| `accounts/js/profile.js` | 2022 | Section-loader / ajax / ui — `profile.js` ilə profil AJAX seksiya yükləmə (bax memory: profile-ajax-section-loader) |
| `accounts/js/register_wizard.js` | 1704 | Wizard step-ləri (step1..4) üzrə modul; validation/state/submit |
| `exams/js/exam_supervision.js` | 1351 | Proctoring: event-capture / scoring / ws — modul-lara |
| `accounts/js/permission_editor_ui.js` | 973 | Matrix / drag / save state modul-ları |

### FAZA 7D — kiçik (aşağı prioritet)
| Fayl | Sətir |
|------|-------|
| `exams/js/profile_group_modal.js` | 680 |
| `blog/js/user_profile.js` | 628 |
| `accounts/js/statistics.js` | 615 |

---

## 🟡 FAZA 8 — JS-in-HTML script partial-ları (CODEX, brauzer)
`{% trans %}`-lı inline JS — pure static ola bilmir. Tövsiyə olunan pattern:
i18n string-ləri `{{ data|json_script:"..." }}` elementinə çıxar, JS-i static `.js`-ə köçür
(DOM-dan i18n oxusun), sonra FAZA 7 kimi böl. Brauzer-doğrulama lazım.

| Fayl | Sətir |
|------|-------|
| `exams/.../_take_exam_scripts.html` | 1309 |
| `accounts/.../_staff_management_scripts.html` | 663 |

---

## 🟢 FAZA 9 — Edge-case CSS (CLAUDE analiz + qərar; icra qərardan sonra)
Bunlar byte-təhlükəsiz bölünə bilər, amma qərar/aydınlaşdırma tələb edir:

| Fayl | Sətir | Problem / qərar |
|------|-------|-----------------|
| `static/css/navbar.css` | 983 | **QLOBAL** (base.html, hər səhifə). Bölmək hər səhifəyə əlavə HTTP request qoyar. **Qərar:** ya `django-compressor`/bundler əlavə et (mənbə bölünür, çatdırılma bundle-lanır) və sonra böl; ya olduğu kimi burax. |
| `blog/static/css/profile.css` | 790 | Template `<link>` loader-i tapılmır — **dead code?** yoxsa dinamik? Əvvəlcə loader-i tap; tapılsa byte-təhlükəsiz böl, tapılmasa sil (dead). |
| `static/css/ai_assistant.css` | 635 | base.html-də yüklənir (qlobal-vari). navbar kimi: bundler və ya burax. |

---

## Bundler tövsiyəsi (FAZA 9 və qlobal assetlər üçün)
CSS/JS-i çatdırılma-cəzasız (əlavə request olmadan) bölmək üçün ideal yol **build/bundle addımı**dır
(django-compressor, yaxud Vite/esbuild). O olmadan qlobal faylları (navbar, ai_assistant) fiziki
bölmək perf-ə zərərdir. Bundler əlavə edilsə: bütün CSS/JS mənbədə komponentlərə bölünür, istehsalda
bir bundle kimi verilir — həm oxunaqlıq həm perf qazanılır.

---

## Sıra tövsiyəsi
1. **FAZA 7B** (host_lobby.js, player.js) — ən böyük, ES modul, aydın feature sərhədləri.
2. **FAZA 7A** (coding_exam.js və s.) — IIFE, daha diqqətli.
3. **FAZA 7C/7D** — orta/kiçik.
4. **FAZA 8** — JS-in-HTML.
5. **FAZA 9** — bundler qərarı + qlobal CSS.

Hər addım: real brauzer + Playwright E2E + `check_module_size.py --update`.
