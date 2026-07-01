# UI rəng token-ları — miqrasiya bələdçisi

## İCRA STATUSU (2026-07-01)

- ✅ `static/css/design-tokens.css` yaradıldı və **hər yerdə** yükləndi
  (base.html + base_auth.html + 6 standalone live_exam template).
- ✅ **623 hardcoded hex → token** miqrasiya edildi (17 böyük CSS faylı,
  behavior-neutral — eyni dəyər). Fayllar: host_lobby, player, wait_room, join,
  host_lobby_shell, test_question_bank, coding_exam, take_exam, teacher_questions_bank,
  teacher_exam_detail, exam_result, teacher_check_attempt, appeals, register, navbar,
  ai_assistant, blog/profile.
- ⬜ Qalan CSS faylları (bulk_workbench_extras, teacher_exam_statistics və s.) —
  eyni sed pattern ilə tədricən.


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
