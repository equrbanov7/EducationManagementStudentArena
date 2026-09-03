# Qayıba görə kəsilən ŞÜBHƏLİ hallar — **v3.1**

**Tarix:** 01.09.2026 · **Versiya:** v3.1 (≤2024 çap düsturu düzəldildi) ·
**Rejim:** yalnız oxu, heç bir yazı əməliyyatı aparılmayıb.

**Mənbələr:**

| Nə | Baza |
|---|---|
| **«Tam data» (bərpadan sonrakı) bütün rəqəmlər** | PostgreSQL **`emsarena_j12_verify`** |
| «Köhnə data» (bərpadan əvvəlki vəziyyət) | PostgreSQL `emsarena_rehearsal_52ea0301808c` |
| Kəsilmə bayrağı və çap tarixləri | MariaDB `myedudb` · `balvereqi_logs` |
| **Generator skripti (təkrar istehsal)** | `scratchpad/qb_kesilenler/generate.py` |
| Məxrəcin validasiya skriptləri | `scratchpad/v3/validate3.py` · `v3/probe6.py` (§1.3) · `v3/diff23.py` |
| **Müstəqil təkrar-yoxlama** (generator-dan asılı olmayan) | `scratchpad/v3_verify_indep.py` |
| Render düsturunun dövrə görə ölçülməsi (v3.1) | `scratchpad/probe_era_render.py` · `probe_qb_ceiling.py` · `probe_ceiling_universe.py` |
| Çap sətirlərinin mənbə faylı (yenidən quruldu) | `scratchpad/rebuild_bal_rows.py` → `scratchpad/bal_rows.tsv` |

> ⚠️ **Bu siyahı əl ilə baxış üçündür.**
> Heç bir tələbənin köhnə statusu dəyişdirilməyib və dəyişdirilməyəcək.
> Qayda dəyişməzdir: **köhnə datanı düzəltmirik, sadəcə yeni sistemə köçürürük.**

---

## 0. DÜZƏLİŞ QEYDİ — v2-dən nə dəyişdi

**v2-nin məxrəci SƏHV idi.** v2 `N₂ = max(dərs saatları, plan ÷ 2)` işlədirdi.
Səbəb **vahid qarışıqlığıdır:** `dərs saatları` **SAAT**dır, `plan ÷ 2` isə **CÜT** sayıdır.
İki fərqli vahidin `max()`-ı mənasızdır və məxrəci **sistematik şişirdir** — nəticədə
**çapın sübut etdiyi real kəsilmələr «keçir» kimi görünür.**

**Sübut (nəzarətli test, aşağıda §1.2):** çapda «Kəsr» bayrağı ilə **sübut olunmuş
4 603 kəsilmədən v2 məxrəci 3 814-ünü (82 %) səhvən «keçir» elan edirdi.**
v3 məxrəci ilə **«kəsilir» DEMƏYƏN** sətir **384-ə (8 %)** düşür — bunun **366-sı**
açıq «keçir», **18-i** «verdikt hesablana bilmir» (məxrəc tapılmır).

> **Qeyd (əvvəlki nəşrdə uyğunsuzluq idi):** Excel «Xülasə» vərəqi yalnız **366**
> yazırdı (açıq «keçir»), sənəd isə **384** (366 + 18 hesablanmayan). İkisi də
> düzdür, sadəcə fərqli tərif idi. **v3.1-də vərəq hər iki rəqəmi açıq yazır.**

| # | v2-də nə deyilirdi | v3-də nə deyilir |
|---|---|---|
| **1** | Məxrəc `N₂ = max(dərs saatları, plan÷2)` | **SƏHV — vahid qarışıqlığı.** Məxrəc: **2025+ çaplarda `plan ÷ 2`, 2023–2024 çaplarda `plan`** |
| **2** | «÷2 vahid çevirməsidir, `max(...)` 2024 keçidini **avtomatik tutur**» | `max(...)` heç nə tutmurdu. Vahid keçidi **açıq şəkildə il üzrə** tətbiq olunur və hər sətirdə sütunda yazılır |
| **3** | «`m > 0.25·N` qaydası **0 səhv** verir» | **DAİRƏVİ iddia idi — silindi.** Müstəqil məxrəclə həqiqi xəta payı: **3.43 %** (§1.4) |
| **4** | «B (383 sətir): düzgün məxrəclə **383/383-ün heç biri** köhnə sistemdə kəsilmirdi» | v3 ilə köhnə tərəfdə **17/383** kəsilir, tam data ilə **242/383**. B artıq «heç nə dəyişmir» səbəti **deyil** |
| **5** | «K (53 sətir): N₂ ilə **53/53-də mənfi bal yoxdur**, təmizləməyə ehtiyac yoxdur» | v3 ilə **53/53-də mənfi bal var**. Amma 28-i «tək plan» səbətindədir → **nə v1, nə v2 verdikti sübut olunmur** |
| **6** | «C (165 sətir): N₂ ilə **165/165-i KEÇİR**» | v3 ilə **165/165-i KƏSİLİR** (v1 ilə eyni). 61-i çapda onsuz da bayraqlıdır |
| **7** | Məxrəcin mənbəyi sətirdə görünmürdü | **3 yeni sütun:** «★ N₃ haradan (geri çəkilmə pilləsi)», «★ Hansı VAHİD rejimi», «★ Məxrəclə bağlı xəbərdarlıq» |

> ### ★★ v3.1 DÜZƏLİŞİ — ≤2024 çap DÜSTURU səhv təsvir olunmuşdu
> v3 «kəsilmiş nərdivan» (`trunc₂`) render modelini **bütün dövrlərə** tətbiq edirdi.
> **Data bunu təkzib edir.** Nəzarətli ölçmədə (qayıb > 0, `probe_era_render.py`)
> hər ilin çap sətirləri **öz** ili ilə yoxlananda:
>
> | çap ili | n | nərdivan `10 − m·trunc₂(10/N)` | kəsilməmiş `10 − 10m/N` |
> |---|---:|---:|---:|
> | 2023 | 5 609 | 21.9 % | **87.1 %** |
> | 2024 | 74 186 | 27.3 % | **45.6 %** |
> | 2025 | 179 891 | **51.9 %** | 7.2 % |
> | 2026 | 217 200 | **57.0 %** | 7.7 % |
>
> Yəni **2025-də İKİ şey birdən dəyişib:** məxrəc yarıya endi (§1.3) **VƏ** renderer
> kəsilməmiş nisbətdən kəsilmiş nərdivana keçdi. v3-ün §1.2 / §1.5 / §1.6 ölçüləri
> nərdivanı ≤2024-ə də tətbiq etdiyi üçün **köhnə dövrün uyğunluğunu sistematik AŞAĞI
> göstərirdi.**
>
> **Düzəliş məxrəc qərarını dəyişmir — MÖHKƏMLƏNDİRİR:** v3 **50.0 % → 53.6 %**,
> sadə `plan÷2` **45.8 % → 45.7 %**, v2 **18.1 % → 20.1 %**. v3 ilə `plan÷2` arasındakı
> fərq **4.2 → 7.9 faiz bəndi** açılır. **Heç bir sətrin verdikti dəyişmir** — düstur
> yalnız *ölçməyə* və çapda göstərilən **davamiyyət balı sütununa** təsir edir.

> **★ v3 daxilində ölçmə düzəlişi (müstəqil yoxlamadan sonra).** v3-ün ilk nəşrində
> nəzarətli test **qayıbı sıfır olan 152 372 sətri (24.2 %) də sayırdı** — orada
> `dav = 10.00` çıxır və **hər** məxrəc «düz» görünür. O sətirlər çıxarıldı; **verdiktlər
> DƏYİŞMƏDİ** (aşağıdakı cədvəl olduğu kimi qalır), yalnız **ölçü rəqəmləri** düzəldi:
> v3 61.8 % → **50.0 %**, v2 37.6 % → **18.1 %** (§1.2). Eyni səbəblə §1.4-ün il üzrə
> xəta bölgüsü də yenidən hesablandı. Aralarındakı **fərq daralmadı, genişləndi.**
> (v3.1-də həmin paylar render düzəlişi ilə bir daha yeniləndi: **53.6 % / 20.1 %**.)

**v2 → v3 fərq cədvəli** (8 221 şübhəli sətir):

| Kat. | Sətir | v2: tam data KƏSİLİR | **v3: tam data KƏSİLİR** | v2: köhnə data KƏSİLİR | **v3: köhnə data KƏSİLİR** | Verdikti DƏYİŞƏN |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 38 | 38 | 38 | 0 | 0 | 0 |
| A2 | 273 | 273 | 273 | 0 | 0 | 0 |
| **B** | 383 | 0 | **242** | 0 | **17** | **242** |
| **C** | 165 | 0 | **165** | 0 | **165** | **165** |
| D | 257 | 257 | 257 | 238 | 242 | 0 |
| **E1** | 2 106 | 102 | **2 003** | 101 | **2 001** | **1 901** |
| **E2** | 1 092 | 25 | **1 019** | 25 | **1 019** | **994** |
| E3 | 302 | 221 | 302 | 217 | 301 | 81 |
| **F** | 1 104 | 476 | **965** | 476 | **958** | **489** |
| H | 1 516 | 1 516 | 1 516 | 1 350 | 1 432 | 0 |
| I | 775 | 510 | 775 | 484 | 758 | 265 |
| J | 69 | 0 | 0 | 0 | 0 | 0 |
| K | 53 | 53 | 53 | 53 | 53 | 0 |
| L | 88 | 88 | 88 | 88 | 88 | 0 |
| **CƏM** | **8 221** | **3 559** | **7 696** | **3 032** | **7 034** | **4 137** |

Vərəq başlıqları dəyişmədi: «Status dəyişir» **311 sətir**, «Köhnə jurnal natamam» **383**,
«Bağlana bilmədi» **1 256 açar**, şübhəli cəmi **8 221**, **11 vərəq**.
Dəyişən — həmin sətirlərin **verdiktləridir**.

---

## 1. Məxrəc — nə seçildi, niyə, hansı sübutla

### 1.1 Qayda

```
«(Kəsr)» bayrağı  ⟺  qayıb > 0.25 × N          (ciddi bərabərsizlik — hər iki dövrdə)

MƏXRƏC          N   = fenn_saati ÷ 2     — çap ili ≥ 2025   (vahid keçidi, §1.3)
                N   = fenn_saati         — çap ili ≤ 2024

ÇAP DÜSTURU     dav = 10 − qayıb × trunc₂(10 ÷ N)   — çap ili ≥ 2025  (kəsilmiş nərdivan)
                dav = 10 × (N − qayıb) ÷ N          — çap ili ≤ 2024  (KƏSİLMƏMİŞ)
```

> **★ 2025-də İKİ şey birdən dəyişib** (v3.1 düzəlişi, §0-a bax): məxrəc yarıya endi
> **və** renderer kəsilməmiş nisbətdən kəsilmiş nərdivana keçdi. v3-ün ilk nəşri
> nərdivanı bütün dövrlərə tətbiq edirdi və ≤2024-ün uyğunluğunu aşağı göstərirdi.
>
> **Diqqət (2025+ üçün):** render **kəsilmiş** nərdivandır (`trunc₂`, yuvarlaqlaşdırma
> deyil). Ona görə **7.50-dən yuxarı çap olunmuş sətir də bayraqlı ola bilər** — bu
> anomaliya deyil. v1/v2-nin «izahsız qalıq» adlandırdığı sətirlərin bir hissəsi budur.
>
> **Bayraq düsturu dəyişmir:** «(Kəsr)» hər iki dövrdə `qayıb > 0.25·N`-dir, ona görə
> **render düzəlişi heç bir sətrin verdiktini dəyişmir** — yalnız ölçüləri və çapdakı
> **davamiyyət balı** sütununu düzəldir.

### 1.2 ★ NƏZARƏTLİ TEST — məxrəc seçiminin əsası

**Populyasiya:** bərpa qayıbı **DƏYİŞMƏYƏN** çap sətirləri (çapdakı qayıb = indiki qayıb).
Bu vacibdir: belə sətirlərdə **məxrəcdən başqa heç bir dəyişən yoxdur** — namizədləri
təmiz müqayisə etmək olur.

> ### ⚠️ TRİVİAL SƏTİRLƏR ÇIXARILIB — ölçmənin özündəki tələ
> Nəzarətli sətirlərin **cəmi 629 258**-dir, **amma bunun 152 372-si (24.2 %) qayıbı
> SIFIR olan sətirlərdir.** Qayıb 0 olanda `dav = 10 − 0 × trunc₂(10÷N) = 10.00` —
> yəni **hansı məxrəci qoysan, çapı «təkrarlayır»**. Belə sətirlər namizədləri ayırd
> etmir, sadəcə **hamısının payını eyni qədər şişirdir**.
> Ona görə aşağıdakı cədvəl **yalnız qayıbı 0-dan böyük 476 886 sətir** üzərindədir.
> (Trivial sətirlərlə birlikdə həmin paylar 61.8 % / 58.5 % / 37.6 % görünürdü —
> nəticə eyni, amma rəqəmlər süni yüksək idi. **Düzəldilib.**)

**Tam çap universi — 476 886 nəzarətli çap sətri (qayıb > 0).** «Çap olunmuş
davamiyyət balını **eynilə** təkrarlayan» namizədin payı. **Render düsturu hər sətrin
ÖZ çap ilinindir** (v3.1); müqayisə üçün v3-ün ilk nəşrinin «hər yerdə nərdivan»
sütunu da saxlanılıb:

| namizəd məxrəc | **dəqiqlik (v3.1, il-şüurlu render)** | v3-də (nərdivan hər yerdə) |
|---|---:|---:|
| **v3 (il-şüurlu: plan÷2 / plan)** | **53.6 %** | 50.0 % |
| `plan ÷ 2` (il fərqi olmadan) | 45.7 % | 45.8 % |
| **`N₂ = max(dərs saatları, plan÷2)` — v2** | **20.1 %** | 18.1 % |
| `dərs saatları` (h_real) | 19.8 % | 17.8 % |
| `dərs sayı` | 15.9 % | 16.7 % |
| `plan` (il fərqi olmadan) | 9.3 % | 5.7 % |

**Hər iki düzəlişdən sonra fərq DARALMIR, AÇILIR:**
v3 ↔ v2 məsafəsi 61.8 / 37.6 (1.6×) → 50.0 / 18.1 (2.8×) → **53.6 / 20.1 (2.7×)**;
v3-ün **sadə `plan÷2` üzərindəki üstünlüyü isə 4.2 → 7.9 faiz bəndinə qalxır.**
Yəni məxrəc qərarı düzəldilmiş ölçü ilə **daha da möhkəmdir.**

**Şübhəli siyahının öz nəzarətli alt-çoxluğu — 9 983 sətir** (qayıb > 0; bu populyasiya
`QB_SUBHELI_HAMISI.tsv` + `QB_ZIDDIYYETSIZ_kesilenler.tsv` sətirlərindən çapı bağlanan
və bərpa qayıbı dəyişməyənlərdir — hər **yazılış bir dəfə**, çap sətri yox):

| namizəd | **dəqiqlik (v3.1)** | v3-də (nərdivan hər yerdə) |
|---|---:|---:|
| **v3** | **36.5 %** | 37.4 % |
| `plan ÷ 2` | 35.2 % | 35.4 % |
| `dərs sayı` | 11.2 % | 11.7 % |
| **v2: `max(dərs saatları, plan÷2)`** | **7.7 %** | 7.7 % |
| `dərs saatları` | 7.6 % | 7.7 % |
| `plan` | 4.6 % | 5.5 % |

> **⚠️ Burada düzəliş payları bir qədər AŞAĞI salır — gizlətmirik.** Tam universdə
> il-şüurlu düstur uyğunluğu qaldırır (50.0 → 53.6 %), şübhəli alt-çoxluqda isə
> **azaldır** (37.4 → 36.5 %). Səbəb: bu alt-çoxluq **hər yazılış üçün bir** çap
> dəyəri götürür və dövrü **yazılışın SON çap ilindən** tapır (`era_of`), halbuki tam
> universdə **hər çap sətri öz ili** ilə yoxlanılır. ≤2024 budağındakı 1 153 sətirdən
> nərdivan 599-unu, il-şüurlu düstur 455-ini izah edir — yəni burada iki düsturun
> çoxluqları **kəsişir, biri o birini örtmür**. Qərar tam universə söykənir (n 48×
> böyükdür və hər sətir öz ili ilə yoxlanılır).

**Çapa qarşı verdikt müqayisəsi** (şübhəli siyahı, çap bayrağı = həqiqət):

| | çapın sübut etdiyi **4 603 KƏSİLMƏ** |
|---|---:|
| v2 səhvən «keçir» dedi | **3 814 (82 %)** |
| v3 «kəsilir» demir | **384 (8 %)** — 366 açıq «keçir» + 18 «hesablana bilmir» |

> **Əks tərəf — gizlətmirik:** çapın **buraxdığı** 818 sətirdə v3 **815-ini** «kəsilir»
> sayır (v2: 541). Amma bu siyahı **artıq süzgəcdən keçib** — sətirlər məhz «tam data
> kəsir» şərti ilə seçilib, ona görə bu tərəf **qərəzlidir** və ölçü kimi işlədilə bilməz.
> Qərəzsiz ölçü §1.4-dədir.

### 1.3 ★ 2024 vahid keçidi — sübut və tətbiq

**Sübut (yalnız çapdan):** **8 002 yazılış** həm 2024-ə qədər, həm 2025-dən sonra çap
olunub. **5 123-ündə çap olunan davamiyyət balı DƏYİŞİB** və `(10 − dav)` nisbəti **≈ ×2**
(dəqiq ×2.00 — 16.0 %; moda 1.86–2.09). Jurnal datası eyni qalıb, deməli **renderer-in
məxrəci 2025-də yarıya enib.**

**Populyasiya:** çapı olan **85 106 yazılış**, hər biri **son çapı ilə bir dəfə**;
qayıbı 0 olan 22 488 trivial sətir və qayıbı dəyişənlər atılıb; aşağıdakı cədvəl
əlavə olaraq **cüt planlılarla** məhdudlaşdırılıb (tək planda `plan÷2` onsuz da
tam ədəd vermir — bax §1.5).

| çap ili | n | `plan ÷ 2` | `plan` |
|---|---:|---:|---:|
| 2023 | 438 | 0.2 % | **66.4 %** |
| 2024 | 6 662 | 2.2 % | **43.5 %** |
| 2025 | 9 980 | **85.9 %** | 2.4 % |
| 2026 | 20 033 | **90.1 %** | 1.8 % |

Eyni sınaq **çap sətri** vahidi ilə (yazılış yox, hər çap ayrıca — n = 288 278)
təkrarlananda rəqəmlər dəyişir, **istiqamət dəyişmir:**
2023 — 0.0 % / 20.5 % · 2024 — 2.3 % / 18.3 % · 2025 — **85.0 %** / 2.2 % ·
2026 — **88.7 %** / 1.9 %. Yəni keçidin **özü** hansı vahidlə saydığından asılı deyil.

> **⚠️ Bu iki cədvəl «nərdivan hər yerdə» modeli ilə ölçülüb** (v3-ün ilk nəşri) və
> ona görə **≤2024-ün mütləq paylarını aşağı göstərir**. Cədvəlin məqsədi — *həmin il
> daxilində* `plan` ilə `plan÷2`-ni tutuşdurmaq — bundan **zərər görmür** (hər iki
> namizəd eyni düsturla ölçülür), keçidin istiqaməti də dəyişmir. Düzəldilmiş düsturla
> (v3.1) eyni sınağın **il üzrə mütləq payları** belədir — nəzarətli **çap sətri**,
> qayıb > 0, geri çəkilmə sırası ilə (`probe_era_render.py`):
>
> | çap ili | n | nərdivan | kəsilməmiş | **il-şüurlu (tətbiq olunan)** |
> |---|---:|---:|---:|---:|
> | 2023 | 5 609 | 21.9 % | 87.1 % | **87.1 %** |
> | 2024 | 74 186 | 27.3 % | 45.6 % | **45.6 %** |
> | 2025 | 179 891 | 51.9 % | 7.2 % | **51.9 %** |
> | 2026 | 217 200 | 57.0 % | 7.7 % | **57.0 %** |
>
> Yəni **hər ilin öz düsturu həmin ildə açıq-aydın qalibdir** — bu, həm vahid keçidini,
> həm render keçidini eyni anda təsdiqləyir.

**Nəticə:** 2023–2024-də `saatliq_ders = 1` **bir akademik saat**, 2025+-də **bir CÜT**
sayılır. Keçid **çap tarixinə** bağlıdır, jurnalın tədris ilinə yox — köhnə jurnal
bu gün yenidən çap olunsa **cari** vahidlə çıxır.

**Tətbiq:** hər sətrə **son bal-vərəqi çapının ili** yazılır (`balvereqi_logs`).
Şübhəli siyahıda: **7 850 sətir 2025+ vahidi**, **371 sətir 2023–2024 vahidi**.
Hər sətirdə **«★ Hansı VAHİD rejimi tətbiq olundu və niyə»** sütunu mənbəni göstərir
(məs. *«2025+ vahidi: saatliq_ders = 1 CÜT → plan ÷ 2 (son çap ili 2025)»*).

> **⚠️ İki fərqli «il» işlədilir — bunu bilərəkdən edirik, amma yazırıq.**
> Siyahının **sətir** səviyyəsində (`era_of`) dövr **yazılışın SON çapının ilidir** —
> bir yazılış üçün bir verdikt lazımdır və ən son çap bugünkü vəziyyətə ən yaxındır.
> **Ölçmədə** isə (§1.2 tam universi, §1.4) **hər çap sətri öz ili** ilə yoxlanılır —
> orada bir yazılışın 2024 və 2026 çapları ayrı-ayrı sətirlərdir. **8 002 yazılış hər
> iki dövrdə çap olunub** (§1.3), yəni bu iki tərif onlarda fərqlənir. Nəticə: sətir
> verdikti ilə ölçü rəqəmi **eyni populyasiyanı fərqli kəsir** — §1.2-nin QB
> alt-çoxluğundakı 37.4 → 36.5 % «geriləməsi» məhz bundandır.

### 1.4 ★ «m > 0.25·N» qaydasının HƏQİQİ xəta payı

> **v2-nin «0 səhv» iddiası DAİRƏVİ idi və çıxarıldı.**
> `mz_resid.py` N-i məhz **bayraq sərhədindən** — `[4·max(bayraqsız m), 4·min(bayraqlı m))`
> aralığından — seçirdi. Belə N ilə `m > 0.25·N` qaydası **riyazi olaraq uğursuz OLA
> BİLMƏZDİ**. Bu, ölçü deyil, tavtologiya idi.
>
> **Üstəlik əks-nümunələr əvvəlcədən atılırdı:** yoxlanan **16 701 vərəqdən 775-ində**
> iki siqnalın aralığı **BOŞ** çıxır (ziddiyyət), **5-ində** bayraq qayıba görə monoton
> deyil — **cəmi 780 vərəq (4.7 %)** kənara qoyulurdu. Bunu gizlətmirik.

**Dürüst ölçü** — məxrəc **plandan** gəlir (bayraqdan yox, yəni müstəqildir),
nəzarətli sətirlər, qayıbı 0-dan böyük **476 886 çap sətri**:

| | sətir | pay |
|---|---:|---:|
| DÜZ | 460 530 | **96.57 %** |
| **SƏHV** | **16 356** | **3.43 %** |
| ↳ qayda «kəsir», çap kəsmir | 13 952 | 2.93 % |
| ↳ çap kəsir, qayda «kəsmir» | 2 404 | 0.50 % |

Çap ili üzrə xəta (**hər ilin öz məxrəci ilə**, yəni pay da, məxrəc də həmin ilin
qayıbı 0-dan böyük sətirləridir):

| çap ili | yoxlanan sətir | xəta |
|---|---:|---:|
| 2023 | 5 609 | 1.11 % |
| 2024 | 74 186 | 2.85 % |
| 2025 | 179 891 | **4.57 %** |
| 2026 | 217 200 | 2.74 % |

> Əvvəlki nəşrdə bu sətir «2023 — 0.65 % · 2024 — 2.20 % · 2025 — 3.48 % · 2026 — 2.15 %»
> yazılmışdı: **cəm düz idi, il üzrə bölgü isə səhv məxrəclə** (ilin trivial `qayıb=0`
> sətirləri də məxrəcə düşürdü) hesablanmışdı. **Düzəldilib.**

### 1.5 ★ MƏXRƏCİN GERİ ÇƏKİLMƏ SIRASI (fallback ladder)

`plan` yoxdursa və ya `÷2` tam ədəd vermirsə **nə edirik** — açıq sıra.
Hər sətirdə işlədilən pillə **«★ N₃ haradan»** sütununda yazılır.

| pillə | şərt | N₃ | şübhəli siyahıda |
|---|---|---|---:|
| **1** | `plan > 0`, çap dövrü **2025+** | `plan ÷ 2` | **5 760** |
| **2** | `plan > 0`, çap dövrü **≤2024** | `plan` | **340** |
| **3** | `plan = 0`, dərs saatı > 0, **2025+** | `dərs saatları ÷ 2` | **2 072** |
| **4** | `plan = 0`, dərs saatı > 0, **≤2024** | `dərs saatları` | **31** |
| **5** | `plan = 0`, saat = 0, dərs sayı > 0 | `dərs sayı` | 0 |
| **6** | heç biri | **YOX — verdikt hesablanmır** | **18** |

**Çap dövrü haradan:** yazılışın **son bal-vərəqi çapının ili**. Çap tapılmasa →
**cari rejim (2025+)** götürülür və sütunda belə yazılır. Səbəb ikiqatdır: (a) sənəd
bu gün çap olunsa cari renderer işləyəcək; (b) empirik olaraq çapı bağlanmayan
sətirlərdə `plan÷2` daha yaxşıdır (**30.8 %** vs `plan` **6.9 %**).

> **★ Bu seçim ölçüyə TƏSİR EDİR — gizlətmirik.** Nəzarətli QB populyasiyasının
> **2 400 sətrində (24 %) heç bir çap yoxdur**, yəni dövrü bilmirik. Geri çəkilməni
> «çap yoxdursa → **jurnalın tədris ili**» seçsək, v3-ün dəqiqliyi **37.4 % → 31.9 %**
> düşür və **sadə `plan÷2`-dən (35.4 %) geri qalır.**
> *(Bu iki rəqəm — 31.9 % və aşağıdakı 30.8 % / 6.9 % — v3-ün «nərdivan hər yerdə»
> modeli ilə ölçülüb və v3.1-də YENİDƏN ölçülməyib; qərarın istiqamətini dəyişmir,
> çünki söhbət çapı OLMAYAN, yəni dövrü bilinməyən sətirlərdən gedir.)*
>
> Yəni v3-ün sadə `plan÷2` üzərindəki üstünlüyü **qismən bu geri çəkilmə seçiminə
> söykənir** (v3.1-də bu üstünlük tam universdə 4.2 → **7.9 faiz bəndinə** genişlənir); il-şüurlu
> qaydanın özü (çapı OLAN sətirlərdə) isə §1.3-dəki keçid sübutuna söykənir.

> ### ⚠️ TƏK plan — məxrəc BƏRPA OLUNMUR
> `plan` tək ədəd olanda (45, 75, 15, 105, 35, 25 …) `plan ÷ 2` tam ədəd vermir.
> **Belə sətirlərdə köhnə məxrəc `fenn_saati`-dən bərpa olunmur:** nəzarətli testdə
> tək planlı **3 797 sətrin yalnız 3.8 %-i** `plan÷2` ilə, **cəmi 35.9 %-i İSTƏNİLƏN
> tam ədəd məxrəclə** izah olunur (cüt planlarda bu rəqəm 73.5 %-dir).
> *(v3-ün nərdivan modeli ilə bunlar 5.1 % / 36.5 % / 75.8 % görünürdü — nəticə eyni.)*
> Çapdan geri həll edildikdə `plan=45` üçün N **24 / 26 / 23 / 27 / 30** kimi
> səpələnir — deterministik qayda yoxdur.
>
> Bu sətirlərdə **N olduğu kimi (kəsr) saxlanılır** və «★ Məxrəclə bağlı xəbərdarlıq»
> sütununda **ETİBARSIZ** kimi işarələnir. Yuvarlaqlaşdırma **tətbiq edilmir** —
> `floor` 9.5 %, `ceil` 8.6 %, `round` 5.3 % verir, yəni fərq səs-küy səviyyəsindədir
> və süni «düzəliş» yaratmaq istəmirik.

**Xəbərdarlıqların paylanması (8 221 sətir):**

| xəbərdarlıq | sətir |
|---|---:|
| — (təmiz məxrəc) | **3 631** |
| ⚠️ **plan TƏK ədəddir → məxrəc ETİBARSIZ** | **2 469** |
| ⚠️ plan saatı 0 → məxrəc bərpa olunan dərs saatlarındandır | **2 103** |
| ⚠️ verdikt hesablana bilmir | 18 |

**Yəni siyahının yalnız 44 %-ində məxrəc təmizdir.** Qalan 56 %-də verdikt
şərtidir — bunu gizlətmirik.

### 1.6 ★ NİYƏ 100 % DEYİL — dürüst izah

Nəzarətli testdə v3 çapı **53.6 %** (şübhəli alt-çoxluqda 36.5 %) təkrarlayır. Niyə
100 % deyil — **tavan testi** cavab verir: hər sətir üçün `N = 1…400` **bütün** tam
ədədləri sınadıq və «bu sətri **ümumiyyətlə hər hansı** tam məxrəc izah edirmi?»
sualına baxdıq. **Render düsturu hər sətrin öz dövrünündür** (v3.1).

**(a) TAM çap universi — 476 886 nəzarətli çap sətri, qayıb > 0**
(`probe_ceiling_universe.py`; burada hər çap sətri **öz ili** ilə yoxlanılır):

| render modeli | tavan: **hər hansı** tam N |
|---|---:|
| nərdivan hər yerdə (v3-ün ilk nəşri) | 72.0 % |
| **il-şüurlu (v3.1 — tətbiq olunan)** | **75.5 %** |

Çap ili üzrə tavan (il-şüurlu): 2023 — **98.8 %** · 2024 — **70.8 %** ·
2025 — 64.2 % · 2026 — 85.8 %. *(Nərdivan hər yerdə: 25.4 / 54.4 / 64.2 / 85.8 %.)*
Yəni **düstur düzəldiləndə «heç bir məxrəclə izah olunmayan» pay 28.0 % → 24.5 %-ə
düşür** — köhnə dövrdə isə qalıq praktik olaraq yox olur (2023-də 74.6 % → 1.2 %).

**(b) Şübhəli siyahının nəzarətli alt-çoxluğu — n = 9 983** (hər yazılış bir dəfə,
dövr `era_of` ilə, yəni **son çap ili**):

| alt-çoxluq | n | tavan: **hər hansı** tam N | v3 | v3-ün tavandan payı |
|---|---:|---:|---:|---:|
| hamısı | 9 983 | **58.4 %** | 36.5 % | **62.5 %** |
| cüt plan | 5 425 | 73.5 % | 62.0 % | 84.4 % |
| **tək plan** | 3 797 | **35.9 %** | **3.8 %** | 10.6 % |
| plan = 0 | 761 | 62.5 % | 17.1 % | 27.3 % |

*(v3-ün nərdivan modeli ilə eyni cədvəl: 59.8 / 37.4 / 62.6 · 75.8 / 62.9 / 83.0 ·
36.5 / 5.1 / 13.9 · 62.3 / 17.2 / 27.6. Bu alt-çoxluqda düzəliş payları bir qədər
AŞAĞI salır — səbəbi §1.3-dəki «iki fərqli il» qeydidir; qərəzsiz ölçü (a) bəndidir.)*

1. **Problemin böyük hissəsi məxrəcdə DEYİL.** Şübhəli alt-çoxluqda sətirlərin
   **41.6 %-ini** (tam universdə **24.5 %-ini**) heç bir tam məxrəc izah etmir —
   orada **çapdakı qayıb rəqəmi bizim rəqəmdən fərqlidir** (üzrlü/üzrsüz bölgüsü,
   çapdan sonrakı əl düzəlişləri, jurnalın qismən datası). Bu, məxrəc seçimi ilə
   **prinsipcə** bağlanmır.
2. **İzah oluna bilənlərin 62.5 %-ni v3 tutur**; cüt planlarda bu pay **84 %-dir** —
   yəni məxrəc qaydası öz sahəsində demək olar bağlanıb.
3. **Qalığın kök səbəbi tək planlardır:** orada tavanın özü **35.9 %**, v3 isə **3.8 %**
   (§1.5-dəki xəbərdarlıq bölməsi). Siyahının **2 469 sətri** məhz budur.
4. **Render düsturu artıq dövrə görə modeldədir** (2025+ `trunc₂` nərdivan, ≤2024
   kəsilməmiş nisbət) — bu, v3.1-dən sonra qalıq mənbəyi deyil.
5. **Qayıbı 0 olan sətirlər sayılmır** (§1.2) — onlar «100 %» rəqəmini süni qaldırırdı.
6. **≤2024 budağı daha zəifdir — açıq yazırıq.** Çapın kəsdiyi sətirlərdən
   **2023–2024 vahid budağında 127 sətirdən 63-ü (50 %) v3-ün gözündən qaçır**, 2025+
   budağında isə **4 476 sətirdən 321-i (7 %)**. Təsir dairəsi kiçikdir (siyahıda cəmi
   **371 sətir** ≤2024 budağındadır), amma **o sətirlərdə verdiktə daha az etibar edin.**

Ona görə **«★ Tam data + N₃ → status» sütunu qəti verdikt deyil.** Hər sətirdə
həssaslıq sütununa baxın: **4 274 sətirdə** məxrəc iki dəfə **böyük** olsaydı verdikt
çevrilirdi, **352 sətirdə** isə iki dəfə **kiçik** olsaydı.

---

## 2. Nəticə rəqəmləri

| | Yazılış | Tələbə |
|---|---:|---:|
| Qayıba görə kəsilmə universi (bütün hallar) | **12 988** | 2 757 |
| **ŞÜBHƏLİ — əl ilə baxılmalı** | **8 221** | **2 538** |
| Ziddiyyətsiz kəsilmə (köhnə də kəsib, tam data da kəsir) | 4 767 | 928 |
| ★ **Bağlana bilmədi** — çapda kəsilib, yeni sistemdə qarşılığı yoxdur | **1 256** | **750** |

İllər üzrə şübhəli sətirlər: 2023/2024 — 3 079 · 2022/2023 — 2 775 · 2021/2022 — 954 ·
2024/2025 — 754 · 2025/2026 — 659.

---

## 3. Kateqoriyalar — v3 verdiktləri ilə

«Əsas» = sətrin baş kateqoriyası (hər yazılış bir dəfə). «Hər hansı» = əlamətin
göründüyü bütün sətirlər. Excel Xülasəsində hər ikisi ayrıca sütundadır.

### 🔴 Status dəyişir — **311 sətir · 228 tələbə**

> ⚠️ Bu sətirlərin **HAMISINDA** fənnin **plan saatı 0**-dır → məxrəc 3-cü/4-cü pillədən
> (bərpa olunan dərs saatları) gəlir. Kafedradan **həqiqi auditoriya saatını** soruşmaq
> bu 311 sətrin böyük hissəsini bir addımda bağlayır. Hamısı 2021/2022-dədir.

**A1 — 38 sətir · 37 tələbə.** Köhnə datada da qayıb var idi, bərpa onu həddin üstünə çıxardı.
v3 ilə: köhnə tərəf **0/38 kəsilir**, tam data **38/38 kəsilir**.

**A2 — 273 sətir · 202 tələbə.** Köhnə datada qayıb ümumiyyətlə görünmürdü (jurnal boş idi).
v3 ilə: köhnə tərəf **0/273**, tam data **273/273**.

> **★ «Köhnə status» = SÜBUT YOXDUR.** A1-in **35/38**, A2-nin **241/273** sətrində çap
> vərəqi ümumiyyətlə yoxdur (`balvereqi_logs` 2023-08-dən başlayır, bu sətirlər
> 2021/2022-dədir). «Köhnə sistem bunları buraxmışdı» **demək olmaz.**

### 🟡 Köhnə jurnal natamam — **383 sətir · 314 tələbə**

**B.** v1 bunları «köhnə sistem kəsirdi, tam data keçirir» sayırdı — bu, v1-in
**süni kiçik məxrəcindən** doğulmuşdu (214 sətirdə jurnalda ≤3 dərs, 47-də cəmi 1).

> **★ v2 burada da səhv etdi.** v2 «düzgün məxrəclə **383/383-ün heç biri** kəsilmirdi»
> yazmışdı — bu, şişirdilmiş `N₂` məxrəcinin nəticəsi idi.
> **v3 ilə:** köhnə tərəf **17/383 kəsilir**, tam data **242/383 kəsilir**.
> Yəni **225 sətir əslində status dəyişməsidir** (köhnə keçir → tam data kəsir),
> «heç nə dəyişmir» deyil.
>
> **Amma sübut yenə zəifdir:** **371/383** sətirdə heç vaxt bal vərəqi çap olunmayıb və
> **383/383-ünün plan saatı 0-dır** (məxrəc 3-cü pillədən). Ona görə bu səbət
> «status dəyişir» vərəqinə **köçürülmür** — verdikt kafedra təsdiqi tələb edir.

### 🔴 Bağlana bilmədi — **1 256 açar · 750 tələbə**

Çap vərəqində «Kəsr» bayrağı **VAR** (köhnə sistem kəsib), yeni sistemdə qarşılığı
**heç bir vərəqdə yoxdur**. Bu bölmə v2-dən **dəyişməyib** — məxrəcdən asılı deyil.

| Səbəb | Açar |
|---|---:|
| Köçürülüb, amma kəsilmə universinə düşmədi | 593 |
| Köçürmədə **atlanıb** (`skipped`) | 457 |
| Xəritədə ümumiyyətlə yoxdur | 206 |

Tələbələrin **1 122-si** yeni sistemdə var, **134-ü** yoxdur. **798 fərqli köhnə jurnal.**
İllər üzrə: **2025 — 640**, **2026 — 317**, 2024 — 232, 2023 — 67 → boşluq **cari
illərdə** cəmlənib, bu **real iş siyahısıdır**.

> **★ Yuxarı sərhəd daha böyükdür:** əlavə **22 965 bayraqlı çap sətri** (12 428 vərəq)
> ümumiyyətlə heç bir jurnala bağlana bilmədi. Örtük tam deyil — gizlətmirik.

### 🔴 Ziddiyyət

**E1 — 2 106 sətir · 1 077 tələbə.** Kəsilib, sonra imtahana buraxılıb.
v3 ilə **2 003/2 106 kəsilir** (v2: 102). Yəni **bayraq demək olar həmişə düzgündür**,
ziddiyyət isə **imtahana buraxılışdadır** — v2-nin «bayraq səhv idi» oxunuşu yanlış idi.
*Nümunə:* `myedu-student-3032`, «Ekosistemlər, onların mühafizəsi», 2023/2024 Yaz:
qayıb 8, plan 60 → **N₃ = 30 → 7.33 KƏSİLİR**; çapda **7.36 + «Kəsr»**.
v2 həmin sətrə `N₂ = 68` verib **8.82 «keçir»** yazmışdı — **səhv**.

**E2 — 1 092 sətir · 654 tələbə.** Geriyə dönük kəsilmə. v3 ilə **1 019/1 092 kəsilir** (v2: 25).

**E3 — 302 sətir.** Çap tarixçəsi yoxdur, sıra müəyyən edilə bilmir. v3: **302/302 kəsilir**.

**F — 1 104 sətir.** Köhnə sistem kəsib, v1 hesabına görə qayıb həddin altında idi.
v3 ilə **965/1 104 (87 %) həqiqətən həddin ÜSTÜNDƏDİR** — yəni köhnə bayraq düzgündür
və bu hallar **bağlanır**. (v2 yalnız 476-nı bağlaya bilmişdi.)
**Qalan 139 sətir izahsızdır** — v2-nin 628 rəqəmi bu qədər azalıb.

**G — 21 sətirdə əlamət · 18 tələbə.** Üzrlü qayıb nəzərə alınanda qərar dəyişir.

**H — 1 516 sətir · 592 tələbə (əsas).** Köhnə sistemdə **heç bir status yoxdur**.
v3 ilə **1 432 sətir köhnə tərəfdə də kəsilir** → **ziddiyyət deyil**, köhnə qərar sadəcə mövcud deyil.

### 🔴 Digər hallar

**I — 775 sətir · 502 tələbə.** Köhnə sistem **buraxıb**, tam data **kəsir**.
v3 ilə **775/775-i kəsilir** (v2: 510). Bu, **ən ciddi ziddiyyət səbətidir** — çapda
bayraq yoxdur, amma qayıb açıq-aydın həddi aşır.

**J — 69 sətir · 65 tələbə.** Kəsilib, amma davamiyyət işarəsi ümumiyyətlə yoxdur.
**18-ində N₃ hesablana bilmir** (6-cı pillə).

**K — 53 sətir · 45 tələbə.** v1: «data pozuntusu, mənfi bal». v2: «məxrəc artefaktı,
53/53-də mənfi bal yoxdur».

> **★ v3 ilə mənfi ballar QAYIDIR: 53/53.** (Məs. qayıb 30, `plan = 15` → N₃ = 7.5 → **−30**.)
> **Amma verdikt yenə sübut olunmur:** 28-i **tək planlı** sətirdir, yəni məxrəc
> `fenn_saati`-dən bərpa oluna bilmir. Deməli **nə v1-in «data pozuntusu», nə v2-nin
> «təmizdir» yarlığı əsaslıdır** — bu 53 sətir kafedra təsdiqi olmadan qapanmır.

**L — 88 sətir.** Köhnə verdikt bağlana bilmədi (bal vərəqi tapılmadı), tam data kəsir.
> L **bağlana bilməyən açarların siyahısı deyil** — o siyahı «Bağlana bilmədi» vərəqindədir.

### 🟠 Sübutu zəif olanlar

**C — 165 sətir.** Fənnin ümumi saatı naməlum və ya ikimənalı idi.
v1: **165/165 KƏSİLİR**. v2: **165/165 KEÇİR**. **v3: 165/165 KƏSİLİR** — yəni v1 ilə eyni.
Bunlardan **61-i çapda onsuz da bayraqlıdır** (köhnə sistem kəsib) → v3 çapla uyğundur.
**72-si tək planlıdır** — orada verdikt etibarsızdır.

**D — 257 sətir.** Sərhəddə: qayıb hədddən ±1 dərs məsafəsindədir; bir xananın səhvi qərarı çevirir.

---

## 4. Sübut kazusu — köhnə proqramın davamiyyəti hesablaya bilmədiyi jurnal

Jurnal `wr17Ahlth8` — «Azərbaycan tarixi», 531 BI rus, 2021/2022 Yaz.

- Mənbədə `journals.fenn_saati = 0`
- `journals_dates_rooms`-da **sıfır slot**
- amma `journals_dates_points`-də **84 `qb` xanası** (bir tələbədə 16 xana → 32 saat)

Məxrəc sıfır olduğu üçün köhnə proqram bu jurnalda davamiyyət balını **ümumiyyətlə
hesablaya bilmirdi** — ağır qayıblar görünməz qaldı. Köçürmə 24 dərs / 48 saat bərpa etdi.
**A2 kateqoriyasının 273 sətrinin mexanizmi budur.**

---

## 5. Siyahının hüdudları — gizlətmirik

1. **Məxrəc siyahının yalnız 44 %-ində təmizdir** (3 631 / 8 221). **2 469 sətirdə plan
   tək ədəddir → məxrəc bərpa olunmur**, **2 103 sətirdə plan saatı 0-dır**, **18 sətirdə
   verdikt ümumiyyətlə hesablanmır**.
2. **v3 çapı 53.6 % (şübhəli alt-çoxluqda 36.5 %) təkrarlayır — 100 % deyil.** Səbəbi
   §1.6-dadır: tam universdə sətirlərin **24.5 %-ini** (şübhəli alt-çoxluqda
   **41.6 %-ini**) heç bir tam ədəd məxrəc izah etmir — orada problem məxrəcdə deyil,
   **qayıb rəqəmindədir**. (Bu paylar qayıbı 0-dan böyük sətirlər üzərindədir; trivial
   `qayıb=0` sətirləri §1.2-yə görə çıxarılıb.)
3. **`m > 0.25·N` qaydasının həqiqi xəta payı 3.43 %-dir** (v2-nin «0 səhv» iddiası
   dairəvi idi). Bundan başqa, N-i qapayan analizdə **780 vərəq (4.7 %) ziddiyyətli
   olduğu üçün atılırdı.**
4. **Verdikt məxrəcə həssasdır:** **4 274 sətirdə** məxrəc 2× böyük olsaydı verdikt
   çevrilirdi, **352 sətirdə** 2× kiçik olsaydı.
5. **Örtük tam deyil.** Çapda bayraqlı 8 757 açardan 1 256-sı heç bir vərəqdə yox idi;
   bundan əlavə **22 965 bayraqlı çap sətri** (12 428 vərəq) heç bir jurnala bağlanmır.
6. **Köhnə sistemin verdikti çox halda YOXDUR, «keçib» deyil.** `balvereqi_logs`
   2023-08-dən başlayır; 2021/2022 və 2022/2023-ün böyük hissəsi üçün çap vərəqi yoxdur.
7. **Bərpa datanı artırdı, azaltmadı.** 11 607 dərs və 161 775 xana bərpa olundu
   (18 794 qayıb). **5 400 yazılışda** qayıb artdı, **heç birində azalmadı.**
8. **Tarix bərpası:** 8 221 sətrin 8 171-ində dərs tarix aralığı var; 50-sində yoxdur.
   **Müəllim adı 829 sətirdə (10.1 %) bərpa olunmadı.**
9. **≤2024 budağı daha zəifdir.** Çapın kəsdiyi sətirlərdən 2023–2024 vahid budağında
   **127 sətirdən 63-ü (50 %)** v3-ün gözündən qaçır; 2025+ budağında **4 476 sətirdən
   321-i (7 %)**. Siyahıda ≤2024 budağı cəmi **371 sətirdir**, amma orada verdikt daha
   şübhəlidir (§1.6/6).
10. **Sətir verdikti ilə ölçü rəqəmi eyni «il» tərifini işlətmir.** Sətirdə dövr
    yazılışın **son çap ilidir**, ölçmədə isə **hər çap sətri öz ili** ilə yoxlanılır
    (§1.3 qeydi). 8 002 yazılış hər iki dövrdə çap olunub.
11. **Çap sətirlərinin mənbə faylı (`bal_rows.tsv`) yenidən quruldu.** Orijinal fayl
    iş qovluğundan silinmişdi; `rebuild_bal_rows.py` onu `balvereqi_logs`-dan yenidən
    parse etdi (**904 252 sətir** — müstəqil parserin sayı ilə **eyni**). Yenidən
    qurulmuş fayl bütün əsas rəqəmləri **eynilə** verir (nəzarətli 629 258 · qayıb > 0
    476 886 · bayraqlı açar 8 757 · bağlana bilməyən 1 256 · v3 nərdivan payı 50.0 %).
    **Yeganə fərq:** bağlana bilməyən bayraqlı çap sətri 22 964 → **22 965** (+1 sətir,
    12 427 → **12 428** vərəq).
12. **Bu siyahı köhnə sistemin qərarını SƏHV elan etmir** — yalnız sübutu zəif və ya
    ziddiyyətli olan halları ayırır. Son söz universitetindir.

---

## 6. Nə etmək lazımdır

**Sistemə heç nə etmək lazım deyil.** Köhnə statuslar olduğu kimi köçürülür.
Prioritet sırası:

1. **★ «Bağlana bilmədi» vərəqi (1 256 açar, 750 tələbə) — ƏN VACİB.** Köhnə sistem
   bu tələbələri kəsib, yeni sistemdə qarşılığı yoxdur. **640-ı 2025, 317-si 2026**
   ilinə aiddir. 457-si köçürmədə `skipped` olub — **düzəlişi bizim tərəfdədir.**
2. **★ TƏK PLANLI 2 469 sətir üçün kafedradan `fenn_saati` təsdiqi.** Bu, bir sorğu ilə
   siyahının 30 %-inin verdiktini etibarlı edir. (45, 75, 15, 105, 35 saatlıq fənlər.)
3. **★ PLAN SAATI 0 olan 2 103 sətir üçün həqiqi auditoriya saatı.** «Status dəyişir»
   (311) və «Köhnə jurnal natamam» (383) tam bu səbətdədir.
4. **E1 (2 106 sətir) — «kəsilib, amma imtahana buraxılıb».** v3 ilə **2 003-ü həqiqətən
   kəsilir** → sual sadədir: **bar əl ilə kim və hansı əsasla keçib?**
5. **I (775 sətir)** — çapda bayraq yoxdur, amma qayıb həddi açıq aşır. Ən kəskin ziddiyyət.
6. **F-in qalan 139 sətri** (965-i v3 ilə bağlandı).
7. **K (53 sətir)** — nə v1-in «data pozuntusu», nə v2-nin «təmizdir» yarlığı əsaslıdır;
   28-i tək planlıdır, kafedra təsdiqi ilə bağlanır.
8. **C və D (422 sətir)** yalnız məxrəc təsdiqləndikdən sonra.

---

## 7. Metodika (texniki qeyd)

- Bütün sorğular `SELECT` / `COPY TO STDOUT` idi; **heç bir yazı** aparılmadı.
- **Generator:** `scratchpad/qb_kesilenler/generate.py` — giriş fayllarını, onları yaradan
  sorğuları və məxrəc qatını sənədləşdirir; XLSX/CSV/TSV çıxışlarını təkrar istehsal edir.
- **Məxrəcin validasiyası:** `scratchpad/v3/validate3.py` (namizəd müqayisəsi + həqiqi
  xəta payı) · `v3/why.py` (niyə 100 % deyil — tavan ölçüsü) · `v3/probe6.py` (vahid
  keçidi, çap ili üzrə) · `v3/probe8.py` (eyni yazılışın iki dövrdəki çapı — ×2 sübutu) ·
  `v3/diff23.py` (v2 → v3 fərq cədvəli).
- Bayraq mənbəyi: `balvereqi_logs.data` HTML-i — davamiyyət xanasındakı
  `<strong>(Kəsr)</strong>`. Parser (v3.1-də yenidən quruldu):
  `scratchpad/rebuild_bal_rows.py` → `scratchpad/bal_rows.tsv` (19 sütun, 904 252 sətir;
  td[2] = «Davamiyyət», `export_table_to_excel_<id>` = jurnal cədvəli).
- **Render modeli (v3.1):** `render_dav(N, m, dövr)` — 2025+ üçün
  `10 − m·trunc₂(10/N)`, ≤2024 üçün `10 × (N − m) / N`. **«★ Davamiyyət balı … N₃ ilə»
  sütunları artıq bu modelə görə hesablanır** (v3-də hər sətir kəsilməmiş düsturla
  yazılırdı, sənəd isə nərdivanı elan edirdi — uyğunsuzluq aradan qaldırıldı).
- **Nəzarətli populyasiya tərifi:** `enr_before.üzrsüz_saat == enr_after.üzrsüz_saat`,
  yəni bərpa qayıbı dəyişməyib → çapdakı qayıb = indiki qayıb → məxrəcdən başqa
  dəyişən yoxdur.
- Örtük boşluğu: `map.tsv`-dəki `journal_enrollment` xəritəsi
  (`legacy_pk = "<jurnalUniqid>:<tələbəId>"`) — köçürmənin öz **rəsmi** xəritəsi.
- E1/E2 bölgüsü: hər (tələbə × fənn × qrup) üçün çap tarixçəsi sıralanır və imtahan
  balının **ilk yazıldığı anda** bayrağın vəziyyətinə baxılır.
- Yeni sistemin buraxılış qaydası: `apps/registrar/exam_eligibility.py`.

**Fayllar**

| Fayl | Nədir |
|---|---|
| `QB_KESILENLER.xlsx` | Sahibin işlək faylı — **11 vərəq**, filtrli, rəngli. ★ sütunlar məxrəc qatıdır |
| `QB_KESILENLER.csv` | Eyni siyahı düz mətn (UTF-8 BOM) — 8 221 sətir, **49 sütun** |
| `QB_KESILENLER_M_baglana_bilmedi.csv` | 1 256 bağlana bilməyən açar |
| `qb_kesilenler/generate.py` | Generator — hamısını yenidən yaradır |
| `qb_kesilenler/QB_*.tsv` | Hər kateqoriyanın xam faylı (texniki) |
| `*_v2.*.bak`, `qb_kesilenler/generate_v2.py.bak` | v2 nüsxələri (müqayisə üçün saxlanılıb) |
| `QB_KESILENLER_v3a.xlsx.bak` · `_v3a.csv.bak` · `QB_KESILENLER_v3.md.bak` | **v3 nüsxələri** (v3.1-dən əvvəlki nəşr) |
| `qb_kesilenler/generate_v3b_pre_era.py.bak` | generator-un v3.1 düzəlişindən əvvəlki nüsxəsi |
| `rebuild_bal_rows.py` → `bal_rows.tsv` | çap sətirlərinin yenidən qurulmuş mənbə faylı (904 252 sətir) |
| `probe_era_render.py` · `probe_qb_ceiling.py` · `probe_ceiling_universe.py` | v3.1 render ölçmələri (§0, §1.3, §1.6) |
