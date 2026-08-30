# Sillabus köçürmə spesifikasiyası (MyEdu → EMS Arena)

Tarix: 2026-08-30 · Mənbə: `emsarena-legacy-source-rehearsal` / `myedudb`

Bu sənəd köçürmə **başlamazdan əvvəl** mənbə datasının nə olduğunu (və nə
OLMADIĞINI) qeyd edir.  Aşağıdakı rəqəmlərin hamısı canlı mənbə üzərində
sorğu ilə alınıb, təxmin deyil.

---

## 1. Mənbə strukturu

Bir başlıq cədvəli + 11 peyk cədvəl.  Peyklərin HAMISI `uniqid` ilə bağlıdır
(başlığın `sillabus.uniqid` sütunu), yad açar yoxdur.

| Cədvəl | Sətir | Sillabus (uniqid) | Rolu |
| --- | ---: | ---: | --- |
| `sillabus` | 8,248 | 8,247 | başlıq |
| `sillabus_sem_muh` | 132,905 | 8,220 | **həftəlik mövzular** (+ saat bölgüsü) |
| `sillabus_serbest_is` | 58,966 | 8,258 | sərbəst iş |
| `sillabus_imtahan_suallari` | 19,750 | 1,553 | imtahan sualları |
| `sillabus_derslikler` | 16,238 | 8,258 | dərsliklər / ədəbiyyat |
| `sillabus_elmi_maraq` | 10,435 | 8,219 | elmi maraq sahələri |
| `sillabus_certificates` | 9,672 | 8,176 | sertifikatlar |
| `sillabus_eldeolunacaq_tecrubeler` | 8,091 | 8,260 | əldə olunacaq təcrübələr |
| `sillabus_dersin_islenme_formasi` | 8,021 | 8,260 | dərsin işlənmə forması |
| `sillabus_yoxlama_formasi` | 7,714 | 8,261 | yoxlama forması |
| `sillabus_tesviri_ve_meqsedi` | 5,217 | 6,491 | təsviri və məqsədi |
| `sillabus_qarsilama_mesaji` | 4,422 | 4,676 | qarşılama mesajı |

Peyklərin sxemi eynidir: `id | uniqid | name:text` (yalnız `sem_muh` genişdir:
`movzu | muh_saat | sem_saat | praktiki_saat | lab_saat | tarix | qeyd`).

---

## 2. ⚠️ Datada OLMAYAN şeylər (sahibin fərziyyəsi ilə ziddiyyət)

Sahib 2026-08-30-da dedi: «əlavə olaraq təsdiqlənmiş kimi gəlsin hamısı, amma
onların **yaranma tarixi var**, hamısı **keçən semestrlər** üçün olandı».

Mənbədə yoxlandı — **bu belə deyil**:

| Gözlənilən | Mənbədəki reallıq |
| --- | --- |
| Yaranma tarixi | `sillabus` cədvəlində **heç bir tarix sütunu yoxdur** |
| Dərs tarixi | `sillabus_sem_muh.tarix` — **131,056 sətrin 131,056-sı BOŞ** |
| Semestr | Sütun yoxdur |
| Qrup | `qrup_id` — **8,248 sətrin hamısında 0** |
| Birləşən qruplar | `birlesen_qruplar` — **hamısında boş** |
| Fakültə / kafedra / ixtisas | `dekan_id`, `kafedra_id`, `ixtisas_id` — **hamısında 0** |
| Təsdiq vəziyyəti | `status` — **hamısında 0** (təsdiq axını heç vaxt işlədilməyib) |

Yəni köhnə sillabus **yalnız (fənn × müəllim) cütünə** bağlıdır:

```
sillabus → lesson_id  (1,822 fənn)  ✔ 8,248/8,248 tam uyğunlaşır
         → teacher_id (669 müəllim) ⚠️ 956 sətir (11.6%) qırıq — işçi silinib
```

Yeganə real tarix `lessons.added_date`-dir (2021-10-15 → 2026-05-07), amma bu
**fənn kataloqunun** tarixidir, sillabusun deyil.

### Nəticə (qərar tələb edir)

Köçürülən sillabusa semestr və ya yaranma tarixi **təyin etmək = data uydurmaq**.
Bu gecə düşmən yoxlayıcı məhz belə bir uydurmaya görə bir düzəlişi rədd etdi
(qrup uyğunsuzluğu).  Ona görə tövsiyə:

> Köçürülən sillabuslar **semestrsiz «baza sillabus»** kimi gəlsin:
> sahibi = müəllim, əhatəsi = fənn, statusu = `APPROVED`, təsdiqləyəni =
> «köçürmə (sistem)», kilid tarixi = köçürmə tarixi (uydurma yox, həqiqi).
> Konkret semestrə aid versiya lazım olanda müəllim dizaynda **onsuz da mövcud
> olan** «Keçən ildən köçür» düyməsi ilə ondan yeni DRAFT yaradır.

Bu, həm sahibin «təsdiqlənmiş gəlsin» tələbini ödəyir, həm də olmayan tarixi
uydurmur.  Alternativ (semestr təyin etmək) yalnız sahib açıq şəkildə hansı
semestri istədiyini deyəndə tətbiq olunmalıdır.

---

## 3. ⚠️ Kodlaşdırma: HTML entity-lər mütləq açılmalıdır

Köhnə PHP tətbiqi Latın-1 adlı entity-si olan hərfləri **escape edib**, olmayanı
hərf kimi saxlayıb:

| Hərf | Mətndə hərf kimi | Qeyd |
| --- | ---: | --- |
| `ə` | 71,270 sətir | hərf |
| `ı` | 51,591 | hərf |
| `ş` | 32,006 | hərf |
| `İ` | 9,389 | hərf |
| `ğ` | 7,812 | hərf |
| **`ç`** | **0** | yalnız `&ccedil;` |
| **`ü`** | **0** | yalnız `&uuml;` |
| **`ö`** | **0** | yalnız `&ouml;` |

`sillabus_sem_muh.movzu`-nun **54,716 / 131,056 sətri (41.7%)** entity daşıyır;
dırnaqlar da `&ldquo;` / `&rdquo;` şəklindədir.

**HTML tag YOXDUR** — dörd böyük mətn cədvəlində `<...>` daşıyan sətir sayı 0.
Ona görə `html.unescape()` kifayətdir və təhlükəsizdir (tag təmizləməyə ehtiyac
yoxdur; render Django avto-escape ilə gedir).

⚠️ Unescape edilməzsə hər ikinci mövzu ekranda `&ccedil;irklənmə` kimi görünəcək.

Kollasiya: bütün cədvəllər `utf8mb3_bin` (Azərbaycan dili üçün kifayətdir).

---

## 4. Dublikatlar və yetimlər

- **(fənn, müəllim) cütü unikal deyil:** 8,248 sətir → 5,646 cüt.
  4,172 cüt tək, qalanı təkrarlı (2 dəfə 945, 3 dəfə 294 … 19 dəfə 1).
  Nümunə: `lesson_id=4, teacher_id=282` üçün **7 sillabus**, hər birində eyni
  23 mövzu — yəni köhnə sistem çox güman hər açılış/qrup üçün nüsxə yaradıb,
  sonra qrup sütunları sıfırlanıb.
- **Təklif:** təkrarlar SİLİNMİR, **versiya** kimi köçürülür — `sillabus.id`
  artan sırada v1.0, v1.1 … ; ən sonuncusu `APPROVED`, əvvəlkilər `ARCHIVED`.
  Bu, uydurma olmadan həm tarixçəni saxlayır, həm siyahını təmiz göstərir.
  Məzmun eynidirsə (hash) tək versiya kimi qatlanır və uzlaşdırmada qeyd olunur.
- **14 yetim `uniqid`** — başlığı olmayan bölmə sətirləri.  Atılır, amma
  uzlaşdırma qalığı kimi hesabata yazılır (səssizcə itməsin).
- `active`: 7,534 aktiv / 714 qeyri-aktiv.  Qeyri-aktivlər `ARCHIVED` gəlir.

---

## 5. Bölmə uyğunlaşdırması (mənbə → dizaynın 10 bölməsi)

| Mənbə cədvəli | Dizayn bölməsi (README §3.2) |
| --- | --- |
| `sillabus_qarsilama_mesaji` | qarşılama / giriş |
| `sillabus_tesviri_ve_meqsedi` | fənnin təsviri və məqsədi |
| `sillabus_sem_muh` | **həftəlik mövzu planı** (+ mühazirə/seminar/praktiki/lab saatı) |
| `sillabus_serbest_is` | sərbəst iş |
| `sillabus_dersin_islenme_formasi` | tədris metodları |
| `sillabus_yoxlama_formasi` | qiymətləndirmə |
| `sillabus_imtahan_suallari` | imtahan sualları |
| `sillabus_derslikler` | ədəbiyyat |
| `sillabus_eldeolunacaq_tecrubeler` | öyrənmə nəticələri |
| `sillabus_elmi_maraq` + `sillabus_certificates` | müəllim profili (elmi maraq, sertifikatlar) |

Peyk sətirləri sıralı siyahıdır — `id` sırası saxlanılır.

---

## 6. Köçürmənin şərtləri (repetisiya çərçivəsinə uyğun)

1. Sahə müqaviləsi (`LegacySourceFieldContract`) hər 12 cədvəl üçün yazılır;
   barmaq izi faza törəməsinə qatılır.
2. `html.unescape()` **transform-un bir hissəsidir** və `transform_version`-a
   təsir edir (sonradan dəyişsə, yenidən köçürmə tələb olunur).
3. Ledger: hər sillabus üçün `LegacyEntityMap` (`source_table='sillabus'`,
   `source_pk=id`), hər bölmə üçün müşahidə.
4. Uzlaşdırma: 8,248 başlıq + 279,431 bölmə sətri mənbə↔hədəf sayı;
   izahsız qalıq **0** olmalıdır (14 yetim + qırıq müəllim izahlı qalıqdır).
5. Müəllimi tapılmayan 956 sillabus: **atılmır**, «müəllimi həll olunmayıb»
   qeydi ilə köçürülür (jurnal köçürməsindəki `instructor_unresolved` nümunəsi).

---

## 7. Açıq qərarlar (sahib)

1. **Semestr/tarix:** §2-dəki tövsiyə (semestrsiz baza sillabus) qəbul olunurmu,
   yoxsa hamısı konkret bir semestrə (məsələn 2025/2026 Yaz) yazılsın?
2. **Təkrarlar:** versiya kimi saxlanılsın, yoxsa yalnız sonuncusu köçürülsün?
3. **Müəllimi silinmiş 956 sillabus** kimə aid görünsün?
