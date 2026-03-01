/**
 * proctoring.js
 * ═════════════════════════════════════════════════════════════════════
 * Exam proctoring and anti-cheating functionality
 * 
 * Features:
 * - Tab/window switch detection
 * - Copy/paste blocking
 * - Right-click/context menu blocking
 * - Fullscreen exit detection
 * - AJAX logging to backend
 * - User warnings
 * 
 * Usage:
 * Include this script on exam pages and call:
 *   ProctoringSecurity.init(examId, strictMode);
 */

const ProctoringSecurity = (function() {
    'use strict';

    // Configuration
    let config = {
        examId: null,
        strictMode: true,
        maxWarnings: 3,
        logEndpoint: '/api/exams/log-violation/',
        warningCount: 0,
        isActive: false,
        requireFullscreen: true
    };

    // Violation types
    const ViolationType = {
        TAB_SWITCH: 'tab_switch',
        WINDOW_BLUR: 'window_blur',
        COPY_ATTEMPT: 'copy_attempt',
        PASTE_ATTEMPT: 'paste_attempt',
        RIGHT_CLICK: 'right_click',
        FULLSCREEN_EXIT: 'fullscreen_exit',
        DEVTOOLS_OPEN: 'devtools_open'
    };

    /**
     * Initialize proctoring system
     */
    function init(examId, options = {}) {
        config = { ...config, ...options, examId };
        
        if (!examId) {
            console.error('ProctoringSecurity: examId is required');
            return false;
        }

        console.log('ProctoringSecurity: Initializing for exam', examId);
        
        // Enable all security measures
        enableTabSwitchDetection();
        enableCopyPasteBlocking();
        enableRightClickBlocking();
        enableFullscreenMonitoring();
        enableDevToolsDetection();
        enableKeyboardShortcutBlocking();
        
        config.isActive = true;
        
        // Request fullscreen if required
        if (config.requireFullscreen) {
            requestFullscreen();
        }
        
        // Log exam start
        logViolation('exam_start', 'İmtahan başladı');
        
        // Show initial warning
        showWarningBanner();
        
        return true;
    }

    /**
     * Disable proctoring (call when exam ends)
     */
    function disable() {
        console.log('ProctoringSecurity: Disabling');
        config.isActive = false;
        
        // Remove event listeners
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        window.removeEventListener('blur', handleWindowBlur);
        document.removeEventListener('copy', handleCopyAttempt);
        document.removeEventListener('paste', handlePasteAttempt);
        document.removeEventListener('contextmenu', handleContextMenu);
        document.removeEventListener('fullscreenchange', handleFullscreenChange);
        document.removeEventListener('keydown', handleKeyboardShortcut);
        
        // Log exam end
        logViolation('exam_end', 'İmtahan bitdi');
    }

    /**
     * Tab/Window switch detection
     */
    function enableTabSwitchDetection() {
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('blur', handleWindowBlur);
    }

    function handleVisibilityChange() {
        if (!config.isActive) return;
        
        if (document.hidden) {
            const message = 'Tab dəyişdirildi - İmtahan səhifəsindən çıxdınız!';
            logViolation(ViolationType.TAB_SWITCH, message);
            showWarning(message);
        }
    }

    function handleWindowBlur() {
        if (!config.isActive) return;
        
        const message = 'Pəncərə fokusunu itirdiniz!';
        logViolation(ViolationType.WINDOW_BLUR, message);
        showWarning(message);
    }

    /**
     * Copy/Paste blocking
     */
    function enableCopyPasteBlocking() {
        document.addEventListener('copy', handleCopyAttempt);
        document.addEventListener('paste', handlePasteAttempt);
        document.addEventListener('cut', handleCopyAttempt);
    }

    function handleCopyAttempt(e) {
        if (!config.isActive) return;
        
        // Allow copy from input fields for answers
        if (e.target.tagName === 'TEXTAREA' || 
            (e.target.tagName === 'INPUT' && e.target.type === 'text')) {
            return;
        }
        
        e.preventDefault();
        const message = 'Mətn köçürmək qadağandır!';
        logViolation(ViolationType.COPY_ATTEMPT, message);
        showWarning(message);
    }

    function handlePasteAttempt(e) {
        if (!config.isActive) return;
        
        // Allow paste into answer fields
        if (e.target.tagName === 'TEXTAREA' || 
            (e.target.tagName === 'INPUT' && e.target.type === 'text')) {
            return;
        }
        
        e.preventDefault();
        const message = 'Mətn yapışdırmaq qadağandır!';
        logViolation(ViolationType.PASTE_ATTEMPT, message);
        showWarning(message);
    }

    /**
     * Right-click blocking
     */
    function enableRightClickBlocking() {
        document.addEventListener('contextmenu', handleContextMenu);
    }

    function handleContextMenu(e) {
        if (!config.isActive) return;
        
        e.preventDefault();
        const message = 'Sağ klik qadağandır!';
        logViolation(ViolationType.RIGHT_CLICK, message);
        showWarning(message, 'warning');
    }

    /**
     * Fullscreen monitoring
     */
    function enableFullscreenMonitoring() {
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('MSFullscreenChange', handleFullscreenChange);
    }

    function handleFullscreenChange() {
        if (!config.isActive || !config.requireFullscreen) return;
        
        const isFullscreen = !!(document.fullscreenElement || 
                               document.webkitFullscreenElement || 
                               document.mozFullScreenElement || 
                               document.msFullscreenElement);
        
        if (!isFullscreen) {
            const message = 'Tam ekran rejimindən çıxdınız! Yenidən tam ekrana keçin.';
            logViolation(ViolationType.FULLSCREEN_EXIT, message);
            showWarning(message, 'danger');
            
            // Auto re-request fullscreen after 3 seconds
            setTimeout(() => {
                if (config.isActive) {
                    requestFullscreen();
                }
            }, 3000);
        }
    }

    function requestFullscreen() {
        const elem = document.documentElement;
        
        if (elem.requestFullscreen) {
            elem.requestFullscreen();
        } else if (elem.webkitRequestFullscreen) {
            elem.webkitRequestFullscreen();
        } else if (elem.mozRequestFullScreen) {
            elem.mozRequestFullScreen();
        } else if (elem.msRequestFullscreen) {
            elem.msRequestFullscreen();
        }
    }

    /**
     * DevTools detection (basic)
     */
    function enableDevToolsDetection() {
        // Check window size changes (basic detection)
        let devtoolsOpen = false;
        const threshold = 160;
        
        setInterval(() => {
            if (!config.isActive) return;
            
            const widthThreshold = window.outerWidth - window.innerWidth > threshold;
            const heightThreshold = window.outerHeight - window.innerHeight > threshold;
            
            if (widthThreshold || heightThreshold) {
                if (!devtoolsOpen) {
                    devtoolsOpen = true;
                    const message = 'Developer tools açıq olduğu şübhəsi!';
                    logViolation(ViolationType.DEVTOOLS_OPEN, message);
                    showWarning(message, 'danger');
                }
            } else {
                devtoolsOpen = false;
            }
        }, 1000);
    }

    /**
     * Block dangerous keyboard shortcuts
     */
    function enableKeyboardShortcutBlocking() {
        document.addEventListener('keydown', handleKeyboardShortcut);
    }

    function handleKeyboardShortcut(e) {
        if (!config.isActive) return;
        
        // Block F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U
        if (e.key === 'F12' || 
            (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) ||
            (e.ctrlKey && e.key === 'U')) {
            e.preventDefault();
            showWarning('Bu klaviatura qısayolu bloklanıb!', 'warning');
            return false;
        }
        
        // Block Ctrl+Alt+Del, Alt+Tab (can't fully block but detect)
        if (e.altKey && e.key === 'Tab') {
            const message = 'Tab dəyişdirmə cəhdi aşkarlandı!';
            logViolation(ViolationType.TAB_SWITCH, message);
        }
    }

    /**
     * Log violation to backend
     */
    function logViolation(type, message) {
        console.warn('ProctoringSecurity violation:', type, message);
        
        // Send to backend via AJAX
        fetch(config.logEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                exam_id: config.examId,
                violation_type: type,
                message: message,
                timestamp: new Date().toISOString()
            })
        }).catch(err => {
            console.error('Failed to log violation:', err);
        });
    }

    /**
     * Show warning to user
     */
    function showWarning(message, type = 'danger') {
        if (!config.strictMode) return;
        
        config.warningCount++;
        
        // Create warning toast
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} proctoring-warning`;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 10000;
            min-width: 400px;
            max-width: 600px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideDown 0.3s ease-out;
        `;
        
        toast.innerHTML = `
            <div style="display: flex; align-items: center; gap: 1rem;">
                <i class="fas fa-exclamation-triangle" style="font-size: 1.5rem;"></i>
                <div style="flex: 1;">
                    <strong>Xəbərdarlıq ${config.warningCount}/${config.maxWarnings}</strong><br>
                    ${message}
                </div>
            </div>
        `;
        
        document.body.appendChild(toast);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.style.animation = 'slideUp 0.3s ease-in';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
        
        // Check if max warnings reached
        if (config.warningCount >= config.maxWarnings) {
            handleMaxWarnings();
        }
    }

    /**
     * Show permanent warning banner
     */
    function showWarningBanner() {
        const banner = document.createElement('div');
        banner.id = 'proctoringBanner';
        banner.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
            color: white;
            padding: 0.75rem 1rem;
            text-align: center;
            font-weight: 600;
            z-index: 9999;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;
        banner.innerHTML = `
            <i class="fas fa-shield-alt"></i>
            İmtahan nəzarəti aktiv - Səhifəni tərk etməyin, mətn köçürməyin və sağ klik etməyin!
        `;
        document.body.appendChild(banner);
    }

    /**
     * Handle max warnings reached
     */
    function handleMaxWarnings() {
        alert('Maksimum xəbərdarlıq sayına çatdınız! İmtahan avtomatik olaraq təqdim ediləcək.');
        
        // Submit exam automatically
        const submitBtn = document.querySelector('[data-exam-submit]');
        if (submitBtn) {
            submitBtn.click();
        }
        
        disable();
    }

    /**
     * Get CSRF token from cookies
     */
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Add CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideDown {
            from {
                transform: translate(-50%, -100%);
                opacity: 0;
            }
            to {
                transform: translate(-50%, 0);
                opacity: 1;
            }
        }
        
        @keyframes slideUp {
            from {
                transform: translate(-50%, 0);
                opacity: 1;
            }
            to {
                transform: translate(-50%, -100%);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);

    // Public API
    return {
        init,
        disable,
        getWarningCount: () => config.warningCount,
        isActive: () => config.isActive
    };
})();

// Auto-init if data-exam-id attribute exists
document.addEventListener('DOMContentLoaded', function() {
    const examElement = document.querySelector('[data-exam-id]');
    if (examElement) {
        const examId = examElement.dataset.examId;
        const strictMode = examElement.dataset.strictMode !== 'false';
        const requireFullscreen = examElement.dataset.requireFullscreen !== 'false';
        
        ProctoringSecurity.init(examId, { strictMode, requireFullscreen });
    }
});
