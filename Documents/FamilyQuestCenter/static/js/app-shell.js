/**
 * Family Quest Center Developer Notes
 * File: static/js/app-shell.js
 * Purpose: Provides client-side behavior for app shell interfaces.
 * Maintenance: Preserve progressive enhancement and avoid exposing sensitive data client-side.
 * Documentation updated: 2026-07-31
 */

(() => {
    const menuButton = document.querySelector('.mobile-menu-button');
    const navigation = document.querySelector('.app-navigation');

    if (menuButton && navigation) {
        menuButton.addEventListener('click', () => {
            const isOpen = navigation.classList.toggle('is-open');
            menuButton.setAttribute('aria-expanded', String(isOpen));

            // Always open at the first navigation item. Browsers can preserve a
            // prior scroll position when a long menu is hidden and reopened.
            if (isOpen) {
                navigation.scrollTop = 0;
            }
        });

        navigation.querySelectorAll('a, button').forEach((item) => {
            item.addEventListener('click', () => {
                navigation.classList.remove('is-open');
                menuButton.setAttribute('aria-expanded', 'false');
            });
        });
    }

    document.querySelectorAll('.toast-close').forEach((button) => {
        button.addEventListener('click', () => {
            const toast = button.closest('.toast');
            if (toast) toast.remove();
        });
    });

    window.setTimeout(() => {
        document.querySelectorAll('.toast').forEach((toast) => {
            toast.classList.add('toast-hiding');
            window.setTimeout(() => toast.remove(), 250);
        });
    }, 6500);

    // Mark the closest matching application navigation link as current.
    const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
    const navLinks = Array.from(document.querySelectorAll('.app-navigation a[href]'));
    const matchingLinks = navLinks.filter((link) => {
        try {
            const path = new URL(link.href, window.location.origin).pathname.replace(/\/$/, '') || '/';
            return path === currentPath;
        } catch (_) {
            return false;
        }
    });
    matchingLinks.at(-1)?.setAttribute('aria-current', 'page');

    document.querySelectorAll('[data-search-target]').forEach((input) => {
        const targetSelector = input.dataset.searchTarget;
        input.addEventListener('input', () => {
            const term = input.value.trim().toLowerCase();
            document.querySelectorAll(targetSelector).forEach((item) => {
                item.hidden = term !== '' && !item.textContent.toLowerCase().includes(term);
            });
        });
    });

    // Prevent accidental double submissions and give immediate feedback.
    document.querySelectorAll('form').forEach((form) => {
        form.addEventListener('submit', () => {
            const submit = form.querySelector('button[type="submit"], input[type="submit"]');
            if (!submit || submit.dataset.keepEnabled === 'true') return;
            submit.setAttribute('aria-busy', 'true');
            if (submit.tagName === 'BUTTON' && !submit.dataset.originalText) {
                submit.dataset.originalText = submit.textContent;
                submit.textContent = 'Working…';
            }
            window.setTimeout(() => {
                submit.disabled = true;
            }, 0);
        });
    });

    // Close the mobile menu with Escape.
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && navigation?.classList.contains('is-open')) {
            navigation.classList.remove('is-open');
            menuButton?.setAttribute('aria-expanded', 'false');
            menuButton?.focus();
        }
    });

})();
