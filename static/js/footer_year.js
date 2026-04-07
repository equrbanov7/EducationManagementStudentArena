document.addEventListener("DOMContentLoaded", function () {
    var yearNode = document.getElementById("footerCurrentYear");
    if (!yearNode) {
        return;
    }

    yearNode.textContent = String(new Date().getFullYear());
});
