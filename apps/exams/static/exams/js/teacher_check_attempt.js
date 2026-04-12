document.addEventListener('DOMContentLoaded', () => {
    const i18n = window.TEACHER_CHECK_I18N || {};
    const t = {
        modalTitleDetails: i18n.modalTitleDetails || "label_question",
        noAnswer: i18n.noAnswer || "label_no_answer",
        pointsUnit: i18n.pointsUnit || "unit_points",
        statusNotChecked: i18n.statusNotChecked || "status_not_checked",
        saveButtonDirty: i18n.saveButtonDirty || "Save",
        confirmTitle: i18n.confirmTitle || "Save review",
        confirmMessage: i18n.confirmMessage || "Are you sure you want to save and finalize this review?",
        aiGrading: i18n.aiGrading || "AI is grading...",
        aiGradeBtn: i18n.aiGradeBtn || "Grade with AI",
        aiError: i18n.aiError || "AI grading error",
        aiCached: i18n.aiCached || "Cached",
        aiQuotaInfo: i18n.aiQuotaInfo || "{remaining}/{limit} ({window})",
        aiNoAnswer: i18n.aiNoAnswer || "No answer to grade",
        maxPointsLabel: i18n.maxPointsLabel || "/ {points}",
    };

    // Elementlər
    const modal = document.getElementById('questionModal');
    const backdrop = document.getElementById('modalBackdrop');
    const warningModal = document.getElementById('warningModal'); 
    const mainSaveBtn = document.getElementById('mainSaveBtn');
    const backBtn = document.getElementById('backBtn'); // HTML-də id="backBtn" olduğundan əmin olun
    const gradingForm = document.getElementById('gradingForm');
    const modalScoreInput = document.getElementById('modalScoreInput');
    
    let isFormDirty = false;  
    let isModalDirty = false;
    let submitConfirmed = false;
    
    // YENİ: İtifadıçının getmək istədiyi ünvanı yadda saxlamaq üçün dəyişən
    let pendingNavigationUrl = null; 

    // 1. Kartlara klikləmə
    document.querySelectorAll('.question-card').forEach(card => {
        card.addEventListener('click', () => {
            const qId = card.getAttribute('data-question-id');
            openModal(qId);
        });
    }); 

    // 2. Modalı açmaq
    function openModal(qId) {
        const currentScore = document.getElementById(`hidden_score_${qId}`).value;
        const currentFeedback = document.getElementById(`hidden_feedback_${qId}`).value;

        const card = document.querySelector(`.question-card[data-question-id="${qId}"]`);
        const dataStore = card.querySelector('.data-store');

        document.getElementById('modalTitle').textContent = `${t.modalTitleDetails} #${qId}`;
        document.getElementById('modalQuestionText').innerText = dataStore.getAttribute('data-q-text');

        const ansText = dataStore.getAttribute('data-ans-text');
        const modalAnswerEl = document.getElementById('modalAnswerText');
        if (ansText) {
            modalAnswerEl.textContent = ansText;
        } else {
            // Use DOM manipulation to safely add italic element
            modalAnswerEl.innerHTML = '';
            const italicEl = document.createElement('i');
            italicEl.className = 'text-danger';
            italicEl.textContent = t.noAnswer;
            modalAnswerEl.appendChild(italicEl);
        }

        document.getElementById('modalScoreInput').value = currentScore;
        document.getElementById('modalFeedbackInput').value = currentFeedback;
        document.getElementById('currentQuestionId').value = qId;
        normalizeIntegerInput(modalScoreInput);

        // Show max points hint and set input max
        const maxPoints = dataStore.getAttribute('data-q-points') || '';
        const maxHint = document.getElementById('maxPointsHint');
        if (maxHint && maxPoints) {
            maxHint.textContent = t.maxPointsLabel.replace('{points}', maxPoints);
        }
        const scoreInput = document.getElementById('modalScoreInput');
        if (scoreInput && maxPoints) {
            scoreInput.setAttribute('max', maxPoints);
            scoreInput.setAttribute('placeholder', '0');
        }

        // Reset AI grade button state
        const aiBtn = document.getElementById('aiGradeBtn');
        const aiStatus = document.getElementById('aiGradeStatus');
        if (aiBtn) {
            aiBtn.disabled = !ansText;
            aiBtn.classList.remove('is-loading');
            // Restore button inner elements visibility
            const iconEl = aiBtn.querySelector('.btn-ai-grade__icon');
            const textEl = aiBtn.querySelector('.btn-ai-grade__text');
            const loaderEl = aiBtn.querySelector('.btn-ai-grade__loader');
            if (iconEl) iconEl.style.display = '';
            if (textEl) textEl.style.display = '';
            if (loaderEl) loaderEl.style.display = 'none';
        }
        if (aiStatus) {
            aiStatus.textContent = '';
            aiStatus.className = 'ai-grade-status';
        }

        backdrop.style.display = 'block';
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';

        isModalDirty = false;
    }

    // 3. Modalda dəyişiklik izləmə
    ['modalScoreInput', 'modalFeedbackInput'].forEach(id => {
        document.getElementById(id).addEventListener('input', () => {
            isModalDirty = true;
        });
    });

    if (modalScoreInput) {
        modalScoreInput.addEventListener('blur', () => {
            normalizeIntegerInput(modalScoreInput);
        });
    }

    // 4. Overlay Click
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
            attemptCloseModal();
        }
    });

    // ===============================================
    // YENİ: "Geri" Düyməsi Məntiqi
    // ===============================================
    if (backBtn) {
        backBtn.addEventListener('click', (e) => {
            // Əgər dəyişiklik varsa, standart keçidi dayandır və xəbərdarlıq aç
            if (isFormDirty) {
                e.preventDefault(); 
                pendingNavigationUrl = backBtn.getAttribute('href'); // Hara getmək istədiyini yadda saxla
                warningModal.style.display = 'flex';
            }
            // Əgər dəyişiklik yoxdursa, heç nə etmə, qoy link işləsin
        });
    }

    // ===============================================
    // Xəbərdarlıq Sistemi (Yenilənmiş)
    // ===============================================
    
    // Sual modalından çıxmağa cəhd edəndə
    function attemptCloseModal() {
        if (isModalDirty) {
            warningModal.style.display = 'flex'; 
        } else {
            closeMainModal();
        }
    }

    // "Xeyr" (Qayıt)
    function closeWarningModal() {
        warningModal.style.display = 'none';
        pendingNavigationUrl = null; // Gediləcək yolu sıfırla
    }

    // "Bəli" (Məcburi Bağla/Get) - ƏSAS DƏYİŞİKLİK BURADADIR
    function forceCloseModal() {
        warningModal.style.display = 'none';
        
        // SENARİ 1: İstifadəçi "Geri" düyməsinə basıb səhifədən getmək istəyir
        if (pendingNavigationUrl) {
            isFormDirty = false; // Brauzerin öz xəbərdarlığını söndürürük
            window.location.href = pendingNavigationUrl; // Yadda saxlanılan linkə yönləndiririk
        }
        // SENARİ 2: İstifadəçi sadəcə Sual Modalını bağlamaq istəyir
        else {
            isModalDirty = false;
            closeMainModal();
        }
    }

    // Əsas sual modalını bağlayan funksiya
    function closeMainModal() {
        backdrop.style.display = 'none';
        modal.style.display = 'none';
        document.body.style.overflow = '';
        isModalDirty = false;
    }

    // 5. Yadda Saxla (Modal daxili)
    function saveFromModal() {
        const qId = document.getElementById('currentQuestionId').value;
        normalizeIntegerInput(modalScoreInput);
        const newScore = document.getElementById('modalScoreInput').value;
        const newFeedback = document.getElementById('modalFeedbackInput').value;

        document.getElementById(`hidden_score_${qId}`).value = newScore;
        document.getElementById(`hidden_feedback_${qId}`).value = newFeedback;

        const badge = document.getElementById(`badge_${qId}`);
        if (newScore) {
            badge.className = 'status-badge status-scored';
            badge.textContent = `${newScore} ${t.pointsUnit}`;
        } else {
            badge.className = 'status-badge status-not-checked';
            badge.textContent = t.statusNotChecked;
        }

        markFormAsDirty();
        isModalDirty = false;
        closeMainModal();
    }

    // Wire up modal button event listeners (CSP-compliant: no inline onclick)
    const modalCloseBtn = document.getElementById('modalCloseBtn');
    const modalCancelBtn = document.getElementById('modalCancelBtn');
    const modalSaveBtn = document.getElementById('modalSaveBtn');
    const warningCancelBtn = document.getElementById('warningCancelBtn');
    const warningConfirmBtn = document.getElementById('warningConfirmBtn');

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', attemptCloseModal);
    if (modalCancelBtn) modalCancelBtn.addEventListener('click', attemptCloseModal);
    if (modalSaveBtn) modalSaveBtn.addEventListener('click', saveFromModal);
    if (warningCancelBtn) warningCancelBtn.addEventListener('click', closeWarningModal);
    if (warningConfirmBtn) warningConfirmBtn.addEventListener('click', forceCloseModal);

    // ===============================================
    // AI Grade Button
    // ===============================================
    const aiGradeBtn = document.getElementById('aiGradeBtn');
    const aiGradeStatus = document.getElementById('aiGradeStatus');

    function setAiButtonLoading(loading) {
        if (!aiGradeBtn) return;
        if (loading) {
            aiGradeBtn.disabled = true;
            aiGradeBtn.classList.add('is-loading');
            const iconEl = aiGradeBtn.querySelector('.btn-ai-grade__icon');
            const textEl = aiGradeBtn.querySelector('.btn-ai-grade__text');
            const loaderEl = aiGradeBtn.querySelector('.btn-ai-grade__loader');
            if (iconEl) iconEl.style.display = 'none';
            if (textEl) textEl.style.display = 'none';
            if (loaderEl) {
                loaderEl.style.display = 'inline-flex';
                loaderEl.innerHTML = '';
                const spinIcon = document.createElement('i');
                spinIcon.className = 'fas fa-circle-notch fa-spin';
                loaderEl.appendChild(spinIcon);
                const loadingText = document.createTextNode(' ' + t.aiGrading);
                loaderEl.appendChild(loadingText);
            }
        } else {
            aiGradeBtn.disabled = false;
            aiGradeBtn.classList.remove('is-loading');
            const iconEl = aiGradeBtn.querySelector('.btn-ai-grade__icon');
            const textEl = aiGradeBtn.querySelector('.btn-ai-grade__text');
            const loaderEl = aiGradeBtn.querySelector('.btn-ai-grade__loader');
            if (iconEl) iconEl.style.display = '';
            if (textEl) textEl.style.display = '';
            if (loaderEl) loaderEl.style.display = 'none';
        }
    }

    if (aiGradeBtn) {
        aiGradeBtn.addEventListener('click', function handleAiGradeClick(e) {
            e.preventDefault();
            e.stopPropagation();

            const qId = document.getElementById('currentQuestionId').value;
            if (!qId) return;

            const card = document.querySelector('.question-card[data-question-id="' + qId + '"]');
            if (!card) return;
            const dataStore = card.querySelector('.data-store');
            if (!dataStore) return;
            const ansText = dataStore.getAttribute('data-ans-text');

            if (!ansText) {
                if (aiGradeStatus) {
                    aiGradeStatus.textContent = t.aiNoAnswer;
                    aiGradeStatus.className = 'ai-grade-status ai-grade-error';
                }
                return;
            }

            const maxPoints = parseInt(dataStore.getAttribute('data-q-points') || '10', 10);
            const aiUrl = window.AI_GRADE_URL;
            if (!aiUrl) return;

            // Loading state
            setAiButtonLoading(true);
            if (aiGradeStatus) {
                aiGradeStatus.textContent = '';
                aiGradeStatus.className = 'ai-grade-status';
            }

            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            fetch(aiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({
                    question_id: parseInt(qId, 10),
                    max_points: maxPoints,
                }),
            })
            .then(function(res) {
                if (!res.ok) {
                    throw new Error('HTTP ' + res.status);
                }
                return res.json();
            })
            .then(function(data) {
                setAiButtonLoading(false);

                if (data.ok) {
                    // Fill score and feedback
                    var scoreInput = document.getElementById('modalScoreInput');
                    var feedbackInput = document.getElementById('modalFeedbackInput');
                    if (scoreInput) scoreInput.value = data.score;
                    if (feedbackInput) feedbackInput.value = data.explanation;
                    isModalDirty = true;

                    // Highlight fields briefly
                    if (scoreInput) {
                        scoreInput.classList.add('ai-filled');
                        setTimeout(function() { scoreInput.classList.remove('ai-filled'); }, 2000);
                    }
                    if (feedbackInput) {
                        feedbackInput.classList.add('ai-filled');
                        setTimeout(function() { feedbackInput.classList.remove('ai-filled'); }, 2000);
                    }

                    // Show quota info
                    var statusParts = [];
                    if (data.cached) {
                        statusParts.push(t.aiCached);
                    }
                    if (data.remaining !== undefined && data.limit !== undefined) {
                        var quotaText = t.aiQuotaInfo
                            .replace('{remaining}', data.remaining)
                            .replace('{limit}', data.limit)
                            .replace('{window}', data.window || '');
                        statusParts.push(quotaText);
                    }
                    if (aiGradeStatus) {
                        aiGradeStatus.textContent = statusParts.join(' \u00B7 ');
                        aiGradeStatus.className = 'ai-grade-status ai-grade-success';
                    }
                } else {
                    if (aiGradeStatus) {
                        aiGradeStatus.textContent = data.error || t.aiError;
                        aiGradeStatus.className = 'ai-grade-status ai-grade-error';
                    }
                }
            })
            .catch(function(err) {
                setAiButtonLoading(false);
                if (aiGradeStatus) {
                    aiGradeStatus.textContent = t.aiError;
                    aiGradeStatus.className = 'ai-grade-status ai-grade-error';
                }
            });
        });
    }

    // 6. Əsas Form statusu
    function markFormAsDirty() {
        if (!isFormDirty) {
            isFormDirty = true;
            mainSaveBtn.disabled = false;
            mainSaveBtn.innerHTML = `<i class="fas fa-save"></i> ${t.saveButtonDirty}`;
            mainSaveBtn.classList.remove('btn-success');
            mainSaveBtn.classList.add('btn-warning');
            mainSaveBtn.style.color = '#000';
        }
    }

    // Səhifədən çıxanda (Browser Tab close / Refresh) xəbərdarlıq
    window.addEventListener('beforeunload', (e) => {
        if (isFormDirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    if (gradingForm) {
        gradingForm.addEventListener('submit', (e) => {
            if (submitConfirmed) {
                submitConfirmed = false;
                isFormDirty = false;
                return;
            }

            e.preventDefault();

            if (typeof window.openActionConfirmModal !== 'function') {
                submitConfirmed = true;
                if (typeof gradingForm.requestSubmit === 'function') {
                    gradingForm.requestSubmit();
                } else {
                    gradingForm.submit();
                }
                return;
            }

            window.openActionConfirmModal({
                title: t.confirmTitle,
                message: t.confirmMessage,
                confirmLabel: mainSaveBtn ? mainSaveBtn.textContent.trim() : 'Yadda saxla',
                confirmButtonClass: 'btn btn-success',
                onConfirm: function () {
                    submitConfirmed = true;
                    if (typeof gradingForm.requestSubmit === 'function') {
                        gradingForm.requestSubmit();
                    } else {
                        gradingForm.submit();
                    }
                }
            });
        });
    }

    function normalizeIntegerInput(input) {
        if (!input) return;
        const normalized = (input.value || '').trim().replace(',', '.');
        if (!normalized) {
            input.value = '';
            return;
        }
        const match = normalized.match(/^-?\d+/);
        if (!match) {
            input.value = '';
            return;
        }
        let nextValue = parseInt(match[0], 10);
        if (Number.isNaN(nextValue) || nextValue < 0) {
            nextValue = 0;
        }
        input.value = String(nextValue);
    }
});
