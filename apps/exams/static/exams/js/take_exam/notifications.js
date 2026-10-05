(function (ns, document) {
    "use strict";

    // Görünüş `take_exam/ux.css`-dədir (.auto-save-notification[.success|.error|.info]):
    // əvvəl hər bildiriş inline cssText ilə sağ-yuxarıya yapışırdı və telefonda
    // taymeri örtürdü; indi telefonda aşağıdan çıxır.
    ns.notifications = {
        show: function (message, type, duration) {
            var notification = document.createElement("div");
            var level = type || "info";
            notification.className = "auto-save-notification " + level;
            notification.setAttribute("role", level === "error" ? "alert" : "status");
            notification.textContent = message;

            document.body.appendChild(notification);

            if (duration > 0) {
                setTimeout(function () {
                    ns.notifications.hide(notification);
                }, duration);
            }

            return notification;
        },

        hide: function (notification) {
            if (notification && notification.parentNode) {
                notification.classList.add("is-hiding");
                setTimeout(function () {
                    if (notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                    }
                }, 300);
            }
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, document);
