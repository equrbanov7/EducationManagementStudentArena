// static/js/main.js (və ya navbar.js)
document.addEventListener('DOMContentLoaded', function () {
    const navToggle = document.querySelector('.blog-header__toggle');
    const mobileNavPanel = document.querySelector('.mobile-nav-panel'); // Partial faylın içindəki mobil menyu paneli
    const mobileNavOverlay = document.querySelector('.mobile-nav-overlay'); // Partial faylın içindəki overlay
    const body = document.body; // Body elementinə overflow gizlətmək üçün

    // Elementlərin olub-olmadığını yoxlayırıq
    if (!navToggle || !mobileNavPanel || !mobileNavOverlay) {
        console.warn("Burger menyu elementləri tapılmadı. JS işləməyəcək.");
        return;
    }

    function openMobileNav() {
        mobileNavPanel.classList.add('is-open');
        mobileNavOverlay.classList.add('is-open');
        navToggle.classList.add('is-open');
        body.style.overflow = 'hidden'; // Scrollu bağlayır
    }

    function closeMobileNav() {
        mobileNavPanel.classList.remove('is-open');
        mobileNavOverlay.classList.remove('is-open');
        navToggle.classList.remove('is-open');
        body.style.overflow = ''; // Scrollu geri qaytarır
    }

    // Burger düyməsinə klikləmə
    navToggle.addEventListener('click', () => {
        if (mobileNavPanel.classList.contains('is-open')) {
            closeMobileNav();
        } else {
            openMobileNav();
        }
    });

    // Overlay-ə klikləmə (kənara basdıqda bağlamaq üçün)
    mobileNavOverlay.addEventListener('click', () => {
        closeMobileNav();
    });

    // Menyu daxilindəki linklərə klikləmə (naviqasiyadan sonra bağlamaq üçün)
    mobileNavPanel.querySelectorAll('.blog-header__nav-link').forEach(link => {
        link.addEventListener('click', (event) => {
            closeMobileNav();
        });
    });

    // Klaviaturada 'Escape' düyməsinə basdıqda bağlamaq (yaxşı UX üçün)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && mobileNavPanel.classList.contains('is-open')) {
            closeMobileNav();
        }
    });

    const userToggle = document.querySelector('.blog-header__user-toggle');
    const userMenu = document.querySelector('.blog-header__user-menu');

    if (userToggle && userMenu) {
        // Aç / bağla
        userToggle.addEventListener('click', function (e) {
            e.stopPropagation(); // body click eventinə düşməsin
            const isOpen = userMenu.classList.contains('blog-header__user-menu--open');
            if (isOpen) {
                userMenu.classList.remove('blog-header__user-menu--open');
                userToggle.setAttribute('aria-expanded', 'false');
            } else {
                userMenu.classList.add('blog-header__user-menu--open');
                userToggle.setAttribute('aria-expanded', 'true');
            }
        });

        // Çöldə klik edəndə bağla
        document.addEventListener('click', function () {
            if (userMenu.classList.contains('blog-header__user-menu--open')) {
                userMenu.classList.remove('blog-header__user-menu--open');
                userToggle.setAttribute('aria-expanded', 'false');
            }
        });
    }
});