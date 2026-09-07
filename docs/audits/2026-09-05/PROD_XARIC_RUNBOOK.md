# Prod: «Xaric olanlar» girişlərinin bağlanması — icra addımları

**Nə üçün.** QA auditi (P1-10 / P2-8) tapdı: köçürmədə «Xaric ol(un)anlar» adlı
psevdo-qrupa yığılan tələbələrin **statusu heç vaxt yazılmayıb** — akademik qeyd
hələ də `enrolled`, yəni **girişləri açıqdır**. QA klonunda bu **31 nəfər** idi.
Prod-da eyni qüsur davam edir — auditin ən ciddi açıq maddəsi budur.

**Hazır olan.** Skript yazılıb, klonda hər iki yolu ilə sınanıb, prod-ops
workflow-una qoşulub:

| | |
|---|---|
| Skript | `scripts/prod_ops/legacy_expelled_access.py` |
| Workflow | `.github/workflows/prod-exam-ops.yml` → `script: legacy_expelled_access` |
| Default | **DRY-RUN** (`apply` işarələnməsə heç nə yazılmır) |
| İdempotent | Bəli — artıq `expelled` olan qeyd və artıq `archived` olan profil atlanır |

**Bloker (2026-09-06 12:40).** İcra edilə bilmədi: **self-hosted runner qeydiyyatda
yoxdur** (`gh api …/actions/runners` → `total_count: 0`) və `10.0.2.42` LAN-dan
cavab vermir — yəni prod server bu an bağlıdır/şəbəkədən kənardır. Prod LAN-only
olduğu üçün başqa kanal yoxdur (SSH açıq deyil). Növbəyə qoyulan qaçış ləğv edildi
ki, gözlənilməz anda özbaşına işləməsin.

## Server qayıdanda — 2 addım

1. **Quru icra** (heç nə yazmır, siyahını göstərir):

```bash
gh workflow run prod-exam-ops.yml --ref Develop -f script=legacy_expelled_access
```

Çıxışda görünəcək: konteynerlərin adı, konteynerdəki qeyd sayı, **statusu hələ
açıq olanlar** və hər birinin `access_state`-i. Rəqəm gözləniləndirsə (klonda 31)
ikinci addıma keçin.

2. **Tətbiq:**

```bash
gh workflow run prod-exam-ops.yml --ref Develop -f script=legacy_expelled_access -f apply=true
```

İstəyə bağlı: `-f repair_actor=<username>` (boş = təşkilat sahibi),
`-f repair_order=<əmr nömrəsi>` (audit izində qalır).

## Skript nə edir (və nə etmir)

**Edir** — mövcud, review olunmuş səthlərlə:

1. `movements.create_movement(kind=EXPULSION, …)` — xam `UPDATE` **yox**: state
   maşını + append-only `StudentMovement` ledger sətri + audit;
2. profilin `access_state` → `archived` — giriş məhz orada bağlanır.

> İkinci addım prod-da AÇIQ yazılıb, çünki onu avtomatlaşdıran
> `movements._sync_access_state` Develop-dadır, prod image-i isə `main`-dən
> qurulur. Deploy-dan sonra bu addım artıq avtomatik olacaq.

**Etmir:** «Level 2025-2026» (228 real tələbə) və `Silinmelidir` qruplarına
toxunmur — onlar data-təmizliyi qərarıdır, təhlükəsizlik məsələsi deyil.
Vahidləri «xidməti» kimi işarələmək də burada yoxdur: `is_service_unit` sahəsi
prod sxemində hələ mövcud deyil (miqrasiya Develop-dadır).

## Klonda sınaq nəticəsi

| Ssenari | Nəticə |
|---|---|
| Boş qaçış (hamısı artıq xaric edilib) | `Konteyner: 1 · qeyd: 31 · açıq: 0` → 0 dəyişiklik |
| Qəsdən bir qeyd geri açıldı | `✓ Xaric edildi: 1 · girişi bağlandı: 0` (profil onsuz da arxivli) |

Klonda profili `archived → active` etməyə cəhd **trigger tərəfindən bloklandı**
(`accounts_reject_active_staged_profile`) — yəni qapı işləyir.
