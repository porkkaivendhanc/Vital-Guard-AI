/* ═══════════════════════════════════════
   Portfolio – Minimal JavaScript
   ═══════════════════════════════════════ */

(function () {
  'use strict';

  // ── Scroll‑reveal ──
  const revealEls = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  revealEls.forEach((el) => observer.observe(el));

  // ── Mobile nav toggle ──
  const toggle = document.getElementById('navToggle');
  const links = document.getElementById('navLinks');
  toggle.addEventListener('click', () => {
    links.classList.toggle('open');
  });
  // Close mobile nav on link click
  links.querySelectorAll('a').forEach((a) => {
    a.addEventListener('click', () => links.classList.remove('open'));
  });

  // ── Active link highlight on scroll ──
  const sections = document.querySelectorAll('section[id]');
  const navAnchors = document.querySelectorAll('.nav-links a');
  window.addEventListener(
    'scroll',
    () => {
      const scrollY = window.scrollY + 120;
      sections.forEach((sec) => {
        const top = sec.offsetTop;
        const height = sec.offsetHeight;
        const id = sec.getAttribute('id');
        if (scrollY >= top && scrollY < top + height) {
          navAnchors.forEach((a) => {
            a.classList.remove('active');
            if (a.getAttribute('href') === '#' + id) a.classList.add('active');
          });
        }
      });
    },
    { passive: true }
  );
})();
