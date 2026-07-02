# Təhlükəsizlik — Secret Rotasiyası Təlimatı (FAZA 1)

> Tarix: 2026-05-24
> Status: **TƏCİLİ — production buraxılışından əvvəl tamamlanmalıdır**

## Problem

`.env` faylı keçmişdə git-ə commit olunub. `e57d012 chore: remove .env from git`
commit-i faylı indeksdən sildi, **lakin git tarixi dəyişməzdir** — fayl 20+ köhnə
commit-də real secret-lərlə qalıb. İstənilən kəs (repo-ya çıxışı olan) bu əmrlə
bütün köhnə secret-ləri oxuya bilər:

```bash
git show 91d71c9f:.env
```

Audit zamanı təsdiqləndi ki, **indiki `SECRET_KEY`, `POSTGRES_PASSWORD` və
`PGADMIN_PASSWORD` git tarixindəki ən köhnə commit ilə eynidir** — yəni heç vaxt
dəyişdirilməyib və tam kompromis olunub.

## Kod tərəfində artıq edilənlər (bu fazada tamamlandı)

- `.env` faylındakı `SECRET_KEY`, `POSTGRES_PASSWORD`, `PGADMIN_PASSWORD`,
  `DJANGO_SUPERUSER_PASSWORD` **yeni, kriptoqrafik təhlükəsiz dəyərlərlə** əvəz olundu.
- `GITHUB_TOKEN` `.env`-dən tamamilə silindi (kodda heç bir yerdə istifadə
  olunmurdu; GitHub Actions öz `GITHUB_TOKEN`-ini avtomatik təmin edir).
- `BREVO_SMTP_KEY` və `GEMINI_API_KEY` `ROTATE-ME-...` placeholder-i ilə
  işarələndi — bunlar yalnız xarici paneldən yenidən yaradıla bilər (aşağıya bax).
- `.gitignore` secret pattern-ləri ilə gücləndirildi (`*.token`, `*.crt`,
  `service-account*.json`, `id_rsa` və s.).
- `DATABASE_URL` yeni `POSTGRES_PASSWORD` ilə sinxronlaşdırıldı.

## Sənin əl ilə etməli olduğun addımlar

### 1. Xarici servis açarlarını rotasiya et (TƏCİLİ)

Köhnə açarlar git tarixində qalıb — onlar **revoke (ləğv)** olunmalıdır:

| Açar | Harada rotasiya olunur | Addım |
|---|---|---|
| `GITHUB_TOKEN` | github.com → Settings → Developer settings → Personal access tokens | Köhnə `github_pat_11ARUS...` token-ini **Revoke** et |
| `BREVO_SMTP_KEY` | app.brevo.com → SMTP & API → SMTP açarları | Köhnə açarı **sil**, yeni yarat, `.env`-də `ROTATE-ME-...` yerinə yaz |
| `GEMINI_API_KEY` | aistudio.google.com → Get API key | Köhnə `AIza...` açarını **sil**, yeni yarat, `.env`-də yaz |

### 2. Production-da yeni secret-ləri tətbiq et

Production serverində (`/opt/emsarena/app/.env`) eyni yeni dəyərləri yaz. CI/CD
QEYD (2026-07-02): CI-dən avtomatik deploy (`_deploy-linode.yml`) silinib —
sirlər birbaşa serverdəki `.env` faylında yenilənir.

**Vacib:** `POSTGRES_PASSWORD` dəyişdikdə mövcud PostgreSQL istifadəçisinin
parolu da DB-də yenilənməlidir:

```sql
ALTER USER emsarena_user WITH PASSWORD 'YENI_GUCLU_PAROL_BURA';
```

### 3. Git tarixini təmizlə (secret-ləri tarixdən sil)

Bu, **destruktiv əməliyyatdır** — bütün commit hash-ları dəyişir, force-push
tələb edir. Komanda ilə razılaşdıraraq et. `git-filter-repo` tövsiyə olunur:

```bash
# 1. git-filter-repo qur
pip install git-filter-repo

# 2. Repo-nun TƏMİZ kopyasını klonla (mirror)
cd /tmp
git clone --mirror <repo-url> emsarena-clean.git
cd emsarena-clean.git

# 3. .env-i bütün tarixdən sil
git filter-repo --path .env --invert-paths --force

# 4. Force-push (BÜTÜN branch-ları və tag-ları yenidən yazır)
git push --force --all
git push --force --tags
```

Bundan sonra komandanın bütün üzvləri repo-nu **yenidən klonlamalıdır** (köhnə
lokal kopyalar köhnə tarixi saxlayır).

> Qeyd: Git tarixini təmizləsən belə, açarlar artıq remote-da (GitHub) bir müddət
> görünüb. **Buna görə 1-ci addım (rotasiya) git təmizliyindən daha vacibdir** —
> rotasiya olmadan git təmizliyi mənasızdır.

### 4. Yoxlama

```bash
# .env artıq git-də izlənmir
git check-ignore -v .env          # → .gitignore qaydası göstərməlidir

# .env tarixdə qalmayıb (filter-repo-dan sonra)
git log --all --oneline -- .env   # → boş olmalıdır

# Gitleaks CI-də artıq secret tapmır
gitleaks detect --source . --config .gitleaks.toml
```

## Niyə bu vacibdir

Universitetlərə satılan multi-tenant platformada `SECRET_KEY` sızması session
forge etmək, `DATABASE_URL` parolu bütün tenant data-sına çıxış, `BREVO_SMTP_KEY`
isə platformanın adından phishing email göndərmək imkanı verir. Bu, FAZA 1-in
buraxılışdan əvvəl bağlanması məcburi olan ən kritik səbəbidir.
