# Dev serveri işə salmaq (daphne)

## Qısa cavab

Terminalda (istənilən qovluqdan):

```bash
ddaphne
```

→ http://127.0.0.1:8000 · dayandırmaq: `Ctrl+C` · loglar elə terminaldadır.

⚠️ **Default baza KLONDUR** (sahib qərarı 2026-09-06): `ddaphne` `:8100`-ün
göstərdiyi `emsarena_rehearsal_*` bazasını açır, yəni gündəlik test **real
datanı əlləmir** — real bazanı prod-a köçürməzdən əvvəl toxunulmaz saxlamaq
üçün. Real baza lazımdırsa: `REAL=1 ddaphne`. Klon `qa.*` hesabları hər iki
portda işləyir.

`ddaphne` artıq ALIAS deyil, FUNKSİYADIR (`~/.zshrc` + `~/.bashrc`) və birbaşa
`scripts/dev-daphne.sh`-i çağırır. Skript **portu özü boşaldır**: əvvəlki
sessiyadan qalan daphne varsa onu dayandırıb yenisini qaldırır (yad proses
tutubsa toxunmur və başqa port təklif edir). Əvvəl belə deyildi — köhnə proses
portu tutanda `ddaphne` sadəcə «port tutulub» deyib çıxırdı, istifadəçi isə
«girə bilmirəm» sanırdı.

Faydalı variantlar:

| Əmr | Nə edir |
|---|---|
| `ddaphne` | 127.0.0.1:8000, **KLON bazası** (:8100 ilə eyni məzmun) |
| `REAL=1 ddaphne` | lokal **REAL** baza ilə (`.env`-dəki `DATABASE_URL`) |
| `REUSE=1 ddaphne` | işləyirsə toxunmur, sadəcə ünvanı yazır |
| `HOST=0.0.0.0 ddaphne` | LAN-dan görünsün (telefon, başqa kompüter) |
| `PORT=8010 ddaphne` | başqa port |
| `ddaphne-stop` | :8000-i dayandır |

LAN-dan (telefon, başqa kompüter) görünsün: `HOST=0.0.0.0 ./scripts/dev-daphne.sh`
Başqa port: `PORT=8010 ./scripts/dev-daphne.sh`

## «`ddaphne` yazıram, işləmir» — niyə

`ddaphne` **alias**-dır (`~/.zshrc`-in ilk sətri). Alias yalnız o faylı oxumuş
**interaktiv zsh** sessiyasında mövcuddur. Ona görə bu hallarda «command not found» olur:

| Hal | Nə baş verir |
|---|---|
| VS Code terminalı **bash** işə salır | zsh alias-ları ümumiyyətlə yüklənmir |
| Terminal alias əlavə olunmazdan **əvvəl** açılıb | köhnə sessiya alias-ı görmür (`source ~/.zshrc` lazımdır) |
| Skript/CI/`bash -c "…"` daxilində | alias-lar interaktiv olmayan shell-də tətbiq edilmir |
| `daphne` (bir «d» ilə) yazılıb | `daphne` PATH-da deyil — o, `venv/bin` içindədir |

`scripts/dev-daphne.sh` bunların HAMISINDAN azaddır: mütləq yol işlədir
(`venv/bin/daphne`), cari qovluqdan asılı deyil, hər shell-də işləyir.

## Port tutulubsa

Daphne kodu avtomatik yeniləmir və **köhnə proses portu tutub qalanda yeni daphne
səssizcə ölür** — brauzerdə köhnə kod görünməyə davam edir (bu tələ layihədə
dəfələrlə təkrarlanıb). `dev-daphne.sh` bunu dərhal deyir; təmiz restart üçün:

```bash
./scripts/restart-daphne.sh
```

Bu skript 8000 portundakı hər şeyi öldürür → miqrasiyaları yoxlayır → daphne-ni
arxa fonda (screen) qaldırır → HTTP cavabını təsdiqləyir.

Kim tutub baxmaq: `lsof -nP -iTCP:8000 -sTCP:LISTEN`

## VS Code

`.vscode/tasks.json` əlavə edilib (repo-da izlənmir — `.gitignore`-dadır, amma
lokal olaraq işləyir):

* **⌘⇧B** → «Daphne başlat (ön planda)»
* «Daphne təmiz restart (arxa fon)» — port tutulubsa
* «Testlər (sürətli, sqlite)» — yol soruşur
* «Lint (black + isort + flake8)»

`.vscode/launch.json` ilə **F5** debug: «Django runserver (debug)» və «Daphne (debug, ASGI)» —
hər ikisi `venv/bin/python` ilə, `DJANGO_SETTINGS_MODULE=config.settings.local`.

## QA klonu (ayrı server, :8100)

Auditdə işlədilən klon bazası ayrı skriptlədir və **port arqument DEYİL**, env-dir:

```bash
INSPECT_PORT=8100 STAGING_POSTGRES_DB=emsarena_rehearsal_a0d170000901 scripts/staging_inspect.sh serve
```

`scripts/staging_inspect.sh serve 8100` **İŞLƏMİR** (runserver «unrecognized arguments» verir,
skript səssizcə ölür və köhnə proses portda qalır).

## Push-dan əvvəl: lint qapıları

CI-nin lint işi **yeddi** qapı işlədir və hamısı repo-genişdir — fayl-fayl
`black` yoxlamaq kifayət etmir. Push-dan əvvəl:

```bash
./scripts/preflight.sh
```

Formatlaşdırma qapılarını avtomatik düzəltmək üçün `./scripts/preflight.sh --fix`.

Qapılar: `black`, `isort`, `flake8`, modul ölçüsü (600 sətir), modul sərhədi
(dövr yoxdur), i18n kataloqu (tərcümə borcu artmır), RLS worker-atomic əhatəsi
(request-dən kənar DB girişləri `rls_worker_atomic()` içində olmalıdır).

