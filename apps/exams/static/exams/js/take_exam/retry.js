(function (ns) {
    "use strict";
    ns.retry = {
        remaining: function (ctx) {
            return Math.max(0, (ctx.saveRetryUntil || 0) - Date.now());
        },
        noteResponse: function (ctx, response) {
            if (response.ok) {
                ctx.saveRetryUntil = 0;
                ctx.saveRetryCount = 0;
                if (ns.syncStatus) ns.syncStatus.recovered(ctx);
                return;
            }
            if (response.status !== 429 && response.status !== 503) return;
            // Daimi göstərici: autosave səssizdir, yoxsa tələbə cavabların hələ serverdə olmadığını bilmir.
            if (ns.syncStatus) ns.syncStatus.show(ctx, "busy");
            ctx.saveRetryCount = Math.min(6, (ctx.saveRetryCount || 0) + 1);
            var raw = response.headers.get("Retry-After");
            var seconds = raw && /^\d+(\.\d+)?$/.test(raw.trim()) ? Number(raw) : NaN;
            var delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(raw) - Date.now();
            if (!Number.isFinite(delay) || delay <= 0) {
                delay = Math.min(30000, 1000 * Math.pow(2, ctx.saveRetryCount));
            }
            // Cap server hints (and client clock skew on HTTP dates) so answers
            // never stay browser-only for long.
            delay = Math.min(delay, 60000);
            // Spread retries after the server's minimum wait, never before it.
            ctx.saveRetryUntil = Math.max(ctx.saveRetryUntil || 0, Date.now() + delay + Math.random() * 1000);
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {});
