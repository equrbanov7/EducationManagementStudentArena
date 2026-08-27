# Giriş balı: köhnə və yeni sistemin MODEL fərqi

**Tarix:** 2026-08-27, gecə
**Status:** ⚠️ SAHİBİN QƏRARI TƏLƏB OLUNUR — kod DƏYİŞDİRİLMƏYİB

Köhnə sistemin düsturu datadan çıxarıldı (bax `LEGACY_GIRISH_FORMULA.md`,
çap olunmuş bal vərəqləri ilə 97.24 % dəqiq təsdiq). Onu yeni sistemin
`entry_score_for` funksiyası ilə tutuşdurdum. **Üç struktur fərqi var.**

---

## Fərq 1 — Davamiyyət balı

| | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Davamiyyət | `10 × (N − qayıb) / N` → **0-10 bal** | Giriş balına **HEÇ NƏ vermir** |

Köhnə sistemdə tələbə sadəcə dərsə gəlməklə 50 balın **10-nu** qazanırdı.
Yeni sistemdə davamiyyət yalnız **qadağan** mexanizmidir (qayıb limiti aşılsa
imtahana buraxılmır) — bal vermir.

**Nəticə:** eyni tələbə eyni fəaliyyətlə yeni sistemdə 10 bal AZ alır.

---

## Fərq 2 — Orta vs Cəm

| | Köhnə | Yeni |
|---|---|---|
| Seminar/kollokvium | `3 × ORTA(bütün qiymətlər)` → 0-30 | Dərs ballarının **CƏMİ** + kollokvium **üstəgəl** |

Köhnə sistem qiymətləri **ortalayıb 3-ə vurur** — yəni 5 dərsdə 8 alan tələbə
ilə 20 dərsdə 8 alan tələbə **eyni** 24 bal alır.
Yeni sistem **cəmləyir** — 20 dərsdə 8 alan tələbə tavana (cap) dirənir.

**Nəticə:** dərs sayı çox olan fənlərdə yeni sistem tavanı erkən doldurur;
az dərsli fənlərdə isə tələbə köhnəyə nisbətən az alır.

---

## Fərq 3 — Sərbəst iş

| | Köhnə | Yeni |
|---|---|---|
| Sərbəst iş | `si` xanasının **BALI** (0-10) | Təhvil verilmiş mövzuların **SAYI** (checklist) |

Köhnə sistemdə müəllim sərbəst işə **qiymət** yazırdı. Yeni sistemdə isə
tələbənin neçə mövzu **təhvil verdiyi** sayılır — keyfiyyət yox, kəmiyyət.

**Nəticə:** 3 mövzunu əla təhvil verən tələbə 3 bal, 10 mövzunu zəif təhvil
verən 10 bal alır.

---

## Köçürülən data üçün bu NƏ demək deyil

⚠️ **Köçürülmüş tarixi ballar TOXUNULMAZDIR.** J5b fazası köhnə `girish`
dəyərini olduğu kimi arxiv komponenti (GENERIC qalıq) kimi saxlayır, ona görə
yuxarıdakı fərqlər **keçmiş semestrlərin ballarına təsir ETMİR**. Sahibin
«köhnə datanı silmə, pozma, dəyişmə — hər necə hesablanıbsa hesablanıbdır»
tələbi qorunur.

Fərq yalnız **YENİ semestrlərdə** — yəni müəllimlərin bundan sonra yeni
sistemdə yazacağı ballarda özünü göstərəcək.

---

## Sahibə verilən suallar

1. **Yeni semestrlərdə hansı model işləsin?**
   (a) Köhnə model bərpa olunsun — davamiyyət balı qaytarılsın, orta×3
       hesablansın, sərbəst işə bal yazılsın;
   (b) Yeni model qalsın — universitet yeni qaydaya keçsin;
   (c) Təşkilat səviyyəsində seçilə bilən olsun (siyasət sahəsi).

2. Əgər (a) və ya (c) seçilsə: bu, `entry_score_for` + `analytics._evaluate`
   güzgüsündə real dəyişiklik tələb edir (üç yerdə), üstəlik sərbəst iş üçün
   `SelfWorkMark`-a **bal** sahəsi əlavə olunmalıdır (indi yalnız `done`
   bayrağı var).

3. Davamiyyət balı qaytarılarsa, `N` (məxrəc) nədir — jurnalda faktiki
   keçirilmiş dərs sayı, yoxsa sillabusdakı planlanmış saat (`fenn_saati`)?
   Köhnə datada `fenn_saati` 11,210 sətirdə 0-dır, ona görə faktiki xana
   sayı daha etibarlıdır.
