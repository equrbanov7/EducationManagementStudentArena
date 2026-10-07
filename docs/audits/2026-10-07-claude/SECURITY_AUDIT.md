# Təhlükəsizlik auditi — 2026-10-07 (Claude, 5 paralel istiqamət + bug ovu)

Hər tapıntı üçün əvvəl uğursuz olan test yazılıb, sonra düzəldilib. Hamısı canlıya çıxıb
(main a00649d7, 2026-10-07 səhər). Əvvəlki auditlərdə (2026-09-13, 2026-09-28, 2026-10-05) bağlanmış
maddələr təkrar sayılmır.

## Düzəldilənlər

| Sev | Sahə | Problem | Test |
|---|---|---|---|
| **P1** | Apellyasiya | Apellyasiya səhifəsi URL-də `from_section`/`return_to` olmayanda tam cavab açarını göstərirdi (midterm həmişə, final 3 günlük apellyasiya pəncərəsi boyunca); nəticəsi gizli imtahanda sual üzrə doğru/yanlış görünürdü | `apps/appeals/tests/test_secaudit_2026_10_07_answer_key.py` |
| **P1*** | Rollar | `grant_role` istənilən platforma istifadəçisini aktiv təşkilata üzv edə bilirdi (sonra RİM parol/email dəyişə bilərdi) | `apps/accounts/tests/test_secaudit_2026_10_07_tenancy.py` |
| **P1/P2*** | RİM | «başqa təşkilatdakı rütbə» yoxlaması RLS-ə görə prod-da həmişə 0 görürdü; blok/sil/email dəyişmə onu çağırmırdı | eyni fayl |
| P2 | Şəbəkə zonası | LAN-da başlanmış superadmin view-as sessiyası kənardan tam yazma ilə işləyirdi (zona `request.user`-ə baxırdı) | `test_secaudit_2026_10_07_zone.py` |
| P2 | Login | Unicode-ekvivalent istifadəçi adları (NFKC) ayrı limit vedrəsi alırdı → hesab üzrə brute-force limiti yan keçilirdi | `test_secaudit_2026_10_07_login_bucket.py` |
| P2 | Sual idxalı | PDF/şəkil «bomb»u: nəhəng MediaBox köhnə OCR yolunda ≥300 DPI-də ~10 GB pixmap; Pillow 178 MP | `test_secaudit_2026_10_07_upload_bombs.py` |
| P2 | Bildirişlər | `unit_<id>`/`role_<key>_<org>` hədəfləri başqa təşkilata göndərə bilirdi | `NotificationStructureTargetsStayInActiveOrgTest` |
| P2 | Müraciətlər | Daxili qeydin faylları müraciət edənə görünür/endirilirdi (`/media/` daxil) | `apps/applications/tests/test_secaudit_2026_10_07.py` |
| P2 | Nəticələr | Yazılı midterm/finalın «ideal cavabı» yoxlanmadan görünürdü | `test_secaudit_2026_10_07_exam_integrity.py` |
| P2 | Statistika | Tələbə statistikası + CSV gizli nəticəli imtahanların ballarını göstərirdi | `test_secaudit_2026_10_07_statistics_visibility.py` |
| P2 | AI köməkçi | İmtahan zamanı başqa tabdan işləyirdi (sual yapışdırmaq) | `apps/ai_assistant/test_secaudit_2026_10_07_exam_lock.py` |
| P2 | Workflow | `seed-database.yml` inputları birbaşa `run:`-a düşürdü (prod runner-də shell injection) | `tests/test_infra_secaudit_2026_10_07.py` |
| P2 | Infra | IPv6 `80:80` bağlantısı 172.18.0.1-dən gəlib «daxili» sayılırdı (zona + /metrics/ /health/ bypass); X-Forwarded-Host müştəridən ötürülürdü | eyni |
| P3 | Final mərkəzi | Arxivlənmiş hesab bir sorğu ərzində PIN ilə autentifikasiya olunurdu | `test_secaudit_2026_10_07_final_entry.py` |
| P3 | İmtahan | `question-seen` vaxt bitəndən sonra / nəzarət kilidində məzmun verirdi; tələbə öz nəzarət tarixçəsinə sistem hadisəsi yaza bilirdi | `test_secaudit_2026_10_07_exam_integrity.py` |
| P3 | İdxal | xlsx dekompressiya bombası (intake, dərs yükü) | `core/tests/test_secaudit_2026_10_07_ooxml_expansion.py` |
| P3 | Yönləndirmə | Bildiriş `next`, export xətası (Referer), admin 2FA `next` — açıq yönləndirmə | `test_secaudit_2026_10_07_open_redirect.py` |
| P3 | Jurnal bağlama | Başqa fakültənin bildirişini öz bölməsinə köçürmək | `test_secaudit_2026_10_07_journal_close.py` |
| P3 | Fənn qovluğu | İKT rəhbəri başqa təşkilatın fayllarına çıxış (yalnız RLS saxlayırdı) | `apps/subject_folder/tests/test_secaudit_2026_10_07.py` |
| P3 | Endirmələr | Content-Type brauzerin iddiasından; kurs modallarında self-XSS; iCal CR injection; hesabat fayl adı | `core/tests/test_download_types.py` və s. |
| P3 | Kod icrası | Docker konteyneri root, capability-lərlə; timeout-da konteyner silinmirdi | `test_coding_sandbox_docker_2026_10_07.py` |
| Gigiyena | Infra | Workflow `permissions`, Action-lar SHA-ya pin, `no-new-privileges`, Prometheus lifecycle bağlandı, `.env`/`.env.bak.*` 600 | infra testləri |

\* P1 yalnız çox-təşkilatlı rejimdə; QKU tək təşkilatdır.

### Dizayn riskləri — həll olundu (2026-10-08, sahibin qərarı: tövsiyə olunan variant)

Əvvəl «Dizayn riskləri (dəyişdirilmədi)» kimi sahib bölməsində idi. Hər düzəliş üçün əvvəl uğursuz
olan test yazılıb; real imtahan axınları (tələbə/anonim oyunçu soketləri, autosave/replay, brauzer
çöküşü, zal «yenidən giriş» proseduru) testlərlə qorunur. Branch-dədir — adi CD deploy ilə çıxır.

| Sev | Sahə | Problem | Həll | Test |
|---|---|---|---|---|
| P2 | WebSocket | WS consumer-ləri admin 2FA və şəbəkə zonası middleware-dən keçmirdi — OTP-siz admin sessiyası, kənar zonadakı superadmin/inzibati sessiya final otaq monitoruna, canlı viktorina host-una qoşulurdu | `config/asgi.py`: `AuthMiddlewareStack(WebSocketAccessGate(...))` (`apps/accounts/ws_gate.py`) — HTTP ilə EYNİ funksiyalar (`network_zone.zone_policy_denial`, `admin_2fa_required_for_user`/`admin_2fa_verified`), eyni etibarlı-proxy İP qaydası (`core/asgi_scope.py`), `accept()`-dən əvvəl bağlanma: **4430** zona, **4431** 2FA; audit `network_zone_deny` / `admin_2fa_ws_deny`. Qoşulma başına əlavə DB sorğusu yoxdur (faktlar sessiyada — `core/access_facts.py`). Tələbə/müəllim/anonim PIN oyunçusu istənilən zonadan qoşulur | `apps/accounts/tests/test_secdesign_2026_10_08_ws_gate.py` |
| P3 | İmtahan | Vaxtlı YAZILI sualın mətni/şəkli/videosu ilk GET-də səhifə mənbəyində idi (strict delivery yalnız test sualları üçün idi) | Başlanmamış vaxtlı sual (test + yazılı) yer tutucudur; gövdə + cavab sahəsi `question-seen` ilə (sahiblik, aktiv giriş, yazı pəncərəsi, nəzarət kilidi yoxlamalarından və taymer başlayandan SONRA) gəlir; «ideal cavab» heç vaxt. Şəbəkə xətasında slide açıq ikən yenidən istək. Büdcə: `question-seen` 23, səhifə 18 sorğu | `apps/exams/tests/test_secdesign_2026_10_08_written_delivery.py`, `tests/js/take_exam_written_delivery.test.js` |
| P2 | Final mərkəzi | Qeydli zal kompüteri olmayan təşkilatda final cəhdi istənilən cihazdan (məs. telefondan adi login ilə) davam etdirilə bilirdi | Davam edən final cəhdi ilk açıldığı brauzerə bağlanır: imzalı HttpOnly `ems_final_device` cookie + sessiya; bazada yalnız `sha256(attempt:id)` (`FinalAttemptDevice`, RLS). Eyni cihaz (brauzer çöküşü/yenidən login) və eyni qeydli zal kompüteri keçir; başqa cihaz → aydın mesajlı 403. Köçürmə yalnız nəzarətçi/mərkəzin «cihaz dəyişikliyi» təsdiqi ilə (15 dəq, birdəfəlik, audit) — PIN axtarışında düymə; bilet axınında «yenidən giriş» PIN-i özü təsdiqdir. Qeydli kompüterli təşkilatda da eyni qayda | `apps/exams/tests/test_secdesign_2026_10_08_final_device.py` |

İstifadəçinin hiss edəcəyi dəyişikliklər:
- **Final imtahanında kompüter dəyişmək** (kompüter sıradan çıxıb, tələbə başqa yerə keçir): yeni cihazda
  «İmtahan başqa cihazda davam edir» səhifəsi çıxır. Nəzarətçi/imtahan mərkəzi **PIN axtarışı** → tələbə →
  «Cihaz dəyişikliyinə icazə ver» düyməsini basır (bilet axınında mövcud «Yenidən giriş» PIN-i bunu özü edir);
  tələbə 15 dəqiqə ərzində səhifəni yeniləyib qaldığı yerdən davam edir, köhnə cihaz dayanır. Eyni brauzerin
  çöküşü / yenidən login və cookie-ni silən kiosk brauzeri (eyni qeydli zal kompüterində) təsdiqsiz davam edir.
  Yerləşdirmə anında davam edən cəhdlər tələbənin indiki cihazına bağlanır (imtahan qırılmır).
- **Vaxtlı yazılı sual** sual açılanda bir anlıq skeletlə yüklənir (test sualları kimi); mənbədə görünmür.
- **WebSocket**: kənar zonadan superadmin (və `NETWORK_ZONE_STAFF_INTERNAL_ONLY` açıqdırsa inzibati hesab), OTP-ni
  keçməmiş admin sessiyası soket aça bilmir (HTTP səhifəsi onsuz da bağlı idi). Brauzer əl sıxışmanın rəddini
  1006 kimi görür; server logunda `network_zone: … transport=websocket` / `admin_2fa: WS …`.

Əlavə: `bypass_rls` inventarı yeniləndi (2026-10-07: 198 çağırış / 97 fayl; 2026-10-08 təkrar sayım: 215 / 106 —
7-si yeni WS qapısı + final cihaz bağlantısı, qalanı aradakı sürüşmə; hamısı təsnif olunub) — yeni təsnifatsız
fayl CI-da (`core/tests/test_secaudit_2026_10_07_rls_bypass_inventory.py`) yıxılır. CVE: `pip-audit` /
`npm audit` — 0.

## Sahib qərarı / server əməliyyatı tələb edənlər

**Bağlandı (DONE):**
- ✅ ~~Hostda 11 gözləyən apt təhlükəsizlik yeniləməsi (`prod-host-maint.yml`).~~ **DONE** — 2026-10-08 prod-da tətbiq
  olunub, prod-audit ilə təsdiqlənib.
- ✅ ~~`EMS_DB_ROLE_ENFORCE=error`.~~ **DONE** — 2026-10-08 prod-da tətbiq olunub, prod-audit ilə təsdiqlənib (app DB
  rolu RLS-ə tabedir).
- ✅ ~~postgres/pgbouncer exporter-lərinə ayrıca `pg_monitor` rolu; promtail `docker.sock` üçün socket-proxy; Redis
  ACL.~~ **DONE** — 2026-10-08 prod-da tətbiq olunub, prod-audit §4a ilə təsdiqlənib (bax «Exporter least privilege»).
- ✅ GitHub `production` environment — **deployment branch policy: custom, yalnız `main`** — DONE (2026-10-08): prod
  sirləri və self-hosted prod runner-i yalnız `main` ref-indən işləyən run-lar istifadə edə bilər.
- ✅ Dizayn riskləri (WebSocket 2FA/zona qapısı, yazılı sualın vaxtlı məzmunu, final cəhdinin cihaz bağlantısı) —
  **həll olundu**, yuxarıdakı «Dizayn riskləri — həll olundu (2026-10-08)» cədvəlinə köçürülüb.

**Yalnız sahib (açıq):**
- GitHub `production` environment-ə **tələb olunan reviewer** — sahib qərarı lazımdır: hər `main` push-unda avtomatik
  CD deploy-u reviewer təsdiqinə qədər dayandırardı (gecə/təcili düzəlişlər gözləyər).
- Off-site backup (köhnə AD-01).

## Exporter least privilege + promtail docker.sock-suz (2026-10-07, avtomatik rollout)

Nə dəyişdi (testlər: `tests/test_infra_monitor_least_privilege_2026_10_07.py`, CI `prod-smoke` proxy addımı):

| Komponent | Əvvəl | İndi | Açar yoxdursa |
|---|---|---|---|
| promtail | xam `/var/run/docker.sock` (= host root) | `tcp://docker-socket-proxy:2375` — yalnız GET, yalnız `/containers` `/networks` `/_ping` `/version`; proxy ayrıca `internal` `docker-api` şəbəkəsində (orada yalnız promtail) | — (həmişə aktiv, açar tələb etmir) |
| postgres_exporter | `POSTGRES_USER` (superuser) | `emsarena_monitor`: NOSUPERUSER NOBYPASSRLS, yalnız `pg_monitor`, `default_transaction_read_only=on`, CONNECTION LIMIT 5 | owner (köhnə) |
| pgbouncer_exporter | owner (`admin_users` → PAUSE/KILL/SHUTDOWN) | eyni monitor istifadəçisi yalnız `stats_users`-də (SHOW-lar) | owner (köhnə) |
| redis_exporter | `default` + əsas parol | ACL `monitor`: açar/kanal yox, yalnız PING/INFO/CLIENT SETNAME/SLOWLOG/LATENCY (`CONFIG GET` YOX — `requirepass`-ı qaytarardı) | əsas parol (köhnə) |
| cadvisor | privileged + host yolları | **dəyişmədi** — cgroup/`/var/lib/docker`/`/dev/kmsg` oxuyur, privileged konteyner üçün proxy sərhəd deyil (compose şərhi) | — |

Avtomatlaşdırma (`scripts/deploy/remote_deploy.sh`, heç bir addım deploy-u dayandırmır):
1. `preflight_monitor_credentials` — `.env`-də `MONITOR_DB_PASSWORD` / `REDIS_MONITOR_PASSWORD` yoxdursa və ya
   təhlükəsiz deyilsə (16–128 simvol `[A-Za-z0-9._~-]`, rol adı owner/app ilə eyni olmamalı) **boş override ixrac edir**
   (compose-da shell mühiti `.env`-dən üstündür) → exporter-lər `${MONITOR_DB_USER:-${POSTGRES_USER}}` /
   `${REDIS_MONITOR_PASSWORD:-${REDIS_PASSWORD}}` ilə köhnə girişdə qalır.
2. `up -d postgres redis pgbouncer …`-dan sonra `activate_monitor_credentials`: `scripts/deploy/provision_monitor_role.sh`
   rolu idempotent yaradır/parolu yeniləyir (parol yalnız stdin ilə, log/pg_stat_statements söndürülmüş sessiyada);
   pgbouncer-də `stats_users` + userlist, Redis-də `ACL USERS` yoxlanır. Hər hansı biri alınmasa → yenə boş override →
   exporter-lər köhnə girişə qayıdır (deploy logunda `WARNING: … fall back`). Beləliklə `PostgresDown`/`RedisDown`
   yalançı alertləri yaranmır.
3. Redis entrypoint-i ACL sətrini əvvəl portsuz müvəqqəti `redis-server`-də sınayır; rədd olunsa ACL-siz qalxır
   (səhv qayda Redis-i yıxmır).
4. `prod_audit.sh` §4a: exporter-lərin hansı istifadəçi ilə qoşulduğu, rol atributları, pgbouncer stats_users,
   Redis ACL, promtail-də docker.sock və proxy icazələri — ✅/⚠️/❌ (sirr çap olunmur).

✅ **Status 2026-10-08: DONE** — aşağıdakı addımlar prod-da tətbiq olunub və prod-audit (§4a) ilə təsdiqlənib.

Sahibin bir dəfəlik addımları (serverə SSH lazım deyil; dəyərlər heç yerdə görünmür):
1. Bu dəyişiklik main-ə çatsın və adi CD deploy keçsin — promtail proxy-yə keçir; exporter-lər hələ köhnə girişdədir
   (deploy logunda `Monitoring: MONITOR_DB_PASSWORD is not set …`). Bu deploy redis və pgbouncer-i bir dəfə yenidən yaradır
   (konfiq hash-i dəyişib, bir neçə saniyə).
2. Actions → **🔑 Prod secret generate** → `key=MONITOR_DB_PASSWORD`, `redeploy=false` → logda yalnız
   `MONITOR_DB_PASSWORD: generated` və `MONITOR_DB_USER: added (emsarena_monitor)`.
3. Actions → **🔑 Prod secret generate** → `key=REDIS_MONITOR_PASSWORD`, `redeploy=true` → `generated`, ardınca deploy.
   Deploy logunda: `Monitoring: postgres/pgbouncer exporters use the least-privilege role emsarena_monitor …` və
   `Monitoring: redis_exporter uses the read-only ACL user 'monitor'.` (yenə redis/pgbouncer bir dəfə yenidən yaradılır).
4. Yoxlama: **prod-audit** workflow-u → §4a-da hamısı ✅ olmalıdır.

Geri qaytarmaq: `env-update` ilə açarları boşaltmaq (`MONITOR_DB_USER=` `MONITOR_DB_PASSWORD=` / `REDIS_MONITOR_PASSWORD=`)
və ya serverdə sətirləri silib deploy — exporter-lər köhnə girişə qayıdır (rol bazada qalır, zərərsizdir:
`DROP ROLE emsarena_monitor` istəyə bağlıdır). Promtail-i köhnə hala qaytarmaq yalnız kod revert-i ilədir.
