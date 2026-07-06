/**
 * Toggle visibility for password/code fields.
 */
document.addEventListener("DOMContentLoaded", function () {
    var toggleButtons = document.querySelectorAll("[data-toggle-visibility]");

    function applyIcon(button, isVisible) {
        if (!button) return;
        // Inline SVG variant (lightweight auth pages without FontAwesome):
        // CSS shows .visibility-icon-show / .visibility-icon-hide based on
        // the button's data-visible attribute.
        button.setAttribute("data-visible", isVisible ? "true" : "false");
        // FontAwesome variant (pages that still load FA):
        // Parol GİZLİ → xətli göz (fa-eye-slash); GÖRÜNƏN → adi göz (fa-eye).
        var icon = button.querySelector("i");
        if (!icon) return;
        icon.classList.toggle("fa-eye", isVisible);
        icon.classList.toggle("fa-eye-slash", !isVisible);
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
