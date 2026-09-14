# Yeni server (wcuserver, 10.0.2.120) — deploy hazırlığı

Son yeniləmə: 2026-09-15 00:20. Yol: Mac → AnyDesk → Windows PC → ESXi (10.0.1.240)
→ WEST VM konsolu (`wcu@wcuserver`, Ubuntu 26.04). Mac (192.168.0.9) serverin
şəbəkəsinə (10.0.2.x) **çıxa bilmir** — yeganə körpü Windows PC-dir.

## ✅ Tamamlandı (bu sessiya, konsoldan yoxlanıb)

- [x] SSH açarı: Mac `emsarena_wcu.pub` → `authorized_keys`
- [x] Repo: `/home/wcu/EducationManagementStudentArena` @ `eda1892f` (=`origin/main`)
- [x] **`.env` tam hazır** (0600): `10.0.2.120`, `EDGE_PROXY_MODE=lan`, serverdə
  `openssl rand` ilə yaradılan bütün sirlər, 32 GB host profili, **Brevo SMTP + Gemini**
  - `POSTGRES_USER=emsarena`, `POSTGRES_DB=emsarena`, `APP_DATABASE_USER=emsarena_app`
- [x] TLS: `docker/nginx/certs/origin.{crt,key}` (self-signed, SAN 10.0.2.120), `validate…lan` keçdi
- [x] `docker compose … config -q` → OK
- [x] **GitHub Actions runner**: qeydiyyat + **systemd xidməti aktiv (running, boot-enabled)**
  — `active (running)`, Main PID 11052, ad `wcuserver`, label `self-hosted`
- [x] **docker qrupu**: `wcu` əlavə edildi (`docker:x:983:wcu`)
- [x] `/opt/emsarena/app` → repo simvolik keçidi
- [x] **İcazə düzəlişi (vacib)**: server umask **077**-dir, ona görə əl ilə klonlanan
  repo qovluqları `700` idi və konteyner (qeyri-root postgres UID) bind-mount-ları
  oxuya bilmirdi. Düzəldildi:
  - `/home/wcu` → `751` (traverse)
  - `docker/postgres-init` → `705`, init skript → `704`
  - `docker/nginx/*.conf`, `origin.crt` → `o+r` (TLS **key** toxunulmadı, 600 qaldı)
  > Qeyd: gələcək CI deploy runner-i systemd altında (umask 022) işlədiyindən
  > faylları normal (755/644) yazacaq — bu problem yalnız əl ilə klonun artefaktı idi.
- [x] **PostgreSQL qaldırıldı və SAĞLAMDIR** (`health=healthy`); image çəkildi,
  volume+network yaradıldı
- [x] **RLS tətbiq rolu yaradıldı** (EXAM-P0-01): `emsarena_app` — `super=false bypass=false` ✅
  (fresh volume-da `10-create-app-role.sh` avtomatik işlədi)

## ⛔ Qalan 1 fiziki addım: DB faylının köçürülməsi (678 MB)

Dump Mac-də: `~/Downloads/emsarena-deploy/emsarena_db_20260914.dump`
(`pg_dump -Fc`, SHA256 `~/Downloads/emsarena-deploy/SHA256.txt`).
Mac→server marşrutu yoxdur, ona görə körpü Windows PC-dir:

1. **AnyDesk fayl transferi** (və ya fayl-clipboard kopyala/yapışdır): Mac → Windows PC.
2. Windows → server (eyni LAN). İki yoldan biri:
   - `scp emsarena_db_20260914.dump wcu@10.0.2.120:~/`
   - və ya Windows-da dump qovluğunda `python -m http.server 8099`, serverdə:
     `curl http://<WINDOWS_LAN_IP>:8099/emsarena_db_20260914.dump -o ~/emsarena_db.dump`
3. **Serverdə bərpa** (postgres artıq işləyir və boşdur):

```bash
cd ~/EducationManagementStudentArena
sudo docker exec -i emsarena-postgres pg_restore \
  -U emsarena -d emsarena --no-owner --no-privileges --clean --if-exists --exit-on-error \
  < ~/emsarena_db.dump
sudo docker exec emsarena-postgres psql -U emsarena -d emsarena \
  -tAc 'select count(*) from pg_tables where schemaname=$$public$$;'   # >0 olmalı
```

> `--no-owner`: dump `emsarena_db`/`emsarena_user`-dən idi; server DB `emsarena`.
> Obyektlər `emsarena` (owner) kimi yaradılır; init-dəki ALTER DEFAULT PRIVILEGES
> yeni cədvəlləri avtomatik `emsarena_app`-a grant edir.

## ▶️ Deploy (DB bərpasından SONRA)

Layihə qovluğu adı compose project adını təyin edir → **həmişə `~/EducationManagementStudentArena`-dan**
işlət (`/opt/…app` simvolik keçidindən deyil, əks halda proje adı dəyişər):

```bash
cd ~/EducationManagementStudentArena
bash scripts/deploy/remote_deploy.sh          # və ya `main`-ə push → runner avtomatik
```

Yoxlama:
- `curl -k https://10.0.2.120/ping/` və `/health/`
- `docker network inspect educationmanagementstudentarena_emsarena-network --format '{{range .IPAM.Config}}{{.Subnet}} gw={{.Gateway}}{{end}}'` → `172.18.0.0/16 gw=172.18.0.1`
- `docker stats --no-stream`; `psql … -c 'SHOW jit;'` → `off`

## Açıq (sahib / şəbəkə)

- `PasswordAuthentication` hələ açıq — LAN-dan `ssh -i emsarena_wcu wcu@10.0.2.120`
  təsdiqləndikdən sonra bağla
- DHCP rezervasiyası `10.0.2.120`; köhnə `10.0.2.42`-yə keçid; reboot testi
- `.env` sirləri yalnız serverdə var — ehtiyat nüsxə sahibdə
