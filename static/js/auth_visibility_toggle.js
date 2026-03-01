/**
 * Toggle visibility for password/code fields.
 */
document.addEventListener("DOMContentLoaded", function () {
    var toggleButtons = document.querySelectorAll("[data-toggle-visibility]");

    function applyIcon(button, isVisible) {
        var icon = button ? button.querySelector("i") : null;
        if (!icon) return;
        icon.classList.toggle("fa-eye", !isVisible);
        icon.classList.toggle("fa-eye-slash", isVisible);
    }

    toggleButtons.forEach(function (button) {
        var targetId = button.getAttribute("data-target");
        if (!targetId) return;
        var input = document.getElementById(targetId);
        if (!input) return;

        button.addEventListener("click", function () {
            var isHidden = input.type === "password";
            input.type = isHidden ? "text" : "password";
            applyIcon(button, isHidden);
            input.focus();
        });
    });
});
