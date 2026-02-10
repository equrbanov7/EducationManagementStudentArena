/* ═══════════════════════════════════════════════════════════════
   MANAGE BLOCKS & QUESTIONS - Complete Logic
   ═══════════════════════════════════════════════════════════════ */

   (function() {
    'use strict';

    // ═══════════════════════════════════════════════════════════
    // CONFIG & HELPERS
    // ═══════════════════════════════════════════════════════════
    
    const LAB_ID = window.LAB_CONFIG.labId;
    const CSRF = window.LAB_CONFIG.csrf;
    const $ = id => document.getElementById(id);

    // ═══════════════════════════════════════════════════════════
    // PENDING DATA STORAGE
    // ═══════════════════════════════════════════════════════════
    
    let pendingBlockData = null;
    let pendingQuestionData = null;
    let pendingImportBlockId = null;
    let pendingAddQuestionBlockId = null;

    // ═══════════════════════════════════════════════════════════
    // EDIT BLOCK MODAL HANDLER
    // ═══════════════════════════════════════════════════════════
    
    const editBlockModal = $('editBlockModal');
    
    if (editBlockModal) {
        editBlockModal.addEventListener('shown.bs.modal', function() {
            if (pendingBlockData) {
                $('editBlockId').value = pendingBlockData.id || '';
                $('editBlockTitle').value = pendingBlockData.title || '';
                $('editBlockDescription').value = pendingBlockData.description || '';
                $('editBlockQTP').value = pendingBlockData.qtp || 0;
                
                console.log('✓ Block data loaded:', pendingBlockData);
                pendingBlockData = null;
            }
        });
    }

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-edit-block');
        if (!btn) return;
        
        pendingBlockData = {
            id: btn.dataset.id,
            title: btn.dataset.title,
            description: btn.dataset.description,
            qtp: btn.dataset.qtp
        };
        
        console.log('→ Block data saved for modal:', pendingBlockData);
        bootstrap.Modal.getOrCreateInstance(editBlockModal).show();
    });

    // ═══════════════════════════════════════════════════════════
    // EDIT QUESTION MODAL HANDLER
    // ═══════════════════════════════════════════════════════════
    
    const editQuestionModal = $('editQuestionModal');
    
    if (editQuestionModal) {
        editQuestionModal.addEventListener('shown.bs.modal', function() {
            if (pendingQuestionData) {
                $('editQuestionId').value = pendingQuestionData.id || '';
                $('editQuestionText').value = pendingQuestionData.text || '';
                $('editQuestionPoints').value = pendingQuestionData.points || 0;
                
                if (pendingQuestionData.attachment) {
                    $('editQuestionCurrentFile').innerHTML = `
                        <a href="${pendingQuestionData.attachment}" target="_blank" class="btn btn-sm btn-outline-secondary">
                            <i class="fas fa-paperclip me-1"></i> Mövcud fayl
                        </a>`;
                } else {
                    $('editQuestionCurrentFile').innerHTML = '';
                }
                
                console.log('✓ Question data loaded:', pendingQuestionData);
                pendingQuestionData = null;
            }
        });
    }

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-edit-question');
        if (!btn) return;
        
        pendingQuestionData = {
            id: btn.dataset.id,
            text: btn.dataset.text,
            points: btn.dataset.points,
            attachment: btn.dataset.attachment
        };
        
        console.log('→ Question data saved for modal:', pendingQuestionData);
        bootstrap.Modal.getOrCreateInstance(editQuestionModal).show();
    });

    // ═══════════════════════════════════════════════════════════
    // ADD QUESTION MODAL HANDLER
    // ═══════════════════════════════════════════════════════════
    
    const addQuestionModal = $('addQuestionModal');
    
    if (addQuestionModal) {
        addQuestionModal.addEventListener('shown.bs.modal', function() {
            if (pendingAddQuestionBlockId) {
                $('addQuestionBlockId').value = pendingAddQuestionBlockId;
                console.log('✓ Block ID set for new question:', pendingAddQuestionBlockId);
                pendingAddQuestionBlockId = null;
            }
        });
    }

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-add-question');
        if (!btn) return;
        
        pendingAddQuestionBlockId = btn.dataset.blockId;
        $('addQuestionForm').reset();
        
        bootstrap.Modal.getOrCreateInstance(addQuestionModal).show();
    });

    // ═══════════════════════════════════════════════════════════
    // IMPORT QUESTIONS MODAL HANDLER
    // ═══════════���═══════════════════════════════════════════════
    
    const importModal = $('importQuestionsModal');
    
    if (importModal) {
        importModal.addEventListener('shown.bs.modal', function() {
            if (pendingImportBlockId) {
                $('importBlockId').value = pendingImportBlockId;
                console.log('✓ Block ID set for import:', pendingImportBlockId);
                pendingImportBlockId = null;
            }
        });
    }

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-import-questions');
        if (!btn) return;
        
        pendingImportBlockId = btn.dataset.blockId;
        $('importQuestionsForm').reset();
        
        bootstrap.Modal.getOrCreateInstance(importModal).show();
    });

    // ═══════════════════════════════════════════════════════════
    // FORM SUBMIT HANDLERS
    // ═══════════════════════════════════════════════════════════
    
    // Add Block
    const addBlockForm = $('addBlockForm');
    if (addBlockForm) {
        addBlockForm.addEventListener('submit', e => {
            e.preventDefault();
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Yaradılır...';
            
            fetch(`/labs/${LAB_ID}/blocks/create/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    location.reload();
                } else {
                    alert('Xəta: ' + (d.error || 'Naməlum xəta'));
                    btn.disabled = false;
                    btn.innerHTML = 'Yarat';
                }
            })
            .catch(() => {
                alert('Server xətası');
                btn.disabled = false;
                btn.innerHTML = 'Yarat';
            });
        });
    }

    // Edit Block
    const editBlockForm = $('editBlockForm');
    if (editBlockForm) {
        editBlockForm.addEventListener('submit', e => {
            e.preventDefault();
            const blockId = $('editBlockId').value;
            if (!blockId) return;
            
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Saxlanılır...';

            fetch(`/labs/blocks/${blockId}/edit/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    location.reload();
                } else {
                    alert('Xəta: ' + (d.error || 'Naməlum xəta'));
                    btn.disabled = false;
                    btn.innerHTML = 'Yadda Saxla';
                }
            })
            .catch(() => {
                alert('Server xətası');
                btn.disabled = false;
                btn.innerHTML = 'Yadda Saxla';
            });
        });
    }

    // Add Question
    const addQuestionForm = $('addQuestionForm');
    if (addQuestionForm) {
        addQuestionForm.addEventListener('submit', e => {
            e.preventDefault();
            const blockId = $('addQuestionBlockId').value;
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Əlavə edilir...';

            fetch(`/labs/blocks/${blockId}/questions/create/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    location.reload();
                } else {
                    alert('Xəta: ' + (d.error || 'Naməlum xəta'));
                    btn.disabled = false;
                    btn.innerHTML = 'Əlavə Et';
                }
            })
            .catch(() => {
                alert('Server xətası');
                btn.disabled = false;
                btn.innerHTML = 'Əlavə Et';
            });
        });
    }

    // Edit Question
    const editQuestionForm = $('editQuestionForm');
    if (editQuestionForm) {
        editQuestionForm.addEventListener('submit', e => {
            e.preventDefault();
            const questionId = $('editQuestionId').value;
            if (!questionId) return;
            
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Saxlanılır...';

            fetch(`/labs/questions/${questionId}/edit/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    location.reload();
                } else {
                    alert('Xəta: ' + (d.error || 'Naməlum xəta'));
                    btn.disabled = false;
                    btn.innerHTML = 'Yadda Saxla';
                }
            })
            .catch(() => {
                alert('Server xətası');
                btn.disabled = false;
                btn.innerHTML = 'Yadda Saxla';
            });
        });
    }

    // Import Questions
    const importForm = $('importQuestionsForm');
    if (importForm) {
        importForm.addEventListener('submit', e => {
            e.preventDefault();
            const blockId = $('importBlockId').value;
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Import edilir...';

            fetch(`/labs/blocks/${blockId}/questions/import/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
            })
            .then(r => r.json())
            .then(d => {
                if (d.success) {
                    alert(d.message || `${d.count} sual əlavə edildi`);
                    location.reload();
                } else {
                    alert('Xəta: ' + (d.error || 'Naməlum xəta'));
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-upload me-1"></i> Import Et';
                }
            })
            .catch(() => {
                alert('Server xətası');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-upload me-1"></i> Import Et';
            });
        });
    }

    // ═══════════════════════════════════════════════════════════
    // DELETE HANDLERS
    // ═══════════════════════════════════════════════════════════
    
    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-delete-block');
        if (!btn) return;
        
        if (!confirm('Bu bloku və içindəki bütün sualları silmək istəyirsiniz?')) return;
        
        fetch(`/labs/blocks/${btn.dataset.id}/delete/`, {
            method: 'POST',
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                location.reload();
            } else {
                alert('Xəta: ' + (d.error || 'Naməlum xəta'));
            }
        })
        .catch(() => alert('Server xətası'));
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.js-delete-question');
        if (!btn) return;
        
        if (!confirm('Bu sualı silmək istəyirsiniz?')) return;
        
        fetch(`/labs/questions/${btn.dataset.id}/delete/`, {
            method: 'POST',
            headers: {'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest'}
        })
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                location.reload();
            } else {
                alert('Xəta: ' + (d.error || 'Naməlum xəta'));
            }
        })
        .catch(() => alert('Server xətası'));
    });

    console.log('✓ Manage Blocks JS initialized');
})();