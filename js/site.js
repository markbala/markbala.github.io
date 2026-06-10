/* Mark Balakrishnan — site interactions */
(function () {
  'use strict';

  /* ---- Theme + accent + typeface (shared with Tweaks panel) ---- */
  var ACCENTS = {
    racing:    '#0B4228',   /* British racing green */
    vermilion: '#B23A1E',
    cobalt:    '#1F3A6B',
    plum:      '#5B2A4E'
  };

  function applyTheme(theme) {
    if (theme === 'carbon') document.documentElement.setAttribute('data-theme', 'carbon');
    else document.documentElement.removeAttribute('data-theme');
  }
  function applyAccent(accent) {
    var hex = ACCENTS[accent] || accent || ACCENTS.racing;
    document.documentElement.style.setProperty('--accent-base', hex);
  }
  function applyType(t) {
    if (t && t !== 'a') document.documentElement.setAttribute('data-type', t);
    else document.documentElement.removeAttribute('data-type');
  }

  function readPrefs() {
    var theme = 'paper', accent = '#0B4228', type = 'a';
    try {
      theme  = localStorage.getItem('mb-theme')  || theme;
      accent = localStorage.getItem('mb-accent') || accent;
      type   = localStorage.getItem('mb-type')   || type;
    } catch (e) {}
    return { theme: theme, accent: accent, type: type };
  }

  // expose for the tweaks panel
  window.MB = {
    accents: ACCENTS,
    setTheme: function (t) { applyTheme(t); try { localStorage.setItem('mb-theme', t); } catch (e) {} },
    setAccent: function (a) { applyAccent(a); try { localStorage.setItem('mb-accent', a); } catch (e) {} },
    setType: function (t) { applyType(t); try { localStorage.setItem('mb-type', t); } catch (e) {} },
    get: readPrefs
  };

  var p = readPrefs();
  applyTheme(p.theme);
  applyAccent(p.accent);
  applyType(p.type);

  /* ---- Scroll reveal (rect-based; robust everywhere) ---- */
  function initReveal() {
    var els = [].slice.call(document.querySelectorAll('.reveal'));
    if (!els.length) return;

    function reveal(el) {
      if (el.classList.contains('in')) return;
      var d = el.getAttribute('data-delay');
      if (d) el.style.transitionDelay = d + 'ms';
      el.classList.add('in');
    }
    function check() {
      var vh = window.innerHeight || document.documentElement.clientHeight;
      var pending = false;
      els.forEach(function (el) {
        if (el.classList.contains('in')) return;
        var top = el.getBoundingClientRect().top;
        if (top < vh * 0.92) reveal(el);
        else pending = true;
      });
      if (!pending) window.removeEventListener('scroll', onScroll);
    }
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(function () { check(); ticking = false; });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    check();
    // ultimate safety net: never leave content hidden
    setTimeout(function () { els.forEach(reveal); }, 2500);
  }

  /* ---- Smooth anchor scroll ---- */
  function initAnchors() {
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var id = a.getAttribute('href');
        if (id.length < 2) return;
        var t = document.querySelector(id);
        if (!t) return;
        e.preventDefault();
        var y = t.getBoundingClientRect().top + window.pageYOffset - 64;
        window.scrollTo({ top: y, behavior: 'smooth' });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initReveal(); initAnchors(); });
  } else { initReveal(); initAnchors(); }
})();
