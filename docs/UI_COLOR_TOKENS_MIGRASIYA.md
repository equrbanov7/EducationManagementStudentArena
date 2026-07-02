# UI rəng token-ları — miqrasiya bələdçisi

## İCRA STATUSU (2026-07-01)

- ✅ `static/css/design-tokens.css` yaradıldı və **hər yerdə** yükləndi
  (base.html + base_auth.html + 6 standalone live_exam template).
- ✅ **623 hardcoded hex → token** miqrasiya edildi (17 böyük CSS faylı,
  behavior-neutral — eyni dəyər). Fayllar: host_lobby, player, wait_room, join,
  host_lobby_shell, test_question_bank, coding_exam, take_exam, teacher_questions_bank,
  teacher_exam_detail, exam_result, teacher_check_attempt, appeals, register, navbar,
  ai_assistant, blog/profile.
- ✅ **2026-07-02 (Faza 6.1-6.2, audit icra planı):** qalan BÜTÜN uyğun CSS
  faylları miqrasiya edildi — **+2723 hex → var(--ems-*)** (155 fayl, skript:
  sərhəd-təhlükəsiz regex, `url(` sətirlərinə toxunulmur). design-tokens.css-ə
  yeni token ailələri əlavə olundu: `--ems-gray-200/500` (legacy gray),
  `--ems-warning-100/500/600/800` (amber), `--ems-danger-100/200/500`,
  `--ems-success-100/600`. ✅ HƏLL OLUNDU (eyni gün): `errors/*.html` (5)
  + `admin/verify_otp.html` şablonlarına design-tokens linki əlavə edildi və
  `error-pages.css` (+19) / `admin_otp.css` (+2) də miqrasiya olundu — artıq
  İSTİSNA YOXDUR.
- ⬜ Qalan iş: `url()`-daxili/istisna fayllardakı ~18 map-lənmiş hex + aşağı
  tezlikli legacy hex-lər (#eee/#333/#555...) — semantik qərar tələb edir.


## Problem

Layihədə **881 CSS custom-property** təyin olunub, amma brend rəngləri hələ də
fayllar boyu **hardcode** edilir (vahid mənbə yoxdur):

| Rəng | İstifadə sayı | Məna |
|------|---------------|------|
| `#ffffff` / `#fff` | ~718 | ağ (fon/mətn) |
| `#2563eb` | 269 | əsas brend mavisi |
| `#1d4ed8` | 139 | mavi (hover) |
| `#64748b` | 135 | boz mətn |
| `#f8fafc` | 123 | subtle fon |
| `#e2e8f0` | 112 | border |
| `#0f172a` | 94 | tünd mətn |
| `#dc2626` | 76 | danger |
| `#10b981` | 59 | success |

Nəticə: rebrand / dark-mode / kontrast düzəlişi **269+ yerdə əl ilə** dəyişməyi
tələb edir; rənglər faylar arası **fərqlənə bilir** (uyğunsuz UI).

## Həll

`static/css/design-tokens.css` — mövcud de-fakto palitranı vahid `var(--ems-*)`
token-larına çevirir (vizual dəyişiklik YOXDUR — eyni hex dəyərləri). Bu fayl
base template-də (bütün digər CSS-lərdən ƏVVƏL) yüklənməlidir:

```html
<link rel="stylesheet" href="{% static 'css/design-tokens.css' %}">
```

## Miqrasiya (tədricən, təhlükəsiz — hər PR bir neçə fayl)

1. Yeni/redaktə olunan CSS-də hex ƏVƏZİNƏ token işlət:
   ```css
   /* əvvəl */  color: #2563eb;
   /* sonra */  color: var(--ems-primary-600);
   ```
2. Mövcud faylları böyükdən-kiçiyə miqrasiya et (host_lobby.css 3606, player.css
   1576, ...). Hər fayl üçün: hex → token sed-əvəzləməsi + vizual smoke.
3. **Təhlükəsizlik:** əvəzləmə eyni-rəng (behavior-neutral) olmalıdır; token
   dəyəri hex ilə eyni. Yalnız adlandırma dəyişir.

## Tövsiyə olunan avtomatlaşdırma

Hər böyük CSS üçün:
```
sed -i 's/#2563eb/var(--ems-primary-600)/gI; s/#1d4ed8/var(--ems-primary-700)/gI; ...' fayl.css
```
Sonra brauzer/regress smoke. **Kütləvi avtomatik əvəzləmə nəzarətsiz
edilməməlidir** — hər fayl ayrıca yoxlanmalıdır (bəzi hex-lər gradient/rgba
kontekstində fərqli davrana bilər).


## İnline style → klass miqrasiyası (Faza 6.4, 2026-07-02)

**İnventar:** cəmi 501 `style=""` atributu, bunun **165-i email şablonlarındadır
və QANUNİDİR** (email klientləri xarici/embedded CSS-i dəstəkləmir — inline
industry-standarddır; bu fayllar hədəfdən ÇIXARILIB). **Browser hədəfi: 336.**

**Qaydalar:**
1. Email şablonlarına (`*email*/`, `*mail*`) toxunulmur.
2. Dinamik dəyərlər (`style="width:{{ x }}%"`) inline qalır — bu, düzgün pattern-dir.
3. `style="display:none"` JS-toggle ilə işləyirsə klassa keçid JS-lə birgə edilməlidir
   (kor-koranə `hidden` atributuna keçmək `el.style.display=""` açılışını sındırar).
4. Statik dekorativ atributlar səhifənin ÖZ CSS faylına semantik klass kimi köçür,
   rənglər `var(--ems-*)` tokenləri ilə.

**Sprint-1 ✅:** `teacher_live_session_detail.html` — 22 atributdan 20-si klassa
(`sd-ai-panel`, `sd-charts-grid`, `sd-num--correct/incorrect/muted`,
`sd-bar__text--green/blue/red`, `sd-col-*` və s.), 2 dinamik width inline (düzgün).

**Növbəti hədəflər (browser, çoxdan-aza):** `teacher_exam_statistics.html` (19),
`_create_exam_modal_form.html` (16), `exam_live_monitor.html` (15) → eyni pattern.
