/**
 * notifications.js
 * ──────────────────
 * Toast notifications (success, error, warning, info)
 * 
 * Nə edər:
 * - Toast göstərmə
 * - Auto-dismiss
 * - Stack management
 */

// Toast container
let notificationContainer = null;

document.addEventListener('DOMContentLoaded', function() {
    initializeNotificationContainer();
});

/**
 * Notification container-ı inisializasiya et
 */
function initializeNotificationContainer() {
    // Check if container already exists
    let container = document.getElementById('notificationContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notificationContainer';
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            max-width: 400px;
        `;
        document.body.appendChild(container);
    }
    notificationContainer = container;
}

/**
 * Toast notification göstər
 * 
 * @param {string} message - Notification message
 * @param {string} type - Type: success, error, warning, info
 * @param {number} duration - Duration in milliseconds (0 = no auto-dismiss)
 */
function notify(message, type = 'info', duration = 3000) {
    if (!notificationContainer) {
        initializeNotificationContainer();
    }
    
    // Type validation
    const validTypes = ['success', 'error', 'warning', 'info'];
    if (!validTypes.includes(type)) {
        type = 'info';
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `alert alert-${getBootstrapAlertClass(type)} alert-dismissible fade show`;
    toast.role = 'alert';
    toast.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas ${getIconClass(type)} me-3"></i>
            <div>${message}</div>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    // Add to container
    notificationContainer.appendChild(toast);
    
    // Animation
    setTimeout(() => {
        toast.classList.add('animate-slideInUp');
    }, 10);
    
    // Auto-dismiss
    if (duration > 0) {
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, duration);
    }
    
    // Close button event
    const closeBtn = toast.querySelector('[data-bs-dismiss="alert"]');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        });
    }
}

/**
 * Success notification
 * 
 * @param {string} message - Message
 * @param {number} duration - Duration
 */
function notifySuccess(message, duration = 3000) {
    notify(message, 'success', duration);
}

/**
 * Error notification
 * 
 * @param {string} message - Message
 * @param {number} duration - Duration
 */
function notifyError(message, duration = 5000) {
    notify(message, 'error', duration);
}

/**
 * Warning notification
 * 
 * @param {string} message - Message
 * @param {number} duration - Duration
 */
function notifyWarning(message, duration = 4000) {
    notify(message, 'warning', duration);
}

/**
 * Info notification
 * 
 * @param {string} message - Message
 * @param {number} duration - Duration
 */
function notifyInfo(message, duration = 3000) {
    notify(message, 'info', duration);
}

/**
 * Bootstrap alert class-ını al
 * 
 * @param {string} type - Type
 * @returns {string} - Bootstrap class
 */
function getBootstrapAlertClass(type) {
    const classMap = {
        'success': 'success',
        'error': 'danger',
        'warning': 'warning',
        'info': 'info',
    };
    return classMap[type] || 'info';
}

/**
 * Font Awesome icon class-ını al
 * 
 * @param {string} type - Type
 * @returns {string} - Icon class
 */
function getIconClass(type) {
    const iconMap = {
        'success': 'fa-check-circle text-success',
        'error': 'fa-exclamation-circle text-danger',
        'warning': 'fa-exclamation-triangle text-warning',
        'info': 'fa-info-circle text-info',
    };
    return iconMap[type] || 'fa-info-circle text-info';
}

/**
 * Bütün notifications-ı silin
 */
function clearAllNotifications() {
    if (notificationContainer) {
        notificationContainer.innerHTML = '';
    }
}

/**
 * Notification count
 * 
 * @returns {number} - Count
 */
function getNotificationCount() {
    if (!notificationContainer) return 0;
    return notificationContainer.querySelectorAll('.alert').length;
}