(function (ns, document) {
    "use strict";

    ns.notifications = {
        show: function (message, type, duration) {
            var notification = document.createElement("div");
            var level = type || "info";
            notification.className = "auto-save-notification " + level;
            notification.textContent = message;
            notification.style.cssText = [
                "position: fixed",
                "top: 20px",
                "right: 20px",
                "padding: 12px 20px",
                "border-radius: 8px",
                "font-size: 14px",
                "font-weight: 500",
                "z-index: 10000",
                "box-shadow: 0 4px 12px rgba(0,0,0,0.15)",
                "animation: slideIn 0.3s ease",
                "transition: opacity 0.3s ease"
            ].join(";");

            if (level === "success") {
                notification.style.backgroundColor = "#10b981";
                notification.style.color = "white";
            } else if (level === "error") {
                notification.style.backgroundColor = "#ef4444";
                notification.style.color = "white";
            } else {
                notification.style.backgroundColor = "#3b82f6";
                notification.style.color = "white";
            }

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
                notification.style.opacity = "0";
                setTimeout(function () {
                    if (notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                    }
                }, 300);
            }
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, document);
