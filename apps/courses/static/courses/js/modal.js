/**
 * modal.js
 * ────────
 * Modal işlətmə funksiyaları.
 * 
 * Nə edər:
 * - Modal açıl/bağlan
 * - Form reset
 * - Error clear
 */

const MODAL_I18N = window.COURSES_I18N || {};
const MODAL_ERRORS_LABEL = MODAL_I18N.errorsLabel || "Errors";

document.addEventListener('DOMContentLoaded', function() {
    initializeModals();
});

/**
 * Modal-ları inisializasiya et
 * Bootstrap 5 Modal API istifadə edir
 */
function initializeModals() {
    // Modal açıldıqda form reset et
    const modals = document.querySelectorAll('.modal');
    
    modals.forEach(modal => {
        modal.addEventListener('show.bs.modal', function() {
            // Form reset
            const form = this.querySelector('form');
            if (form) {
                form.reset();
                
                // Error messages silin
                const errorAlerts = form.querySelectorAll('.alert-danger');
                errorAlerts.forEach(alert => {
                    alert.classList.add('d-none');
                    alert.innerHTML = '';
                });
            }
        });
    });
}

/**
 * Modal-u aç (dinamik)
 * 
 * @param {string} modalId - Modal ID
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
}

/**
 * Modal-u bağla (dinamik)
 * 
 * @param {string} modalId - Modal ID
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) {
            bsModal.hide();
        }
    }
}

/**
 * Modal form-inda error göstər
 * 
 * @param {string} modalId - Modal ID
 * @param {object} errors - Errors object {field: [messages]}
 */
function showModalErrors(modalId, errors) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    const errorContainer = modal.querySelector('.alert-danger');
    if (!errorContainer) return;
    
    let errorHtml = '<strong>' + MODAL_ERRORS_LABEL + ':</strong><ul class="mb-0">';
    
    Object.keys(errors).forEach(field => {
        const messages = errors[field];
        if (Array.isArray(messages)) {
            messages.forEach(msg => {
                errorHtml += `<li>${msg}</li>`;
            });
        }
    });
    
    errorHtml += '</ul>';
    
    errorContainer.innerHTML = errorHtml;
    errorContainer.classList.remove('d-none');
    
    // Scroll to error
    errorContainer.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Modal-daki error-ları silin
 * 
 * @param {string} modalId - Modal ID
 */
function clearModalErrors(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    
    const errorContainers = modal.querySelectorAll('.alert-danger');
    errorContainers.forEach(container => {
        container.innerHTML = '';
        container.classList.add('d-none');
    });
}
