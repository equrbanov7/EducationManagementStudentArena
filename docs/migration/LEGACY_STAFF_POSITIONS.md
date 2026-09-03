# Köhnə sistemdə («myedudb») vəzifə məlumatı — nə var, nə yoxdur

**Tarix:** 2026-08-31 · **Mənbə:** `myedudb` repetisiya dump-ı (729 `workers` sətri)

Bu sənəd `workers.teacher_type` və `workers.inzibati` sütunlarının mənasının
**datadan** necə çıxarıldığını, nəyin naməlum qaldığını və hədəfə nəyin
yazıldığını qeyd edir. Kodda istinad: `core/staff_position.py`,
`apps/accounts/management/commands/import_legacy_staff_positions.py`.

---

## 1. Ayrıca vəzifə cədvəli YOXDUR

Mənbədə vəzifə (dekan, kafedra müdiri, proqram koordinatoru…) saxlayan cədvəl
və ya sütun tapılmadı. Yoxlanılan yerlər:

| Namizəd | Nəticə |
|---|---|
| `information_schema` üzrə `%vezif%`, `%position%`, `%dekan%`, `%rehber%`, `%mudir%`, `%title%`, `%role%`, `%head%`, `%kafedra%`, `%derece%`, `%elmi%` sütun axtarışı | Yalnız `sillabus.dekan_id`, `sillabus.kafedra_id`, `xidmeti_muraciet.head`, `notifications.head` |
| `sillabus.dekan_id` | **8,248 sətrin hamısında 0** — istifadə olunmayıb |
| `sillabus.kafedra_id` | **8,248 sətrin hamısında 0** — istifadə olunmayıb |
| `departments` cədvəlində rəhbər sütunu | **yoxdur** (`id, name, phone, adress, who_is_added, kollec_or_uni, img_url, department_id, department_types_id, added_date, update_date, note, text`) |
| `sillabus_elmi_maraq` və s. | müəllim haqqında sərbəst mətn, vəzifə yox |
| `ferdi_plan` (fərdi plan) | **0 sətir** |

Deməli vəzifəyə oxşar bütün siqnal üç yerdədir: `workers.inzibati`,
`workers.teacher_type`, `workers_permits.permits`.

---

## 2. `workers.inzibati` — MƏNASI ÇIXARILDI: «inzibati işçi»

Bölgü: `0 → 596`, `1 → 133`.

**Sübut 1 — dərs yükü.** `inzibati=1` olanların yalnız **43.6 %-nin** (58/133)
ümumiyyətlə jurnalı var; `inzibati=0` olanlarda bu göstərici **87.6 %-dir**
(522/596). Yəni bayraq «dərs deməyən, amma sistemdə olan işçi» qrupunu ayırır.

**Sübut 2 — inzibati səhifə icazələri.** `inzibati=1` işçilər ümumi heyətin
**18 %-idir**, lakin inzibati icazələrin böyük hissəsini onlar daşıyır:

| `permits` tokeni | `inzibati=1` | cəmi | pay |
|---|---:|---:|---:|
| `dekan` | 13 | 16 | 81 % |
| `journals_admin` | 34 | 47 | 72 % |
| `journals_report` | 22 | 29 | 76 % |
| `report_hours` | 13 | 18 | 72 % |
| `students` | 38 | 55 | 69 % |
| `teachers` | 16 | 22 | 73 % |
| `curricula` | 16 | 21 | 76 % |
| `journal_close` | 51 | 66 | 77 % |

Müqayisə üçün sırf müəllim tokenləri (`sillabus`, `showjournals`, `journals`)
`inzibati=1`-də cəmi ~16 % paya malikdir — yəni zənginləşmə təsadüfi deyil.

**Qeyd — bu vəzifə ADI deyil, kateqoriyadır.** `inzibati=1` işçinin dekan,
kafedra müdiri, katib və ya mühasib olduğunu demir. Ona görə hədəfə yazılan
etiket də kateqoriyadır: **«İnzibati işçi»**.

**Qeyd 2.** `inzibati=1` işçilərin hamısı akademik kafedralara
(`departments.department_types_id = 4`) bağlıdır — köhnə sistemdə inzibati
şöbə üçün ayrıca vahid tipi yox idi, ona görə struktur bu bayraqdan oxuna bilməz.

---

## 3. `workers.teacher_type` — NAMƏLUM QALDI

Bölgü: `1 → 451`, `2 → 258`, `3 → 20`.

**Nə istisna olundu (sübutla):**

| Fərziyyə | Yoxlama | Nəticə |
|---|---|---|
| Vəzifə/rol kodudur | üç dəyərin hamısı dərs deyir (jurnalı olan: 335 / 228 / 17) | **istisna** |
| Müəllim / qeyri-müəllim ayrımıdır | eyni səbəb | **istisna** |
| Kollec ↔ universitet ayrımıdır | `kollec_or_uni` ilə çarpaz: hər üç dəyər hər iki tərəfdə | **istisna** |
| Əyani ↔ qiyabi ayrımıdır | jurnalların `eyani_qiyabi` bölgüsü üç dəyərdə praktiki eynidir (əyani payı 85.5 % / 84.4 % / 82.0 %) | **istisna** |
| Öz kafedrasının fənni ↔ kənar fənn | `lessons.department_id = workers.department_id` payı: 78.1 % / 79.8 % / 71.2 % | **istisna** |
| Mühazirə ↔ seminar | `lessons.type` bütün sətirlərdə boşdur | **yoxlanıla bilmir** |
| Kafedraya bağlıdır | hər üç dəyər praktiki olaraq bütün 19 kafedrada var | **istisna** |

**Nə müşahidə olundu:**

* Yük fərqi: müəllim başına orta jurnal `tt=1 → 20.7`, `tt=2 → 12.1`,
  `tt=3 → 24.5`; orta fənn saatı `880 / 525 / 1121`.
* İnzibati səhifə icazələrini **praktiki olaraq YALNIZ `tt=1` daşıyır**:
  `dekan` 16/16, `journals_admin` 45/47, `report_hours` 18/18, `curricula`
  21/21, `lessons` 16/16, `rooms` 12/12, `specialities` 11/11, `curricula_plan`
  11/11. `tt=2` bir dənə də `dekan`/`report_hours`/`curricula` icazəsi
  daşımır; `tt=3` heç birini daşımır.
* `tt=3` cəmi 20 nəfərdir və içində iki test/könüllü hesabı var
  (`konullugulsen`, `konullurena` — 0 jurnal).

Bu, `tt=1`-in «əsas/ştat heyət», `tt=2`-nin isə «əlavə/saathesabı» olduğu
oxunuşu ilə uyğundur, **lakin sübut deyil** — `tt=3` bu oxunuşa oturmur
(ən böyük yük ondadır). Sənədləşdirilmiş mənbə tapılmadığı üçün **kod naməlum
elan olunur** və heç bir etiketə çevrilmir.

> ⚠️ Sahibdən tələb olunan qərar: `teacher_type` 1/2/3 kodlarının HR mənası.
> Cavab gələnə qədər `import_legacy_staff_positions` yalnız bölgünü çap edir.

---

## 4. `workers_permits.permits` — yeganə vəzifə-şübhəli siqnal

914 sətir; JSON massivi kimi saxlanılan **səhifə icazələri**. Vəzifə adı DEYİL —
dekanlıq əməkdaşı da `dekan` tokenini ala bilərdi. Ona görə avtomatik
YAZILMIR, əmr onları «əl ilə təsdiq» siyahısı kimi çap edir.

| Token | Daşıyan | `inzibati=1` | `tt=1` |
|---|---:|---:|---:|
| `dekan` | 16 | 13 | 16 |
| `kafedra` | 13 | 7 | 11 |

16 nəfər `dekan` tokeni daşıyır, halbuki mənbədə cəmi 9 fakültə/məktəb
(`department_types_id = 3`) var → token təkbaşına «dekan» vəzifəsini vermir.

**Proqram koordinatoru:** mənbədə belə bir token, sütun və ya cədvəl **yoxdur**.

---

## 5. Mənbə faylının çıxarılması

```bash
mariadb -h <host> -u <user> -p myedudb --batch --default-character-set=utf8mb4 -e "
SELECT w.id, w.email, w.inzibati, w.teacher_type, COALESCE(p.permits, '[]')
FROM workers w LEFT JOIN workers_permits p ON p.worker_id = w.id;
" | tail -n +2 > workers.tsv
```

TSV → JSON (`permits` mənbədə mətn kimi saxlanılan JSON massividir, ona görə
ayrıca `json.loads` lazımdır):

```python
import json

rows = []
for line in open("workers.tsv", encoding="utf-8"):
    worker_id, email, inzibati, teacher_type, permits = line.rstrip("\n").split("\t")
    try:
        parsed = json.loads(permits)
    except ValueError:
        parsed = []
    rows.append({
        "legacy_worker_id": int(worker_id),
        "username": email,          # hədəfdəki User.username ilə uyğunlaşdırın
        "inzibati": int(inzibati),
        "teacher_type": int(teacher_type) if teacher_type not in ("", "NULL") else None,
        "permits": parsed if isinstance(parsed, list) else [],
    })
json.dump(rows, open("workers.json", "w", encoding="utf-8"), ensure_ascii=False)
```

```bash
python manage.py import_legacy_staff_positions --source workers.json          # quru işləyiş
python manage.py import_legacy_staff_positions --source workers.json --apply  # yazır
```

`username` sahəsi hədəfdəki `User.username` ilə **eyni** olmalıdır; uyğun
gəlməyən sətirlər sayılır və atlanılır.

---

## 6. Hədəfə necə yazılır

| Mənbə faktı | Hədəf | İcazə təsiri |
|---|---|---|
| `inzibati = 1` | `UserProfile.staff_position = «İnzibati işçi»` | **YOX** — sırf mətn |
| `inzibati = 0` | yazılmır | — |
| `teacher_type` (istənilən) | yazılmır (naməlum) | — |
| `permits: dekan` / `kafedra` | yazılmır → hesabatda əl-təsdiq siyahısı | — |

* **Rol təyinatı YOXDUR.** Naməlum mənbə koduna görə heç kimə dekan/kafedra
  müdiri səlahiyyəti verilmir.
* **Additive:** yalnız boş `staff_position` doldurulur.
* **Quru işləyiş defolt**, yazmaq üçün `--apply`.

Vəzifə etiketi səthlərdə bu zəncirlə göstərilir (bax `core/staff_position.py`):

```
Membership.title  →  UserProfile.staff_position  →  real rol adı  →  (boş)
```

Doldurucu `member` rolu bu zəncirdən **kənardadır** — vəzifəsi olmayan
istifadəçinin adının yanında «Üzv» yazılmır, sahə boş qalır.
