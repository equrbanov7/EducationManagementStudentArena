import { ExamSupervision } from "./state.js?v=20260716-intervention";

Object.assign(ExamSupervision, {
        /* ---------- WebSocket for real-time teacher actions ---------- */

        _wsSocket: null,
        _wsReconnectTimer: null,
        _wsReconnectDelay: 2000,

        _connectWebSocket: function () {
            if (!this.attemptId) return;
            var self = this;
            var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            var url = protocol + "//" + window.location.host + "/ws/exams/supervision/" + this.attemptId + "/";

            try {
                this._wsSocket = new WebSocket(url);
            } catch (e) {
                return;
            }

            this._wsSocket.onmessage = function (event) {
                try {
                    var data = JSON.parse(event.data);
                    self._handleWsEvent(data);
                } catch (e) {}
            };

            this._wsSocket.onclose = function () {
                self._wsSocket = null;
                // Reconnect after delay unless destroyed
                if (self._initialized) {
                    self._wsReconnectTimer = setTimeout(function () {
                        self._connectWebSocket();
                    }, self._wsReconnectDelay);
                }
            };

            this._wsSocket.onerror = function () {
                // Will trigger onclose
            };
        },

        _closeWebSocket: function () {
            if (this._wsReconnectTimer) {
                clearTimeout(this._wsReconnectTimer);
                this._wsReconnectTimer = null;
            }
            if (this._wsSocket) {
                this._wsSocket.onclose = null;
                this._wsSocket.close();
                this._wsSocket = null;
            }
        },

        _handleWsEvent: function (data) {
            if (!data || !data.action) return;

            if (data.action === "locked") {
                // Teacher temporarily blocked the student's screen. A manual
                // teacher pause shows a distinct "your teacher paused you"
                // overlay (no auto-finish countdown); an auto-lock keeps the
                // violation-limit flow.
                if (data.manual) {
                    this._showTeacherLockOverlay(data.reason);
                } else {
                    this._onLimitExceeded();
                }
            } else if (data.action === "stopped") {
                // Səbəbi tələbəyə göstər, sonra nəticəyə keçidi onun ixtiyarına ver.
                this._showRemovalOverlay(data.reason, data.intervention_action);
            } else if (data.action === "resumed") {
                // Teacher resumed the student
                if (this._lockCountdownTimer) {
                    clearInterval(this._lockCountdownTimer);
                    this._lockCountdownTimer = null;
                }
                var overlay = document.getElementById("supervision-locked-overlay");
                if (overlay) overlay.remove();
                var teacherLockOverlay = document.getElementById("supervision-teacher-lock-overlay");
                if (teacherLockOverlay) teacherLockOverlay.remove();
                this.isActive = true;
                if (data.violation_count !== undefined) {
                    this.violationCount = data.violation_count;
                }
                if (data.max_violations !== undefined) {
                    this.maxViolations = data.max_violations;
                }
                this._updateBadge();
                this._showResumeFullscreenOverlay(null);
            } else if (data.action === "session_revoked") {
                this._closeWebSocket();
                window.location.replace("/exams/final/");
            }
        },
});
