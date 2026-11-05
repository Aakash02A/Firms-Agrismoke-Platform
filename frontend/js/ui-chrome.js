/**
 * AgriSmoke AI - UI Chrome & PWA Bootstrap
 * Layout-only behavior extracted from index.html's inline <script> blocks.
 *
 * Why external: the production CSP is `script-src 'self'` (see backend/main.py),
 * which blocks ALL inline scripts. Previously the sidebar toggle/breadcrumb sync
 * and the Service Worker registration were inline, so on the live (Render/nginx)
 * host they were silently blocked — the toggle did nothing and the PWA never
 * installed. Serving them as a same-origin file makes them execute while keeping
 * the strict CSP in place. This file must NOT rely on any inline handler either.
 */
(function () {
    'use strict';

    function init() {
        // ---- Sidebar toggle: desktop icon-rail collapse vs mobile drawer ----
        // Below 640px the sidebar is an off-canvas overlay (see styles.css
        // @media 640px) driven by the .nav-open class; on wider screens the
        // same button collapses it to the 78px icon rail via .collapsed.
        var shell = document.getElementById('app-shell');
        var toggleBtn = document.getElementById('sidebar-toggle');
        var overlay = document.getElementById('nav-overlay');
        var mobileQuery = window.matchMedia('(max-width: 640px)');

        function isMobile() { return mobileQuery.matches; }

        function closeDrawer() {
            if (shell) shell.classList.remove('nav-open');
            if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
        }

        // Leaving the mobile range must drop drawer state so a stale .nav-open
        // never interferes with the desktop layout.
        function syncMode() { if (!isMobile()) closeDrawer(); }

        if (shell && toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', 'false');
            toggleBtn.addEventListener('click', function () {
                if (isMobile()) {
                    var open = shell.classList.toggle('nav-open');
                    toggleBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
                } else {
                    shell.classList.toggle('collapsed');
                }
                // Let the map recompute its canvas size after the width transition
                setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 240);
            });
        }

        if (overlay) overlay.addEventListener('click', closeDrawer);

        var crumb = document.getElementById('crumb-section');
        document.querySelectorAll('.nav-tab-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (crumb) {
                    var t = btn.querySelector('.nav-txt');
                    crumb.textContent = t ? t.textContent : btn.textContent;
                }
                // On mobile, dismiss the drawer so the chosen panel is visible.
                if (isMobile()) closeDrawer();
            });
        });

        if (mobileQuery.addEventListener) {
            mobileQuery.addEventListener('change', syncMode);
        } else if (mobileQuery.addListener) {
            mobileQuery.addListener(syncMode);  // older Safari
        }

        // ---- Service Worker registration (PWA / offline) ----
        if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
            window.addEventListener('load', function () {
                navigator.serviceWorker.register('service-worker.js')
                    .then(function (reg) { console.log('[PWA] Service Worker registered:', reg.scope); })
                    .catch(function (err) { console.log('[PWA] Service Worker registration skipped:', err); });
            });
        }
    }

    // The script tag sits at the end of <body>, so the DOM is already parsed;
    // still guard for the case where it is loaded with defer in <head>.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
