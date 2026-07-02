import { ExamSupervision } from "./state.js?v=20260611-fresh-csrf";

Object.assign(ExamSupervision, {
        _checkSupervisionStatus: function (callback) {
            if (!this.statusEndpoint) return;
            fetch(this.statusEndpoint, {
                method: "GET",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (data) {
                    if (callback) callback(data);
                })
                .catch(function () {});
        },

        // Tokeni hər sorğuda cookie-dən təzə oxu: uzun imtahanda token
        // rotasiya olunarsa init-də verilmiş statik token 403 verir.
        _freshCsrfToken: function () {
            var row = document.cookie.split("; ").find(function (c) {
                return c.indexOf("csrftoken=") === 0;
            });
            if (row) {
                return decodeURIComponent(row.split("=").slice(1).join("="));
            }
            return this.csrfToken;
        },

        _logEvent: function (eventType, metadata) {
            if (!this.logEndpoint) return;
            fetch(this.logEndpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": this._freshCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({
                    event_type: eventType,
                    metadata: metadata || {},
                }),
            })
                .then(function (r) {
                    return r.json();
                })
                .then(
                    function (data) {
                        if (data.supervision_status === "locked" || data.supervision_status === "removed") {
                            if (data.manual_lock) {
                                ExamSupervision._showTeacherLockOverlay();
                            } else {
                                ExamSupervision._onLimitExceeded();
                            }
                        }
                        if (data.violation_count !== undefined) {
                            ExamSupervision.violationCount = data.violation_count;
                            ExamSupervision.maxViolations = data.max_violations || ExamSupervision.maxViolations;
                            ExamSupervision._updateBadge();
                        }
                    }
                )
                .catch(function () {});
        },

        destroy: function () {
            this.isActive = false;
            this._clearGraceTimer();
            if (this._resumeCountdownTimer) {
                clearInterval(this._resumeCountdownTimer);
                this._resumeCountdownTimer = null;
            }
            if (this._lockCountdownTimer) {
                clearInterval(this._lockCountdownTimer);
                this._lockCountdownTimer = null;
            }
            if (this._teacherLockPoll) {
                clearInterval(this._teacherLockPoll);
                this._teacherLockPoll = null;
            }
            if (this._bgStatusWatch) {
                clearInterval(this._bgStatusWatch);
                this._bgStatusWatch = null;
            }
            this._closeWebSocket();
        },
});
