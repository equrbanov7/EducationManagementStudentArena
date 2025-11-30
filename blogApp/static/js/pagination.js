// static/js/pagination.js

document.addEventListener('DOMContentLoaded', function () {
    // Səhifədə pagination varsa linkləri götür
    const paginationLinks = document.querySelectorAll('.pagination a');

    if (!paginationLinks.length) {
        return; // Heç bir pagination yoxdursa, heç nə etmə
    }

    paginationLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            // Yalnız normal sol klik olanda işlə (Ctrl+click, middle click və s. pozma)
            if (
                e.button !== 0 ||           // yalnız sol düymə
                e.metaKey ||                // Cmd (Mac)
                e.ctrlKey ||                // Ctrl
                e.shiftKey ||               // Shift
                e.altKey                    // Alt
            ) {
                return;
            }

            e.preventDefault();

            const targetUrl = this.href;

            // Əgər istifadəçi "reduced motion" istəyi qoyubsa, birbaşa keç
            const prefersReducedMotion = window.matchMedia &&
                window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            if (prefersReducedMotion) {
                window.location.href = targetUrl;
                return;
            }

            // Yuxarıya smooth scroll
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });

            // Kiçik gecikmədən sonra yeni səhifəyə keç
            // (scrollun bitməsi üçün ~300–500 ms kifayətdir)
            setTimeout(function () {
                window.location.href = targetUrl;
            }, 400);
        });
    });
});
