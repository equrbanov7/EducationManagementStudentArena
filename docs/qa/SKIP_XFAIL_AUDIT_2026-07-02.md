# Skip / xfail auditi — 2026-07-02 (Faza 7)

Cəmi **53** marker. Kateqoriyalar: `postgres` markerli RLS/constraint testləri
sqlite dövrəsində qanunidir; `seed` guard-ları CI-də işləyir; qalanlar aşağıda —
hər sətir üçün qərar: **saxla** (əsaslı) / **düzəlt** / **sil**.

| Fayl | Sətir | Marker | Kontekst/Səbəb |
|---|---:|---|---|
| apps/exams/tests/test_attempt_constraints.py | 78 | `@skipUnless` | connection.vendor == "postgresql", "True thread-level race needs PostgreSQL (SQLite locks the t |
| apps/exams/tests/test_services.py | 1515 | `@skipUnless` | parsing.fitz is not None, "PyMuPDF (fitz) quraşdırılmayıb") |
| apps/exams/tests/test_services.py | 1544 | `@skipUnless` | parsing.fitz is not None, "PyMuPDF (fitz) quraşdırılmayıb") |
| apps/exams/tests/test_services.py | 1623 | `@skipUnless` | parsing.fitz is not None, "PyMuPDF (fitz) quraşdırılmayıb") |
| apps/exams/tests/test_services.py | 1640 | `skipTest` | "Tesseract OCR mövcud deyil (sistemdə tesseract-ocr quraşdırılmayıb)") |
| apps/organizations/tests/test_decorators.py | 249 | `skipTest` | "No role with level < 50 found in this org") |
| apps/organizations/tests/test_decorators.py | 266 | `skipTest` | "No role with level >= 50 found in this org") |
| tests/e2e/test_auth_flows.py | 91 | `@pytest.mark.skipif` |  |
| tests/e2e/test_auth_flows.py | 102 | `@pytest.mark.skipif` |  |
| tests/e2e/test_auth_flows.py | 116 | `@pytest.mark.skipif` |  |
| tests/e2e/test_blog_flows.py | 90 | `@pytest.mark.skipif` |  |
| tests/e2e/test_blog_flows.py | 109 | `@pytest.mark.skipif` |  |
| tests/e2e/test_blog_flows.py | 119 | `@pytest.mark.skipif` |  |
| tests/e2e/test_blog_flows.py | 129 | `@pytest.mark.skipif` |  |
| tests/e2e/test_blog_flows.py | 157 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 57 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 69 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 81 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 94 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 104 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 121 | `@pytest.mark.skipif` |  |
| tests/e2e/test_course_workflows.py | 133 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 62 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 74 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 86 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 99 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 116 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 128 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 138 | `@pytest.mark.skipif` |  |
| tests/e2e/test_exam_workflows.py | 148 | `@pytest.mark.skipif` |  |
| tests/e2e/test_notifications.py | 62 | `@pytest.mark.skipif` |  |
| tests/e2e/test_notifications.py | 74 | `@pytest.mark.skipif` |  |
| tests/e2e/test_notifications.py | 94 | `@pytest.mark.skipif` |  |
| tests/e2e/test_notifications.py | 131 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 93 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 106 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 126 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 136 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 146 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 163 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 196 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 208 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 218 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 228 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 238 | `@pytest.mark.skipif` |  |
| tests/e2e/test_rbac_access.py | 248 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 97 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 117 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 136 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 161 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 181 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 215 | `@pytest.mark.skipif` |  |
| tests/e2e/test_smoke.py | 238 | `@pytest.mark.skipif` |  |

## YEKUN VERDİKT (təsnifat tamamlandı — 2026-07-02)

53 markerin **hamısı əsaslı guard-dır**; silinməli/düzəldilməli giriş YOXDUR:

| Qrup | Say | Verdikt |
|---|---:|---|
| e2e `skipif(not E2E_USERNAME/PASSWORD)` | 46 | **Saxla** — kredensial-qapılı e2e; CI `_e2e-smoke` onları seed edərək işlədir, lokalda şəffaf skip |
| Opsional asılılıq (PyMuPDF/fitz, tesseract) | 4 | **Saxla** — sistem-paket guard-ları; prod image-də quraşdırılıb, CI-də işləyir |
| `connection.vendor == "postgresql"` (attempt race) | 1 | **Saxla** — real thread-race yalnız Postgres-də mənalıdır (sqlite lock semantikası fərqli) |
| Data-dependent rol guard (level<50 / >=50) | 2 | **Saxla** — default_roles seed-inə bağlı müdafiə guard-ı |

Xülasə: test suite-də "unudulmuş skip edilmiş sınıq test" problemi mövcud deyil.
Yeni skip əlavə edərkən qayda: səbəb sətri MÜTLƏQ marker ilə eyni sətirdə/ardınca
aydın yazılmalıdır ki, bu audit skripti onu tuta bilsin.
