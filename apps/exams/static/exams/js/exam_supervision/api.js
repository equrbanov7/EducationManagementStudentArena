import { ExamSupervision } from "./state.js?v=20260914-w4r3";

Object.assign(ExamSupervision, {
        // W4 2026-09-14 (w3sweep R3): status sorğusu ETag daşıyır — dəyişməyibsə
        // server 304 qaytarır və son yük təkrar istifadə olunur; 429 gələndə
        // Retry-After qədər bütün pollerlər susur. `onDone` cavabdan (uğur və ya
        // xəta) SONRA çağırılır ki, növbəti sorğu üst-üstə düşməsin.
        _statusEtag: "",
        _statusLastData: null,
        _checkSupervisionStatus: function (callback, onDone) {
            var finish = function () {
                if (onDone) onDone();
            };
            if (!this.statusEndpoint) {
                finish();
                return;
            }
            var self = this;
            var headers = { "X-Requested-With": "XMLHttpRequest" };
            if (this._statusEtag) headers["If-None-Match"] = this._statusEtag;
            fetch(this.statusEndpoint, {
                method: "GET",
                cache: "no-store",
                headers: headers,
            })
                .then(function (r) {
                    if (r.status === 304) {
                        return self._statusLastData;
                    }
                    if (r.status === 429) {
                        if (self._noteStatusRetryAfter) {
                            self._noteStatusRetryAfter(r.headers.get("Retry-After"));
                        }
                        return null;
                    }
                    var etag = r.headers.get("ETag") || "";
                    return r.json().then(function (data) {
                        if (r.ok && etag) {
                            self._statusEtag = etag;
                            self._statusLastData = data;
                        }
                        return data;
                    });
                })
                .then(function (data) {
                    if (data && data.entry_session_valid === false) {
                        ExamSupervision.destroy();
                        window.location.replace(data.redirect_url || "/exams/final/");
                        return;
                    }
                    if (callback) callback(data);
                })
                .catch(function () {})
                .then(finish, finish);
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
                                ExamSupervision._showTeacherLockOverlay(data.intervention_reason);
                            } else {
                                ExamSupervision._onLimitExceeded();
                            }
                        } else if (data.is_trial && data.limit_exceeded) {
                            // Sınaqda kilid yoxdur — yalnız məlumat xarakterli xəbərdarlıq.
                            ExamSupervision._showTrialViolationNotice();
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
            if (this._stopLockStatusPolling) this._stopLockStatusPolling();
            if (this._stopBackgroundStatusWatch) this._stopBackgroundStatusWatch();
            this._closeWebSocket();
        },
});
