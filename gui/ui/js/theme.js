/* AXIS OS — Theme System (Dark / Light toggle) */
(function () {
  'use strict';

  var THEME_KEY = 'axis_theme';

  var DARK_VARS = {
    '--bg':      '#08090f',
    '--bg2':     '#0d0f1b',
    '--bg3':     '#131629',
    '--card':    '#0f1120',
    '--border':  '#1e2235',
    '--text':    '#f1f5f9',
    '--text2':   '#94a3b8',
    '--text3':   '#475569',
  };

  var LIGHT_VARS = {
    '--bg':      '#f6f8fa',
    '--bg2':     '#ffffff',
    '--bg3':     '#f0f2f5',
    '--card':    '#ffffff',
    '--border':  '#d0d7de',
    '--text':    '#24292f',
    '--text2':   '#57606a',
    '--text3':   '#8c959f',
  };

  var _current = 'dark';

  function _applyTheme(theme) {
    _current = theme;
    var vars = theme === 'light' ? LIGHT_VARS : DARK_VARS;
    var root = document.documentElement;
    Object.keys(vars).forEach(function (k) {
      root.style.setProperty(k, vars[k]);
    });

    // color-scheme for native controls
    document.documentElement.style.colorScheme = theme;
    document.body.style.colorScheme = theme;

    // Update toggle button icon
    var btn = document.getElementById('themeToggleBtn');
    if (btn) btn.textContent = theme === 'light' ? '☀️' : '🌙';

    // Save to localStorage
    try { localStorage.setItem(THEME_KEY, theme); } catch(e){}

    // Save to Python config
    try { pyCall('save_config', JSON.stringify({ theme: theme })); } catch(e){}
  }

  window.toggleTheme = function () {
    _applyTheme(_current === 'dark' ? 'light' : 'dark');
  };

  // Load from localStorage on startup (before Python config arrives)
  (function _init() {
    var VALID_THEMES = ['dark', 'light', 'midnight', 'ocean', 'forest', 'sunset'];
    var saved = 'dark';
    try {
      var savedTheme = localStorage.getItem(THEME_KEY);
      if (savedTheme && !VALID_THEMES.includes(savedTheme)) {
        console.warn('[AXIS] Invalid theme in localStorage:', savedTheme, '— resetting to dark');
        savedTheme = 'dark';
        localStorage.setItem(THEME_KEY, 'dark');
      }
      saved = savedTheme || 'dark';
    } catch(e){}
    _applyTheme(saved);
  })();

})();
