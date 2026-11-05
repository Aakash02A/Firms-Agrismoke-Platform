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
        // ---- Sidebar collapse toggle + breadcrumb label sync ----
        var shell = document.getElementById('app-shell');
        var toggleBtn = document.getElementById('sidebar-toggle');
        if (shell && toggleBtn) {
            toggleBtn.addEventListener('click', function () {
                shell.classList.toggle('collapsed');
                // Let the map recompute its canvas size after the width transition
                setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 240);
            });
        }

        var crumb = document.getElementById('crumb-section');
        document.querySelectorAll('.nav-tab-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (crumb) {
                    var t = btn.querySelector('.nav-txt');
                    crumb.textContent = t ? t.textContent : btn.textContent;
                }
            });
        });

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
