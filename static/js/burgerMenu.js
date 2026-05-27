document.addEventListener('DOMContentLoaded', function () {
    initMobileNav();
    initUserMenu();
    initStickyNavScrollState();
});

/**
 * Add `blog-header--scrolled` modifier once the user has scrolled past the top
 * of the page so the sticky navbar can gain a deeper shadow / heavier opacity.
 * Uses a passive scroll listener with rAF throttling to stay cheap.
 */
function initStickyNavScrollState() {
    const header = document.querySelector('.blog-header');
    if (!header) return;

    const THRESHOLD = 8;
    let ticking = false;

    function update() {
        const scrolled = window.scrollY > THRESHOLD;
        header.classList.toggle('blog-header--scrolled', scrolled);
        ticking = false;
    }

    window.addEventListener('scroll', function () {
        if (!ticking) {
            window.requestAnimationFrame(update);
            ticking = true;
        }
    }, { passive: true });

    update();
}

function initMobileNav() {
    const navToggle = document.querySelector('.blog-header__toggle');
    const mobileNavPanel = document.querySelector('.mobile-nav-panel');
    const mobileNavOverlay = document.querySelector('.mobile-nav-overlay');
    const body = document.body;

    if (!navToggle || !mobileNavPanel || !mobileNavOverlay) {
        return;
    }

    function openMobileNav() {
        mobileNavPanel.classList.add('is-open');
        mobileNavOverlay.classList.add('is-open');
        navToggle.classList.add('is-open');
        body.style.overflow = 'hidden';
    }

    function closeMobileNav() {
        mobileNavPanel.classList.remove('is-open');
        mobileNavOverlay.classList.remove('is-open');
        navToggle.classList.remove('is-open');
        body.style.overflow = '';
    }

    navToggle.addEventListener('click', function () {
        if (mobileNavPanel.classList.contains('is-open')) {
            closeMobileNav();
            return;
        }
        openMobileNav();
    });

    mobileNavOverlay.addEventListener('click', closeMobileNav);

    mobileNavPanel.querySelectorAll('.blog-header__nav-link').forEach(function (link) {
        link.addEventListener('click', closeMobileNav);
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && mobileNavPanel.classList.contains('is-open')) {
            closeMobileNav();
        }
    });
}

function initUserMenu() {
    const userToggle = document.querySelector('.blog-header__user-toggle');
    const userMenu = document.querySelector('.blog-header__user-menu');

    if (!userToggle || !userMenu) {
        return;
    }

    userToggle.addEventListener('click', function (event) {
        event.stopPropagation();
        const isOpen = userMenu.classList.contains('blog-header__user-menu--open');
        if (isOpen) {
            userMenu.classList.remove('blog-header__user-menu--open');
            userToggle.setAttribute('aria-expanded', 'false');
            return;
        }
        userMenu.classList.add('blog-header__user-menu--open');
        userToggle.setAttribute('aria-expanded', 'true');
    });

    document.addEventListener('click', function () {
        if (userMenu.classList.contains('blog-header__user-menu--open')) {
            userMenu.classList.remove('blog-header__user-menu--open');
            userToggle.setAttribute('aria-expanded', 'false');
        }
    });
}
