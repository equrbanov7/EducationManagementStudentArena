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

    /* 2026-09-30 (sahib: «menyu açıqkən içində sürüşdürəndə arxa səhifə də
       sürüşür»). Əvvəl yalnız `body.style.overflow` bağlanırdı — `html`-in öz
       `overflow-x`-i olduğu üçün təsirsiz idi. İndi ortaq `EMSScrollLock`
       (modal_scroll_lock.js): html+body kilidi, iOS touchmove qoruyucusu,
       bağlananda scroll mövqeyinin dəqiq bərpası. Şkafın öz sürüşməsi qalır. */
    var LOCK_KEY = 'mobile-nav';

    function setPageLock(on) {
        if (window.EMSScrollLock) {
            window.EMSScrollLock.set(LOCK_KEY, on, mobileNavPanel);
        }
    }

    function isOpen() {
        return mobileNavPanel.classList.contains('is-open');
    }

    function openMobileNav() {
        // Başlığın açılan menyuları (istifadəçi, dil) şkafın altında açıq qalmasın.
        document.dispatchEvent(new CustomEvent('ems:popover:open', { detail: { source: 'mobile-nav' } }));
        mobileNavPanel.classList.add('is-open');
        mobileNavOverlay.classList.add('is-open');
        navToggle.classList.add('is-open');
        navToggle.setAttribute('aria-expanded', 'true');
        setPageLock(true);
    }

    function closeMobileNav() {
        if (!isOpen()) {
            return;
        }
        mobileNavPanel.classList.remove('is-open');
        mobileNavOverlay.classList.remove('is-open');
        navToggle.classList.remove('is-open');
        navToggle.setAttribute('aria-expanded', 'false');
        body.style.overflow = '';
        setPageLock(false);
    }

    /* Ekran masaüstü ölçüsünə keçəndə (fırlatma, pəncərə genişlənməsi) şkaf CSS ilə
       gizlənir (`display: none`) — açıq qalsa səhifə görünməz şkafa kilidli qalardı. */
    var desktopQuery = window.matchMedia ? window.matchMedia('(min-width: 769px)') : null;
    function onBreakpoint(event) {
        if (event.matches) {
            closeMobileNav();
        }
    }
    if (desktopQuery) {
        if (typeof desktopQuery.addEventListener === 'function') {
            desktopQuery.addEventListener('change', onBreakpoint);
        } else if (typeof desktopQuery.addListener === 'function') {
            desktopQuery.addListener(onBreakpoint);
        }
    }

    // Panelin öz «×» düyməsi — delegasiya ilə (açar bu faylda təkdir).
    // `preventScroll`: toggle yapışqan başlıqdadır; adi `focus()` Chrome-da sənədi
    // ƏN BAŞA sürüşdürürdü — bağlananda istifadəçi oxuduğu yeri itirirdi.
    if (window.EMSDelegate) {
        window.EMSDelegate.on('click', '[data-mobile-nav-close]', function () {
            closeMobileNav();
            navToggle.focus({ preventScroll: true });
        });
    }

    navToggle.addEventListener('click', function () {
        if (isOpen()) {
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
        if (event.key === 'Escape' && isOpen()) {
            closeMobileNav();
            navToggle.focus({ preventScroll: true });
        }
    });

    // bfcache-dən qayıdanda (iOS «geri») şkaf açıq qalıbsa kilidlə birlikdə bağla.
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
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

    /* ⚠️ 2026-09-11 (sahib: «header-ə klik edərək search və s. vururam —
       açılmır, ilişir»). Başlıqda ÜÇ ayrı açılan mexanizm var və bir-birini
       tanımırdı: dil menyusu Bootstrap dropdown-dur, istifadəçi/«Yarat»
       menyuları bu kontrollerdir, axtarış isə ayrıca örtükdür. Toggle-lar
       `stopPropagation()` çağırırdı — Bootstrap-ın sənəd səviyyəli bağlama
       dinləyicisi kliki heç görmürdü → dil menyusu AÇIQ qalırkən istifadəçi
       menyusu da açılırdı (ikisi üst-üstə), dil menyusu isə z-index 1200 ilə
       axtarış panelinin (1100) üstündə üzürdü. İndi qayda TƏKDİR: başlıqda
       eyni anda yalnız BİR açılan ola bilər. Hər mexanizm açılanda
       `ems:popover:open` hadisəsi yayır, digərləri onu eşidib bağlanır. */
    const POPOVER_EVENT = 'ems:popover:open';

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

    /* Bootstrap dil menyusu — açıqdırsa onun öz API-si ilə bağlanır. */
    function closeBootstrapDropdowns() {
        const api = window.bootstrap && window.bootstrap.Dropdown;
        document.querySelectorAll('.blog-header [data-bs-toggle="dropdown"]').forEach(function (toggle) {
            const instance = api ? api.getInstance(toggle) : null;
            if (instance && toggle.getAttribute('aria-expanded') === 'true') {
                instance.hide();
            }
        });
    }

    function announceOpen(source) {
        document.dispatchEvent(new CustomEvent(POPOVER_EVENT, { detail: { source: source } }));
    }

    dropdowns.forEach(function (d) {
        d.toggle.addEventListener('click', function () {
            // `stopPropagation` YOXDUR: klik sənədə çatır ki, Bootstrap dil
            // menyusunu bağlaya bilsin; özümüzü isə aşağıdakı sənəd
            // dinləyicisində `closest` ilə tanıyırıq.
            const isOpen = d.menu.classList.contains(d.openClass);
            closeAll(d);
            if (isOpen) {
                close(d);
                return;
            }
            closeBootstrapDropdowns();
            announceOpen('header-dropdown');
            d.menu.classList.add(d.openClass);
            d.toggle.setAttribute('aria-expanded', 'true');
        });
    });

    document.addEventListener('click', function (event) {
        const inside = dropdowns.some(function (d) {
            return d.toggle.contains(event.target) || d.menu.contains(event.target);
        });
        if (!inside) {
            closeAll(null);
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeAll(null);
        }
    });

    /* Başqa mexanizm (dil menyusu, axtarış) açılanda biz bağlanırıq. */
    document.addEventListener(POPOVER_EVENT, function (event) {
        if (!event.detail || event.detail.source !== 'header-dropdown') {
            closeAll(null);
        }
    });
    document.addEventListener('show.bs.dropdown', function (event) {
        if (event.target && event.target.closest && event.target.closest('.blog-header')) {
            closeAll(null);
            announceOpen('bootstrap-dropdown');
        }
    });
}
