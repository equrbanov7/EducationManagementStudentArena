# Sillabus redaktoru — bitirilməyən iş

**Tarix:** 2026-08-31 · **Şaxə:** `Develop`
**Vəziyyət:** sahib sillabus istiqamətini bağladı («müəllim yenidən özü yaradar
sillabusunu sonra»).  Aşağıdakılar **qəsdən** düzəldilməyib — sənəd ona görə
var ki, geri qayıtmaq mümkün olsun.  Hər maddə üçün: nə problemdir · miqyası ·
necə ölçülüb · hazır həll varsa yeri · niyə indi edilmədi.

> Bu sənəddəki heç bir maddə üzrə kod dəyişikliyi edilməyib.
> Bağlanan (və ölçülmüş) yeganə şey **«+ Təlim nəticəsi əlavə et» ölü düyməsi**
> idi — onun qapısı `apps/syllabus/tests/test_editor_add_outcome.py`-dədir.

---

## 1. Göndərilən JS-in test qapısı sındırıla bilir

### Nə problemdir

`apps/syllabus/tests/editor_dom.py` — göndərilən `syllabus_editor_fields.js`
toplayıcısının **Python-da yenidən yazılmış nüsxəsidir**.  Semantik testlər
(`test_editor_shipped_js.py`-dəki «məzmun itmir» qapıları) həmin **güzgünü**
icra edir, brauzerə gedən JS-i yox.  Yəni real icra yeri qapısızdır.

Bu gün ikisini bağlayan yeganə şey `test_editor_shipped_js.CONTRACT_DIGEST`-dir:
göndərilən faylın `@collector-contract:begin/end` sentinel-ləri arasındakı
blokun SHA-256-sı testdə bərkidilib.  Blokda bir bayt dəyişsə qapı çökür.

**Qapının zəif yeri:** barmaq izini «sadəcə yeniləmək» öz sənədində
**icazəlidir** (test faylının docstring-i bunu açıq yazır).  Yəni güzgünü
yeniləmədən JS-i dəyişən adam testi yaşıllaşdıra bilir — qapı şüursuz sürüşməni
tutur, qəsdən (və ya tələsik) yan keçməni yox.

### Miqyas

Toplayıcının qorunan səkkiz bölməsi: `info` · `desc` · `out` · `week` ·
`method` · `assess` · `self` · `lit`.  Ölçülmüş itki yolları bu blokdadır
(köçürülmüş sillabuslar üzrə: `out.outcomes` 4,790 · `method` 8,260 ·
`self.topics` 8,258 · `week` sətir açarları 8,220 · `assess.note` 5,893).

### Necə ölçülüb

Göndərilən JS-də hər iki `carried()` çağırışı orijinal (səhv) formaya
qaytarıldı → **7 semantik testin 7-si də YAŞIL qaldı.**  Yəni mutasiya
öldürülmədi: testlər güzgünü icra edirdi.

### Hazır həll (repoda DEYİL)

```
`apps/syllabus/tests/e2e/`
```

Node + jsdom qoşqusu: serverin render etdiyi HƏQİQİ panelləri jsdom-a qoyur,
göndərilən `syllabus_editor_fields.js` + `syllabus_editor.js` fayllarını
**olduğu kimi** icra edir və autosave gövdəsini oradan oxuyur.

* `regress.js` — sürücü (EMSReady/EMSDelegate/EMSCore stub-ları, davranışı
  saxlayan);
* `test_real_js_roundtrip.py`, `test_regression.py`, `test_banner.py`,
  `test_fifth_path.py`, `test_empty_outcomes.py` — pytest sarğıları;
* `package.json` → `jsdom ^24`;
* ölçülmüş nəticə: **19/19 mutasiya öldürüldü**.

Eyni naxışın daha yeni, uçdan-uca nümunəsi (yeni qaralama → düymə → 100% →
təsdiq): `…/scratchpad/deadbtn/` (`add_outcome_e2e.js` +
`test_add_outcome_e2e.py`).

### Niyə indi edilmədi

CI-da **Node yoxdur**.  Qoşqunu repoya salmaq CI-ya node + `npm ci` addımı
əlavə etmək deməkdir (yeni qapı, yeni keş, yeni uğursuzluq səthi) — sahib
istiqaməti bağladığı gecə buna girmək düzgün deyildi.  Ona görə repoda qalan
qapılar **node-suz**: barmaq izi + mətn-müqavilə + render yoxlaması.

### Qayıdanda nə etməli

1. CI-ya node addımı əlavə et (yalnız `apps/syllabus/tests/` üçün ayrıca job).
2. `…/scratchpad/e2e/` qoşqusunu `apps/syllabus/tests/e2e/` altına köçür.
3. `editor_dom.py` güzgüsünü **sil** — jsdom onu artıq lazımsız edir; qalan
   yeganə həqiqət mənbəyi göndərilən JS olur.  `CONTRACT_DIGEST` də gedir.

---

## 2. `assess.project` — toxunulmadan yazılan bal

### Nə problemdir

Qiymətləndirmə panelində müəllim **sürüşdürücüyə toxunmadan** «Qaralama saxla»
basanda autosave gövdəsi `midterm: 0, project: 30` göndərirdi (`project` =
`data-flex − midterm`).  Köçürmə isə qəsdən `midterm: 0, project: 0` yazır —
bu cüt «bölgü YOXDUR» deməkdir və oxu sənədi (`apps.syllabus.document`) onu
`None` sayıb tələbəyə heç nə göstərmir.

Nəticə: tələbə sillabusda **heç kimin yazmadığı** bal bölgüsü görürdü.

### Miqyas

Köçürülmüş bütün sillabuslar — hər biri müəllimin qiymətləndirmə addımına bir
dəfə girməsi ilə zədələnirdi.  Yalnız oxu səthi (tələbənin gördüyü sənəd)
təsirlənir; jurnaldakı real ballar bu sahədən gəlmir.

### Necə ölçülüb

jsdom qoşqusunda panel açılıb heç nəyə toxunulmadan `collect(root, "assess")`
çağırıldı → gövdədə `project: 30` göründü, halbuki DOM-da o rəqəmi yazan heç
bir istifadəçi əməli yox idi.

### Vəziyyət — DİQQƏT

Bu maddə **paralel iş axını tərəfindən artıq düzəldilib** (işçi ağacda,
commit olunmamış): `collectAssess` indi bal açarlarını yalnız sürüşdürücüdə
`data-touched="1"` bayrağı varsa göndərir; bayraq `input`/`change` hadisəsində
qoyulur, yəni **0 seçmək də toxunmaqdır** və silmə niyyəti kimi ötürülür.
Bayraq yoxdursa açar ümumiyyətlə göndərilmir → serverdəki bölgü toxunulmaz
qalır (fail-safe).

Qapısı: `test_editor_shipped_js.py::test_assess_collector_writes_scores_only_after_the_slider_was_touched`.

⚠️ Amma bu qapı da **güzgünü** icra edir (bax maddə 1) — yəni düzəlişin
göndərilən JS-də qalması hələ də yalnız `CONTRACT_DIGEST`-lə qorunur.

---

## 3. Struktur-saxlama yarışı digər bölmələrin gözləyən redaktələrini atır

### Nə problemdir

`syllabus_editor.js`-də `STRUCTURAL = { out: true, self: true }`.  Bu iki bölmə
saxlanandan sonra fraqment serverdən **yenidən yüklənir** (`reloadSection`),
çünki server markup-u dəyişir (TN etiketləri, tapşırıq yuvaları, arxiv sətirləri).

Yarış budur: `flush()` növbədən **bir** bölmə götürür (`pending[0]`), qalanları
`dirty` obyektində saxlayır.  Struktur bölmə saxlanandan sonra `flush(el)`
çağırılmır — funksiya `reloadSection` ilə **qayıdır**.  Fraqment yenidən
yüklənəndə DOM tam əvəzlənir, `dirty` isə modul səviyyəsində qalır, amma onun
göstərdiyi panellər artıq **serverdən gələn köhnə dəyərlə** doludur.

Praktik ssenari: müəllim təsvir sahəsinə yazır (debounce 800 ms işləyir) və
800 ms bitməmiş «nəticə əlavə et» düyməsinə basır → `out` dərhal saxlanılır →
fraqment yenidən yüklənir → **təsvirə yazılan mətn itir**.

### Miqyas

Ölçülməyib.  Yalnız kod oxunuşu ilə müəyyən edilib — vaxt pəncərəsi dardır
(800 ms), amma iki struktur bölmənin hər saxlanışında mövcuddur, yəni nəticə
və sərbəst iş redaktəsi zamanı təkrarlanan risk.

### Necə yoxlamalı (təkrar-icra resepti)

`…/scratchpad/e2e/regress.js` naxışı ilə: `desc` sahəsinə `input` hadisəsi
göndər (debounce başlasın), 800 ms bitməmiş `[data-syl-outcome-add]`-a klik et,
`EMSProfileLoadSection` stub-unu **həqiqətən** paneli əvəz edən funksiya ilə
dəyiş, sonra autosave gövdələrini oxu: `desc` üçün gövdə heç vaxt getməyəcək.

### Niyə indi edilmədi

Düzəlişin özü kiçikdir (struktur saxlamadan ƏVVƏL qalan `dirty` bölmələri
flush et, və ya `reloadSection`-u yalnız növbə boşalandan sonra çağır), amma
autosave mühərrikinin növbə semantikasına toxunur — sahib istiqaməti bağlayan
gecədə, sabah komanda yoldaşı işə başlayanda, avtosaxlama davranışını
dəyişmək düzgün risk deyil.  Ölçülməmiş problem üçün ölçülməmiş düzəliş
göndərilmir.

---

## 4. ƏLAVƏ TAPINTI — yeni qaralama 100%-ə HEÇ VAXT çata bilmir

> Bu maddə brifinqdə yox idi; «yeni sillabus yarat → təsdiqə göndər» uçdan-uca
> yoxlanışı zamanı ölçüldü.  **Sahibin dediyi yol məhz budur** («müəllim
> yenidən özü yaradar sillabusunu»), ona görə burada qeyd olunur.

### Nə problemdir

`apps/accounts/views/syllabus/api.py::_do_create` yeni versiyanı
`plan_hours={}` ilə açır.  `apps/syllabus/completion.py::_check_week` isə:

* hər dərs növü üzrə saat cəmi `plan_hours`-dakı gözlənilən dəyərə **bərabər**
  olmalıdır → boş plan = cəm **0** olmalıdır;
* mövzusu dolu olan hər sətir **ən azı 1 saat** daşımalıdır
  (`week.topic_without_hours`), və ən azı 14 sətir dolu olmalıdır.

İki qayda **bir-birini istisna edir**.  `week` bölməsi ödənilə bilmir →
tamamlanma 8-dən 7 bölmə = **88%** → `submit` `requires_complete` qapısında
`transition.incomplete` ilə dayanır.

### Necə ölçülüb

`…/scratchpad/deadbtn/test_add_outcome_e2e.py::test_new_draft_button_fills_the_out_section`
— HTTP `action=create` ilə qaralama açır, bütün 8 bölməni həqiqi autosave
ucundan doldurur:

```
[YENİ QARALAMA] v1.0 · plan_hours = {}
  tamamlanma: 88 % · {'info': True, 'desc': True, 'out': True, 'week': False,
                      'method': True, 'assess': True, 'self': True, 'lit': True}
  qalan çatışmazlıq: [{'section': 'week', 'code': 'week.topic_without_hours',
                       'params': {'count': 14}}]
```

Müqayisə üçün eyni testdə `plan_hours` DOLU olan versiya (köçürülmüş dosyenin
yeni qaralaması) **100%** verir və `submitted` statusuna keçir.

### Niyə indi edilmədi

Düzəlişin yeri `_do_create`-dir, amma **doğru dəyəri haradan alacağı** sillabus
modulundan kənardadır: mühazirə/seminar/laboratoriya bölgüsü tədris planından
gəlməlidir (bax `project_tedris_plani_ders_yuku_zenciri` — 1 kredit = 30 saat /
15 həftə, saat düsturu birləşmə/yarımqrup ilə dəyişir).  `CourseOffering` yalnız
`lesson_hours` **cəmini** daşıyır, bölgünü yox.  Yəni bu, bir sətirlik düzəliş
deyil, `apps/workload` ↔ `apps/syllabus` arasında yeni müqavilədir — bu
tapşırığın icazə verilən sahəsindən kənar.

### Qayıdanda nə etməli

1. Bölgü mənbəyini qərarlaşdır (tədris planı sətri, yoxsa müəllimin özünün
   girdiyi bölgü?).
2. `_do_create`-ə `plan_hours` ötür; mənbə yoxdursa **müəllimə açıq şəkildə
   soruş** — səssiz `{}` ən pis variantdır, çünki səbəbi görünmür.
3. Alternativ (ucuz) yol: `plan_hours` boş olanda `_check_week` saat bərabərliyi
   qaydasını **tətbiq etmə** (yalnız «mövzu var, saat var» qalsın).  Bu, yeni
   qaralamanı dərhal göndərilə bilən edir, amma plan uyğunluğu qapısını itirir.

---

## Bağlanmış maddə (məlumat üçün)

**«+ Təlim nəticəsi əlavə et» ölü düyməsi** — `addOutcome` mövcud sətri
klonlayırdı, şablonda `{% empty %}` budağı yoxdur, `outcomes == []` olanda
0 sətir render olunur → klon mənbəyi tapılmır → düymə səssizcə heç nə edirdi.
Miqyas: 8,247 başlığın 2,157-si (26.2%) + hər yeni qaralama.

Düzəliş: klon mənbəyi yoxdursa sətir `EMSSyllabusFields.makeOutcomeRow` ilə
sıfırdan qurulur (mətn şablonun `data-t-placeholder`-indən gəlir — dörd dil
pozulmur).  Qapı: `apps/syllabus/tests/test_editor_add_outcome.py` (5 test,
node tələb etmir).  Uçdan-uca sübut: `…/scratchpad/deadbtn/`.
