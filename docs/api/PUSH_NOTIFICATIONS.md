# Push bildirişləri — mobil tətbiq üçün API (2026-10-25)

Saytda istifadəçiyə bildiriş yarananda (q/b, bal, imtahan, elan, müraciət, …) o, mobil tətbiqi
quraşdırıb hesabına daxil olubsa, **telefonun bildiriş panelində** də görünür. Çatdırma
**Firebase Cloud Messaging (FCM) HTTP v1** ilədir — Android birbaşa, iOS FCM → APNs vasitəsilə.

Server tərəfi: `apps/notifications/push/` (göndərmə), `apps/notifications/api_views.py` (API).

---

## 1. Autentifikasiya

API saytın öz sessiyasını işlədir (ayrıca token/JWT YOXDUR):

| Nə | Necə |
|---|---|
| Giriş | Saytın adi giriş axını (`/accounts/login/telebe/` və ya `/accounts/login/muellim/`, lazım olsa OTP). Uğurlu girişdən sonra `sessionid` kukisi. |
| Oxu (GET) | `sessionid` kukisi kifayətdir. |
| Yazı (POST / DELETE) | `sessionid` + `X-CSRFToken: <csrftoken kukisinin dəyəri>` başlığı. `Referer` HTTPS-də saytın öz ünvanı olmalıdır (WebView-dan gələn sorğuda avtomatikdir; native HTTP müştərisi `Referer: https://<domen>/` göndərsin). |
| Girişsiz sorğu | `401 {"ok": false, "error": "auth_required"}` — yönləndirmə yoxdur. |
| Sessiya bitəndə | Növbəti sorğu 401 → tətbiq girişə qaytarır; cihaz qeydiyyatı serverdə QALIR (token istifadəçiyə bağlıdır). |

WebView tətbiqi üçün ən sadə yol: FCM tokenini native qatdan JS-ə ötürüb səhifədən `fetch` etmək
(`credentials: "same-origin"`, `X-CSRFToken` — `EMSCore.getCookie("csrftoken")`).

---

## 2. Uclar

Kök: `https://<domen>/api/notifications/`. Bütün cavablar JSON, `ok: true|false`.

### 2.1 Cihaz qeydiyyatı — `POST /api/notifications/devices/`

Girişdən sonra **və** FCM tokeni yeniləndikdə (`onNewToken` / `messaging:didReceiveRegistrationToken`) çağırın.
İdempotentdir: eyni token yenidən gələndə sətir yenilənir. Token başqa hesabda qeydiyyatdadırsa YENİ hesaba keçir.

```json
{
  "token": "<FCM registration token>",
  "platform": "android",          // android | ios | web
  "app_version": "1.4.2",          // ixtiyari
  "language": "ru",                // ixtiyari: push mətninin dili (az|en|ru|tr|de; "ru-RU" də olar). Boş → az
  "muted_types": ["system"]        // ixtiyari: bu cihaza GÖNDƏRİLMƏYƏN növlər (bax §4). Verilməsə köhnə seçim qalır
}
```

Cavab — `201` (yeni) / `200` (yeniləndi):

```json
{
  "ok": true,
  "created": true,
  "push": {"configured": true, "enabled": true},
  "device": {"id": 17, "platform": "android", "app_version": "1.4.2", "language": "ru",
             "muted_types": ["system"], "token_tail": "x9Qa1Z", "last_seen": "…", "last_success_at": null}
}
```

`push.configured=false` — serverdə Firebase açarı hələ qoşulmayıb (qeydiyyat yenə saxlanır; açar qoşulan kimi push başlayır).
`push.enabled=false` — RİM «Sistem tənzimləmələri»ndə push-u söndürüb.

Xətalar (`400`): `invalid_token`, `invalid_platform`, `invalid_muted_types`. `429 rate_limited` — istifadəçi başına saatda 60 yazı.

### 2.2 Çıxış — `DELETE /api/notifications/devices/`

Hesabdan çıxanda (sessiya hələ etibarlı ikən) çağırın, yoxsa telefon köhnə hesabın bildirişlərini almağa davam edər.

```json
{"token": "<FCM registration token>"}
```
→ `{"ok": true, "deactivated": 1}`

### 2.3 Cihazlarım — `GET /api/notifications/devices/`

→ `{"ok": true, "push": {...}, "devices": [ ...device ]}` (token özü qaytarılmır, yalnız `token_tail`).

### 2.4 Bildiriş qutusu — `GET /api/notifications/`

| Parametr | Defolt | |
|---|---|---|
| `page` | 1 | |
| `page_size` | 20 | ≤ 50 |
| `filter` | `all` | `all` / `unread` / `read` |
| `type` | — | §4-dəki növ |
| `lang` | sorğunun dili | mətnlər bu dildə qaytarılır |

```json
{
  "ok": true, "page": 1, "page_size": 20, "has_next": false, "unread_count": 3, "language": "az",
  "results": [
    {"id": 812, "type": "grade", "title": "Elektron jurnal — Riyaziyyat", "message": "Qayıb (q/b) qeyd edildi: 25.10.2026",
     "link": "/organizations/switch/qku/?next=/accounts/profile/%3Fsection%3Dmy-journal",
     "url": "https://<domen>/organizations/switch/qku/?next=…", "is_read": false, "created_at": "2026-10-25T09:12:03+04:00"}
  ]
}
```

### 2.5 Oxundu sinxronu

* `POST /api/notifications/<id>/read/` → `{"ok": true, "changed": true, "unread_count": 2}` (başqasının bildirişi → `404`)
* `POST /api/notifications/read-all/` → `{"ok": true, "updated": 3, "unread_count": 0}`
* `GET  /api/notifications/unread-count/` → `{"ok": true, "unread_count": 2}` (ikon nişanı üçün)

Kabinetdə oxunan bildiriş tətbiqdə də oxunmuş görünür (eyni sətir). Push gəlməmiş oxunubsa push göndərilmir.

### 2.6 Özümə test push — `POST /api/notifications/devices/test/`

Yalnız **superadmin / RİM** (`ikt_rehber`, `rim_staff`; aktiv təşkilatda). İstifadəçinin bütün aktiv cihazlarına
DƏRHAL (sinxron) «Test bildirişi» göndərir; bildiriş qutusuna yazılmır (`data.notification_id = "0"`).
Saatda 10 dəfə.

```json
{"ok": true, "report": {"configured": true, "enabled": true, "devices": 2, "ok": 1, "unregistered": 1}}
```

`report`-da nəticə açarları: `ok`, `unregistered` / `invalid` / `sender_mismatch` (token deaktiv edildi),
`retry` (müvəqqəti FCM xətası), `error` + `errors` (mətn), `auth_failed` (server açarı yararsızdır).

---

## 3. Push payload-u (FCM `message`)

```json
{
  "token": "<cihaz tokeni>",
  "notification": {"title": "Elektron jurnal — Riyaziyyat", "body": "Qayıb (q/b) qeyd edildi: 25.10.2026"},
  "data": {
    "notification_id": "812",
    "type": "grade",
    "link": "/organizations/switch/qku/?next=/accounts/profile/%3Fsection%3Dmy-journal",
    "url": "https://<domen>/organizations/switch/qku/?next=…",
    "created_at": "2026-10-25T09:12:03.512+00:00"
  },
  "android": {"priority": "high", "notification": {"channel_id": "ems_notifications", "tag": "ems-812"}},
  "apns": {"headers": {"apns-priority": "10"},
           "payload": {"aps": {"sound": "default", "badge": 3, "thread-id": "grade"}}}
}
```

* **Dil**: başlıq və mətn cihazın `language`-ında (qeydiyyatda verilən); yoxdursa Azərbaycan dili.
  Tətbiqin dili dəyişəndə `POST /devices/`-i yeni `language` ilə təkrar çağırın.
* **`data` dəyərləri həmişə sətirdir** (FCM tələbi).
* **Android kanalı**: tətbiq `ems_notifications` id-li bildiriş kanalını (importance HIGH) yaratmalıdır, əks halda
  Android 8+ bildirişi «Miscellaneous» kanalında göstərir.
* **iOS nişanı**: `badge` = istifadəçinin oxunmamış bildiriş sayı (göndərmə anında).
* **Eyni bildiriş** təkrarlanmır: `tag` (`ems-<id>`) Android-də eyni bildirişi əvəz edir.

### Deep link sxemi

Toxunuşda tətbiq `data.url`-i (mütləq ünvan) WebView-da açır **və ya** `data.link`-i (saytın nisbi yolu) öz
marşrutlaşdırmasına çevirir, sonra `POST /api/notifications/<notification_id>/read/` göndərir.
Keçidlər saytın kabinet bölmələridir (`/accounts/profile/?section=<bölmə>`); bildiriş başqa təşkilatdandırsa
keçid əvvəl `/organizations/switch/<slug>/?next=…` ilə həmin təşkilata keçirir. Tez-tez rast gəlinən bölmələr:
`my-journal` (jurnal: q/b, ballar), `my-schedule` (cədvəl), `notifications`, `announcements`, `applications`.
`link` boş ola bilər — onda bildiriş qutusunu (`?section=notifications`) açın.

---

## 4. Bildiriş növləri (`type`, `muted_types`)

`assignment`, `exam`, `grade` (jurnal: q/b, bal, limit), `system`, `course`, `live_exam`, `approval`, `application`.

---

## 5. Server konfiqurasiyası (ops)

| Mühit dəyişəni | |
|---|---|
| `FCM_SERVICE_ACCOUNT_JSON` | Firebase service account açarı: base64 (prod), fayl yolu və ya xam JSON. Boş → push NO-OP. |
| `FCM_PROJECT_ID` | Boş → JSON-dakı `project_id`. |
| `PUSH_NOTIFICATIONS_ENABLED` | Defolt `true`; RİM «Sistem tənzimləmələri → Bildirişlər» açarı ilə də söndürür. |
| `PUSH_LINK_BASE_URL` | `data.url` kökü; boş → `DOCUMENT_VERIFY_BASE_URL` (publik domen) → `SITE_URL`. |
| `PUSH_SEND_CHUNK` | Bir Celery işində bildiriş sayı (defolt 100). |

Axın: `create_notification*` → commit-dən sonra yalnız aktiv cihazı olan alıcılar → Celery `notifications.push_send`
(hissələrlə) → FCM. FCM `UNREGISTERED`/404, yararsız token və `SENDER_ID_MISMATCH` → cihaz avtomatik deaktiv.
Prod-a açar qoşmaq: `.github/workflows/prod-push-key.yml` (secret `FCM_SERVICE_ACCOUNT_JSON_B64`, rejimlər verify/apply/remove).

### Firebase layihəsi (bir dəfəlik)

1. console.firebase.google.com → layihə yarat (məs. `ems-qku`) → Android tətbiqi (paket adı) və iOS tətbiqi (bundle id)
   əlavə et; `google-services.json` / `GoogleService-Info.plist` mobil komandaya.
2. iOS: Project settings → Cloud Messaging → **APNs Authentication Key** (.p8, Apple Developer → Keys) yüklə.
3. Project settings → Service accounts → **Generate new private key** → JSON fayl (SİRR — git-ə, çata yazmayın).
4. `base64 -i <fayl>.json | tr -d '\n' | gh secret set FCM_SERVICE_ACCOUNT_JSON_B64 --env production`
5. Actions → «📱 Prod push açarı» → `verify`, sonra `apply` (app yenidən başlayır).
6. Yoxlama: tətbiqdə daxil ol → RİM hesabı ilə `POST /api/notifications/devices/test/`.
