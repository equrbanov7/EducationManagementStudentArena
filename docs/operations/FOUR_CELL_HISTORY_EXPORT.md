# Sabit dörd xana üçün şifrəli read-only sübut

`export_wcu_four_cell_history --actor USER --public-key PATH --output PATH`
əmri yalnız source point 5458056, 5558632, 5558637, 5558643, iki mövcud dərs və
dörd qeydiyyatın available AuditLog, correction/reversal, hygiene,
LegacyGradeFact/Artifact və typed ledger sübutunu toplayır. Arbitrary selector,
append, delete, source/roster/grade write yoxdur. Parent scope SHA decoder-də
sabitdir; şifrəli payload ayrıca formatdadır, köhnə metadata decoder dəyişmir.

Yeni PostgreSQL REPEATABLE READ READ ONLY transaction, aktiv fixed-tenant
superuser, RLS hər iki rejimdə, statement/query/time/row/byte limitləri tətbiq
edilir. Serverdə tam record hash hesablanır; xam kontakt, mətn və JSON çıxmır.
Sabit cari course/lesson/enrollment typed tuple-ları və hash-ləri daxil edilir.
Mənbənin fiziki immutability-si və olmayan core ledger iddia edilmir.

Audit best-effort-dur. `available_scope_collected` silmə olmadığının riyazi
sübutu və avtomatik apply icazəsi deyil. Current exact label + date/kind
uyğunluğunun saat daşımadığı və həll edilməmiş audit sətirləri ayrıca görünür.
Silmə, blank clear, malformed grade intent, rəsmi correction/hygiene və əvvəlki
recovery undo marker-i ayrıca review üçündür. Başqa 338 held xana daxil deyil.

`four-cell-history-export.yml` production concurrency lock və uzaq build SHA
checkout uyğunluğu ilə yalnız actor qəbul edir. Cipher və public SHA manifest
bir günlük artifact-dır. `decrypt_four_cell_history.py` AES-GCM/RSA və sərt
text-free schema təsdiqlənmədən plaintext yaratmır; output yeni private fayldır.

## Syllabus capture pack-ləri

`syllabus-content-packs.yml` mövcud 91/1791 registry-ni 19 fixed pack-də, hər
pack üçün ən çox 5 ardıcıl müstəqil capture ilə oxuyur. Hər çağırış ayrıca
READ ONLY transaction, köhnə cap və müstəqil cipher saxlayır. Union cap
artırılmır. Held, quarantine, not_attempted və always-finalizer explicitdir;
silent skip yoxdur. Fərqli anların capture-ları vahid atomik snapshot deyil.
