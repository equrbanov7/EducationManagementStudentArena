# FAZA 18 — «Müraciətlərim» kabinet bölməsi (UI)

Branch `audit/post-migration-qa-2026-09` · 2026-09-02 · QA klonu
`emsarena_rehearsal_a0d170000901` (`http://127.0.0.1:8100/`)

Backend müqaviləsi: `PHASE11_APPLICATIONS_BACKEND.md`.
Dizayn mənbəyi: `design_handoff_muracietler/README.md` §2–§8 +
`design/00 Baza - Muracietler paneli.dc.html` (mətnlər eynilə götürülüb).

| | |
|---|---|
| Bölmə açarı | **`applications`** (sahib tələbi) |
| Sidebar etiketi | **«Müraciətlərim»** — ÜMUMİ blokunda, «Bildirişlər»in yanında |
| Görünürlük qapısı | `application.create` **və ya** `.handle` **və ya** `.manage`; superuser/sahib həmişə |
| Badge | `data-badge-key="applications_pending_count"` — emalçıya `inbox_open`, göndərənə `waiting_info` |
| Panel | AJAX-safe fraqment (`[data-profile-section-panel="applications"]`), sol sidebar QALIR |

⚠️ **Bölmə açarı dəyişdi:** backend sənədindəki `my-applications` → `applications`
(sahibin sərt tələbi). `apps/applications/services/notify.py::PROFILE_SECTION`
uyğunlaşdırıldı ki, bildiriş linki (`?section=…`) doğru panelə düşsün. Başqa
istinad yox idi (yalnız docstring + bu sənəd).

---

## 1. Fayllar

### Yeni

| fayl | rolu |
|---|---|
| `apps/accounts/templates/accounts/profile/sections/_applications.html` | panel çərçivəsi (kontekst zolağı, başlıq, KPI, tablar, filtrlər, iki sütun) |
| `apps/accounts/templates/accounts/profile/sections/_applications_dialogs.html` | 5 dialoq — panelin İÇİNDƏ (AJAX swap-da itmir) |
| `apps/accounts/static/accounts/css/profile/applications.css` (582) | §4.1–§4.6 |
| `apps/accounts/static/accounts/css/profile/applications_detail.css` (366) | §4.7 detal paneli + dar ekran slide-over |
| `apps/accounts/static/accounts/css/profile/applications_dialogs.css` (290) | §4.8/§4.9 dialoqlar |
| `apps/accounts/static/accounts/js/profile/applications_core.js` (146) | mətn/tarix/ölçü köməkçiləri, toast, HTTP, CSRF |
| `apps/accounts/static/accounts/js/profile/applications.js` (563) | siyahı, KPI, tablar, filtrlər, səhifələmə, boot |
| `apps/accounts/static/accounts/js/profile/applications_detail.js` (296) | detal paneli + `allowed_actions` düymələri |
| `apps/accounts/static/accounts/js/profile/applications_dialogs.js` (519) | yeni müraciət / yönləndirmə / səbəb / təyinat / təsdiq |
| `apps/accounts/views/profile/_sections/applications.py` | bölmə context-i (yalnız `applications.public` fasadından) |
| `apps/accounts/views/profile/_sections/applications_i18n.py` | JS mətn kataloqu (`json_script`) |
| `apps/accounts/views/applications.py` | `accounts:applications_assignees` — «Təyin et» namizədləri |
| `apps/accounts/tests/test_applications_section.py` | 9 test |
| `scripts/i18n_fill_applications_ui.py` | 122 giriş × 4 dil |

### Dəyişən

`profile.html` (extraCss + `data-ajax-sections` + dispatch) ·
`profile/_sidebar.html` (universal bənd + badge) ·
`profile/sidebar.css` (`.sidebar-menu-badge:empty{display:none}` + `profile.css`
`@import` versiyası) · `sections_api.py` (SECTION_PARTIALS + AJAX_SAFE_SECTIONS +
badge açarı) · `_sections/labels.py` · `_helpers/rbac_sections.py`
(`can_use_applications`) · `context_builder/_stage1..4.py` ·
`_dashboard_helpers/cheap_counts.py` (`count_applications_pending`) ·
`accounts/urls.py`, `accounts/views/__init__.py` ·
`applications/public.py` (`pending_badge_count`, `handled_unit_names`,
`can_use_applications`, `assignable_handlers`) ·
`applications/services/notify.py` (`PROFILE_SECTION`) · 4 locale kataloqu.

---

## 2. Dizayn DoD (README §8) — nəticə

| # | tələb | nəticə | sübut |
|---|---|---|---|
| 1 | Bir şablon + bir view bütün rollara; rol sessiyadan | ✅ | eyni fraqment `qa.student` / `qa.program_coordinator` / `qa.ikt_rehber` üçün 200; budaqlanma `family`/`is_handler`/`can_create` bayraqları ilə |
| 2 | Bütün növlər düzgün marşrut + SLA, ünvan serverdə | ✅ | `catalog/`-dan 13 tələbə növü; «Digər» → «Proqram koordinatoru · 5 iş günü»; `create/`-ə şöbə GÖNDƏRİLMİR |
| 3 | Tam status maşını + append-only zaman xətti, yönləndirmə izləməni saxlayır | ✅ | canlı: `↑ 👁 → 💬 ✓ ✓`; koordinator yönləndirdikdən sonra «İzlədiklərim 1» |
| 4 | Yoxlama həm klient, həm server (5/20/10) | ✅ | qaydalar `rules`-dan `data-min-*` ilə gəlir, sabit yazılmayıb |
| 5 | Filtrlər, tablar, KPI qısayolları, debounced axtarış real data üzərində | ✅ | 260 ms debounce; KPI kartı `tab`+`stat` tətbiq edir; `Sıfırla` → `stat=open`, `kind=""` |
| 6 | 1400 px-də dizayna uyğun, dar ekranda tək sütun | ✅ | 1280 px: iki sütun; 375 px: `grid-template-columns: 343px`, detal `position: fixed` slide-over, `Bağla` düyməsi görünür, üfüqi sürüşmə YOX |

### §7 a11y

Gizli `<label>` axtarışda ✅ · tablarda `aria-current` ✅ · seçili sətirdə
`aria-current` ✅ · dropdown `aria-haspopup="listbox"` / `aria-expanded` +
`role="option"` / `aria-selected` + Enter/Space ✅ (14 seçim, Enter «Digər»
seçdi) · dialoqlar `role="dialog" aria-modal="true" aria-labelledby`, açılanda
fokus, Esc + overlay bağlayır ✅ · toast `role="status" aria-live="polite"`
(`static/js/toast.js` markup-u, 2800 ms) ✅ · fokus halqası
`outline:2px solid var(--ems-primary-600)` ✅ · status həmişə MƏTN etiketi
daşıyır ✅.

### Dizayndan ŞÜURLU sapmalar

1. **«Rədd et» / «Əlavə məlumat istə» səbəbi cavab qutusundan gəlir** (dizayn
   §4.7: «üç status düyməsi cavab ≥10 simvol olana qədər deaktivdir»). Ayrıca
   səbəb dialoqu **«Düzəliş üçün qaytar»**, **«Ləğv et»** və **«Əlavə məlumat
   göndər»** üçün var (backend bu üçündə fayl/uzunluq fərqi tələb edir).
2. **Şöbə kataloqu 9-dur** (dizaynda 6): backend `koordinator`, `kadrlar`,
   `imtahan` əlavə edib, `ikt` → `rim` adlanıb.
3. **Sahibin əməl qutusunda textarea YOXDUR** — onun əməlləri (`close`,
   `cancel`, `resubmit`, `provide_info`) öz dialoqunu açır, ona görə dizaynın
   «yalnız-oxu qeyd»i göstərilir və düymələr onun altındadır.

---

## 3. Canlı ssenari (QA klonu, AZ dili)

1. `qa.student` → sidebar «Müraciətlərim» klik → panel SAĞDA açıldı, **sol
   sidebar qaldı**, bənd `active`, URL `?section=applications` (AJAX swap;
   `data-apx-booted=1`, KPI-lar doldu).
2. «Yeni müraciət» → növ «Digər» → canlı sətir: *«Bu müraciət «Proqram
   koordinatoru»-nə gedəcək · cavab müddəti 5 iş günü.»*; mövzu + mətn (90
   simvol sayğacı) + `kitabxana_karti.pdf` (69 B) → **MR-000002** yarandı,
   status «Yeni», sətirdə `1` sancaq, sağ etiket «5 iş günü müddət».
3. `qa.program_coordinator` (əməkdaş portalı) → «Mənə gələnlər **1**», sidebar
   badge **1**; açanda status «Yeni → Baxılır», zaman xəttinə `👁` düşdü, 7 əməl
   düyməsi göründü.
4. «Başqa şöbəyə yönləndir» → siyahıda **8 şöbə** (cari `koordinator` çıxarılıb)
   → `rim` + qeyd + «izləməkdə davam edim» ✔ → status «Yönləndirilib»,
   KPI: gələn 0 / izlədiyim 1, yalnız-oxu qeyd mətni göründü.
5. `qa.ikt_rehber` → «Mənə gələnlər 1», `sizdədir`; «Qeyd əlavə et» → `💬`;
   cavab + «Həll olundu — bağla» → «Həll olunub», arxiv 2.
6. `qa.student` → zaman xətti TAM: `↑ 👁 → 💬 ✓`, SLA zolağı «Müraciət
   bağlanıb — həll olunub», `allowed_actions = ["close"]`.
   «Təsdiqləyirəm — bağla» → təsdiq dialoqu → status «Bağlanıb», `✓` əlavə
   olundu, əməllər boşaldı, toast: *«MR-000002 — Bağlanıb. Müraciət sahibinə
   bildiriş göndərildi.»*
7. **Sənəd linki qapılıdır:** `GET …/attachments/…/download/` → `200`,
   `Content-Disposition: attachment; filename="kitabxana_karti.pdf"`,
   `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`.
8. **Badge:** `profile_badges_api` cavabında `applications_pending_count` var
   (koordinatorda 1 → yönləndirmədən sonra 0; tələbədə 0). Sayğac paylaşılan
   keşdən gəlir və `applications.services.notify` mutasiyada keşi invalidasiya
   edir.

### Konsol / şəbəkə

Təmiz tabda panelin yüklənməsi və SPA swap-ından sonra **0 konsol xətası**,
**0 CSP pozuntusu**. `list/`, `kpis/`, `catalog/`, `badges/` — hamısı `200`.

### Ekran görüntüləri

Brauzer aləti şəkli yalnız INLINE qaytarır (fayla yazma API-si yoxdur), ona görə
`docs/audits/2026-09-02/screenshots/applications_*.png` **yaradıla bilmədi**.
Görülənlərin dəqiq təsviri:

* **Tələbə — siyahı + detal (1280×900).** Solda kabinet sidebar-ı, «Müraciətlərim»
  mavi aktiv. Sağda: ağ kontekst zolağı «Tələbə kabineti · öz müraciətlərim» +
  sağda mavi rol pill-i; `Müraciətlər` başlığı + izah + sağda mavi «+ Yeni
  müraciət»; 4 KPI kartı (1-ci mavi tinted, 2-ci sarı, 3-4 ağ; etiket/rəqəm/qeyd
  üç sətir); tablar «Müraciətlərim 1 · Arxiv 1» (aktivin altında mavi xətt);
  ağ filtr paneli (axtarış + 4 çip, «Açıq olanlar» mavi doldurulmuş + «Bütün
  növlər» dropdown + «Sıfırla»); solda seçili sətir (mavi haşiyə + `#eff6ff`
  fon): `MR-000002` mono · «Digər» boz nişan · sağda «Yeni» mavi pill · qalın
  mövzu · `Proqram koordinatoru · 02.09.2026 · 📎1` · sağda «5 iş günü müddət»;
  sağda sticky detal: nömrə+nişan+pill, başlıq, göndərən sətri, mavi SLA zolağı
  «Cavab müddətinə 5 iş günü qalıb (norma 5 iş günü)», «MÜRACİƏTİN MƏTNİ» boz
  qutu, «ƏLAVƏ OLUNAN SƏNƏDLƏR» sətri.
* **Yeni müraciət dialoqu.** Tünd yarımşəffaf overlay, 620 px ağ panel; başlıq +
  alt izah; növ siyahısı (hər sətirdə rəngli nöqtə, ad, izah, sağda «N iş günü»),
  seçilmiş «Digər» mavi haşiyə + `#eff6ff`; «MÖVZU *» input; «MÜRACİƏTİN MƏTNİ *»
  textarea + «90 simvol» sayğacı; kəsik-xətli «Fayl seç — PDF, JPG və ya DOCX,
  maks. 10 MB» + altında `kitabxana_karti.pdf · 69 B · ✕`; mavi info qutusu
  routing hint-i ilə; boz footer-də «Ləğv et» + mavi «Müraciəti göndər».
* **Koordinator — gələnlər.** Kontekst zolağı «Proqram koordinatoru · şöbəyə
  gələn müraciətlər»; KPI-lar «Mənə gələn açıq 1 / Yeni — baxılmayıb 0 (hamısına
  baxılıb) / Cavab müddəti keçən 0 (gecikən yoxdur) / İzlədiyim 0»; tablar «Mənə
  gələnlər 1 · İzlədiklərim · Müraciətlərim · Arxiv 1»; sətirdə ikinci sətir
  «QA Student · 634 ing», sağda «sizdədir».
* **RİM — detal + əməllər.** Detal altında `#f8fafc` qutu: «Cavab ver» etiketi,
  3 sətirlik textarea, sonra 7 düymə — mavi «Həll olundu — bağla», ağ «Əlavə
  məlumat istə», mavi konturlu «Başqa şöbəyə yönləndir», ağ «Düzəliş üçün
  qaytar», qırmızı konturlu «Rədd et», ağ «Təyin et», ağ «Qeyd əlavə et»;
  altında boz ipucu «Cavab mətni ən azı 10 simvol olmalıdır…».
* **Mobil 375 px.** Tək sütun (`grid-template-columns: 343px`), üfüqi sürüşmə
  yoxdur; sətirə klik detalı ekranın altından `position: fixed` slide-over kimi
  açır (yuxarı künc radiusu 16 px, kölgə), başlıqda «Bağla» düyməsi görünür.

---

## 4. Testlər və gate-lər

**Testlər — 146 keçdi** (özəl baza `ems_appui_22184955` @ agent postgres):
`apps/accounts/tests/test_applications_section.py` **9** (hər ailə üçün fraqment
200 · endpoint/rules/`json_script` · göndərən vs emalçı budaqlanması · emalçı+
yaradan «Müraciətlərim» tabı · sidebar bəndi + badge açarı · `badges_api`
açarı · icazəsiz üzv bəndi GÖRMÜR · üzvlüksüz istifadəçi bəndi görmür və
fraqment 403 · namizəd endpoint-i) + `apps/applications/tests` **137** (backend
regressiyası yoxdur — `PROFILE_SECTION` dəyişikliyindən sonra da yaşıl).
Əlavə regressiya: `test_profile_views.py` + `test_cabinet_modules.py` — **171
keçdi**.

| gate | nəticə |
|---|---|
| black / isort / flake8 (dəyişən 17 fayl) | ✅ |
| `check_module_size.py --check` | ✅ **mənim fayllarım** (ən böyüyü 582); qırmızı qalan İKİ fayl başqa agentlərindir: `apps/legacy_import/models.py` 604, `apps/registrar/models/grading.py` 602 |
| `module_deps.py --check` | ✅ yeni dövr yoxdur |
| `makemigrations --check` | ✅ dəyişiklik yoxdur |
| `check_i18n_catalogs.py` | ⚠️ aşağıya bax |
| `check_worker_atomic_coverage.py --check` | ❌ **mənim faylım deyil** — `apps/applications/management/commands/{close_stale_resolved,seed_application_catalog}.py` (backend agenti) + 4 `apps/legacy_import/management/commands/legacy_repair_*.py` |

### i18n

`scripts/i18n_fill_applications_ui.py` 4 dilə **122 giriş** əlavə etdi
(`applications`, `accounts.applications`, `profile.sidebar` kontekstləri);
`compilemessages` icra olundu. Qapı yalnız İKİ ölçüdə qırmızıdır və **hər ikisi
paylaşılan sayğacdır**:

* `django/tr identity 270 → 280`. Bunun **8-i əvvəlki agentlərdəndir**
  (cədvəl agentinin `accounts.schedule_manage` 7 girişi + backend-in
  `applications|Yeni`). **Mənim payım 2-dir** və hər ikisi DÜZGÜN türkcədir,
  sadəcə azərbaycanca ilə eyni yazılır: `applications|gün` və
  `applications|{n} iş günü`. Sahibin göstərişi ilə `--update` EDİLMƏDİ.
* `django source_missing 3 → 4`. Yeni giriş
  `exams.final_center.permission|Bu bölmə yalnız imtahan mərkəzi və
  nəzarətçilər üçündür.` — **təhlükəsizlik agentinindir**, mənim mətnlərimin
  hamısı dörd kataloqdadır.

---

## 5. Yol boyu düzəldilən İKİ tələ (gələcək bölmələr üçün)

1. **Panel script-i `ems_ajax_init.js`-dən ƏVVƏL icra olunur.** `<script src>`
   `[data-profile-section-panel]` İÇİNDƏ olmalıdır (AJAX swap tələbi), amma
   `<body>` içindəki parser-inserted script `base.html`-in sonundakı
   `EMSDelegate`/`EMSReady`-dən əvvəl işləyir → `Cannot read properties of
   undefined (reading 'on')`. Həll: script-lərə `defer` + hər modulda
   primitivləri gözləyən kiçik `ready()` döngəsi (AJAX swap-da dinamik script
   sırası zəmanətli olmadığı üçün ikinci qapı lazımdır).
2. **QA/staging-də CSRF kuki adı fərqlidir.** `staging_inspect.py`
   `CSRF_COOKIE_NAME = "emsarena_staging_csrftoken"` təyin edir, `EMSCore
   .getCsrfToken()` isə adı `csrftoken` kimi SABİT oxuyur → köhnə kukini
   götürüb bütün POST-ları 403 edir. Həll: panel öz `{% csrf_token %}`-ini
   daşıyır və POST başlığı `NS.csrfToken()`-dən gəlir (kuki yalnız ehtiyat yol).
   Bu, prod-da da token rotasiyasına qarşı möhkəmdir.

## 6. Mühit qeydi (sahibə)

Sessiyanın ortasında `~/Desktop` iCloud symlink-i itdi və yerinə BOŞ lokal
`Desktop` qovluğu yarandı (20:47); repo `~/Library/Mobile Documents/
com~apple~CloudDocs/Desktop/…`-da toxunulmaz qaldı və iş oradan davam etdi.
20:22-də symlink özü bərpa olundu, hər iki yol indi eyni fayllara baxır.
`scratchpad/serve_qa.sh` kanonik (iCloud) yolu işlədəcək şəkildə yeniləndi —
symlink yenidən itsə də işləyir. QA klonuna bu sessiyada başqa agentlərin ÜÇ
RLS miqrasiyası tətbiq olundu (`ai_assistant.0003`, `audit.0003`,
`monitoring.0002`) — onlarsız server qalxmırdı.
