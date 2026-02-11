/* ═══════════════════════════════════════════════════════════════
   LAB DETAIL - Complete Logic
   ═══════════════════════════════════════════════════════════════ */

   (function() {
    'use strict';

    const LAB_ID = window.LAB_CONFIG.labId;
    const CSRF = window.LAB_CONFIG.csrf;
    const END_TIME = new Date(window.LAB_CONFIG.endTime);
    const TOTAL_QUESTIONS = window.LAB_CONFIG.totalQuestions;
    
    let labStartTime = localStorage.getItem('lab_' + LAB_ID + '_start');
    if (!labStartTime) {
        labStartTime = new Date().toISOString();
        localStorage.setItem('lab_' + LAB_ID + '_start', labStartTime);
    }
    labStartTime = new Date(labStartTime);
    
    // ═══════════════════════════════════════════════════════════
    // FILE UPLOAD HANDLER
    // ═══════════════════════════════════════════════════════════
    
    document.querySelectorAll('.file-input').forEach(function(input) {
        input.addEventListener('change', function() {
            const questionId = this.id.replace('file-', '');
            const preview = document.getElementById('preview-' + questionId);
            
            if (this.files && this.files[0]) {
                preview.classList.remove('d-none');
                preview.querySelector('.file-name').textContent = this.files[0].name;
                
                // Faylı dərhal yüklə
                const formData = new FormData();
                formData.append('question_id', questionId);
                formData.append('answer', '');
                formData.append('answer_file', this.files[0]);
                
                fetch('/labs/' + LAB_ID + '/auto-save/', {
                    method: 'POST',
                    body: formData,
                    headers: {'X-CSRFToken': CSRF}
                })
                .then(r => r.json())
                .then(data => {
                    const statusEl = document.getElementById('status-' + questionId);
                    statusEl.innerHTML = data.success 
                        ? '<i class="fas fa-check-circle text-success"></i> Saxlanıldı'
                        : '<i class="fas fa-exclamation-circle text-danger"></i> Xəta';
                })
                .catch(() => {
                    console.error('File upload failed');
                });
            }
        });
    });
    
    window.removeFile = function(questionId) {
        document.getElementById('file-' + questionId).value = '';
        document.getElementById('preview-' + questionId).classList.add('d-none');
    };
    
    // ══════════════════════════════════════════════════════════��
    // TIMER
    // ═══════════════════════════════════════════════════════════
    
    function updateTimers() {
        const now = new Date();
        const elapsed = Math.floor((now - labStartTime) / 1000);
        document.getElementById('elapsedTimer').textContent = formatTime(elapsed);
        
        const remaining = Math.max(0, Math.floor((END_TIME - now) / 1000));
        document.getElementById('remainingTimer').textContent = formatTime(remaining);
        
        if (remaining <= 0) {
            document.getElementById('labForm').submit();
        }
    }
    
    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        return String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
    }
    
    setInterval(updateTimers, 1000);
    updateTimers();
    
    // ═══════════════════════════════════════════════════════════
    // PROGRESS
    // ═══════════════════════════════════════════════════════════
    
    function updateProgress() {
        let answered = 0;
        document.querySelectorAll('.answer-textarea').forEach(function(ta) {
            if (ta.value.trim()) answered++;
        });
        document.getElementById('answeredCount').textContent = answered;
        document.getElementById('progressBar').style.width = (answered / TOTAL_QUESTIONS * 100) + '%';
    }
    
    // ═══════════════════════════════════════════════════════════
    // AUTO-SAVE
    // ═══════════════════════════════════════════════════════════
    
    const saveTimeouts = {};
    
    document.querySelectorAll('.answer-textarea').forEach(function(ta) {
        ta.addEventListener('input', function() {
            const card = this.closest('.question-card');
            const qId = card.dataset.questionId;
            
            clearTimeout(saveTimeouts[qId]);
            saveTimeouts[qId] = setTimeout(function() {
                autoSave(qId, ta.value);
            }, 800);
        });
    });
    
    function autoSave(questionId, answer) {
        const statusEl = document.getElementById('status-' + questionId);
        statusEl.innerHTML = '<i class="fas fa-spinner fa-spin text-primary"></i> Saxlanılır...';
        
        fetch('/labs/' + LAB_ID + '/auto-save/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF
            },
            body: JSON.stringify({
                question_id: questionId,
                answer: answer
            })
        })
        .then(r => r.json())
        .then(data => {
            statusEl.innerHTML = data.success 
                ? '<i class="fas fa-check-circle text-success"></i> Saxlanıldı'
                : '<i class="fas fa-exclamation-circle text-danger"></i> Xəta';
            
            updateProgress();
        })
        .catch(() => {
            statusEl.innerHTML = '<i class="fas fa-exclamation-circle text-danger"></i> Xəta';
        });
    }
    
    updateProgress();
    
    // ═══════════════════════════════════════════════════════════
    // SUBMIT
    // ═══════════════════════════════════════════════════════════
    
    document.getElementById('labForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        const answered = parseInt(document.getElementById('answeredCount').textContent);
        const unanswered = TOTAL_QUESTIONS - answered;
        
        if (unanswered > 0) {
            if (!confirm(unanswered + ' sual cavabsızdır. Göndərmək istəyirsiniz?')) {
                return;
            }
        }
        
        const btn = document.getElementById('submitBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Göndərilir...';
        
        fetch('/labs/' + LAB_ID + '/submit/', {
            method: 'POST',
            body: new FormData(this),
            headers: {'X-CSRFToken': CSRF}
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                localStorage.removeItem('lab_' + LAB_ID + '_start');
                window.location.href = data.redirect_url || '/';
            } else {
                alert('Xəta: ' + (data.error || 'Naməlum xəta'));
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-paper-plane me-2"></i> Labı Bitir';
            }
        })
        .catch(() => {
            alert('Server xətası');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-paper-plane me-2"></i> Labı Bitir';
        });
    });

    console.log('✓ Lab Detail JS initialized');
    console.log('Total questions:', TOTAL_QUESTIONS);
})();