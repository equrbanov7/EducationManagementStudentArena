"""Tələbə imtahan siyahısı üçün səhifə-səviyyəli TOPLU icazə/cəhd/dil/jurnal hesabı.

P1-3 (2026-09-10 auditi, düzəliş 2026-09-12). Siyahının baza sorğusu düzgün
annotasiyalı idi, amma ``_build_exam_items`` dövründəki heç bir çağırış onunla
örtülmürdü: ``can_user_see`` (4 M2M ``exists``), ``attempts_left_for`` (3),
``can_user_start`` (4–5 + dil parity-si), ``registrar_block_reason`` (5–8) və
``available_language_options`` (1 + variant sayı) — 9 kartlıq səhifədə 130+
sorğu.  Sessiya başlanğıcında minlərlə tələbə eyni anda açanda baza doyurdu.

Bu modul həmin yoxlamaların məlumatını səhifə üçün BİR DƏFƏ, sabit sayda
sorğu ilə yükləyir (üzvlük dəstləri ``values_list`` ilə, cəhd sayı aqreqatla,
jurnal qapısı və dil variantları toplu) və hər imtahan üçün model metodlarının
saf güzgüsünü təqdim edir.  QAYDA: buradakı hər metod ``ExamAccessPolicyMixin``
/ ``Exam.attempts_left_for`` / ``language_parity`` / ``journal_sync`` ilə
EYNİ nəticəni verməlidir (``test_student_list_query_budget`` bunu kilidləyir);
model metodlarının özləri (start/attempt axınının qapısı) toxunulmaz qalır.

Yan təsir də güzgülənir: model metodları köhnəlmiş (deadline-ı keçmiş)
draft/in_progress cəhdləri lazy expire edir — burada da eyni nöqtələrdə, eyni
obyektlər üzərində edilir (bir cəhd = bir Python obyekti, ona görə təkrar
yazı/metrik/jurnal sinxronu yaranmır) və yeni expire olunmuş cəhdlər
«istifadə olunmuş cəhd» sayına və «eyni gün rəsmi imtahan» dəstinə yaddaşda
əlavə olunur — DB-yə təzədən getmədən tək variantla eyni cavab alınır.
"""

from __future__ import annotations

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, StudentExamAttemptGrant
from apps.exams.services.journal_sync import registrar_block_reasons
from apps.exams.services.language_variants import (
    active_question_counts_for_exams,
    active_variants_for_exams,
    build_language_options,
)

# Model tərəfi ilə eyni dəstlər (ExamAccessPolicyMixin).
ACTIVE_ATTEMPT_STATUSES = ("draft", "in_progress")
OFFICIAL_EXAM_CATEGORIES = frozenset({"final", "midterm"})


class StudentExamListBatch:
    """Səhifədəki imtahanlar üçün tələbə-icazə/cəhd/dil/jurnal məlumatının toplu hesabı.

    ``exams`` — səhifənin (annotasiyalı, ``select_related("author", "organization",
    "course")``) imtahan nümunələri; ``user`` — tələbə; ``request`` — jurnal qapısı
    üçün (``None`` → jurnal blok səbəbi hesablanmır).
    """

    def __init__(self, exams, user, *, request=None):
        self.exams = list(exams)
        self.user = user
        self.request = request
        self.exam_ids = [exam.pk for exam in self.exams]
        self._exam_by_id = {exam.pk: exam for exam in self.exams}
        # Bu sorğu ərzində expire olunmuş cəhdlər (yaddaş güzgüsü, bax modul şərhi).
        self._newly_expired = []
        self._load()

    # ── toplu yükləmə (sabit sayda sorğu) ───────────────────────────────────
    def _load(self):
        ids = self.exam_ids
        if not ids:
            self._allowed_ids = self._excluded_ids = self._group_ids = self._course_member_ids = frozenset()
            self._page_attempts = {}
            self._all_active_attempts = []
            self._finished_counts = {}
            self._grants = {}
            self._same_day_official_ids = frozenset()
            self._variants = {}
            self._question_counts = {}
            self._variant_totals = {}
            self._block_reasons = {}
            return

        user = self.user
        # order_by() — Meta sıralaması (-created_at) DISTINCT/values_list sorğularına lazımsız sütun əlavə edir.
        page = Exam.objects.filter(id__in=ids).order_by()
        # M2M üzvlükləri — hər biri tək sorğu (model: hər imtahan üçün ayrıca .exists()).
        self._allowed_ids = frozenset(page.filter(allowed_users=user).values_list("id", flat=True))
        self._excluded_ids = frozenset(page.filter(excluded_users=user).values_list("id", flat=True))
        self._group_ids = frozenset(page.filter(allowed_groups__students=user).values_list("id", flat=True).distinct())
        self._course_member_ids = frozenset(
            page.filter(course__memberships__user=user, course__memberships__role="student")
            .values_list("id", flat=True)
            .distinct()
        )

        self._load_active_attempts()
        # attempts_left_for ilə eyni say: bitmiş + sınaq olmayan (annotasiya sınağı çıxarmır).
        self._finished_counts = {
            row["exam_id"]: row["cnt"]
            for row in ExamAttempt.objects.filter(
                exam_id__in=ids, user=user, status__in=ATTEMPT_FINISHED_STATUSES, is_trial=False
            )
            .values("exam_id")
            .annotate(cnt=Count("id"))
        }
        # Qrant: həm mövcudluq (retake → gün qaydası keçilir), həm əlavə cəhd sayı.
        self._grants = dict(
            StudentExamAttemptGrant.objects.filter(exam_id__in=ids, student=user).values_list(
                "exam_id", "extra_attempts"
            )
        )
        self._same_day_official_ids = self._load_same_day_official_ids()
        self._load_language_data()
        self._block_reasons = registrar_block_reasons(self.request, self.exams) if self.request is not None else {}

    def _load_active_attempts(self):
        """İstifadəçinin BÜTÜN aktiv cəhdləri (tək sorğu, model sırası ``-started_at``).

        Səhifə imtahanlarının cəhdləri (sınaq daxil) ``_expire_stale_attempts_for``
        üçün, digər imtahanların sınaq-olmayan cəhdləri «eyni anda bir imtahan»
        qaydası üçün.  Səhifə cəhdlərinə səhifənin öz (annotasiyalı) imtahan
        nümunəsi bağlanır — model-in related manager-i də belə edir.
        """
        attempts = list(
            ExamAttempt.objects.filter(user=self.user, status__in=ACTIVE_ATTEMPT_STATUSES)
            .select_related("exam")
            .order_by("-started_at")
        )
        self._page_attempts = {}
        for attempt in attempts:
            page_exam = self._exam_by_id.get(attempt.exam_id)
            if page_exam is not None:
                attempt.exam = page_exam
                self._page_attempts.setdefault(attempt.exam_id, []).append(attempt)
        self._all_active_attempts = attempts

    def _load_same_day_official_ids(self):
        """Bu gün bitmiş rəsmi (final/midterm) imtahanların id dəsti — yalnız səhifədə
        rəsmi imtahan varsa (qayda yalnız onlara tətbiq olunur)."""
        if not any(getattr(exam, "exam_type_extended", None) in OFFICIAL_EXAM_CATEGORIES for exam in self.exams):
            return frozenset()
        return frozenset(
            ExamAttempt.objects.filter(
                user=self.user,
                is_trial=False,
                status__in=ATTEMPT_FINISHED_STATUSES,
                finished_at__date=timezone.localdate(),
                exam__exam_type_extended__in=OFFICIAL_EXAM_CATEGORIES,
            ).values_list("exam_id", flat=True)
        )

    def _load_language_data(self):
        self._variants = active_variants_for_exams(self.exam_ids)
        self._question_counts = active_question_counts_for_exams(self.exam_ids)
        # Parity yalnız 2+ aktiv variantlı imtahanda mənalıdır (language_parity ilə eyni).
        multi_variant_ids = [
            variant.id for variants in self._variants.values() if len(variants) >= 2 for variant in variants
        ]
        self._variant_totals = {}
        if multi_variant_ids:
            rows = (
                ExamQuestion.objects.filter(language_variant_id__in=multi_variant_ids, is_active=True)
                .values("language_variant_id")
                .annotate(cnt=Count("id"), total=Sum("points"))
            )
            self._variant_totals = {row["language_variant_id"]: (row["cnt"], row["total"] or 0) for row in rows}

    # ── yan təsir: lazy expire (model ilə eyni nöqtələrdə) ───────────────────
    def _expire(self, attempt):
        if attempt.is_finished:
            return False  # bu sorğuda artıq bağlanıb — təzə sorğu onu qaytarmazdı
        expired = attempt.expire_if_time_limit_reached()
        if expired:
            self._newly_expired.append(attempt)
        return expired

    def _expire_stale_attempts_for(self, exam):
        changed = False
        for attempt in self._page_attempts.get(exam.pk, ()):
            if self._expire(attempt):
                changed = True
        return changed

    def _user_has_active_attempt(self, exam):
        self._expire_stale_attempts_for(exam)
        return any(not attempt.is_finished for attempt in self._page_attempts.get(exam.pk, ()))

    def _newly_expired_count(self, exam):
        return sum(1 for attempt in self._newly_expired if attempt.exam_id == exam.pk and not attempt.is_trial)

    def _same_day_official_blocks(self, exam):
        today = timezone.localdate()
        exam_ids = set(self._same_day_official_ids)
        for attempt in self._newly_expired:
            if attempt.is_trial or not attempt.finished_at:
                continue
            if getattr(attempt.exam, "exam_type_extended", None) not in OFFICIAL_EXAM_CATEGORIES:
                continue
            if timezone.localdate(attempt.finished_at) == today:
                exam_ids.add(attempt.exam_id)
        exam_ids.discard(exam.pk)
        return bool(exam_ids)

    def _concurrent_or_same_day_block(self, exam):
        """``ExamAccessPolicyMixin._concurrent_or_same_day_block`` güzgüsü."""
        for attempt in self._all_active_attempts:
            if attempt.is_trial or attempt.exam_id == exam.pk or attempt.is_finished:
                continue
            if not self._expire(attempt):
                return True, pgettext("exams.model.access", "other_exam_in_progress")

        if getattr(exam, "exam_type_extended", None) in OFFICIAL_EXAM_CATEGORIES:
            has_retake_grant = exam.pk in self._grants
            if not has_retake_grant and self._same_day_official_blocks(exam):
                return True, pgettext("exams.model.access", "already_examined_today")

        return False, None

    # ── model metodlarının saf güzgüləri ─────────────────────────────────────
    def _is_author(self, exam):
        return exam.author_id == self.user.pk

    def _in_allowed_any(self, exam):
        return exam.pk in self._allowed_ids or exam.pk in self._group_ids or exam.pk in self._course_member_ids

    def can_user_see(self, exam):
        """``Exam.can_user_see(user)`` güzgüsü."""
        if self._is_author(exam):
            return True
        if not exam.is_active or exam.is_archived or getattr(exam, "is_deleted", False):
            return False
        if exam.pk in self._excluded_ids:
            return False
        if exam.is_public:
            return True
        if exam.pk in self._allowed_ids:
            return True
        if exam.pk in self._group_ids:
            return True
        if exam.pk in self._course_member_ids:
            return True
        if exam.access_code:
            return True
        return False

    def attempts_left_for(self, exam):
        """``Exam.attempts_left_for(user)`` güzgüsü (lazy expire daxil)."""
        if not exam.max_attempts_per_user:
            return None
        self._expire_stale_attempts_for(exam)
        used = self._finished_counts.get(exam.pk, 0) + self._newly_expired_count(exam)
        extra = self._grants.get(exam.pk) or 0
        return max(exam.max_attempts_per_user + extra - used, 0)

    def can_user_start(self, exam, code=None):
        """``Exam.can_user_start(user, code)`` güzgüsü — eyni qaydalar, eyni mesajlar."""
        user = self.user
        if not exam.is_active:
            return False, pgettext("exams.model.access", "exam_not_active")
        if exam.is_archived or getattr(exam, "is_deleted", False):
            return False, pgettext("exams.model.access", "exam_not_active")
        if exam.is_before_start():
            start_str = exam.start_datetime.strftime("%d.%m.%Y %H:%M")
            return False, pgettext("exams.model.access", "exam_not_started").format(start_str=start_str)
        if exam.is_after_end():
            return False, pgettext("exams.model.access", "exam_ended")

        is_author = self._is_author(exam)
        if not is_author and exam.pk in self._excluded_ids:
            return False, pgettext("exams.model.access", "no_exam_access")

        if self._user_has_active_attempt(exam):
            return True, None

        if not is_author:
            blocked, block_reason = self._concurrent_or_same_day_block(exam)
            if blocked:
                return False, block_reason

        parity_error = self.language_parity_error_message(exam)
        if parity_error:
            return False, parity_error

        left = self.attempts_left_for(exam)
        if left is not None and left <= 0:
            return False, pgettext("exams.model.access", "attempt_limit_reached")

        if is_author:
            return True, None

        in_allowed_any = self._in_allowed_any(exam)

        if getattr(exam, "exam_type_extended", None) in OFFICIAL_EXAM_CATEGORIES:
            if not exam.is_public and not in_allowed_any:
                return False, pgettext("exams.model.access", "no_exam_access")
            if not code:
                return False, pgettext("exams.model.access", "access_code_required")
            # Siyahı heç vaxt kod ötürmür; tam güzgü üçün PIN yolu saxlanılır.
            from apps.exams.services.student_pins import verify_student_pin

            if not verify_student_pin(exam, user, code):
                return False, pgettext("exams.model.access", "access_code_invalid")
            return True, None

        if not exam.access_code:
            if exam.is_public:
                return True, None
            if in_allowed_any:
                return True, None
            return False, pgettext("exams.model.access", "no_exam_access")

        if not exam.is_public and not in_allowed_any:
            return False, pgettext("exams.model.access", "no_exam_access")

        if not code:
            return False, pgettext("exams.model.access", "access_code_required")
        if code != exam.access_code:
            return False, pgettext("exams.model.access", "access_code_invalid")

        return True, None

    def language_parity_error_message(self, exam):
        """``language_parity.language_parity_error_message(exam)`` güzgüsü.

        Kanonik mənbə ``apps.exams.services.language_parity``-dir (mesajlar və
        müqayisə oradan birə-bir götürülüb); fərq yalnız məlumatın prefetch-dən
        gəlməsidir.  Orada dəyişiklik olsa bu güzgü də yenilənməlidir — test
        iki yolun bərabərliyini yoxlayır.
        """
        variants = self._variants.get(exam.pk, [])
        if len(variants) < 2:
            return ""

        reference = variants[0]
        ref_count, ref_points = self._variant_totals.get(reference.id, (0, 0))
        ref_label = reference.display_name or reference.get_language_display()

        issues = []
        for variant in variants[1:]:
            count, points = self._variant_totals.get(variant.id, (0, 0))
            label = variant.display_name or variant.get_language_display()
            if count != ref_count:
                issues.append(
                    pgettext(
                        "exams.service.language_parity",
                        "'{lang}' variantında {count} aktiv sual var, '{ref}' variantında isə {ref_count}.",
                    ).format(lang=label, count=count, ref=ref_label, ref_count=ref_count)
                )
            if points != ref_points:
                issues.append(
                    pgettext(
                        "exams.service.language_parity",
                        "'{lang}' variantının ümumi balı {points}, '{ref}' variantınınkı isə {ref_points}.",
                    ).format(lang=label, points=points, ref=ref_label, ref_points=ref_points)
                )
        if not issues:
            return ""
        return pgettext(
            "exams.service.language_parity",
            "Dil variantları eyni aktiv sual sayına və ümumi bala malik olmalıdır: {issue}",
        ).format(issue=issues[0])

    def available_language_options(self, exam):
        """``language_variants.available_language_options(exam)`` güzgüsü."""
        return build_language_options(self._variants.get(exam.pk, []), self._question_counts, exam.pk)

    def journal_block_reason(self, exam):
        """``journal_sync.registrar_block_reason(request, exam)`` güzgüsü."""
        return self._block_reasons.get(exam.pk)


__all__ = ["StudentExamListBatch"]
