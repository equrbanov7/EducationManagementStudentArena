# EMS Arena — tam dizayn handoff paketi (22 ekran)

Layihə: **EMS Arena** — Qərbi Kaspi Universiteti üçün təhsil idarəetmə sistemi
Hədəf codebase: `equrbanov7/EducationManagementStudentArena` (Django, `branch: main`)
Mərhələ: **dizayn tamamlanıb, kod yazılmayıb**
İnterfeys dili: **Azərbaycan dili** — fayllardaki bütün mətn YEKUN copy-dir, hərfi götürülməlidir.
Fidelity: **high-fidelity** — rənglər, tipoqrafiya, boşluqlar, state-lər və copy yekundur.

---

## Mündəricat

1. [Bu paketi necə istifadə etməli](#1-bu-paketi-necə-istifadə-etməli)
2. [⚠ Dizayn tokenləri — ən vacib bölmə](#2--dizayn-tokenləri--ən-vacib-bölmə)
3. [Qlobal shell (bütün ekranlarda eyni)](#3-qlobal-shell-bütün-ekranlarda-eyni)
4. [Ümumi komponent lüğəti](#4-ümumi-komponent-lüğəti)
5. [Modullar və 22 ekran](#5-modullar-və-22-ekran)
6. [Axınlar və state maşınları](#6-axınlar-və-state-maşınları)
7. [Accessibility](#7-accessibility)
8. [Backend acceptance qaydaları](#8-backend-acceptance-qaydaları)
9. [İmplementasiya ardıcıllığı](#9-implementasiya-ardıcıllığı)
10. [Açıq qalan product qərarları](#10-açıq-qalan-product-qərarları)
11. [Fayl siyahısı](#11-fayl-siyahısı)

---

## 1. Bu paketi necə istifadə etməli

```
design_handoff_full/
├── README.md                  ← bu fayl
├── CLAUDE-CODE-PROMPT.md      ← Claude Code-a yapışdırılacaq mətn
├── index.html                 ← 22 ekranın vizual indeksi (brauzerdə aç)
├── github.md                  ← hədəf repo qeydi
└── design/
    ├── 00 … 21 *.dc.html      ← 22 ekran prototipi
    ├── support.js             ← prototip runtime (layihəyə köçürülmür)
    └── brand/                 ← logo faylları
```

**Addımlar:**
1. Qovluğu layihənin kökünə çıxar.
2. `index.html` faylını brauzerdə aç — 22 ekranı yanaşı miqyaslı şəkildə göstərir; «Tam ölçüdə aç» ilə hər ekranı ayrıca aça bilərsən. Prototiplər interaktivdir: tab-lar, filtrlər, modallar işləyir — dizaynı yalnız oxumaqla deyil, klikləməklə də yoxla.
3. Claude Code-a `CLAUDE-CODE-PROMPT.md` mətnini ver.

**Prototiplərin təbiəti.** Hər `.dc.html` bir səhifədir: markup `<x-dc>…</x-dc>` arasında, məntiq və nümunə data aşağıdakı `<script type="text/x-dc">` blokundadır. `support.js` onları brauzerdə render edən runtime-dır. **Bu faylların heç biri production-a getmir.** Onlar spesifikasiyadır: markup strukturu, ölçülər, rənglər, copy və davranış mənbəyidir.

**Hardcoded massivlər = queryset-lər.** `UNITS`, `PEOPLE`, `FACS`, `PROGRAMS`, `CAT`, `ROWS`, `GROUPS`, `DEPS`, `PLAN`, `TICKETS`, `SEC`, `AUDIT` və s. — hamısı real ORM sorğusunun yerinə duran nümunə datadır. Sətir sayı və konkret adlar əhəmiyyətli deyil; **sahə (field) tərkibi əhəmiyyətlidir** — hansı sütunların göstərildiyi modeldən nə tələb olunduğunu deyir.

**Stil köçürməsi.** Prototiplərdə stil qəsdən inline yazılıb (dizayn alətinin tələbi). Porting zamanı bu dəyərləri layihənin mövcud CSS qatına (`static/css/design-tokens.css`, `ems_components.css`) çevir — inline saxlama.

---

## 2. ⚠ Dizayn tokenləri — ən vacib bölmə

`design/00 Dizayn konstantlari.dc.html` — bütün tokenlərin, status rənglərinin, tipoqrafiya şkalasının və komponent variantlarının canlı kataloqudur. **Şübhə yaranan hər dəfə bu fayla bax.**

### 2.1 Kodda ARTIQ mövcud olan tokenlər

`static/css/design-tokens.css` faylında bunlar var — **dəyişdirmə, yenisini icad etmə**:

| Qrup | Tokenlər |
| --- | --- |
| Primary | `--ems-primary-50 #eff6ff` · `-100 #dbeafe` · `-200 #bfdbfe` · `-500 #3b82f6` · **`-600 #2563eb` (brend)** · `-700 #1d4ed8` · `-800 #1e40af` |
| Neutral | `--ems-neutral-0 #ffffff` · `-50 #f8fafc` · `-100 #f1f5f9` · `-200 #e2e8f0` · `-300 #cbd5e1` · `-400 #94a3b8` · `-500 #64748b` · `-600 #475569` · `-700 #334155` · `-800 #1f2937` · `-900 #0f172a` |
| Success | `--ems-success #10b981` · `--ems-success-100 #dcfce7` · `-600 #059669` · `--ems-success-strong #0f766e` |
| Danger | `--ems-danger #dc2626` · `-100 #fee2e2` · `-200 #fecaca` · `-500 #ef4444` · `--ems-danger-strong #b91c1c` |
| Warning | `--ems-warning-100 #fef3c7` · `-500 #f59e0b` · `-600 #d97706` · `-700 #b45309` · `-800 #92400e` |
| Alias | `--ems-text` · `--ems-text-muted` · `--ems-border` · `--ems-bg` · `--ems-bg-subtle` · `--ems-link` · `--ems-link-hover` |

### 2.2 Prototiplərin işlətdiyi, kodda OLMAYAN adlar

Bu adlar mock-larda var, `design-tokens.css`-də yoxdur. **İki variantdan BİRİNİ seç, qarışdırma:**

**Variant A — CSS faylına əlavə et** (mövcud sətirlərə toxunmadan, faylın sonuna):

```css
/* === Dizayn handoff — əlavə tokenlər === */
:root{
  --ems-success-bg:  #dcfce7;   /* = --ems-success-100 */
  --ems-warning-bg:  #fef3c7;   /* = --ems-warning-100 */
  --ems-danger-bg:   #fee2e2;   /* = --ems-danger-100  */
  --ems-warning:     #f59e0b;   /* = --ems-warning-500 */
  --ems-success-700: #15803d;   /* yaşıl mətn — badge fg */
  --ems-success-bd:  #bbf7d0;   /* yaşıl kart konturu   */
  --ems-warning-bd:  #fde68a;   /* sarı kart konturu    */
  --ems-danger-bd:   #fecaca;   /* qırmızı kart konturu */
}
```

**Variant B — sed ilə mövcud adlara çevir:**

```
--ems-success-bg  → --ems-success-100
--ems-warning-bg  → --ems-warning-100
--ems-danger-bg   → --ems-danger-100
--ems-warning     → --ems-warning-500
```
(qalan 4-ü hər halda əlavə edilməlidir — kodda ekvivalenti yoxdur)

### 2.3 Bilinən ziddiyyət (kontrast)

Dizaynlarda «təsdiqlənib» yaşılı **mətn üçün `#15803d`**, fon `#dcfce7`-dir. Kodun `--ems-success` dəyəri `#10b981`-dir — daha açıqdır və kiçik mətn kimi WCAG AA-dan keçmir.

**Qayda:** yaşıl **mətn/badge yazısı → `#15803d`**; yaşıl **ikon, nöqtə, progress fill, accent → `--ems-success`**. Eyni məntiq: sarı mətn `#92400e`, qırmızı mətn `#b91c1c`.

### 2.4 Tipoqrafiya

Sistem şrift stack-i, web font YOXDUR (qəsdən):
```
-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif
```
Monospace (fənn kodu, reyestr kodu, FİN): `ui-monospace, SFMono-Regular, Menlo, monospace`

| Rol | Dəyər |
| --- | --- |
| Səhifə H1 | `1.55rem / 800 / letter-spacing:-.02em` |
| Bölmə başlığı | `1.05–1.25rem / 700–800` |
| Kart başlığı | `.93rem / 800` |
| Nav elementi | `.95rem / 500` |
| Gövdə / kontrol | `.83–.86rem` |
| Meta / footnote | `.72–.76rem` |
| Badge / pill | `.71–.75rem / 700–800` |
| Uppercase overline | `.7rem / 800 / letter-spacing:.08em` (nav qrup label-ı `1px`) |
| Wordmark | `1.02rem / 800 / #2563eb / -.02em` |

**Minimum:** heç bir mətn `.7rem`-dən (≈11px) kiçik deyil.

### 2.5 Radius / boşluq / kölgə

- **Radius:** `9px` ikon düymə · `10px` input və düymə · `12px` (`.75rem`) nav elementi · `14–16px` kart və modal · `50%` collapse düyməsi · `999px` pill, chip, progress.
- **Boşluq:** 4px baza. Təkrarlananlar: `gap:.6rem` (nav), `gap:10px` (header kontrolları), `gap:14px` (KPI grid), `padding:.82rem 1.05rem` (nav elementi), `padding:10px 12px|16px` (kontrol), `padding:17px 19px` (KPI kartı), `padding:1.5rem 1.25rem` (sidebar header).
- **Kölgə:** cəmi biri — `0 4px 12px rgba(59,130,246,.25)` aktiv nav elementində. Kartlarda kölgə yoxdur (kontur + `--ems-bg-subtle` fon ilə ayrılır). Drawer/dialog/toast öz scrim-i ilə gəlir.
- **Kontur:** `1px solid var(--ems-border)`; seçili/vurğulu kart `2px`.

### 2.6 Toxunma hədəfləri

Bütün düymə / chip / select `min-height: 34px`; əsas əməllər `40–44px`. Cədvəl içindəki sıra əməlləri `min-height:32px`-ə düşə bilər, amma klik sahəsi bütün xanaya yayılır.

---

## 3. Qlobal shell (bütün ekranlarda eyni)

**Bir dəfə partial kimi qur, 22 ekran onu miras alır.**

### Body
`background:#f8fafc` · `color:#0f172a` · `min-height:100vh` · `-webkit-font-smoothing:antialiased`
Linklər: `#2563eb`, hover `#1d4ed8`, `text-decoration:none`
Input fokus halqası: `border-color:#3b82f6; box-shadow:0 0 0 3px #dbeafe; outline:none`
Scrollbar: 10px, thumb `#cbd5e1` r8, track `#f1f5f9`

### Top bar
`position:sticky; top:0; z-index:60; height:56px; padding:0 20px` · `background:#fff; border-bottom:1px solid #e2e8f0` · flex, space-between
- Sol: `brand/wcu-logo-horizontal.svg` (`height:34px; max-width:180px`) → `1×22px #e2e8f0` divider → wordmark **EMS Arena**
- Sağ: iki sətir sağa düzülü (`line-height:1.25`) — ad `.83rem/600/#0f172a`, rol `.72rem/#64748b`
- Çıxış ikon düyməsi: `34×34`, `radius 9px`, `1px solid #e2e8f0`, `#fff`, ikon `#64748b` 17px stroke-1.8; hover `background:#fee2e2; border-color:#fecaca; color:#dc2626`

### Sidebar
`flex:0 0 300px; width:300px; min-height:calc(100vh - 56px)` · `background:#fff; border-right:1px solid #e2e8f0`
- Header bloku: `padding:1.5rem 1.25rem; border-bottom:1px solid #e2e8f0`; başlıq `1.25rem/700/nowrap` — rola görə dəyişir (`Tədris şöbəsi`, `Koordinator`, `Kafedra müdiri`, `Dekanlıq`, `Müəllim`, `Rektorluq`, `Tələbə Mərkəzi`, `Tələbə`); collapse düyməsi `36×36; radius:50%; background:#eff6ff; icon:#3b82f6`, hover `background:#3b82f6; color:#fff`
- Nav: `padding:1rem .75rem; gap:.6rem`
  - Qrup label-ı: `.7rem/700/uppercase/letter-spacing:1px/#9ca3af`, `padding:1rem 1rem .5rem`
  - Element: `padding:.82rem 1.05rem; border-radius:.75rem; gap:.8rem; .95rem/500`, ikon 20px stroke-1.8
    - passiv: şəffaf fon, `color:#64748b`; hover `background:#f8fafc`
    - **aktiv: `background:#3b82f6; color:#fff; box-shadow:0 4px 12px rgba(59,130,246,.25)`**
  - Sayğac pill-i: `margin-left:auto; padding:.15rem .6rem; radius:999px; .75rem/700` — məlumat `#eff6ff/#1d4ed8`, xəbərdarlıq `#fef3c7/#92400e`, kritik `#fee2e2/#b91c1c`
- Progress kartı (nav-ın altında): `padding:14px; radius:16px; background:#f9fbff; border:1px solid #e2e8f0`; label `.7rem/800/uppercase`, dəyər `.72rem/800/#1d4ed8`, başlıq `1.05rem/800/#1e40af`, bar `height:7px; radius:999px; track #e2e8f0; fill #2563eb`
- Altda `Çıxış` — eyni nav geometriyası, `color:#ef4444`, şəffaf fon

### Content header (hər ekranda)
- Breadcrumb `.76rem/#94a3b8`, 12px chevron, son crumb `#334155/600`
- `<h1>` `1.55rem/800/-.02em/#0f172a`
- Alt sətir `.86rem/#64748b/text-wrap:pretty`
- Sağ tərəfdə `select` (`padding:10px 12px`) və ikinci dərəcəli düymələr (`padding:10px 16px`), `border:1px solid #cbd5e1; radius:10px; background:#fff; .84–.85rem`

### Canvas ölçüləri
Desktop-first: 1240–1500px arası (hər ekranın `$preview` dəyəri §5-də göstərilib). Geniş cədvəllər `overflow-x:auto` konteynerdə `min-width:900px` ilə. Layout `repeat(auto-fit, minmax(...))` üzərində — fixed-width blok yoxdur.

---

## 4. Ümumi komponent lüğəti

Bu 14 komponent 22 ekranın hamısını qurur. Bir dəfə yaz, hər yerdə istifadə et.

| # | Komponent | Variantlar / qeyd |
| --- | --- | --- |
| 1 | **KPI kartı** | statik · **klik edilə bilən filtr** (`aria-pressed`, seçildə `2px` kontur) · rəngli semantik variantlar |
| 2 | **Filtr paneli** | label-lı select sırası + axtarış (240ms debounce) + `Tətbiq et`/`Sıfırla`. **Draft state ayrı, applied state ayrı** — cədvəl yalnız applied-i oxuyur |
| 3 | **Searchable dropdown** | `*Open`/`*Query` state cütü ilə (kafedra, ixtisas, müəllim seçimi) |
| 4 | **Status badge** | fon/mətn/kontur üçlüyü; **status yalnız rənglə deyil, mətnlə də verilir** |
| 5 | **Data cədvəli** | `th scope="col"`, sıra başlığı `th scope="row"`, birinci sütun `position:sticky`, zebra: cüt `#fff` / tək `#f8fafc`, sıralanan sütun başlığı (`sortKey`/`sortDir`) |
| 6 | **Kart grid** | cədvəlin mobil/alternativ görünüşü; `Cədvəl ⇄ Kart` açarı |
| 7 | **Drawer** | 720–940px, sağdan; `role="dialog" aria-modal="true"` |
| 8 | **Modal / dialoq** | sadə · siyahılı · seçimli (radio kartlar) · **səbəb tələb edən** (textarea, boş olanda OK disabled) |
| 9 | **Toast** | `role="status" aria-live="polite"`, `position:fixed; bottom:24px; left:50%`, tünd navy fon |
| 10 | **Stepper / mərhələ zolağı** | tamamlanıb (yaşıl tik) · cari (primary) · gözləyir (boz) · xəta (qırmızı) |
| 11 | **Addım naviqasiyası** (sol sütun) | aktiv: `--ems-primary-50` fon + `--ems-primary-600` sol kontur |
| 12 | **Diff kartı** | köhnə `--ems-danger-100` / yeni `--ems-success-100`, yanaşı |
| 13 | **Audit timeline** | nöqtəli xronologiya; nöqtə rəngi statusa uyğun |
| 14 | **Boş / skeleton / xəta vəziyyəti** | ikon + başlıq + izah + CTA. **Hər siyahıda üçü də var** — `dataState`/`listState` prop-u ilə keçid edilir |

**Disabled düymə gizlədilmir, stillənir:** `background:#f1f5f9; color:#94a3b8; border:1px solid #e2e8f0; cursor:not-allowed`.

**Arxiv / read-only rejimi:** keçmiş tədris ili seçildikdə bütün yazma əməlləri söndürülür, status qeydi `arxiv — yalnız oxunuş` (`#b45309`) olur.

---

## 5. Modullar və 22 ekran

4 modul, 22 ekran. Modul A → B → C → D ardıcıllığı həm data asılılığı, həm də implementasiya ardıcıllığıdır: **struktur olmadan tələbə, tələbə olmadan yük, yük olmadan sillabus qurula bilmir.**

```
A. Struktur və kataloq (7)   →   B. Tələbə (4)   →   C. Dərs yükü (6)   →   D. Sillabus və jurnal (4)
```

---

### MODUL A — Struktur və kataloq

#### 01 · Universitetin strukturu
`design/01 Tedris shobesi - Universitet strukturu.dc.html` · canvas **1400×1150**
**İstifadəçi:** Tədris şöbəsi. **Məqsəd:** rektorat → fakültə → dekanlıq → kafedra → ixtisas → qrup ağacını idarə etmək.

- Props: `role` = `Tədris Şöbəsi müdiri | Tədris Şöbəsi əməkdaşı | Rektorat | Dekanlıq`
- State: `loading, w, open, root, sel, q/qRaw, typeF, edit, heads, names, toast`
- Data: `UNITS` (ağac qovşaqları), `PEOPLE` (rəhbər təyinatı)
- Bölmə tipləri (`typeF` filtri): Rektorat · Fakültə · **Dekanlıq — fakültənin inzibati aparatı** · Kafedra · **İxtisas — akademik proqram** · Tələbə qrupu · **Mərkəz — fakültədən kənar struktur** · Tədris laboratoriyası
- Sol tərəfdə genişlənən ağac (`open` map), sağda seçilmiş qovşağın detalı: rəhbər, müəllim heyəti, qrup sayı, tələbə sayı
- Xüsusi vəziyyət: **«Rəhbəri olmayan bölmə»** — vurğulanır, təyinat CTA-sı verilir
- Redaktə inline (`edit`), uğurda toast

#### 02 · Kafedra profili
`design/02 Tedris shobesi - Kafedra profili.dc.html` · canvas **1320×1180**
**Məqsəd:** kafedranın ştat cədvəli, müəllim heyəti, yük riski.

- Props: `role` (4 dəyər) · `normSet` = `Nazirlik normaları | Universitet normaları` · `dataState` = `Avtomatik | Skeleton | Xəta`
- State: `loading, err, w, sel, tab, stage, railQ/railOpen, staffQ/staffQRaw, typeF, onlyOff, sort/sortOpen, sem, ownF, tsel, hourly, edit, openMeet, toast`
- Data: `FACS`, `RANK_ORDER` (elmi dərəcə iyerarxiyası), `SORTS`
- Sol rail: kafedra axtarışı; əsas panel: tab-lar + müəllim cədvəli
- **Ştat növləri:** `Ştat` · `Əvəzçilik` · `Saathesabı` — hər biri ayrıca sayılır, `Ştat vahidi cəmi` göstərilir
- **Yük statusu 4 vəziyyət:** `boş tutum` · `normada` · `yüklü` · `risk` — rəng + mətn
- `normSet` seçimi normaları dəyişir → yük statusları yenidən hesablanır. **Norma dəyərləri policy cədvəlindən gəlir, kodda hardcode olunmur.**

#### 03 · İxtisaslar
`design/03 Tedris shobesi - Ixtisaslar.dc.html`
**Məqsəd:** təhsil proqramlarının reyestri.

- Props: `role` (4) · `listState` = `Avtomatik | Skeleton | Boş | Xəta`
- State (böyük): ağac (`node, type, openFac, eng, eco, hum`), rail (`railOpen/railQ`), filtr (`q/qRaw, deg, form, onlyNoPlan, sort/sortOpen/sortQ`), seçim (`sel, tab, semF, blokF, deptF/deptOpen/deptQ, course`), `edit`, **arxivləmə (`arch, archReason`)**, `toast`
- Data: `FACS`, `PROGRAMS`, `SORTS`
- İxtisas sahələri: **İxtisas kodu · Tam ad · Təhsil pilləsi · Təhsil forması · Tabe olduğu kafedra · Fakültə · Məzuniyyət üçün ECTS · Qayıb limiti · Vəziyyət**
- Metrikalar: Qrup · Tələbə · Cari semestrdə açılmış fənn
- **⚠ «Plan yoxdur» bayrağı** — tədris planı olmayan ixtisas vurğulanır; `onlyNoPlan` filtri ilə süzülür. Bu, 05 və 07 ekranları üçün bloklayıcı şərtdir.
- Arxivləmə **səbəb tələb edir** (`archReason`) — silmə yoxdur

#### 04 · Fənn kataloqu
`design/04 Tedris shobesi - Fenn kataloqu.dc.html` · canvas **1360×1180**
**Məqsəd:** universitet üzrə vahid fənn reyestri.

- Props: `role` (4) · `dataState` (3)
- State: `loading, err, w, sel, tab, railOpen, q/qRaw, dept/deptOpen, blok, sort/sortOpen, only, merge, edit, toast`
- Data: `DEPTS`, `BLOKS` (fənn blokları), `CAT` (kataloq), `SORTS`, `TEACHERS`
- Fənn sahələri: **Reyestr kodu · Sahibi kafedra · Kredit · Tədris dili · Qiymətləndirmə forması · Prerekvizit · Fənn blokları · Semestrlər · Vəziyyət · Sillabus · Planlarda istifadə**
- Saat bölgüsü: **Mühazirə / Seminar / Laboratoriya** — hər növ ayrıca saxlanılır (bax §8 qayda 0)
- **`merge` — fənn birləşdirmə:** iki dublikat reyestr yazısı birləşdirilir; əlaqəli plan sətirləri və sillabuslar yeni koda keçir. Destruktiv əməldir — confirmation + audit tələb edir.
- `Planlarda istifadə` sütunu silmənin qarşısını alır: istifadədə olan fənn silinmir

#### 05 · Tədris planı redaktoru
`design/05 Tedris plani redaktoru.dc.html` · canvas **1240×1180**
**Məqsəd:** ixtisasın 4 illik tədris planını qurmaq, kredit balansını saxlamaq, təsdiq zəncirindən keçirmək.

- Props: `planStatus` = `Qaralama | Kafedra baxışı | Fakültə şurası | Tədris şöbəsi | Təsdiqlənib` · `semTarget` = `30` · `showAudit` = `true`
- State: `tab, kurs, fSem, fBlok, fKaf, q/qApplied, openDd/ddQuery, tableState, focus, sortKey/sortDir, modal, target` + plan sətri formu (`dSifr, dName, dKredit, dSerbest, dMuh, dSem, dLab, dSemestr, dPre, dKaf`) + `catQ, blokCode, blokName, cloneSrc, sendNote`
- Data: `BLOKS`, `ROWS` (plan sətirləri), `LATER`, `KATALOQ`, `GRAFIK` (tədris qrafiki), `KURS`
- Metrikalar: **Plan sətri · Cəmi kredit (təkrarsız fənn) · Ümumi saat · Auditoriya saatı · Açıq xəbərdarlıq**
- **Kredit balansı:** semestr hədəfi `semTarget` (30 ECTS). Hədəfdən kənar semestr xəbərdarlıq verir; **açıq xəbərdarlıq varsa təsdiqə göndərmə bloklanır.**
- Plan sətri saat bölgüsü: mühazirə / seminar / laboratoriya + sərbəst iş — cəmi kreditlə uzlaşmalıdır
- `cloneSrc` — başqa ixtisasın planından köçürmə; nəticə **yalnız QARALAMA**
- `showAudit` — dəyişiklik jurnalı paneli
- **Təsdiqlənmiş plan immutable-dır** (§8 qayda 1) — 07 ekranı yalnız təsdiqlənmiş plandan açılış yaradır

#### 06 · Qruplar
`design/06 Tedris shobesi - Qruplar.dc.html` · canvas **1360×1180**
**Məqsəd:** tələbə qrupları, dərs cədvəli, qrup daxilində tələbə hərəkəti.

- Props: `role` = `Tədris Şöbəsi müdiri | Tədris Şöbəsi əməkdaşı | Dekanlıq | Kafedra müdiri | **Kurator**` · `dataState` (3)
- State: `loading, err, w, sel, tab, railOpen, q/qRaw, prog/progOpen, kurs, lang, stQ/stQRaw, stF, ssel, move, create, toast`
- Data: `GROUPS`, `DAYS` (Bazar ertəsi … Cümə), `SLOTS`, `KINDS`, `MOVE_KINDS`, ad generatorları (`AD_Q, AD_O, SOY`)
- Qrup sahələri: **İxtisas · Kafedra / fakültə · Təhsil pilləsi və forma · Tələbə sayı · Kurs · Dil**
- Metrikalar: **Qrupun orta balı · Orta GPA · Dərsə gəlmə · Akademik borcu olanlar**
- Həftəlik cədvəl grid-i: 5 gün × slotlar, dərs növü (`KINDS`) rənglə fərqlənir
- `move` — tələbə köçürmə dialoqu (`MOVE_KINDS`); `create` — yeni qrup

#### 07 · Semestr açılışı
`design/07 Tedris shobesi - Semestr acilishi.dc.html` · canvas **1400×1150**
**Məqsəd:** təsdiqlənmiş plandan semestr açılışlarını yaratmaq, müəllim təyin etmək, jurnalları açmaq, semestri kilidləmək.

- Props: `role` (4)
- State: `loading, w, view, q/qRaw, dept/deptOpen, stat, assigned, cancelled, journals, sent, selected, assign, gen, lock, locked, toast`
- Data: `GROUPS`, `TEACHERS`
- **5 addımlı mərhələ zolağı (stepper) — bu ekranın onurğasıdır:**
  1. `Plandan açılış yaradıldı`
  2. `Kafedraya göndərildi`
  3. `Müəllim təyin olundu`
  4. `Jurnal açıldı`
  5. `Semestr kilidləndi`
- Açılış sətri statusları: `Müəllim təyin olunub` · `Müəllim gözləyir` · `Jurnalı açılıb`
- Şərt mətnləri (gate-lər): «Açılışlar təsdiqlənmiş plandan gəlir» · «Bütün açılışlara müəllim təyin olunub» · «Elektron jurnallar açılıb» — hər üçü ödənməsə kilid düyməsi disabled
- `Semestr saatı` metrikası plan saatı ilə müqayisə olunur
- **Kilid geri qaytarılmır** — açmaq üçün ayrıca səlahiyyət + səbəb tələb olunur

---

### MODUL B — Tələbə

#### 08 · Tələbə qəbulu — ATİS və qrup təyinatı
`design/08 Telebe qebulu - ATIS ve qrup teyinati.dc.html` · canvas **1440×1150**
**Məqsəd:** ATİS-dən gələn qəbul siyahısını import etmək, validasiyadan keçirmək, fakültələrə və qruplara paylamaq.

- Props: `role` = `Tələbə Mərkəzi | Tədris Şöbəsi müdiri | Dekanlıq | Proqram koordinatoru`
- State: `tab, q/qRaw, stage, fixed, impF, prog/progOpen, picked, assign, groups, newG, toast`
- **4 addımlı stepper:** `ATİS siyahısı yükləndi` → `Tədris şöbəsi yoxladı` → `Fakültələrə paylandı` → `Qruplara təyin edildi`
- KPI: **Cəmi sətir · Yoxlamadan keçdi · Bloklayan xəta · Xəbərdarlıq**
- **Validasiya mesajları (hərfi copy):**
  - `Uyğundur`
  - `FİN təkrarlanır — eyni şəxs iki sətirdə` (bloklayan)
  - `İxtisas kodu universitetdə tapılmadı` (bloklayan)
  - `Attestatın surəti yüklənməyib` (xəbərdarlıq)
- **Bloklayan xəta olan sətir qrupa təyin edilə bilmir**; `fixed` map düzəldilmiş sətirləri izləyir
- `newG` — dolu qrup halında yeni qrup yaratma

#### 09 · Tələbə reyestri və hərəkəti
`design/09 Telebe reyestri ve hereketi.dc.html` · canvas **1440×1150**
**Məqsəd:** tələbə reyestri və bütün akademik hərəkət əmrləri.

- Props: `role` = `Tələbə Mərkəzi | Dekanlıq | Proqram koordinatoru`
- State: `tab, q/qRaw, prog/progOpen, stat, form, moveF, card, move, toast`
- Tələbə sahələri: **Statusu · Kurs · GPA (4 ballıq) · İxtisas · Təhsil forması**
- KPI: **Cəmi tələbə · Əyani / qiyabi · Riskdə olan · Xüsusi statuslu · Açıq hərəkət əmri**
- **6 hərəkət növü — enum kimi saxla:**
  | # | Hərəkət | Qeyd |
  | --- | --- | --- |
  | 1 | Qrupdan qrupa köçürmə | qrup tutumu yoxlanılır |
  | 2 | İxtisasdan ixtisasa köçürmə | kredit tanınması tələb olunur |
  | 3 | Əyanidən qiyabiyə (və ya tərsi) | plan dəyişir |
  | 4 | Akademik məzuniyyət | müddət tələb olunur |
  | 5 | Bərpa | əvvəlki statusa istinad |
  | 6 | Xaric etmə | səbəb + əmr nömrəsi məcburi |
- Hər hərəkət: **əmr nömrəsi, tarix, səbəb, icraçı** ilə audit-ə yazılır. **Status dəyişikliyi silinmir — tarixçə yazısıdır.**
- `card` — tələbə kartı (drawer): şəxsi məlumat, akademik göstəricilər, hərəkət tarixçəsi

#### 10 · Tələbə kabineti
`design/10 Telebe kabineti.dc.html` · canvas **1360×1100**
**Məqsəd:** tələbənin öz görünüşü.

- Props: `transcriptPolicy` = `request | download` (bax §10, açıq qərar)
- Bölmələr (`view`): `syl` (sillabus) · `grade` (qiymətlər) · `att` (davamiyyət) · `req` (müraciətlər) · `ss` (semestr tarixçəsi)
- Data: `COURSES`, `DAYS`, `SLOTS`, `SCHED` (cədvəl), `DOCS`, `TICKETS`, `TERMS`, `NOTIF`
- Metrikalar: **Toplanmış bal · Gözlənilən GPA**
- Sillabus paneli: **yalnız APPROVED versiya göstərilir** (§8 qayda 9) — mövzular, qiymətləndirmə strukturu, sərbəst iş nəticələri, öz davamiyyəti, PDF
- Müraciət növləri: Transkript sorğusu · Arayış sorğusu · Qiymətə etiraz · Şikayət · Tələbə hərəkəti · Təhsil haqqı · Texniki problem
- `transcriptPolicy` = `download` → birbaşa möhürlü PDF; `request` → sorğu axını (3 iş günü)

#### 11 · Müraciətlər paneli
`design/11 Muracietler paneli.dc.html` · canvas **1400×1150**
**Məqsəd:** müraciətlərin (ticket) hər iki tərəfdən idarəsi.

- Props: `role` = `Tələbə | Müəllim | Tələbə Mərkəzi | Dekanlıq | Kafedra müdiri | Tədris Şöbəsi` — **rol görünüşü tam dəyişir**
- State: `tab, sel, q/qRaw, stat, kind/kindOpen, replies, states, newT, fwd, toast`
- Data: `TICKETS`
- 8 müraciət növü: Transkript sorğusu · Arayış sorğusu · Qiymətə etiraz · Şikayət · Tələbə hərəkəti · Təhsil haqqı · **Təqdimat** · Texniki problem
- Tələbə görünüşü KPI: **Açıq müraciətim · Məlumat gözlənilir · Cavablanıb · Orta cavab müddəti**
- İcraçı görünüşü KPI: **Mənə gələn açıq · Yeni — baxılmayıb** + orta cavab müddəti
- `fwd` — başqa bölməyə yönləndirmə (səbəb qeydi ilə); `replies` — cavab zənciri
- **SLA:** orta cavab müddəti göstərilir; gecikən müraciət warning rəngi alır

---

### MODUL C — Dərs yükü

Beş rollu təsdiq zənciri:
```
Tədris şöbəsi → Koordinator → Kafedra müdiri → Dekanlıq → Rektorluq
                                    ↓
                            Müəllim (təsdiq / etiraz)
```

#### 12 · Dərs yükü mərkəzi (Tədris şöbəsi)
`design/12 Ders yuku - Tedris shobesi.dc.html` · canvas **1440×960**
**Məqsəd:** ilin yük sətirlərini yaratmaq, kafedralara paylamaq, plandan import etmək, pipeline-ı izləmək.

- Görünüşlər (`state.view`): `dashboard` · `tasks` · `import` · `reports` (boş vəziyyət) · `settings` (boş vəziyyət)
- Daxili tab (`state.tab`): `editor` (sətir-sətir yük cədvəli) + dəstək panelləri
- Layout: KPI zolağı `repeat(4, minmax(0,1fr)); gap:14px` → filtr paneli → ağ kartda yük cədvəli
- Filtrlər: tədris ili · semestr · fakültə/kafedra · ixtisas · qrup — `applyFilters` / `resetFilters` cütü, **cədvəl yalnız `applied`-i oxuyur**
- Data: `CAT`

#### 13 · Koordinator — Yük vizası
`design/13 Koordinator - Yuk vizasi.dc.html` · canvas **1440×960**
**Məqsəd:** hər yük sətrini kafedra müdirinə çatmadan yoxlamaq, viza vermək və ya irad yazmaq.

- Görünüşlər: `queue` (default) · `history`
- State: `view, reviewed{}, remarks{}, modal, target, remarkText, fYear/fSem/fGroup/fState, applied`
- Sətir əməlləri: **baxıldı** açarı (`reviewed[i]`) · **İrad** (modal) · **Detal** (modal)
- **Qayda: irad yazılan sətrin `reviewed` bayrağı silinir** — sətir həm işarələnmiş, həm vizalanmış ola bilməz
- Göstəricilər: `"{done} sətirdən {n}-i baxılıb"` + faiz
- `reviewAll()` iradı olmayan bütün sətirləri vizalayır; `confirmSubmit()` görünüşü `history`-yə keçirir
- **İrad modalı validasiyası:** textarea boş olduqda amber `İrad göndər` düyməsi disabled; hint `Şərh kafedraya və dekana görünəcək.` (`#64748b`) → boşdursa `Şərh yazılmadan irad göndərilə bilməz.` (`#dc2626`)
- **Arxiv rejimi:** keçmiş il seçildikdə ekran read-only; qeyd `arxiv — yalnız oxunuş` (`#b45309`), əks halda `viza mərhələsi açıqdır` (`#2563eb`)

#### 14 · Kafedra müdiri — Yük bölgüsü
`design/14 Kafedra mudiri - Yuk bolgusu.dc.html` · canvas **1500×980**
**Məqsəd:** hər yük sətrini müəllimə təyin etmək və hamını norma daxilində saxlamaq.

- Görünüşlər: `dist` (bölgü cədvəli) · `teachers` (müəllim üzrə yük kartları) · `reports`
- Data: `ROWS`, `ACTS`, `TEACHERS`
- Saat növləri: **Mühazirə / Seminar / Laboratoriya**
- Müəllimin cari cəmi norma ilə müqayisə olunur → **normadan az / normada / normadan artıq** badge-i
- Filtrlənmiş nəticə boş olduqda `noRows` boş vəziyyəti

#### 15 · Dekanlıq — Yük təsdiqi
`design/15 Dekanliq - Yuk tesdiqi.dc.html` · canvas **1440×960**
**Məqsəd:** kafedraların yük paketlərini təsdiqləmək və ya qaytarmaq.

- Görünüşlər: `queue` · `summary` (fakültə yekunu) · `history`
- Növbədə iki tab (`state.tab`): `dean` (dekanı gözləyən sətirlər) · `coord` (koordinatorun bitirdiyi)
- State: `view, tab, reviewed{}, remarks{}, selected{}, modal, target, remarkText, returnText, fYear/fSem/fSpec/fGroup, applied`
- Sətir əməlləri: çoxseçim checkbox (`selected[i]`) · **İrad** modalı · **Detal** modalı
- Toplu əməllər: **Qaytar** (yalnız ≥1 sətir seçildikdə aktiv; əks halda `cursor:not-allowed`) · **Təsdiqlə** — hər ikisi modal ilə təsdiqlənir
- Status pill palitrası:
  | Status | fon | mətn | kontur |
  | --- | --- | --- | --- |
  | Göndərilib | `#dbeafe` | `#1d4ed8` | `#bfdbfe` |
  | Qaytarılıb | `#fee2e2` | `#b91c1c` | `#fecaca` |
  | Təsdiqlənib | `#dcfce7` | `#166534` | `#bbf7d0` |
- `summary` cədvəli: kafedra adı, ixtisaslar, sətir sayı, saat, kredit, status pill-i
- `history`: zəncir hadisələri vertikal timeline kimi (`✓ Koordinator — L. Hüseynova …`)

#### 16 · Müəllim — Şəxsi yük
`design/16 Muellim - Shexsi yuk.dc.html` · canvas **1440×1024**
**Məqsəd:** müəllim öz saatlarını görür, fərdi iş planını yoxlayır, yükü təsdiqləyir və ya etiraz edir.

- Görünüşlər: `load` · `plan` · `paid` · `notes`
- Data: `ROWS`, `PLAN`, `PAID`, `NOTES`, `REASONS`
- **1) Saat bölgüsü cədvəli** — sütunlar: fənn, kod, kredit, qrup, semestr, səviyyə, **mühazirə / seminar / laboratoriya / digər** saat, tələbə sayı, həftəlik, status. Auditoriya dərsi olmayan sətirlər (məs. `Kurs işi rəhbərliyi`) kod/kredit/həftəlik üçün `—` yazır.
- **2) Fərdi iş planı** (`PLAN`) — 4 nömrələnmiş bölmə, plan/fakt saatı ilə:
  | # | Bölmə | Qeyd | plan / fakt |
  | --- | --- | --- | --- |
  | 1 | Tədris işi | Auditoriya saatları, kurs və buraxılış işləri | 780 / 402 |
  | 2 | Metodiki iş | Sillabus, fənn proqramı, test bankı | 120 / 65 |
  | 3 | Elmi-tədqiqat işi | Məqalə, konfrans, layihə | 200 / 110 |
  | 4 | İnzibati / ictimai iş | (fayla bax) | |
  Element statusu (`ok` kodu): `İcra olunub` (1) · `İcra olunmada` (2) · `Planda` (0)
- **3) Ödəniş kalkulyatoru** — saat × tarif, törəmə, read-only
- **4) Təsdiq / etiraz** — yükü təsdiqlə, ya da etiraz göndər (`{subject, text, when, status}`)
- **Etiraz səbəbləri (`REASONS`, hərfi copy):** `Saat sayı düz deyil` · `Qrup/tələbə sayı səhvdir` · `Fənn ixtisasım deyil` · `Norma həddindən artıqdır`

#### 17 · Rektor — Ümumi baxış
`design/17 Rektor - Umumi baxish.dc.html` · canvas **1440×1024**
**Məqsəd:** universitet üzrə nəzarət; sətir səviyyəsində redaktə YOXDUR.

- Görünüşlər: `overview` · `fac` (5 fakültə) · `dep` (16 kafedra) · `rep`
- Başlıqlar: `Universitet üzrə dərs yükü` — «2026 / 2027 tədris ili — tapşırıqdan müəllim təsdiqinə qədər bütün mərhələlərin vəziyyəti.» · `Fakültələr üzrə yük` · `Kafedralar üzrə bölgü` · `Hesabatlar` — «Elmi Şura və nazirlik formatında hazır hesabatlar.»
- **Yük bantları (rəng şkalası):** `Normadan az (< 90%)` · `Normada (90–105%)` · `Norma üstü (105–125%)` · `Kritik yüklü (> 125%)`
- Bloklar: 4-lük KPI grid-i (`repeat(4, minmax(0,1fr)); gap:14px`, kart `padding:17px 19px`) · fakültə bölgü barları · təsdiq pipeline vizualizasiyası · riskli kafedralar (sidebar-da amber sayğac) · fakültə/kafedra cədvəlləri
- Data: `DEPS` (16 kafedra: `fac, name, head, teachers, hours, pct, vacant, over`), `FACS`, `REPORTS`
- **⚠ Aqreqasiya qaydası:** fakültə və universitet yekunları `DEPS`-dən hesablanır. Real implementasiyada da **yalnız aqreqasiya edilir, yekun rəqəmlər ayrıca saxlanılmır** — əks halda üç səviyyə bir-birindən ayrılır.
- Zebra: cüt `#ffffff`, tək `#f8fafc`

---

### MODUL D — Sillabus və jurnal

#### 18 · Müəllim — Sillabuslar
`design/18 Muellim - Sillabuslar.dc.html` · canvas **1440×1120**
**Məqsəd:** müəllim öz fənlərinin sillabus statusunu görür, filtrləyir, əməl edir.

- Görünüşlər/modallar: `table` · `card` · `minor` · `major`
- Data: `ORDER` (sıralama), `DATA`, `BLOCKS`, `HIST` (versiya tarixçəsi)
- **5 KPI kartı (klikləndikdə filtr tətbiq edir, `aria-pressed`):**
  | Kart | fon / kontur / mətn |
  | --- | --- |
  | Cari il üzrə fənn | `--ems-neutral-0` / `--ems-neutral-200` / `--ems-neutral-900` |
  | Təsdiqlənib | `--ems-success-bg` / `#bbf7d0` / `#15803d` |
  | Təsdiq gözləyir | `--ems-primary-50` / `--ems-primary-200` / `--ems-primary-800` |
  | Düzəliş tələb olunur | `--ems-warning-bg` / `#fde68a` **2px** / `#92400e` |
  | Sillabussuz fənn | `--ems-danger-bg` / `#fecaca` / `#b91c1c` |
- Filtrlər: axtarış (240ms debounce) + `Akademik il` · `Semestr` · `Kafedra` + 4 sıralama (son dəyişikliyə, fənn adına, tamamlanma faizinə, statusa) + **Cədvəl ⇄ Kart** açarı
- Sütunlar: Fənn (kod monospace + ad + proqram) · Semestr · Versiya · Tamamlanma % · Status + təsdiqləyən · Əməllər · `PDF yüklə`
- **7 status — dəqiq enum:**
  | key | label | fon | mətn | accent |
  | --- | --- | --- | --- | --- |
  | `draft` | Qaralama | `--ems-neutral-100` | `--ems-neutral-700` | `--ems-neutral-300` |
  | `submitted` | Təqdim edilib | `--ems-primary-100` | `--ems-primary-800` | `--ems-primary-600` |
  | `review` | Baxışdadır | `--ems-primary-50` | `--ems-primary-800` | `--ems-primary-600` |
  | `revision` | Düzəliş tələb olunur | `--ems-warning-bg` | `#92400e` | `--ems-warning` |
  | `approved` | Təsdiqlənib | `--ems-success-bg` | `#15803d` | `--ems-success` |
  | `rejected` | Rədd edilib | `--ems-danger-bg` | `#b91c1c` | `--ems-danger` |
  | `archived` | Arxivlənib | `--ems-neutral-100` | `--ems-neutral-500` | `--ems-neutral-200` |
  Statusa görə sıralama: `revision → rejected → draft → submitted → review → approved → archived`
- **Statusa görə «növbəti addım» mətni** (sətir altında):
  draft → «Qaralamanı tamamlayıb təsdiqə göndər» · submitted → «Kafedra müdirinin baxışı gözlənilir» · review → «Baxış nəticəsi gözlənilir» · revision → «Kafedra qeydlərini nəzərə alıb yenidən göndər» · approved → «Əməl tələb olunmur — versiya kilidlidir» · rejected → «Rədd səbəbini oxuyub yeni versiya yarat» · archived → «Arxiv qeydi — yalnız baxış»
- **Dialoqlar:** *Yeni versiya* — **Kiçik (v1.2)** «Ədəbiyyat, məsləhət saatı, mövzu adının redaktəsi. Jurnal strukturu dəyişmir, cari semestrə tətbiq olunur.» / **Böyük (v2.0)** növbəti semestrdən; OK `Qaralama yarat`. *Keçən ildən köçür* — nəticə **yalnız QARALAMA**. *Təqdimatı geri çağır* — **səbəb məcburi**, OK rəngi `--ems-warning`.
- Boş vəziyyət: «Filtrə uyğun sillabus yoxdur» + `Filtrləri sıfırla`

#### 19 · Müəllim — Sillabus redaktoru
`design/19 Muellim - Sillabus redaktoru.dc.html` · canvas **1480×1120**
**Məqsəd:** 10 bölməli wizard; qaralamanı doldurub təsdiqə göndərmək.

- Props: `viewState` = `normal | readonly | loading | permission` · `saveState` = `saved | saving | failed | offline | conflict | stale`
- Data: `SEC` (10 bölmə), `RULE` (8 validasiya qaydası), `METHODS`, `HIST`
- Layout: sol = addım naviqasiyası (sticky), mərkəz = aktiv bölmə, sağ = kontekst (versiya tarixçəsi, autosave çipi)
- **10 bölmə (`id` dəyərlərini saxla):**
  | id | Başlıq | Validasiya |
  | --- | --- | --- |
  | `info` | Ümumi məlumat | tədris planından gəlir, **kilidli**; yalnız müəllim seçimi redaktə olunur |
  | `desc` | Təsvir və məqsəd | mətn tələb olunur |
  | `out` | Təlim nəticələri | **ən azı 3** nəticə |
  | `week` | Həftəlik mövzular | auditoriya saatları həftələrə tam bölünməli |
  | `method` | Tədris metodları | **ən azı 2** metod |
  | `assess` | Qiymətləndirmə | davamiyyət/sərbəst iş/yekun çəkiləri **siyasətlə kilidli** |
  | `self` | Sərbəst iş | 3 icazəli variant, cəmi 10 bal |
  | `lit` | Ədəbiyyat | əsas ≥2, əlavə ≥1 mənbə |
  | `prev` | Preview | tələbə və kafedra ilə eyni görünüş |
  | `send` | Təsdiqə göndərmə | yuxarıdakı 8 qayda (`RULE`) ödənməlidir |
- Addım naviqasiyası 3 vəziyyət: tamamlanıb (yaşıl tik) / çatışır (boz) / xəta (qırmızı). Aktiv addım `--ems-primary-50` fon + `--ems-primary-600` sol kontur.
- Ümumi məlumat sahələri: Fənnin adı və kodu · Fakültə · Kafedra · Təhsil proqramı — hamısı plandan, read-only
- **Sərbəst iş variantları:** `1x10` «Bir böyük sərbəst iş — semestr layihəsi formatına uyğundur.» · `2x5` «İki tapşırıq — semestrin ortası və sonu üçün balanslı variant.» · `10x1` «Hər həftə kiçik tapşırıq — davamlı iş tələb edir.» · **`3x5` — disabled kart:** «Universitet siyasətinə uyğun deyil — cəmi 15 bal edir.» (`cursor:not-allowed`, fon `--ems-neutral-50`, mətn `--ems-neutral-400`, cəm `--ems-danger`). **Bu kartı silmə** — siyasəti izah edir.
- **Tədris metodları (`METHODS`):** Mühazirə · İnteraktiv müzakirə · Problem əsaslı öyrənmə · Layihə əsaslı iş · Laboratoriya təcrübəsi · Case study təhlili · Kod baxışı (peer review) · Fərdi məsləhət
- **`saveState` — 6 vəziyyət, hər biri üçün ayrı banner:**
  | dəyər | banner | rəng |
  | --- | --- | --- |
  | `saved` | «Saxlanıldı» çipi | success |
  | `saving` | spinner | primary |
  | `failed` | «Son dəyişiklik saxlanılmadı» — server 503, mətn brauzerdə saxlanılıb; **Retry düyməsi** | danger |
  | `offline` | «İnternet bağlantısı yoxdur» — dəyişikliklər növbəyə alınır, təsdiqə göndərmə bloklanır | warning |
  | `conflict` | «Başqa versiya ilə konflikt yarandı» — 2 CTA: öz versiyanı saxla / serverdəkini götür | danger |
  | `stale` | «Səhifədəki məlumat köhnəlmişdir» — yeniləmə tələb olunur | warning |
- **`viewState`:** `readonly` → «Bu versiya təsdiqlənib və dəyişdirilə bilmir», bütün input-lar disabled · `loading` → skeleton · `permission` → icazə yoxdur
- **Təsdiqə göndərmə dialoqu:** «Sillabus kafedra təsdiqinə göndərilsin?» — göndərildikdən sonra versiya **kilidlənir**, yalnız düzəliş tələbi gələndə açılır. OK `Göndər` (`--ems-primary-600`), Cancel `Geri qayıt`. Uğur toast-ı: «v2.0 kafedra müdirinin təsdiq növbəsinə göndərildi. Cavab gələnə qədər tələbələr v1.1-i görür.»
- **Silmə qadağası:** qiyməti olan sərbəst iş mövzusu silinmir → «Arxivə köçür» dialoqu (warning)

#### 20 · Kafedra müdiri — Sillabus təsdiqi
`design/20 Kafedra mudiri - Sillabus tesdiqi.dc.html` · canvas **1480×1080**
**Məqsəd:** təsdiq növbəsi, review, versiya müqayisəsi, qərar.

- Props: `role` = `kafedra | dekan | noscope`
- Data: `SECS` (bölmə-bölmə sillabus), `DIFFS`, `AUDIT`
- KPI: **Növbədə gözləyən · 10 gündən çox gözləyir · Çatışmayan bölməsi var · Orta gözləmə**
- Filtrlər: `Status` · `Sıralama` · semestr (`2026/2027 payız`)
- Analitika: **Təsdiq faizi · Təsdiqlənmiş · Baxışda · Gecikib** + kafedra/proqram breakdown-u
- Review paneli: bölmə-bölmə sillabus + **hər bölməyə şərh sahəsi**
- **Diff kartı** — v1.1 ↔ v2.0 yanaşı (köhnə `--ems-danger-100`, yeni `--ems-success-100`)
- **Audit timeline** — nöqtə rəngi statusa uyğun (`--ems-primary-600` cari, `--ems-success` təsdiq, `--ems-neutral-300` köhnə)
- **3 qərar düyməsi:** `Təsdiqlə` (success) · `Düzəliş üçün geri qaytar` (warning, **səbəb məcburi**) · `Rədd et` (danger, **səbəb məcburi**)
- `role = noscope` → əhatə yoxdur: boş vəziyyət + administrator CTA (§8 qayda 8)

#### 21 · Müəllim — Keçilmiş dərslər
`design/21 Muellim - Kecilmish dersler.dc.html` · canvas **1420×1150**
**Məqsəd:** keçirilmiş dərslərin və jurnal qeydlərinin izlənməsi.

- Props: `role` = `Müəllim | Kafedra müdiri | Dekanlıq | Tədris Şöbəsi müdiri`
- State: `range, from, to, q/qRaw, course/courseOpen, kind, onlyFlagged, teacher, toast`
- Data: `TEACHERS`, `COURSES`, `GROUPS`, `SLOTS`, `WD`, `MON`, `RANGES`
- KPI: **Keçilmiş dərs · Auditoriya saatı · Orta iştirak · Jurnalı boş dərs · Gec yazılan qeyd**
- **Qeyd statusu 3 vəziyyət:** `Vaxtında yazılıb` (success) · `Gec yazılıb` (warning) · `Jurnal boşdur` (danger)
- `onlyFlagged` — yalnız problemli dərsləri göstərir; `range/from/to` tarix aralığı (`RANGES` presetləri)
- `role` müəllimdən yuxarı olduqda `teacher` filtri açılır — müəllim üzrə nəzarət görünüşü
- Kontekst panelində jurnal və sillabus keçidləri

---

## 6. Axınlar və state maşınları

### 6.1 Struktur → semestr
```
Struktur (01) → İxtisas (03) → Fənn kataloqu (04) → Tədris planı (05)
   ↓ təsdiq zənciri: Qaralama → Kafedra baxışı → Fakültə şurası → Tədris şöbəsi → Təsdiqlənib
Təsdiqlənmiş plan → Semestr açılışı (07) → Müəllim təyinatı → Jurnal → Semestr kilidi
```
`Plan yoxdur` bayrağı olan ixtisas üçün semestr açılışı **mümkün deyil**.

### 6.2 Tələbə
```
ATİS import (08) → validasiya → fakültə → qrup təyinatı → Reyestr (09)
Reyestrdən 6 hərəkət növü → əmr + səbəb + audit → status dəyişikliyi (tarixçə yazısı)
```

### 6.3 Dərs yükü
```
Tədris şöbəsi (12) yaradır → Koordinator (13) viza/irad → Kafedra müdiri (14) müəllimə bölür
   → Dekanlıq (15) təsdiq/qaytarma → Rektor (17) nəzarət
                    ↓
        Müəllim (16) təsdiq / etiraz (4 səbəbdən biri)
```
İrad yazılan sətir vizalanmış sayılmır. Keçmiş il = arxiv, read-only.

### 6.4 Sillabus (7 status)
```
DRAFT ──(Təsdiqə göndər)──> SUBMITTED ──(müdir açır)──> REVIEW
  ^                              │                        │
  │                              │(Geri çağır, səbəb)     ├─(Təsdiqlə)──────> APPROVED [kilidli]
  └──────────────────────────────┘                        ├─(Düzəliş, səbəb)─> REVISION ──> DRAFT
                                                          └─(Rədd et, səbəb)─> REJECTED
APPROVED ──(Yeni versiya)──> kiçik v1.2 (cari semestr) | böyük v2.0 (növbəti semestr) → DRAFT
Köhnə APPROVED ──(yeni versiya təsdiqlənəndə)──> ARCHIVED
```

### 6.5 Jurnal
```
Təsdiqlənmiş sillabus → jurnal strukturu yaranır (sillabus yoxdursa kilid + səbəb + CTA)
Davamiyyət/qiymət → Saxla → Təqdim et → Kafedra Təsdiqlə → Şöbə Dərc et → Kilidlə
Düzəliş yalnız sənədli sorğu ilə (səbəb + protokol nömrəsi)
```

---

## 7. Accessibility

- Hər input və select-in **görünən `label`-i** var (yoxdursa `aria-label`); ikonlar `aria-hidden="true"`.
- Cədvəllərdə `th scope="col"` / `th scope="row"`; sıralanan başlıqlar `aria-sort`.
- **Status yalnız rənglə deyil, mətnlə də verilir** — badge mətni, «qayıb / iştirak», validasiya mesajı.
- Dialoq və drawer: `role="dialog" aria-modal="true"` + `aria-labelledby`; açılışda fokus içəri keçir, **fokus tələsi** var, Escape bağlayır, bağlananda fokus əvvəlki elementə qayıdır.
- Tab-lar `aria-current`, açar düymələr `aria-pressed`, canlı bildirişlər `role="status" aria-live="polite"`.
- `:focus-visible` outline heç bir yerdə söndürülməyib.
- Kontrast: status mətnləri `#15803d` / `#92400e` / `#b91c1c` / `#166534` öz açıq fonları üzərində WCAG AA.
- Klaviatura ilə tam keçid: ağac naviqasiyası (01), cədvəl sıra əməlləri, searchable dropdown-lar (oxlarla naviqasiya + Enter).

---

## 8. Backend acceptance qaydaları

**Ən vacib şərt:** APPROVED sillabus həftəlik mövzuların, qiymətləndirmə strukturunun və sərbəst iş konfiqurasiyasının **dəyişdirilməz source-of-truth**-udur. Jurnal həmin təsdiqlənmiş versiyadan yaranır və heç bir əməliyyat tarixi qiymət/davamiyyət məlumatını silmir.

0. **Bir mövzu — bir neçə dərs növü.** Sillabusun həftəlik planında mövzu bir dəfə yazılır, saat isə mühazirə / seminar / laboratoriya üzrə ayrıca saxlanılır. Jurnalda həmin mövzu hər növ üçün ayrı dərs sətri kimi açılır — başlıq eynidir, `kind` fərqlidir. Keçirilmiş saat hər növ üzrə ayrıca hesablanır və tədris planındaki bölgü (məs. 30/16/14) ilə müqayisə olunur; ayırma pozulduqda təsdiqə göndərmə bloklanır.
1. **APPROVED versiya immutable-dır:** PATCH/PUT qəbul edilmir; dəyişiklik yalnız yeni versiya (minor/major) yaradır. Eyni qayda təsdiqlənmiş tədris planına aiddir.
2. Jurnal yaradılması təsdiqlənmiş sillabus olmadan **bloklanır** (403 + səbəb kodu); icazə varsa yalnız read-only görünüş qaytarılır.
3. Sərbəst işin ümumi maksimumu **10 bal**; icazə verilən strukturlar yalnız `1×10`, `2×5`, `10×1`. Digər kombinasiya (məs. `3×5`) validasiya xətası verir. Jurnaldaki sərbəst iş sütunlarının sayı və hər sütunun maksimum balı sillabusdan gəlir.
4. **Qiymətləndirmə çəkiləri:** davamiyyət 10, sərbəst iş 10, yekun imtahan 50 — universitet siyasəti ilə kilidli; müəllim yalnız qalan **30 balı** bölür. Cəm həmişə 100.
5. **Silmə yoxdur — arxivləmə var.** Mövzu, sərbəst iş tapşırığı, ixtisas, fənn, qrup: `archived` bayrağı ilə istifadədən çıxarılır; əlaqəli qiymətlər və tarixçə saxlanılır.
6. **Səbəb məcburi olan əməllər** (≥20 simvol, audit-ə istifadəçi + timestamp ilə yazılır): «Geri qaytar», «Rədd et», «Yenidən aç», «Düzəliş sorğusu», «İrad», «Arxivləmə», «Xaric etmə», «Semestr kilidini aç».
7. **Qiymət dəyişikliyi əvəzləmə deyil, versiyalı yazıdır:** köhnə dəyər, yeni dəyər, səbəb və protokol nömrəsi saxlanılır.
8. **Scope qaydası: `no scope ≠ bütün universitet`.** Əhatəsi olmayan istifadəçiyə məlumat qaytarılmır (boş vəziyyət + administrator kanalı). Tələbə — yalnız öz məlumatı; müəllim — öz dərsləri; kafedra müdiri — öz kafedrası; dekan — öz fakültəsi; registrar — verilmiş təşkilati əhatə.
9. Tələbəyə **yalnız APPROVED versiya** göstərilir; yeni versiya baxışdadırsa əvvəlki təsdiqlənmiş versiya aktiv qalır.
10. **Autosave:** konflikt (409) halında server versiyası ilə müqayisə təklif olunur; istifadəçi dəyişikliyi səssizcə itirilmir.
11. Auditoriya saatlarının cəmi tədris planındaki saatla üst-üstə düşməlidir; uyğunsuzluq təsdiqə göndərməni bloklayır.
12. Semestr açılışı zamanı sillabusu olmayan fənlər gecikmə hesabatına düşür (coverage KPI-ları buradan hesablanır).
13. **Aqreqasiya yalnız aşağıdan yuxarı:** kafedra → fakültə → universitet. Yekun rəqəmlər ayrıca saxlanılmır (17-ci ekran).
14. **Filtr semantikası:** `applied` state server sorğusuna çevrilir; draft filtr dəyəri sorğu göndərmir. Sıralama və pagination server tərəfdə.

### Təxmini model xəritəsi

| Sahə | Modellər |
| --- | --- |
| Struktur | `OrgUnit` (tip enum, self-FK ağac), `Person`, `HeadAssignment`, `StaffPosition` (ştat/əvəzçilik/saathesabı), `NormSet` |
| Kataloq | `Program` (ixtisas), `Course` (fənn), `CourseBlock`, `Prerequisite`, `CurriculumPlan`, `PlanRow`, `PlanApproval` |
| Semestr | `Term`, `TermOffering` (açılış), `TeacherAssignment`, `Group`, `ScheduleSlot`, `TermLock` |
| Tələbə | `Student`, `Admission` (ATİS sətri + validasiya nəticəsi), `StudentMovement` (6 növ), `Ticket`, `TicketReply` |
| Yük | `LoadLine`, `LoadReview` (viza/irad), `LoadApproval`, `IndividualPlan`, `PlanItem`, `LoadObjection` |
| Sillabus | `Syllabus` (versiya, status, müəllif, təsdiqləyən, kilid tarixi), `SyllabusSection`, `SyllabusReview`, `SyllabusAudit` |
| Jurnal | `Journal`, `JournalLesson` (`kind`), `Attendance`, `Grade`, `GradeRevision`, `JournalApproval` |
| Ümumi | `AuditLog` (aktor, əməl, obyekt, səbəb, timestamp) — **bütün səbəb tələb edən əməllər buraya yazılır** |

---

## 9. İmplementasiya ardıcıllığı

Data asılılığına görə **bu sıra ilə** gedin — geriyə asılılıq yoxdur:

| Mərhələ | Əhatə | Ekranlar |
| --- | --- | --- |
| **0** | Shell + tokenlər + komponent kitabxanası (§2, §3, §4) | 00 |
| **1** | Struktur və kataloq | 01, 02, 03, 04 |
| **2** | Tədris planı + semestr açılışı | 05, 06, 07 |
| **3** | Tələbə qəbulu və reyestr | 08, 09 |
| **4** | Dərs yükü zənciri | 12, 13, 14, 15, 16, 17 |
| **5** | Sillabus və təsdiq | 18, 19, 20 |
| **6** | Jurnal izi + tələbə görünüşü + müraciətlər | 21, 10, 11 |

Mərhələ 0 atlanmamalıdır: 22 ekranın hamısı həmin 14 komponentdən qurulur. Komponentləri əvvəlcədən yazmasanız hər ekranda təkrar iş çıxacaq.

---

## 10. Açıq qalan product qərarları

Bu 4 məsələ **dizaynda hər iki variant hazır** şəkildə saxlanılıb — qərar veriləndən sonra yalnız policy dəyəri dəyişir, yeni UI lazım deyil.

1. **Transkript (əsas açıq qərar)** — `transcriptPolicy` prop-u (ekran 10):
   - **A `download`:** kabinetdən elektron möhürlü PDF, müraciət yoxdur. Sürətli; möhür/imza siyasəti və QR verifikasiyası tələb edir.
   - **B `request`:** Tələbə Xidmətləri Mərkəzinə sorğu, 3 iş günü. Mövcud kağız prosesə uyğundur.
   Qərar sahibi: Tədris şöbəsi + Tələbə Xidmətləri.
2. **İkinci (dekan) təsdiqi** — məcburi proses kimi qurulmayıb; policy parametri kimi göstərilib (default: söndürülüb). Açıldıqda marşrut kafedra → dekan kimi uzanır (ekran 20, `role=dekan`).
3. **Kiçik/böyük versiya təsnifatı** — hazırda müəllimin seçimidir; avtomatik qayda (mövzu/çəki/struktur dəyişikliyi → major) təsdiq edilməlidir.
4. **Sillabus təsdiq SLA-sı** — dizaynda hədəf 5 gün, «10 gündən çox gözləyir» KPI-ı var; rəsmi müddət qərarlaşdırılmalıdır.

**Norma dəyərləri** (ekran 02, `normSet`) da policy cədvəlindən oxunmalıdır — kodda hardcode edilməməlidir.

---

## 11. Fayl siyahısı

| Fayl | Modul | Nədir |
| --- | --- | --- |
| `00 Dizayn konstantlari.dc.html` | Baza | **token, status, tipoqrafiya, komponent kataloqu** |
| `01 Tedris shobesi - Universitet strukturu.dc.html` | A | struktur ağacı |
| `02 Tedris shobesi - Kafedra profili.dc.html` | A | kafedra, ştat, müəllim heyəti |
| `03 Tedris shobesi - Ixtisaslar.dc.html` | A | ixtisas reyestri |
| `04 Tedris shobesi - Fenn kataloqu.dc.html` | A | fənn reyestri |
| `05 Tedris plani redaktoru.dc.html` | A | tədris planı |
| `06 Tedris shobesi - Qruplar.dc.html` | A | qruplar və cədvəl |
| `07 Tedris shobesi - Semestr acilishi.dc.html` | A | semestr açılışı |
| `08 Telebe qebulu - ATIS ve qrup teyinati.dc.html` | B | ATİS import |
| `09 Telebe reyestri ve hereketi.dc.html` | B | reyestr, hərəkət əmrləri |
| `10 Telebe kabineti.dc.html` | B | tələbə kabineti |
| `11 Muracietler paneli.dc.html` | B | müraciətlər |
| `12 Ders yuku - Tedris shobesi.dc.html` | C | yük mərkəzi |
| `13 Koordinator - Yuk vizasi.dc.html` | C | koordinator vizası |
| `14 Kafedra mudiri - Yuk bolgusu.dc.html` | C | müəllimlərə bölgü |
| `15 Dekanliq - Yuk tesdiqi.dc.html` | C | dekanlıq təsdiqi |
| `16 Muellim - Shexsi yuk.dc.html` | C | şəxsi yük, fərdi plan |
| `17 Rektor - Umumi baxish.dc.html` | C | rektor analitikası |
| `18 Muellim - Sillabuslar.dc.html` | D | sillabus siyahısı |
| `19 Muellim - Sillabus redaktoru.dc.html` | D | 10 bölməli redaktor |
| `20 Kafedra mudiri - Sillabus tesdiqi.dc.html` | D | təsdiq, diff, audit |
| `21 Muellim - Kecilmish dersler.dc.html` | D | keçilmiş dərslər |
| `support.js` | — | prototip runtime — **layihəyə köçürülmür** |
| `brand/wcu-logo-horizontal.svg` | — | top bar logosu (34px hündürlük) |
| `brand/logo-mark.png` | — | kvadrat mark (favicon / kompakt kontekst) |
| `_extract.md` | — | ekranların props/state/array xülasəsi (avtomatik çıxarış) |

**İkonlar:** inline SVG, `24×24` viewBox, `stroke: currentColor`, `stroke-width: 1.8` (chevron 2.2–2.6), yuvarlaq caps və joins — Feather üslubu. Layihədə mövcud ikon dəsti varsa onu istifadə et; stroke qalınlığını və ölçüləri (nav 20px, header 17px) saxla.
**Raster şəkil yoxdur, web font yoxdur** — sistem şrift stack-i qəsdəndir.
