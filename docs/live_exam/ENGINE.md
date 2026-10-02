# Canlı viktorina mühərriki (live_exam) — vəziyyət maşını, axınlar, bal qaydaları

Audit 2026-09-28 LX-BE. Kod: `apps/live_exam/{services,scoring,reveal,transport,serializers,consumers,consumer_support,session_settings,typed_answers}.py`, `domain/{session,question_config}.py`.
Testlər: `apps/live_exam/tests/test_lx_be_*.py`. Yük testi: [LOAD_TEST.md](LOAD_TEST.md).

## 1. Vəziyyət maşını

```
            start (host, yalnız LOBBY)            reveal (host) | hamı cavab verdi | server auto-reveal
  LOBBY ───────────────────────────► QUESTION ───────────────────────────────────────────────► REVEAL
    │                                   ▲                                                          │
    │ finish (host)                     └────────────── next (host, YALNIZ REVEAL-dən) ────────────┤
    ▼                                                                                              │
 FINISHED ◄──────────── finish (host, istənilən vəziyyət) / next (son sualdan sonra) ──────────────┘
```

| Keçid | Kim | Qoruyucu (kilid altında) | Yayım |
|---|---|---|---|
| LOBBY → QUESTION(0) | `POST /live/host/<pin>/start/` | `state == lobby` (ikiqat «Başla» → 409) | lobby: `game_started`; play: `question_published` |
| QUESTION → REVEAL | `POST …/reveal/` | `state == question` (ikiqat → 409) | host: tam reveal; oyunçular: ümumi reveal + şəxsi sətir |
| QUESTION → REVEAL | sonuncu cavab (`scoring`) | commit-dən SONRA say + kilid altında təkrar say → tək dəfə | eyni |
| QUESTION → REVEAL | server (autoplay açıq, `ends_at + 2 s`) | `state == question`, sual eyni, vaxt keçib | eyni |
| REVEAL → QUESTION(i+1) | `POST …/next/` | `state == reveal` — QUESTION-dan **409** (əvvəl eyni sualı yeni taymerlə yenidən nəşr edirdi) | `question_published` |
| REVEAL → FINISHED | `next` son sualdan sonra | — | `finished` (host tam, oyunçu + `my_stats`) |
| * → FINISHED | `POST …/finish/` | `state != finished` | `finished` |

Kilid modeli (`services.lock_session`, `scoring._lock_session_for_answer`):

* **Keçidlər** sessiya sətrini `SELECT … FOR UPDATE OF live_exam_livesession` ilə tutur (imtahan sətri kilidlənmir).
* **Cavablar** sessiya sətrini `FOR SHARE` (cavablar bir-birini gözləmir) + oyunçu sətrini `FOR UPDATE` tutur.
* Nəticə: hər qəbul olunmuş cavab keçiddən ƏVVƏL commit olunur və reveal paketinə düşür; keçiddən sonra gələn cavab
  yeni vəziyyəti görür və rədd olunur. «Arada qalan» cavab yoxdur (testlə sübut: `test_lx_be_concurrency`, raund 2).
* Xarici tranzaksiya varsa (`RLS_TRANSACTION_SCOPED` / `ATOMIC_REQUESTS`) «hamı cavab verdi» yoxlaması `FOR UPDATE SKIP
  LOCKED` ilə edilir, alınmasa `on_commit`-ə təxirə salınır — kilid yüksəltmə deadlock-u olmur.
* Yayımlar `transaction.on_commit` ilə göndərilir (klient heç vaxt commit olunmamış vəziyyəti görmür).

## 2. Sual fazaları (server vaxtı)

`started_at = nəşr + 1 s` → get-ready (yalnız 1-ci sual, 4 s) → intro 5 s → **cavab pəncərəsi** `[answer_starts_at, ends_at]`
(`time_limit`, default 15 s) → reveal → nəticə 3.5 s → liderlik 5 s → `next_question_at` (host autoplay növbəti sualı açır).
`skip-intro` pəncərəni dərhal açır (`_question_phase_override`).

## 3. Kim reveal edir (vaxt bitəndə)?

1. **Host JS** (autoMode açıq, idarə pəncərəsi): `ends_at + 0.18 s`-də `POST reveal`.
2. **Hamı cavab verdi** — server özü (sonuncu cavabın commit-indən sonra).
3. **Server təhlükəsizlik toru (YENİ)** — autoplay açıqdırsa: hər play consumer `question_published` alanda taymer qurur
   (`ends_at + SERVER_AUTO_REVEAL_GRACE_SECONDS` (2 s) + 0–0.75 s səpələnmə); keş «claim» (`cache.add`) ilə klaster
   üzrə tək cəhd; DB-də şərtli keçid. Əlavə olaraq `GET /live/state/<pin>/` vaxtı keçmiş sualı tənbəl (lazy) reveal edir.
   Host tabı bağlansa / yuxuya getsə / POST 503 alsa belə oyunçular «vaxt bitdi» ekranında qalmır.
   Autoplay SÖNÜKdürsə reveal yalnız hostun əlindədir (müəllim tempi idarə edir). «Next» həmişə host-dadır.

## 4. Axınlar və kənar hallar

| Hal | Davranış |
|---|---|
| Gec qoşulma | Yalnız LOBBY-də yeni oyunçu; oyun gedərkən yalnız artıq qəbul olunmuş klient (cookie) geri qayıdır (`join.py`, LX-SEC) |
| Kilidli sessiya | Yeni qoşulma 403 (mövcud oyunçu token-lə davam edir) |
| Oyunçu çıxarıldı (kick) | Yalnız LOBBY; `remember_kicked_client` + sətir silinir; **açıq lobby/play socket-lərinə `{"type":"kicked"}` + close 4403** |
| Oyunçu yenidən qoşulur (refresh / Wi-Fi) | Play WS yenidən qoşulur, `GET state` — sual/pre-reveal «saved»/reveal (şəxsi)/final (`my_stats`) snapshot-u |
| Host refresh / qopma | State snapshot (host: `results`, `fastest_correct`, `typed_summary`, tam ayarlar); autoplay taymerləri yenidən qurulur; server toru |
| İkiqat göndəriş (WS + HTTP eyni an) | Oyunçu sətri `FOR UPDATE` → ikinci «already answered» (idempotent `answer_saved`), bir sətir |
| Aktiv olmayan sual | `question_not_active` / başqa imtahanın sualı `question_not_found` |
| Pəncərədən əvvəl | rədd (`submission_outside_active_window`) |
| Vaxtdan sonra | `ends_at + 0.5 s`-ə qədər (şəbəkə gecikməsi) qəbul, əmsal 0.5; sonra rədd |
| Çox seçimli | `max_select` = düzgün variant sayı (min 2); `multi_scoring` partial/strict |
| `answer_mode="multiple"`, 1 düzgün | İndi multi kimi (əvvəl tək-seçim kimi ilk toxunuşda göndərilirdi) |
| Düzgün variantı olmayan sual | Cavab qəbul olunur, 0 bal, seriyaya təsirsiz (neytral); əvvəl heç kim cavab verə bilmirdi |
| Bütün variantlar düzgün | Multi; hamısını seçən tam bal |
| 0 oyunçu | Erkən reveal yoxdur; vaxtla reveal (host/server) |
| Pause / resume | Mühərrikdə YOXDUR (endpoint yoxdur) |

## 5. Bal qaydaları

* **Vaxt əmsalı** (Kahoot): `tf = max(0.5, 1 − 0.5 · t / T)`, `T = ends_at − answer_starts_at`.
* **t = max(server_elapsed, client_answer_ms)**, `[0, T]`. `server_elapsed` — mesajın serverə **çatdığı** an (WS `receive`
  anı / HTTP view girişi), DB növbəsindən əvvəl. Müştəri dəyəri balı yalnız AZALDA bilər (əvvəl 2.5 s üstünlük verirdi).
* **Tək seçim**: düz → `round_half_up(base · tf)`, səhv → 0.
* **Çox seçim**: `partial` (default) → `base · tf · max(0, (düz − səhv) / cəmi_düz)`; `strict` → yalnız dəqiq dəst.
  `is_correct` = dəqiq dəst.
* **Yazılı cavab**: düz → `base · tf`; səhv/boş → 0. Uyğunluq: NFKC + az/tr qatlanması (ə→e, ı/İ/I→i, ö→o, ü→u, ş→s,
  ç→c, ğ→g) + casefold; durğu → boşluq, boşluqlar sıxılır; rəqəm ekvivalentliyi (`3,0 = 3.0 = 3`, səhv tolerantlığı
  YOX); qəbul cavabı ≥ 6 simvoldursa Damerau–Levenshtein ≤ 1 (`typed_typo_tolerance`, default açıq).
* **base** = `question.points` (> 1), yoxsa `exam.default_question_points` (> 1), yoxsa 1000.
* **Seriya (streak)**: dəqiq düz → +1 (`best_streak` = maks); digər cavab → 0; reveal-də cavabsız qalan → 0; neytral
  sual → dəyişmir. **Bonus bal yoxdur** (`bonus = 0`) — yalnız göstərici.
* Oyunçu balı cavabla EYNİ tranzaksiyada, kilidli sətirdə artır → `score == Σ LiveAnswer.awarded_points` (invariant).

## 6. Liderlik sırası (tie qaydası)

`score ↓, created_at (qoşulma) ↑, id ↑` — canlı `top`, `previous_top`, reveal `rank`, final `top` və nəticə səhifəsi
(`views/results.py`: `-score, created_at`) eyni qaydadır. Sürət sırası (`answer_rank`, `fastest_correct`): `answer_ms ↑, id ↑`.

## 7. Yazılı cavab konfiqurasiyası

`host_settings.typed_questions = {"<qid>": {"accepted": [...]}}` (tam əvəzləmə, `POST …/settings/`). Uyğunluq:
tək düzgün variantlı (mətn ≤ 60) tək-seçimli sual və ya variantsız sual (`correct_answer`: 1–10 sətir, hər biri ≤ 60).
Boş `accepted` → default. Yararsız → 400 (aydın mesaj). Sualın qaydası **nəşr anında dondurulur**
(`host_settings._question_config`) — oyun gedərkən ayar dəyişsə aktiv sual dəyişmir. `typed_questions` (qəbul cavabları)
**heç vaxt** oyunçuya getmir: `get_session_settings` ictimai görünüşdür, tam görünüş `get_host_session_settings`.

## 8. Protokol — ƏLAVƏ olunan sahələr (heç nə silinməyib / adı dəyişməyib)

| Yer | Sahə |
|---|---|
| `question` (nəşr + state) | `answer_input` (`choice`/`text`), `text_max_length` (text), `answer_grace_ms`; text-də `options: []` |
| `settings` (hamı) | `typed_typo_tolerance`, `multi_scoring`; host-da əlavə `typed_questions` |
| `game_started` | `redirect_jitter_ms` (1500 — yönləndirməni səpələmək üçün) |
| reveal (hamı) | `answer_input`; text: `accepted_answers`; multi: `multi_scoring`, `total_correct` |
| reveal (host) | `fastest_correct` {player_id, nickname, avatar_key, accessory_key, answer_ms}\|null, `total_players`; text: `typed_summary` [{text,count,correct}] (≤ 8), `typed_total`, `typed_correct`; `results[].text_answer` (text) |
| reveal (hər oyunçuya ŞƏXSİ) | `rank`, `gap_to_next`, `next_nickname`; `player_answer.streak`; text: `your_text`; multi: `correct_selected`, `wrong_selected`, `total_correct` (həm üst səviyyədə, həm `player_answer`-da) |
| `finished` (hamı) | `total_players`, `stats` {total_players, total_questions, answer_count, correct_rate, avg_answer_ms}; `top[]`: `correct_count`, `answered_count`, `best_streak`, `avg_answer_ms` |
| `finished` (hər oyunçuya ŞƏXSİ) | `my_stats` {correct, total, answered, best_streak, avg_answer_ms}, `rank`, `gap_to_next`, `next_nickname` |
| state (oyunçu) | reveal-də yuxarıdakı şəxsi sahələr; finished-də `my_stats`, `rank`; host: `stats`, `fastest_correct`, … |
| yeni WS mesajı | `{"type":"kicked"}` (sonra close 4403) |
| cavab mesajı (klient → server) | yazılı: `{"type":"answer","question_id",…,"text": "..."}` (variant sahəsi əvəzinə); HTTP fallback da `text` qəbul edir |

Şəxsi sahələr kanal-qatında `personal` xəritəsi (oyunçu id → JSON sətri) ilə gəlir; hər consumer yalnız ÖZ sətrini
klientə qoşur, `personal` açarı heç vaxt klientə getmir.

## 9. WebSocket təhlükəsizliyi

* Origin: `config/asgi.py` — `AllowedHostsOriginValidator` (Origin başlığı yoxdursa da rədd).
* Anonim socket (imzalı oyunçu token-i və ya daxil olmuş host yoxdur) **DB-yə toxunmadan 4401** — real və uydurma PIN eyni
  cavab alır (PIN oracle yoxdur; anonim ad siyahısı yoxdur). Pin-entry/join səhifələrinin «tema» socket-ləri artıq qoşulmur.
* Oyunçu socket-i host qrupuna qoşula bilməz (rol token-dən); klientdən yalnız `answer` qəbul olunur, yalnız ÖZ oyunçusu
  üçün (token-dəki player_id/client_id) və yalnız aktiv sual üçün.
* Qoşulma limiti: kimlik (oyunçu client_id / istifadəçi) üzrə `LIVE_WS_CONNECT_RATE_LIMIT` + (PIN, İP) üzrə geniş tavan
  `LIVE_WS_CONNECT_IP_RATE_LIMIT` (default `1000/1m`) — bir NAT arxasında 150 tələbə yenidən qoşularkən bloklanmır.
* Mesaj: > 4096 simvol → close 1009; binar kadr/yararsız JSON/dict olmayan → atılır; mesaj və cavab limitləri.

## 10. Miqyas (50–90, ehtiyatla 150)

* Consumer DB işi `database_sync_to_async(thread_sensitive=False)` → ASGI thread hovuzu (`ASGI_THREADS`). Default
  `thread_sensitive=True` prosesin BÜTÜN socket-lərinin DB işini TƏK thread-də növbəyə düzürdü.
* Reveal: 1 cavab sorğusu + 1 oyunçu sorğusu; consumer başına DB sorğusu yoxdur (əvvəl 150 × ~6 sorğu).
* Lobby `lobby_state` socket başına ≤ 4/s (ön + son kənar birləşdirmə).
* State endpoint ~8 sorğu (əvvəl ~15+).
* Ops tövsiyələri: bax LOAD_TEST.md «Tövsiyələr».

## Zəif şəbəkə: sualın çatması, ədalət və bağlantı (LXNET, 2026-10-02)

- **Çatma sübutu** (`apps/live_exam/delivery.py`): serverin öz saatı ilə, ilk qeyd qalib — play socket-in
  ötürdüyü sual üçün klientin `seen` təsdiqi və ya `GET /live/state/<pin>/` sualı oyunçuya verdiyi an
  (keşdə, `live_exam:seen:*`). Klient saatına etibar edilmir.
- **Fərdi anker**: sual `answer_starts_at`-dan GEC çatıbsa, sürət balı `answer_starts_at + min(gecikmə, tavan)`-dan
  ölçülür; tavan = `min(3 s, 0.2 × pəncərə)`. Pəncərə, reveal vaxtı, düzgün cavabın gizliliyi dəyişmir; maksimal
  bal eynidir. Keş əlçatmazdırsa köhnə qayda.
- **Yeni mesajlar**: `ping` / `pong` (6 s heartbeat; cavab gəlməsə klient yeni bağlantı açıb vəziyyəti HTTP ilə
  çəkir), `seen` (klient → server), `delivery_progress` + `received_count` (yalnız HOST-a: «N/M aldı»).
  Oyunçunun yeni sual mesajında `previous_top` artıq yoxdur (yalnız host alır).
- **Klient saatı** (`static/js/player/clock.js`): server vaxtı round-trip ölçmələri ilə sinxronlanır; cavab
  düymələri dəqiq anda açılır. State/answer sorğularının 6 s timeout-u var; WS ilişəndə cavab dərhal HTTP ilə.
- Ölçmə (4 telefon, proksi ilə gecikmə/kəsinti): yavaş 3G-də düymələrin gecikməsi 457 → 10 ms, ilk sual
  5.9 → 2.9 s; 8 s kəsintidə itən cavab 2/6 → 0.
