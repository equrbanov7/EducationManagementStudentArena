/* Manage blocks and questions logic */
(function () {
    'use strict';

    const LAB_ID = window.LAB_CONFIG.labId;
    const CSRF = window.LAB_CONFIG.csrf;
    const $ = (id) => document.getElementById(id);
    const I18N = window.LAB_I18N || {};
    const t = (key, fallback) => I18N[key] || fallback;
    const RELOAD_NOTIFICATION_KEY = 'labs.manageBlocks.pendingNotification';
    const ICON_CLASS_BY_TYPE = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
    };

    let pendingBlockData = null;
    let pendingQuestionData = null;
    let pendingImportBlockId = null;
    let pendingAddQuestionBlockId = null;

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function getToastContainer() {
        let container = document.querySelector('.toast-container');
        if (container) return container;

        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }

    function showNotification(message, type = 'info', duration = 4000) {
        const normalizedType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';
        const alertType = normalizedType === 'error' ? 'danger' : normalizedType;
        const container = getToastContainer();
        const toast = document.createElement('div');
        toast.className = `alert alert-${alertType} alert-dismissible fade show`;
        toast.setAttribute('role', 'alert');
        toast.dataset.autoHide = String(duration);
        toast.innerHTML = `
            <i class="fas ${ICON_CLASS_BY_TYPE[normalizedType] || ICON_CLASS_BY_TYPE.info} me-2"></i>
            ${escapeHtml(message)}
            <button type="button" class="btn-close" aria-label="Bağla"></button>
        `;

        const closeButton = toast.querySelector('.btn-close');
        const removeToast = () => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        };

        closeButton.addEventListener('click', removeToast);
        container.appendChild(toast);

        if (duration > 0) {
            setTimeout(removeToast, duration);
        }
    }

    function showError(message) {
        showNotification(message, 'error', 5000);
    }

    function persistNotificationForReload(message, type = 'success', duration = 4000) {
        try {
            sessionStorage.setItem(
                RELOAD_NOTIFICATION_KEY,
                JSON.stringify({ message, type, duration })
            );
        } catch (error) {
            // Ignore storage failures and continue with reload.
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        try {
            const rawValue = sessionStorage.getItem(RELOAD_NOTIFICATION_KEY);
            if (!rawValue) return;

            sessionStorage.removeItem(RELOAD_NOTIFICATION_KEY);
            const notification = JSON.parse(rawValue);
            if (!notification || !notification.message) return;

            showNotification(notification.message, notification.type || 'info', notification.duration || 4000);
        } catch (error) {
            sessionStorage.removeItem(RELOAD_NOTIFICATION_KEY);
        }
    });

    const editBlockModal = $('editBlockModal');
    if (editBlockModal) {
        editBlockModal.addEventListener('shown.bs.modal', () => {
            if (!pendingBlockData) return;
            $('editBlockId').value = pendingBlockData.id || '';
            $('editBlockTitle').value = pendingBlockData.title || '';
            $('editBlockDescription').value = pendingBlockData.description || '';
            $('editBlockQTP').value = pendingBlockData.qtp || 0;
            pendingBlockData = null;
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.js-edit-block');
        if (!btn) return;
        pendingBlockData = {
            id: btn.dataset.id,
            title: btn.dataset.title,
            description: btn.dataset.description,
            qtp: btn.dataset.qtp,
        };
        bootstrap.Modal.getOrCreateInstance(editBlockModal).show();
    });

    const editQuestionModal = $('editQuestionModal');
    if (editQuestionModal) {
        editQuestionModal.addEventListener('shown.bs.modal', () => {
            if (!pendingQuestionData) return;
            $('editQuestionId').value = pendingQuestionData.id || '';
            $('editQuestionText').value = pendingQuestionData.text || '';
            $('editQuestionPoints').value = pendingQuestionData.points || 0;

            if (pendingQuestionData.attachment) {
                $('editQuestionCurrentFile').innerHTML =
                    '<a href="' +
                    pendingQuestionData.attachment +
                    '" target="_blank" class="btn btn-sm btn-outline-secondary">' +
                    '<i class="fas fa-paperclip me-1"></i> ' +
                    t('fileExisting', 'Existing file') +
                    '</a>';
            } else {
                $('editQuestionCurrentFile').innerHTML = '';
            }

            pendingQuestionData = null;
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.js-edit-question');
        if (!btn) return;
        pendingQuestionData = {
            id: btn.dataset.id,
            text: btn.dataset.text,
            points: btn.dataset.points,
            attachment: btn.dataset.attachment,
        };
        bootstrap.Modal.getOrCreateInstance(editQuestionModal).show();
    });

    const addQuestionModal = $('addQuestionModal');
    if (addQuestionModal) {
        addQuestionModal.addEventListener('shown.bs.modal', () => {
            if (!pendingAddQuestionBlockId) return;
            $('addQuestionBlockId').value = pendingAddQuestionBlockId;
            pendingAddQuestionBlockId = null;
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.js-add-question');
        if (!btn) return;
        pendingAddQuestionBlockId = btn.dataset.blockId;
        $('addQuestionForm').reset();
        bootstrap.Modal.getOrCreateInstance(addQuestionModal).show();
    });

    const importModal = $('importQuestionsModal');
    if (importModal) {
        importModal.addEventListener('shown.bs.modal', () => {
            if (!pendingImportBlockId) return;
            $('importBlockId').value = pendingImportBlockId;
            pendingImportBlockId = null;
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.js-import-questions');
        if (!btn) return;
        pendingImportBlockId = btn.dataset.blockId;
        $('importQuestionsForm').reset();
        bootstrap.Modal.getOrCreateInstance(importModal).show();
    });

    const addBlockForm = $('addBlockForm');
    if (addBlockForm) {
        addBlockForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> ' + t('stateCreating', 'Creating...');

            fetch(`/labs/${LAB_ID}/blocks/create/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.json())
                .then((d) => {
                    if (d.success) {
                        location.reload();
                    } else {
                        showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                        btn.disabled = false;
                        btn.innerHTML = t('actionCreate', 'Create');
                    }
                })
                .catch(() => {
                    showError(t('errorServer', 'Server error'));
                    btn.disabled = false;
                    btn.innerHTML = t('actionCreate', 'Create');
                });
        });
    }

    const editBlockForm = $('editBlockForm');
    if (editBlockForm) {
        editBlockForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const blockId = $('editBlockId').value;
            if (!blockId) return;

            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> ' + t('stateSaving', 'Saving...');

            fetch(`/labs/blocks/${blockId}/edit/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.json())
                .then((d) => {
                    if (d.success) {
                        location.reload();
                    } else {
                        showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                        btn.disabled = false;
                        btn.innerHTML = t('actionSave', 'Save');
                    }
                })
                .catch(() => {
                    showError(t('errorServer', 'Server error'));
                    btn.disabled = false;
                    btn.innerHTML = t('actionSave', 'Save');
                });
        });
    }

    const addQuestionForm = $('addQuestionForm');
    if (addQuestionForm) {
        addQuestionForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const blockId = $('addQuestionBlockId').value;
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> ' + t('stateAdding', 'Adding...');

            fetch(`/labs/blocks/${blockId}/questions/create/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.json())
                .then((d) => {
                    if (d.success) {
                        location.reload();
                    } else {
                        showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                        btn.disabled = false;
                        btn.innerHTML = t('actionAdd', 'Add');
                    }
                })
                .catch(() => {
                    showError(t('errorServer', 'Server error'));
                    btn.disabled = false;
                    btn.innerHTML = t('actionAdd', 'Add');
                });
        });
    }

    const editQuestionForm = $('editQuestionForm');
    if (editQuestionForm) {
        editQuestionForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const questionId = $('editQuestionId').value;
            if (!questionId) return;

            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> ' + t('stateSaving', 'Saving...');

            fetch(`/labs/questions/${questionId}/edit/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.json())
                .then((d) => {
                    if (d.success) {
                        location.reload();
                    } else {
                        showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                        btn.disabled = false;
                        btn.innerHTML = t('actionSave', 'Save');
                    }
                })
                .catch(() => {
                    showError(t('errorServer', 'Server error'));
                    btn.disabled = false;
                    btn.innerHTML = t('actionSave', 'Save');
                });
        });
    }

    const importForm = $('importQuestionsForm');
    if (importForm) {
        importForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const blockId = $('importBlockId').value;
            const btn = e.target.querySelector('[type=submit]');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> ' + t('stateImporting', 'Importing...');

            fetch(`/labs/blocks/${blockId}/questions/import/`, {
                method: 'POST',
                body: new FormData(e.target),
                headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.json())
                .then((d) => {
                    if (d.success) {
                        persistNotificationForReload(
                            d.message ||
                                t('successImportDefault', '{count} questions imported').replace('{count}', d.count || 0),
                            'success',
                            4500
                        );
                        const modal = bootstrap.Modal.getInstance(importModal);
                        if (modal) {
                            modal.hide();
                        }
                        location.reload();
                    } else {
                        showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-upload me-1"></i> ' + t('actionImport', 'Import');
                    }
                })
                .catch(() => {
                    showError(t('errorServer', 'Server error'));
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-upload me-1"></i> ' + t('actionImport', 'Import');
                });
        });
    }

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.js-delete-block');
        if (!btn) return;

        if (!confirm(t('confirmDeleteBlock', 'Delete this block and all questions inside it?'))) return;

        fetch(`/labs/blocks/${btn.dataset.id}/delete/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then((r) => r.json())
            .then((d) => {
                if (d.success) {
                    location.reload();
                } else {
                    showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                }
            })
            .catch(() => showError(t('errorServer', 'Server error')));
    });

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.js-delete-question');
        if (!btn) return;

        if (!confirm(t('confirmDeleteQuestion', 'Delete this question?'))) return;

        fetch(`/labs/questions/${btn.dataset.id}/delete/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then((r) => r.json())
            .then((d) => {
                if (d.success) {
                    location.reload();
                } else {
                    showError(t('errorPrefix', 'Error') + ': ' + (d.error || t('errorUnknown', 'Unknown error')));
                }
            })
            .catch(() => showError(t('errorServer', 'Server error')));
    });
})();
