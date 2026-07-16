/**
 * Exam Supervision Module
 *
 * Browser-based anti-cheating enforcement for supervised exams.
 * Handles fullscreen, focus detection, copy/paste blocking,
 * right-click prevention, keyboard shortcut restriction, and
 * violation tracking with server-side logging.
 *
 * Usage: Call ExamSupervision.init(config) after DOM is ready.
 */
export var ExamSupervision = {
        config: null,
        attemptId: null,
        csrfToken: "",
        logEndpoint: "",
        statusEndpoint: "",
        violationCount: 0,
        maxViolations: 3,
        gracePeriodSeconds: 15,
        graceTimer: null,
        warningModal: null,
        isActive: false,
        isFullscreen: false,
        capabilities: null,
        requestedConfig: null,
        isSupervised: true,
        _fullscreenDisabledByCapability: false,
        _acknowledged: false,
        _initialized: false,
        _initialStatus: "active",
        _thresholdWarned: false,
        _navigatingToResult: false,

        /**
         * Initialize the supervision module.
         * @param {Object} opts - Configuration from server
         */
        init: function (opts) {
            // Prevent double initialization
            if (this._initialized) return;
            this._initialized = true;

            this.requestedConfig = this._cloneConfig(opts.config || {});
            this.config = this._cloneConfig(opts.config || {});
            this.attemptId = opts.attemptId;
            this.csrfToken = opts.csrfToken;
            this.logEndpoint = opts.logEndpoint;
            this.statusEndpoint = opts.statusEndpoint;
            this.violationCount = opts.violationCount || 0;
            this.maxViolations = opts.maxViolations || 3;
            this.gracePeriodSeconds = this.config.grace_period_seconds || 15;
            this.isSupervised = opts.supervised !== false;
            this._initialStatus = opts.supervisionStatus || "active";
            this.isActive = true;
            this._acknowledged = false;
            this._fullscreenDisabledByCapability = false;
            this.capabilities = this._detectCapabilities();
            this._applyCapabilityFallbacks();

            if (this.isSupervised) {
                this._createWarningModal();
                this._createSupervisionBadge();
            }

            // Connect WebSocket for real-time teacher action notifications
            this._connectWebSocket();
            // Start the resilient status poll immediately as well. If the
            // teacher pauses the student while the acknowledgment modal is
            // still open, the manual-lock modal should still appear.
            this._startBackgroundStatusWatch();

            // If attempt is already locked/removed, show the right overlay
            // immediately. We ask the status API whether this was a manual
            // teacher pause (distinct overlay, no auto-finish countdown) or an
            // auto-lock from the violation limit.
            if (this._initialStatus === "locked" || this._initialStatus === "removed") {
                this._acknowledged = true;
                this._bindEvents();
                var self = this;
                this._checkSupervisionStatus(function (data) {
                    if (data && data.manual_lock) {
                        self._showTeacherLockOverlay(data.intervention_reason);
                    } else if (data && data.supervision_status === "removed") {
                        self._showRemovalOverlay(data.intervention_reason, data.intervention_action);
                    } else {
                        self._onLimitExceeded();
                    }
                });
                // Fallback: if the status call fails the callback never fires,
                // so show the limit overlay after a short delay to be safe.
                window.setTimeout(function () {
                    if (!document.getElementById("supervision-teacher-lock-overlay") &&
                        !document.getElementById("supervision-locked-overlay")) {
                        self._onLimitExceeded();
                    }
                }, 1500);
                return;
            }

            if (!this.isSupervised) {
                return;
            }

            // Show acknowledgment overlay - events bind AFTER student acknowledges
            this._showAcknowledgment();
        },

        _cloneConfig: function (config) {
            var clone = {};
            Object.keys(config || {}).forEach(function (key) {
                clone[key] = config[key];
            });
            return clone;
        },

        _detectCapabilities: function () {
            var el = document.documentElement || document.body;
            var ua = navigator.userAgent || "";
            var platform = navigator.platform || "";
            var isIOS = /iPad|iPhone|iPod/.test(ua) ||
                (platform === "MacIntel" && navigator.maxTouchPoints > 1);
            var isMobileLike = isIOS || /Android|Mobi|Tablet|IEMobile|Opera Mini/i.test(ua) ||
                (navigator.maxTouchPoints && navigator.maxTouchPoints > 1 && Math.min(window.innerWidth, window.innerHeight) < 900);
            var hasRequestFullscreen = !!(
                el &&
                (typeof el.requestFullscreen === "function" || typeof el.webkitRequestFullscreen === "function")
            );
            var fullscreenEnabled = true;
            if (typeof document.fullscreenEnabled === "boolean") {
                fullscreenEnabled = document.fullscreenEnabled;
            } else if (typeof document.webkitFullscreenEnabled === "boolean") {
                fullscreenEnabled = document.webkitFullscreenEnabled;
            }

            return {
                fullscreen_supported: !!(hasRequestFullscreen && fullscreenEnabled),
                has_request_fullscreen: hasRequestFullscreen,
                fullscreen_enabled: fullscreenEnabled,
                is_ios: !!isIOS,
                is_mobile: !!isMobileLike,
                user_agent: ua
            };
        },

        _applyCapabilityFallbacks: function () {
            if (this.config.force_fullscreen && !(this.capabilities && this.capabilities.fullscreen_supported)) {
                this.config.force_fullscreen = false;
                this._fullscreenDisabledByCapability = true;
                if (this.capabilities) {
                    this.capabilities.fullscreen_disabled_reason = "unsupported";
                }
            }
        },

        _disableFullscreenForSession: function (reason) {
            this.config.force_fullscreen = false;
            this._fullscreenDisabledByCapability = true;
            if (this.capabilities) {
                this.capabilities.fullscreen_supported = false;
                this.capabilities.fullscreen_disabled_reason = reason || "request_failed";
            }
        },

        _isFullscreenActive: function () {
            return !!(
                document.fullscreenElement ||
                document.webkitFullscreenElement
            );
        },

        _publicConfig: function (config) {
            return {
                force_fullscreen: !!config.force_fullscreen,
                detect_tab_switch: !!config.detect_tab_switch,
                block_copy_paste: !!config.block_copy_paste,
                disable_right_click: !!config.disable_right_click,
                disable_text_selection: !!config.disable_text_selection,
                restrict_keyboard_shortcuts: !!config.restrict_keyboard_shortcuts
            };
        },
};

export default ExamSupervision;
