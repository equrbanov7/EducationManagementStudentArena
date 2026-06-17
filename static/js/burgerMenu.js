document.addEventListener('DOMContentLoaded', function () {
    initMobileNav();
    initHeaderDropdowns();
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

/**
 * Generic toggle handling for the header's click-to-open dropdowns
 * (user menu + "Yarat" quick-create). One open at a time; closes on
 * outside-click and Escape. Kept dependency-free and idempotent.
 */
function initHeaderDropdowns() {
    const configs = [
        {
            toggle: '.blog-header__user-toggle',
            menu: '.blog-header__user-menu',
            openClass: 'blog-header__user-menu--open',
        },
        {
            toggle: '.blog-header__create-toggle',
            menu: '.blog-header__create-menu',
            openClass: 'blog-header__create-menu--open',
        },
    ];

    const dropdowns = configs
        .map(function (cfg) {
            return {
                toggle: document.querySelector(cfg.toggle),
                menu: document.querySelector(cfg.menu),
                openClass: cfg.openClass,
            };
        })
        .filter(function (d) { return d.toggle && d.menu; });

    if (!dropdowns.length) {
        return;
    }

    function close(d) {
        if (d.menu.classList.contains(d.openClass)) {
            d.menu.classList.remove(d.openClass);
            d.toggle.setAttribute('aria-expanded', 'false');
        }
    }

    function closeAll(except) {
        dropdowns.forEach(function (d) {
            if (d !== except) {
                close(d);
            }
        });
    }

    dropdowns.forEach(function (d) {
        d.toggle.addEventListener('click', function (event) {
            event.stopPropagation();
            const isOpen = d.menu.classList.contains(d.openClass);
            closeAll(d);
            if (isOpen) {
                close(d);
            } else {
                d.menu.classList.add(d.openClass);
                d.toggle.setAttribute('aria-expanded', 'true');
            }
        });

        // Keep the menu open when interacting inside it; links/forms still work.
        d.menu.addEventListener('click', function (event) {
            event.stopPropagation();
        });
    });

    document.addEventListener('click', function () { closeAll(null); });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeAll(null);
        }
    });
}
