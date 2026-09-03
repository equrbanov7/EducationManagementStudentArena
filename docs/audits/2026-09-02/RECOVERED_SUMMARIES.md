# Bərpa edilmiş agent xülasələri (2026-09-02)

> Host yenidən yükləndikdə `/private/tmp` scratchpad-dakı tam hesabatlar itdi. Aşağıdakılar həmin agentlərin yekun mesajlarından bərpa edilmiş xülasələrdir; rəqəmlər klon bazada (`emsarena_rehearsal_a0d170000901`) ölçülüb.

## 1. Data köçürmə auditi (PHASE 1) — yalnız oxu, 0 yazma
| Varlıq | Mənbə | Hədəf | Çatmayan | Dup | Sınıq |
|---|---:|---:|---:|---:|---:|
| Tələbə hesabı | 7,816 | 7,716 | **100** | 0 | 0 |
| SAR | 7,716 | 7,703 | 13 (staged) | 0 | 0 |
| Müəllim/işçi | 729 | 715 | **14** | 0 | 0 |
| Fakültə / kafedra | 13 / 18 | 13 / 18 | 0 | 0 | 0 |
| İxtisas / Proqram | 83 | 83 / 101 | 0 | 0 | 0 |
| Qrup | 766 | 766 | 0 | 0 | 0 |
| Fənn | 2,521 | 2,501 | 0 | 20 birləşmə (9 ad hələ dup) | 0 |
| Kurikulum / sətri | 126 / 3,424 | 210 / 4,681 | 0 | 0 | 87 boş plan |
| Akademik dövr | 13 | 13 | 0 | 0 | `is_current` yox |
| Açılış | 13,875 | 11,115 | — | 0 | 1,206 müəllimsiz |
| Yazılış | 199,454 | 148,020 | 18,253 | 0 | 0 |
| Dərs | 379,215 | 293,070 | — | 0 | 0 |
| LessonMark | 5,070,824 | 3,711,153 | izahsız **0** | 0 | 0 |
| Komponent | 701,005 | 538,457 (+148k generic) | izahsız **0** | 0 | 0 |
| İmtahan `im/im2` | 134,834 | 119,084 | izahsız **0** | 0 | 0 |
| LegacyGradeFact / bal vərəqi | 169,231 / 52,386 | 169,231 / 52,386 | 0 | 0 | 0 |

Müsbətlər: kodlaşdırma itkisi 0 (3,352 HTML-entity açılıb, ə/ı/ş/ğ/ö/ü/ç sağlam); FK orphan və açar dublikatı 0; 12 tələbə + 6 müəllimdə sahə-sahə (ad/soyad/ata adı/FİN/qrup/ixtisas/fakültə/e-poçt) 100 % uyğun; UI-da tələbə nəticə sayı DB ilə eyni (10=10, 22=22, 24=24); 500 xətası 0; 27 avqustdakı 193,516 izahsız xana dərin icrada 0-a düşdü; legacy bal sübutu 100 % itkisiz.
P0: (1) 2,291 cari tələbə səhvən archived (qrup `start_year='0000'`, 248 qrup; nümunə id 1970, 1994, 2081, 3492, qrup 2031) — 122-sinin 2026 dərslərində bal var; (2) 14 e-poçt toqquşması → 28 kimlik karantin + 86 etibarsız e-poçt → 100 tələbə + 14 işçi hesabsız (`Xəyalə Balayeva` S:1285/W:381 hədəfdə yoxdur; `admin@admin.com` iki nəfəri əridib; 12 karantinli işçiyə 62 jurnal bağlıdır); (3) cari akademik dövr yoxdur.
P1: 12,457 bal + 19,116 qayıb dərs sətirsiz (J12 işlədilməyib); 3,075 SAR plansız kurikuluma bağlı; `birth_date` 8,440/8,440 NULL, `gender` 100 % unspecified (mənbədə 2,252 + 2,877 dəyər); `student_group_number` boş; `FinalGrade.is_published=false` 114,021/114,021; 1,589 toqquşma uduzanı UI-da yox; `yekun`↔imtahan 884 sətirdə fərqli (19-u >30 bal).

## 2. Rol matrisi (PHASE 2)
Rollar: rector(100, org `*`) · vice_rector(90) · exam_center/head(85, imtahan domeni, admin-alias istisna) · ikt_rehber=RİM(88, 38 ekran, `user.grant_privileged` yox) · exam_center_staff(60) · hr(65) · dean(80, fakültə) · chair_head(70, kafedra, sillabus təsdiqçisi) · teacher(50, öz açılışları) · assistant/lab_assistant/tutor(40) · program_coordinator(45, ixtisas, 10 ekran) · lead_student(30)/student(10) · alumni(5, icazəsiz, giriş ayrıca bağlı) · member(20).
Boşluqlar: (a) cədvəl — icazə açarı yox, yalnız `is_direct_editor`; (b) dərs yükü modeli yox; (c) sillabus təsdiqi `syllabus.approve` + `covers_unit` fail-closed; (d) RİM düzəlişləri `journal.correct` + PDF, tam audit; (e) kollokvium pəncərəsi icazə açarsız (rol adı ilə); (f) dean/chair_head level≥80 qaydası ilə `org_admin` alias alır → bloq moderasiyası org-səviyyəli sızır. 33 mənfi test planlaşdırıldı; klonda ikinci təşkilat yoxdur (cross-tenant yalnız RLS testləri ilə).

## 3. Performans (PHASE 24) — baza və düzəlişlər
| Səhifə | Sorğu əvvəl→sonra | SQL ms | Wall ms |
|---|---:|---:|---:|
| journal_detail (555 yazılış × 226 dərs) | 10,075 → 102 | 5,233 → 477 | 15,936 → 7,202 |
| tələbə my-results | 692 → 68 | 1,090 → 47 | 1,645 → 96 |
| tələbə overall-academic | 688 → 64 | 1,203 → 48 | 1,599 → 104 |
| heyət groups bölməsi | 69 → 61 | 123 → 46 | 813 → 90 |
| records_overview_summary | 30 → 30 | 2,386 → 748 | 2,762 → 1,046 |
| journal_detail tipik | 192 → 101 | 114 → 75 | 217 → 165 |
Düzəlişlər: `apps/registrar/finals_batch.py` (compute_final_result `batch=`/`frozen=`), `exam_attempt_history.attempt_rows_by_student`, `legacy_import/0007_legacy_map_lookup_index` (97.7 ms/5,011 buffer → 0.409 ms/4 buffer), `registrar/0063_selfwork_enrollment_done_index`, `StudentGroupForm(defer_choices=True)` + `exams:teacher_group_candidates`. Çıxış bayt-bəbayt eyni (CSRF/nonce çıxılmaqla hash bərabər). Testlər 147/0 (6 PDF testi iCloud-boşalmış `static/fonts/DejaVuSans.ttf` səbəbindən düşürdü, fayl materiallaşdırıldıqdan sonra 10/10). Qalan: profil qabığı vergisi (~50–65 sorğu/səhifə) — context_builder mərhələləri.

## 4. Hesab provisioning + giriş (PHASE 1 §4)
Yeganə işləyən kütləvi yol legacy köçürmə (`identity_access.py`, `identity_archive.py`). `apps/accounts/management/commands/import_users_from_excel.py` mövcuddur, amma `core/management/command_safety.py` (`MANAGEMENT_COMMAND_ENVIRONMENT` default `production`) onu prod-da söndürür. RİM mərkəzi yalnız mövcud hesabları idarə edir (blok/aç/sil/bərpa/parol) — yaratma/idxal yoxdur. Klon: 5,213 aktiv / 2,490 arxiv / 13 staged `myedu.student.*`; FİN dublikatı 0; ad-soyad dublikatları (6× «Əli Əliyev») axtarış UX qeydi. Rate limit: 5/10 dəq cihaz + 60/10 dəq IP (kodda). Əlavə test: `apps/accounts/tests/test_staged_portal_login.py` (6, hələ yaşıl təsdiqlənməyib).

## 5. Təhlükəsizlik alt-icmalı (auth/sessiya)
P0: login rate-limiter-in superadmin escape hatch ilə yan keçilməsi (`apps/accounts/views/auth/login.py:219-241`, `_shared.py:135-145`). P1: `/accounts/send-otp/` (`otp_api.py:85-92`) və parol bərpası «done» səhifəsində (`login.py:317-325`, `password_reset_done.html:34,57`) hesab sadalama. P2: base→production settings sürüşməsi; portal qapısının `POST /accounts/login/` ilə keçilməsi; silinə bilən audit jurnalı; `get_client_ip` ən sol XFF; 5 kiçik sərtləşdirmə. Təhlükəsiz: OTP brute-force tavanı, hash-lənmiş OTP/PIN, həssas log yoxdur, view-as eskalasiyası bloklanıb, SECRET_KEY, admin URL/2FA, cookie/başlıqlar, logout, redirect sanitizasiyası.

## 6. Legacy köçürmə mexanikası (tədqiqat)
`legacy_import_rehearse` yalnız `emsarena_rehearsal_<12hex>` birdəfəlik hədəfə işləyir; `--phase` alt-dəsti `policy_digest → transform_version`-u dəyişir və ledger `legacy_entity_identity_conflict` verir → artıq köçürülmüş hədəfdə hədəfli təkrar icra mümkün deyil (ona görə repair komandaları yazılır). J12 `journal_lesson_recovery` (sıra 41) tam və testlidir, default fazadadır: +11,607 dərs, +161,775 LessonMark, +37,579 qayıb saatı (klonda ölçülüb); hədəfə yalnız tam təzə repetisiya ilə gedir. `AcademicPeriod.is_current` qəsdən köçürülmür (V9 qərarı) — istifadəçi təyin etməlidir.
