# Elektrik kəsilməsi: avtomatik bərpa və yoxlama

Son yeniləmə: 2026-10-07. Sahibin tələbi: «server resurslarını düzgün istifadə etsin, yüklənmədə çökməsin; elektrik kəsilib server yenidən yananda sistem özü-özünü ayağa qaldırsın».

Bərpa zənciri belədir:

**güc gəlir → BIOS serveri yandırır → ESXi açılır → WEST VM autostart → Ubuntu → docker + runner → konteynerlər → converge → autoheal**

İlk iki halqanı (BIOS və ESXi) **yalnız sahib** qura bilər (bölmə 2). Qalan halqalar artıq avtomatikdir.

---

## 1. Avtomatik olanlar (server tərəfi)

| Qat | Mexanizm | Mənbə |
|---|---|---|
| Ubuntu boot | `docker.service` və GitHub runner xidməti `enabled`-dir. Reboot-dan sonra uzaqdan idarə (deploy, `prod-*` workflow-ları) geri gəlir. | prod-audit §12 yoxlayır |
| Docker | Hər servisdə `restart: unless-stopped` var. `live-restore: true` olduğundan dockerd restart olanda konteynerlər dayanmır. | `docker-compose.prod.yml`, `prod-host-maint → tune` |
| Boot converge | `emsarena-converge.service` boot-da bir dəfə işləyir. Docker-i gözləyir, sonra deploy-un əmrini təkrarlayır: `docker compose up -d --no-build --pull never --scale app=N --scale celery_worker=M`. Uğursuz olsa 10 dəqiqəyə qədər yenidən cəhd edir. | `scripts/ops/selfheal/emsarena-converge.sh` |
| Autoheal | `emsarena-autoheal.timer` hər 2 dəqiqədən bir işləyir. 3 ardıcıl yoxlamada `unhealthy` qalan konteyneri restart edir. Start-ı alınmayan (`exited` + xəta, və ya `created`) konteyneri isə start edir. | `scripts/ops/selfheal/emsarena-autoheal.sh` |
| Resurs prioriteti | CPU uğrunda rəqabət olanda `cpu_shares` DB, PgBouncer, Redis və nginx-ə üstünlük verir. Yaddaş çatmayanda `oom_score_adj` sayəsində kernel əvvəlcə monitorinq, heavy və app replikasını öldürür, Postgres və Redis-i ən sonda. | `docker-compose.prod.yml` (başdakı şərh) |
| PostgreSQL | `fsync`, `full_page_writes` və `synchronous_commit` defolt (`on`) qalır. Kəsilmədən sonra WAL bərpası data itirmədən başa çatır. Loqda `database system was interrupted … redo done` sətirlərini görmək normaldır. | compose `postgres.command` |
| Redis | AOF açıqdır (`everysec`). `aof-load-truncated yes` yarımçıq qalmış AOF quyruğunu atır və Redis qalxır. | `docker/redis/redis.conf.tmpl` |
| Celery beat | Start-dan əvvəl cədvəl faylı yoxlanır. Fayl korlanıbsa silinir və beat təmiz cədvəllə başlayır, yəni crash-loop olmur. | `docker/celery-beat/start.sh` |
| nginx | `app` hələ qalxmayıbsa nginx yenə start olur: upstream `resolver 127.0.0.11` və dəyişən vasitəsilə sorğu anında tapılır. App qalxana qədər cavab 502 olur, sonra öz-özünə düzəlir. Bu hissədə dəyişiklik lazım deyil. | `docker/nginx/nginx.conf` |

Ölçülmüş nəticə: 2026-10-07-də planlı reboot-dan sonra sistem **~112 saniyədə** özü qalxdı.

### Converge hansı image-i işə salır

Converge heç vaxt yeni və ya test olunmamış image işə salmır. Seçim deploy qaydasına əsaslanır: `emsarena-prod:latest` teqi yalnız health-gate keçəndən sonra yeni release-ə keçirilir.

- **Konteynerlər `latest`-in image ID-sini işlədirsə:** öz teqləri saxlanılır. Heç nə yenidən yaradılmır, konteynerlər sadəcə start olunur.
- **Fərqli image işlədirlərsə:** deploy yarımçıq kəsilib deməkdir. Konteynerlər `emsarena-prod:latest` (sonuncu sağlam release) ilə yenidən yaradılır.
- **`latest` yoxdursa:** konteynerlərin işlətdiyi tək lokal teq götürülür. O da yoxdursa, converge app image-ini **start etmir**: jurnalda xəta yazır və deploy-u gözləyir.
- **Miqrasiya işləmir** (`RUN_RELEASE_ON_START=false`). `--remove-orphans` istifadə olunmur, yəni converge heç nə silmir.

### Autoheal-ın təhlükəsizlik limitləri

- **Yalnız bu layihə:** autoheal yalnız `com.docker.compose.project=<layihə>` etiketli və `working_dir = APP_DIR` olan konteynerlərə baxır. One-off (`compose run`) konteynerlərinə toxunmur.
- **Deploy zamanı işləmir:** deploy və converge `/run/emsarena/deploy.lock` kilidini saxlayır, `seed_database.sh` də. Bu müddətdə autoheal keçidi ötürür.
- **Restart limiti:** konteyner başına saatda ən çox 3 əməliyyat edilir. Bir keçiddə ən çox 3 əməliyyat, servis başına isə 1 əməliyyat olur (rolling).
- **Vəziyyətli servislər restart olunmur:** postgres, redis və postgres-backup `unhealthy` olduqda restart edilmir, çünki crash recovery və ya AOF yüklənməsi kəsilməməlidir. Bu halda jurnala `HOLD` yazılır.
- **Əsas servis xəstədirsə gözləyir:** postgres və ya redis sağlam deyilsə, digər servislərin restart-ı gözlədilir, çünki səbəb oradadır.
- **Yük altında restart yoxdur:** `load1 > 2 × nüvə` olanda autoheal unhealthy restart etmir. Yük altında yavaş healthcheck simptomdur, restart isə yarımçıq imtahan sorğularını öldürər.
- **Əl ilə dayandırılan qalır:** səliqəli və ya əl ilə dayandırılmış konteynerə (kod 0, 137, 143, xətasız) toxunulmur.
- **Pauza və söndürmə:**
  - müvəqqəti pauza: `touch /run/emsarena/autoheal.pause` (6 saatdan sonra öz-özünə keçir);
  - tam söndürmə: Actions → «🛠 Prod host maintenance» → `selfheal-off`.

---

## 2. Sahibin bir dəfə qurmalı olduğu ayarlar (avadanlıq / hipervizor)

### 2.1 Fiziki server: «AC güc gələndə avtomatik yan»

Sahibin quraşdırma sənədlərinə görə server HPE ProLiant-dır (iLO, Smart Storage).

- **HPE, BIOS (RBSU):** reboot zamanı F9 basın → System Utilities → System Configuration → BIOS/Platform Configuration (RBSU) → Server Availability → **Automatic Power-On = Always Power On**. Sonra F10 ilə saxlayın.
- **HPE, iLO veb interfeysi (reboot-suz):** Power & Thermal (iLO 4-də Power Management) → Server Power → **Automatic Power-On = Always Power On**.
- **Dell olsaydı (iDRAC):** Configuration → BIOS Settings → System Security → **AC Power Recovery = On**.

«Restore Last Power State» əvəzinə «Always Power On» seçin. Server kəsilmə anında hər hansı səbəbdən söndürülmüş olsa belə, güc gələndə yenə yanacaq.

### 2.2 ESXi: hostun və WEST VM-in autostart-ı

> **✅ 2026-10-07 22:44-də quruldu.** Host Autostart: Enabled=Yes, start/stop delay 120 s, Stop action=Shut down.
> WEST: autostart sırası 1. VM-də VMware Tools işləyir.
> Səhər baş verən hadisənin səbəbi də bu imiş: host ~10:30-da yenidən başlamışdı, autostart isə söndürülü idi.
> Ona görə WEST VM 17:19-a qədər, kimsə əl ilə «Power on» basana qədər sönük qaldı.
>
> **Hardware:** HPE ProLiant DL360 Gen10, 2 × Xeon Gold 6138 (40 nüvə / 80 thread), 127 GB RAM, 1,7 TB datastore.
> - **ESXi 8.0 U3:** `https://10.0.0.216/ui`
> - **iLO 5:** `https://10.0.1.112`
>
> **⚠️ ESXi EVALUATION rejimindədir — lisenziya ~2026-11-08-də bitir.** Bitəndən sonra VM yandırıla
> bilməz. Yəni ilk kəsilmədən sonra autostart da işləməz. Lisenziya açarı Host → Manage → Licensing →
> **Assign license** ilə daxil edilməlidir.

Aşağıdakı addımlar yenidən qurmaq lazım olsa istinad üçündür. ESXi Host Client-ə daxil olun: `https://10.0.0.216/ui`
(Windows PC üzərindən; köhnə ünvan 10.0.1.240 idi).

1. Navigator → **Host → Manage → System → Autostart** → **Edit settings** düyməsini basıb bunları qurun:
   - Enabled = **Yes**
   - Start delay = **120** s
   - Stop delay = **120** s
   - Stop action = **Shut down**
   - Wait for heartbeat = **Yes**
2. **Save** basın.
3. Navigator → **Virtual Machines** → **WEST** üzərində sağ klik → **Autostart → Enable**.
4. Yenə sağ klik → **Autostart → Start earlier** basın. WEST siyahıda **1-ci** olana qədər təkrarlayın.
5. Sağ klik → **Autostart → Configure** bölməsində bunları yazın:
   - Start delay = **60–120 s** (disk və şəbəkə hazır olsun deyə)
   - Stop action = **Shut down**
6. Yoxlayın: Manage → System → Autostart siyahısında WEST **Enabled** və sırası **1** olmalıdır.

«Shut down» əməliyyatı (host söndürüləndə VM-i səliqəli söndürmək) yalnız VM-də `open-vm-tools` işləyəndə mümkündür. Bunu prod-audit §12 yoxlayır. Host vCenter/HA klasterinə qoşulubsa, autostart-ı HA idarə edir. Bu halda VM-in «VM restart priority» ayarını High edin.

### 2.3 UPS (tövsiyə)

- **Növ:** online (double-conversion) UPS.
- **Qoşulan avadanlıq:** server, onun switch-i və firewall/router (Kerio). Bunlar qoşulmasa, server işləsə də kənardan əlçatmaz olur.
- **İşləmə müddəti:** ən azı 10–15 dəqiqə.
- **Şəbəkə kartı (SNMP):** batareya azalanda ESXi-ni səliqəli söndürmək üçün lazımdır, məs. APC PowerChute Network Shutdown for ESXi və ya NUT. Söndürmə ESXi-də Stop action = Shut down ilə VM-ə ötürülür.
- **RAID keşi:** iLO-da Smart Array keşinin batareya/flash (FBWC) vəziyyətini yoxlayın. UPS olmadan RAID keşi kəsilmədə yazıları qoruyan yeganə qatdır.
- **Sınaq:** ildə bir dəfə UPS-in kabelini çıxarıb test edin.

---

## 3. Kəsilmədən sonra yoxlama

Güc gələndən təxminən 8–10 dəqiqə sonra:

1. Saytı yoxlayın: `https://ems.wcu.edu.az/ping/` (LAN-da `https://10.0.2.120/ping/`) `{"status": "ok"}` qaytarmalıdır.
2. GitHub → Actions → **🔎 Prod Audit** → Run workflow. **§12 «Enerji kəsilməsi / özünü bərpa»** bölməsində bütün sətirlər ✅ olmalıdır:
   - docker və runner `enabled`;
   - `live-restore=true`;
   - converge `enabled` və son nəticə `success`;
   - autoheal timer `enabled` + `active`;
   - postgres və app üçün `oom_score_adj` / `cpu_shares` effektivdir.
3. GitHub → Actions → **🛠 Prod host maintenance** → `status` addımı bunları göstərir:
   - converge-in boot jurnalı;
   - son autoheal əməliyyatları (`ACTION` / `LIMIT` / `HOLD`).
4. Konteyner vəziyyəti prod-audit §3-də görünür. Restart sayının (`restarts=`) bir dəfə artması kəsilmədən sonra normaldır.

Tipik vaxtlar:

| Mərhələ | Müddət |
|---|---|
| ESXi boot | ~3–5 dəq |
| VM start delay | 2 dəq |
| Ubuntu | ~1 dəq |
| Stack (app healthcheck start_period 120 s) | ~2 dəq |

---

## 4. ESXi hostun özü əlçatmazdırsa (2026-10-07 hadisəsi)

2026-10-07-də host LAN-dan tam itdi: `10.0.1.240` ping-ə cavab vermirdi və ARP cədvəlində qeydi yox idi. Bu o deməkdir ki, şəbəkə kartı link vermir: host söndürülüb, asılıb, kabel/switch portu problemlidir və ya enerji yoxdur.

1. **Windows PC-dən yoxlayın:**
   - `ping 10.0.1.240`
   - `arp -a | findstr 10.0.1.240`
   - `ping 10.0.2.120` (VM)

   VM cavab verirsə, problem yalnız ESXi idarəetmə şəbəkəsindədir. Sayt işləyir, **reboot etməyin**.
2. **iLO (ayrı idarəetmə portu) qurulubsa:** iLO veb interfeysində güc vəziyyətinə və **Integrated Management Log**-a baxın, Remote Console-u açın.
   - Server söndürülübsə **Momentary Press** ilə yandırın.
   - Konsol tam asılıbsa son çarə **Cold Boot**-dur.
3. **iLO da əlçatmazdırsa, serverin yanına gedin:**
   - güc LED-lərinə və PSU-lara baxın;
   - serverdə və switch portunda kabelin link işıqlarını yoxlayın;
   - monitorda DCUI ekranına baxın: IP, xəta və ya PSOD (bənövşəyi ekran — şəklini çəkin).

   Söndürülübsə power düyməsini basın. Host açıqdırsa, amma IP-si əlçatmazdırsa: DCUI-də F2 → **Restart Management Network** / **Test Management Network**.
4. **ESXi açılandan sonra:** Host Client → Virtual Machines → WEST `Powered on` olmalıdır. Deyilsə → **Power on**. Sonra 3-cü bölmədəki yoxlamanı edin.
5. **Host düşən müddətdə:** runner VM-in içindədir, ona görə deploy və `prod-*` workflow-ları növbədə gözləyir (24 saata qədər). Onları təkrar-təkrar işə salmayın.
6. **Hadisəni qeyd edin:** vaxt, səbəb, nə edildiyi. Alertmanager «Watchdog» e-poçtlarının kəsildiyi vaxt bunun üçün kömək edir.

---

## 5. Əl ilə müdaxilə (nadir hallar)

- **Autoheal-ı müvəqqəti saxlamaq** (məs. əl ilə baxım):
  - serverdə `touch /run/emsarena/autoheal.pause` (6 saat qüvvədədir, reboot-da silinir);
  - və ya Actions → Prod host maintenance → `selfheal-off`; geri qaytarmaq üçün `selfheal`.
- **Redis start-da «Bad file format reading the append only file» verirsə:** bu, yarımçıq quyruq deyil, ortadan korlanmadır. Addımlar:
  1. autoheal-ı pauzaya alın;
  2. `docker compose -f docker-compose.prod.yml stop redis`;
  3. `redis_data` volume-unun ehtiyat nüsxəsini alın;
  4. APP_DIR-də bu əmri işlədin:

  ```bash
  docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh redis \
    -c 'redis-check-aof --fix /data/appendonlydir/*.manifest'
  docker compose -f docker-compose.prod.yml up -d redis
  ```

  Korlanmadan sonrakı hissə itir. Bu, broker, keş və WS üçün qəbul olunandır: sessiyalar yenidən yaranır, Celery task-ları yenidən göndərilir.
- **Postgres qalxmırsa** (`PANIC: could not locate a valid checkpoint record` və s.):
  - `pg_resetwal` **işlətməyin**;
  - backup-dan yeni bazaya bərpa edin: `docs/operations/deployment.md` §12 «Restore procedure».
- **Converge 10 dəqiqədə alınmayıbsa:** autoheal hər 2 dəqiqədən bir davam edir. Səbəb `journalctl -u emsarena-converge -b` jurnalındadır və `prod-host-maint → status` onu göstərir. Ən etibarlı yol: `main`-ə son commit-i yenidən deploy etmək (Actions → CI → Re-run).

## 6. Quraşdırma ardıcıllığı (bir dəfə)

1. `main`-ə deploy. İlk deploy `cpu_shares` / `oom_score_adj` səbəbilə bütün konteynerləri bir dəfə yenidən yaradır (postgres və redis ~10–30 s fasilə), ona görə **imtahan pəncərəsindən kənarda** edin.
2. Actions → **🛠 Prod host maintenance** → `selfheal`. Bu addım vahidləri quraşdırır, sonra `converge --check` və `autoheal --dry-run` çıxışını göstərir.
3. Actions → **🔎 Prod Audit** → §12-də hamısı ✅ olmalıdır.
4. Sahib: bölmə 2.1 (BIOS) və 2.2 (ESXi autostart). 2.3 (UPS) tövsiyədir.
