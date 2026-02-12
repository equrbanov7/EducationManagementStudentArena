document.addEventListener('DOMContentLoaded', () => {
    // Elementlər
    const modal = document.getElementById('questionModal');
    const backdrop = document.getElementById('modalBackdrop');
    const warningModal = document.getElementById('warningModal'); 
    const mainSaveBtn = document.getElementById('mainSaveBtn');
    const backBtn = document.getElementById('backBtn'); // HTML-də id="backBtn" olduğundan əmin olun
    
    let isFormDirty = false;  
    let isModalDirty = false;
    
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
        
        document.getElementById('modalTitle').textContent = `Sual #${qId} Təfərrüatları`;
        document.getElementById('modalQuestionText').innerText = dataStore.getAttribute('data-q-text');
        
        const ansText = dataStore.getAttribute('data-ans-text');
        document.getElementById('modalAnswerText').innerHTML = ansText ? ansText : '<i class="text-danger">Cavab yoxdur</i>';
        
        document.getElementById('modalScoreInput').value = currentScore;
        document.getElementById('modalFeedbackInput').value = currentFeedback;
        document.getElementById('currentQuestionId').value = qId;

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
    window.attemptCloseModal = function() {
        if (isModalDirty) {
            warningModal.style.display = 'flex'; 
        } else {
            closeMainModal();
        }
    }

    // "Xeyr" (Qayıt)
    window.closeWarningModal = function() {
        warningModal.style.display = 'none';
        pendingNavigationUrl = null; // Gediləcək yolu sıfırla
    }

    // "Bəli" (Məcburi Bağla/Get) - ƏSAS DƏYİŞİKLİK BURADADIR
    window.forceCloseModal = function() {
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
    window.saveFromModal = function() {
        const qId = document.getElementById('currentQuestionId').value;
        const newScore = document.getElementById('modalScoreInput').value;
        const newFeedback = document.getElementById('modalFeedbackInput').value;

        document.getElementById(`hidden_score_${qId}`).value = newScore;
        document.getElementById(`hidden_feedback_${qId}`).value = newFeedback;

        const badge = document.getElementById(`badge_${qId}`);
        if (newScore) {
            badge.className = 'status-badge status-scored';
            badge.textContent = `${newScore} Bal`;
        } else {
            badge.className = 'status-badge status-not-checked';
            badge.textContent = 'Yoxlanmayıb';
        }

        markFormAsDirty();
        isModalDirty = false;
        closeMainModal();
    }

    // 6. Əsas Form statusu
    function markFormAsDirty() {
        if (!isFormDirty) {
            isFormDirty = true;
            mainSaveBtn.disabled = false;
            mainSaveBtn.innerHTML = '<i class="fas fa-save"></i> Yadda Saxla (Dəyişiklik var)';
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

    document.getElementById('gradingForm').addEventListener('submit', () => {
        isFormDirty = false;
    });
});