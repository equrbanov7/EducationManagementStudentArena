"""«Fənn qovluğu» modulunun SABİTLƏRİ — status/növ kataloqları, limitlər, UI tokenləri.

Model, servis, public API və (UI agentinin) şablonları eyni mənbədən oxusun
deyə hər sabit BURADADIR. Rəng HARDCODE edilmir: cədvəllərdə yalnız
``--ems-*`` token ADLARI saxlanılır (``static/css/design-tokens.css``).

Sərbəst iş siyasəti sillabusdan gəlir (``apps.syllabus.public.SELFWORK_OPTIONS``:
1x10 / 2x5 / 10x1, cəmi HƏMİŞƏ 10 bal). Burada həmin qayda TƏKRARLANMIR —
yalnız DB trigger-inin sabiti (``SELFWORK_TOTAL_CAP``) testlə sillabus
sabitinə bağlanır.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_CTX = "subject_folder.choice"


class FolderStatus(models.TextChoices):
    """Qovluğun həyat dövrü: qaralama → aktiv (tələbələr görür) → arxiv (yalnız oxu)."""

    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    ACTIVE = "active", pgettext_lazy(_CTX, "Aktiv")
    ARCHIVED = "archived", pgettext_lazy(_CTX, "Arxivlənib")


class TopicSource(models.TextChoices):
    """Mövzunun mənbəyi — təsdiqlənmiş sillabusun həftəlik planı və ya müəllimin öz mövzusu."""

    SYLLABUS = "syllabus", pgettext_lazy(_CTX, "Sillabusdan")
    CUSTOM = "custom", pgettext_lazy(_CTX, "Müəllimin mövzusu")


class MaterialKind(models.TextChoices):
    """Tədris materialının növü."""

    FILE = "file", pgettext_lazy(_CTX, "Fayl")
    IMAGE = "image", pgettext_lazy(_CTX, "Şəkil")
    CODE = "code", pgettext_lazy(_CTX, "Kod nümunəsi")
    LINK = "link", pgettext_lazy(_CTX, "Keçid")
    VIDEO_LINK = "video_link", pgettext_lazy(_CTX, "Video keçidi")
    NOTE = "note", pgettext_lazy(_CTX, "Qeyd")


class CodeLanguage(models.TextChoices):
    """Kod nümunəsinin dili (yalnız GÖSTƏRİŞ — mətn heç vaxt icra olunmur)."""

    PYTHON = "python", "Python"
    JAVA = "java", "Java"
    C = "c", "C"
    CPP = "cpp", "C++"
    CSHARP = "csharp", "C#"
    JAVASCRIPT = "javascript", "JavaScript"
    TYPESCRIPT = "typescript", "TypeScript"
    SQL = "sql", "SQL"
    HTML = "html", "HTML"
    CSS = "css", "CSS"
    PHP = "php", "PHP"
    GO = "go", "Go"
    RUST = "rust", "Rust"
    KOTLIN = "kotlin", "Kotlin"
    SWIFT = "swift", "Swift"
    R = "r", "R"
    MATLAB = "matlab", "MATLAB"
    BASH = "bash", "Bash"
    OTHER = "other", pgettext_lazy(_CTX, "Digər")


class TaskKind(models.TextChoices):
    """Tapşırığın növü: sərbəst iş (ballı, jurnala düşür) və ev tapşırığı (yalnız yoxlanır)."""

    SELFWORK = "selfwork", pgettext_lazy(_CTX, "Sərbəst iş")
    HOMEWORK = "homework", pgettext_lazy(_CTX, "Ev tapşırığı")


class LatePolicy(models.TextChoices):
    """Son tarixdən sonra göndərişə münasibət."""

    NONE = "none", pgettext_lazy(_CTX, "Son tarixdən sonra qəbul edilmir")
    ALLOW = "allow", pgettext_lazy(_CTX, "Gecikmə ilə qəbul edilir")


class SubmissionStatus(models.TextChoices):
    """Göndərişin (bir cəhdin) statusu.

    ``returned`` — müəllim rəy yazıb QAYTARIB: bal YAZILMIR («0 düşmür»),
    tələbə yeni cəhd göndərir. ``accepted`` yalnız sərbəst iş, ``checked``
    yalnız ev tapşırığı üçündür (DB CheckConstraint).
    """

    DRAFT = "draft", pgettext_lazy(_CTX, "Qaralama")
    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Yoxlanılır")
    RETURNED = "returned", pgettext_lazy(_CTX, "Yenidən işləməyə qaytarılıb")
    ACCEPTED = "accepted", pgettext_lazy(_CTX, "Qəbul edilib")
    CHECKED = "checked", pgettext_lazy(_CTX, "Yoxlanılıb")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edilib")


class RejectReason(models.TextChoices):
    """Rəddin səbəbi (rəy mətni ayrıca MƏCBURİDİR)."""

    LATE = "late", pgettext_lazy(_CTX, "Son tarixdən sonra göndərilib")
    PLAGIARISM = "plagiarism", pgettext_lazy(_CTX, "Plagiat / köçürülmüş iş")
    OFF_TOPIC = "off_topic", pgettext_lazy(_CTX, "Mövzuya uyğun deyil")
    OTHER = "other", pgettext_lazy(_CTX, "Digər səbəb")


class JournalSyncStatus(models.TextChoices):
    """Sərbəst iş balının jurnala ötürülmə vəziyyəti."""

    NONE = "none", pgettext_lazy(_CTX, "Tətbiq olunmur")
    PENDING = "pending", pgettext_lazy(_CTX, "Jurnala ötürülməsi gözlənilir")
    SYNCED = "synced", pgettext_lazy(_CTX, "Jurnala düşüb")
    BLOCKED = "blocked", pgettext_lazy(_CTX, "Jurnal qəbul etmədi")


class PlagiarismStatus(models.TextChoices):
    """Oxşarlıq yoxlamasının vəziyyəti."""

    PENDING = "pending", pgettext_lazy(_CTX, "Yoxlama gözlənilir")
    DONE = "done", pgettext_lazy(_CTX, "Yoxlanılıb")
    SKIPPED = "skipped", pgettext_lazy(_CTX, "Yoxlanıla bilən mətn yoxdur")
    FAILED = "failed", pgettext_lazy(_CTX, "Yoxlama alınmadı")


class MatchMethod(models.TextChoices):
    """Oxşarlığın tapılma üsulu."""

    EXACT = "exact", pgettext_lazy(_CTX, "Eyni məzmun")
    SHINGLE = "shingle", pgettext_lazy(_CTX, "Mətn oxşarlığı")


class EventKind(models.TextChoices):
    """Göndərişin append-only tarixçə hadisələri."""

    DRAFT_SAVED = "draft_saved", pgettext_lazy(_CTX, "Qaralama saxlanıldı")
    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Göndərildi")
    RESUBMITTED = "resubmitted", pgettext_lazy(_CTX, "Yenidən göndərildi")
    FILE_REMOVED = "file_removed", pgettext_lazy(_CTX, "Fayl silindi")
    RETURNED = "returned", pgettext_lazy(_CTX, "Rəylə qaytarıldı")
    ACCEPTED = "accepted", pgettext_lazy(_CTX, "Qəbul edildi")
    CHECKED = "checked", pgettext_lazy(_CTX, "Yoxlanıldı")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edildi")
    REOPENED = "reopened", pgettext_lazy(_CTX, "Rədd ləğv edildi")
    JOURNAL_SYNCED = "journal_synced", pgettext_lazy(_CTX, "Jurnala düşdü")
    JOURNAL_PENDING = "journal_pending", pgettext_lazy(_CTX, "Jurnala ötürülmə gözləyir")
    JOURNAL_BLOCKED = "journal_blocked", pgettext_lazy(_CTX, "Jurnal qəbul etmədi")
    PLAGIARISM_FLAGGED = "plagiarism_flagged", pgettext_lazy(_CTX, "Oxşarlıq aşkarlandı")


#: Yekun (zəncirin bağlandığı) statuslar — bundan sonra yeni cəhd açılmır.
FINAL_STATUSES = frozenset(
    {SubmissionStatus.ACCEPTED.value, SubmissionStatus.CHECKED.value, SubmissionStatus.REJECTED.value}
)

#: Müəllimin baxış NÖVBƏSİNDƏ olan status.
REVIEWABLE_STATUSES = frozenset({SubmissionStatus.SUBMITTED.value})

#: Status → (fon, mətn, accent) TOKEN adları — sillabus kataloqu ilə eyni nizam.
STATUS_TOKENS = {
    SubmissionStatus.DRAFT.value: ("--ems-neutral-100", "--ems-neutral-700", "--ems-neutral-300"),
    SubmissionStatus.SUBMITTED.value: ("--ems-primary-100", "--ems-primary-800", "--ems-primary-600"),
    SubmissionStatus.RETURNED.value: ("--ems-warning-bg", "--ems-warning-800", "--ems-warning"),
    SubmissionStatus.ACCEPTED.value: ("--ems-success-bg", "--ems-success-700", "--ems-success"),
    SubmissionStatus.CHECKED.value: ("--ems-success-bg", "--ems-success-700", "--ems-success"),
    SubmissionStatus.REJECTED.value: ("--ems-danger-bg", "--ems-danger-strong", "--ems-danger"),
}

#: Jurnal sinxron vəziyyəti → token üçlüyü (review UI zolağı).
JOURNAL_SYNC_TOKENS = {
    JournalSyncStatus.NONE.value: ("--ems-neutral-100", "--ems-neutral-500", "--ems-neutral-200"),
    JournalSyncStatus.PENDING.value: ("--ems-warning-bg", "--ems-warning-800", "--ems-warning"),
    JournalSyncStatus.SYNCED.value: ("--ems-success-bg", "--ems-success-700", "--ems-success"),
    JournalSyncStatus.BLOCKED.value: ("--ems-danger-bg", "--ems-danger-strong", "--ems-danger"),
}

# ── Sərbəst iş siyasəti ─────────────────────────────────────────────────────
#: DB trigger-inin (0003 miqrasiyası) sabiti. ``apps.syllabus.public.SELFWORK_TOTAL_SCORE``
#: ilə EYNİ olmalıdır — ``tests/test_models_constraints.py`` bunu kilidləyir.
SELFWORK_TOTAL_CAP = 10

#: Bal dəqiqliyi — 0.1 (məs. 4.5/5). ``DecimalField(max_digits=4, decimal_places=1)``.
POINTS_DECIMAL_PLACES = 1

# ── Limitlər ────────────────────────────────────────────────────────────────
MAX_TITLE_CHARS = 255
MAX_DESCRIPTION_CHARS = 20_000
MAX_INSTRUCTIONS_CHARS = 20_000
MAX_CODE_CHARS = 200_000
MAX_TEXT_ANSWER_CHARS = 50_000
MIN_FEEDBACK_CHARS = 5
MAX_FEEDBACK_CHARS = 5_000
MAX_URL_CHARS = 1_000

#: Materialın ölçü limiti (MB) — ``settings.SUBJECT_FOLDER_MATERIAL_MAX_MB`` ilə dəyişir.
DEFAULT_MATERIAL_MAX_MB = 50
#: Göndəriş faylının DEFAULT limiti (tapşırıq öz limitini bundan aşağı qoya bilər).
DEFAULT_SUBMISSION_MAX_MB = 20
#: Tapşırığın qoya biləcəyi ən böyük fayl limiti.
SUBMISSION_MAX_MB_CAP = 50
DEFAULT_MAX_FILES = 5
MAX_FILES_CAP = 10
#: Bir tapşırığa müəllimin əlavə edə biləcəyi qoşma sayı.
MAX_TASK_ATTACHMENTS = 10

#: Kod/mətn faylları — brauzer çox vaxt ``application/octet-stream`` göndərir;
#: bu uzantılar üçün həmin MIME qəbul olunur (fayl HƏMİŞƏ attachment + nosniff verilir).
TEXTUAL_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".py",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".cs",
        ".go",
        ".rs",
        ".kt",
        ".swift",
        ".sql",
        ".r",
        ".m",
        ".ipynb",
        ".json",
        ".yaml",
        ".yml",
        ".tex",
        ".rtf",
    }
)

#: Şəkil materialı üçün icazəli uzantılar (Pillow ilə yoxlanılır).
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})

#: Ofis/sənəd/arxiv/media uzantıları.
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".odt",
        ".odp",
        ".ods",
        ".zip",
        ".rar",
        ".7z",
        ".mp4",
        ".webm",
        ".mp3",
    }
)

#: Materiallar üçün TAM ağ siyahı (``core.upload_security`` qara siyahısı üstəlik qalır).
MATERIAL_EXTENSIONS = frozenset(DOCUMENT_EXTENSIONS | TEXTUAL_EXTENSIONS | IMAGE_EXTENSIONS)

#: Tələbə göndərişi üçün ağ siyahı (media faylları yoxdur — iş sənəd/kod/şəkildir).
SUBMISSION_EXTENSIONS = frozenset(
    (DOCUMENT_EXTENSIONS - {".mp4", ".webm", ".mp3"}) | TEXTUAL_EXTENSIONS | IMAGE_EXTENSIONS
)

#: Video keçidi üçün tanınan hostlar YOXDUR — istənilən https keçidi qəbul olunur;
#: sxem isə yalnız bunlardan biri ola bilər (``javascript:`` və s. rədd).
ALLOWED_URL_SCHEMES = ("http", "https")

# ── Media prefiksləri (``core.media_policies.register_media_policy``) ────────
MATERIALS_MEDIA_PREFIX = "subject_folder/materials/"
SUBMISSIONS_MEDIA_PREFIX = "subject_folder/submissions/"

# ── Oxşarlıq (plagiat) yoxlaması ────────────────────────────────────────────
#: Bu həddən yuxarı oxşarlıq ``SimilarityMatch`` kimi SAXLANILIR.
SIMILARITY_STORE_THRESHOLD = 0.5
#: Bu həddən yuxarı oxşarlıq BAYRAQLANIR (müəllim növbəsində xəbərdarlıq).
SIMILARITY_FLAG_THRESHOLD = 0.8

# ── Profil bölmələri (UI agenti bu slug-ları qeydiyyatdan keçirir) ──────────
#: Müəllimin qovluq siyahısı / redaktoru.
SECTION_TEACHER = "subject-folders"
#: Müəllimin göndəriş baxış növbəsi.
SECTION_REVIEW = "subject-folder-review"
#: Tələbənin «Fənn qovluqlarım» bölməsi.
SECTION_STUDENT = "my-subject-folders"

# ── Struktur-əhatəli (yalnız-oxu) əməkdaş girişi ────────────────────────────
#: Bu açarların ƏHATƏSİ açılışın qrupunu örtürsə, əməkdaş qovluğu və
#: göndərişləri YALNIZ OXUYA bilər (jurnal müşahidəçisi ilə eyni qayda:
#: ``apps.registrar.journal_access.can_observe_journal``).
STAFF_VIEW_PERMISSIONS = ("journal.view",)
#: Org-wide əhatəsi olan bu açarların daşıyıcısı bütün təşkilatı oxuyur.
ORG_VIEW_PERMISSIONS = ("journal.correct",)
#: Müəllim səlahiyyəti (canlı müəllim yoxlaması, registrar ``integrity`` ilə eyni açar).
INSTRUCTOR_PERMISSION = "grade.input"
