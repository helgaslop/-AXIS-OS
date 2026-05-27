/* AXIS OS — Quick Search (Ctrl+Space spotlight) */
// ═══════════════════════════════════════════════════

var _qsOpen = false;
var _qsResults = [];
var _qsSelected = -1;
var _qsDebounce = null;

// ── Built-in nav pages ───────────────────────────────────────────────────────
var _qsPages = [
  { icon: '⬡', label: 'Головна',         category: 'Сторінки', action: function(){ showPage('dashboard'); }},
  { icon: '📊', label: 'Монітор',         category: 'Сторінки', action: function(){ showPage('monitor'); }},
  { icon: '🤖', label: 'AI Агенти',       category: 'Сторінки', action: function(){ showPage('agents'); }},
  { icon: '💬', label: 'AI Чат',          category: 'Сторінки', action: function(){ showPage('chat'); }},
  { icon: '💻', label: 'AI Агенти / IDE', category: 'Сторінки', action: function(){ showPage('agents'); }},
  { icon: '✨', label: 'Генератор',       category: 'Сторінки', action: function(){ showPage('generator'); }},
  { icon: '🎵', label: 'Музика',          category: 'Сторінки', action: function(){ showPage('music'); }},
  { icon: '📋', label: 'Команди',         category: 'Сторінки', action: function(){ showPage('commands'); }},
  { icon: '⚡', label: 'Автоматизація',   category: 'Сторінки', action: function(){ showPage('macros'); }},
  { icon: '📝', label: 'Нотатки',         category: 'Сторінки', action: function(){ showPage('network'); }},
  { icon: '🔑', label: 'API Ключі',       category: 'Сторінки', action: function(){ showPage('api'); }},
  { icon: '⚙',  label: 'Налаштування',   category: 'Сторінки', action: function(){ showPage('settings'); }},
  { icon: '📋', label: 'Системні логи',   category: 'Сторінки', action: function(){ showPage('logs'); }},
];

// ── Open / Close ─────────────────────────────────────────────────────────────
function openQuickSearch() {
  var overlay = R('quickSearch');
  if (!overlay) return;
  _qsOpen = true;
  _qsSelected = -1;
  overlay.classList.add('qs-visible');
  var inp = R('qsInput');
  if (inp) { inp.value = ''; inp.focus(); }
  _qsShowDefaultResults();
}

function closeQuickSearch() {
  var overlay = R('quickSearch');
  if (!overlay) return;
  _qsOpen = false;
  overlay.classList.remove('qs-visible');
  var inp = R('qsInput');
  if (inp) inp.blur();
}

function qsOverlayClick(e) {
  if (e.target.id === 'quickSearch') closeQuickSearch();
}

// ── Default results (show pages + recent commands) ────────────────────────────
function _qsShowDefaultResults() {
  var items = [];
  // First 6 pages
  for (var i = 0; i < Math.min(6, _qsPages.length); i++) {
    items.push({ icon: _qsPages[i].icon, label: _qsPages[i].label, category: _qsPages[i].category, action: _qsPages[i].action });
  }
  // Show recent commands if available
  if (typeof commands !== 'undefined' && Array.isArray(commands)) {
    var recentCmds = commands.slice(0, 4);
    recentCmds.forEach(function(c) {
      items.push({ icon: '📋', label: c.name || c.label || c.body, category: 'Команди', action: function(cmd){ return function(){ pyCall('run_command', JSON.stringify({type: cmd.type || 'shell', body: cmd.body, name: cmd.name})); closeQuickSearch(); }; }(c) });
    });
  }
  _qsRenderResults(items, '');
}

// ── Search ────────────────────────────────────────────────────────────────────
function qsOnInput(val) {
  clearTimeout(_qsDebounce);
  if (!val.trim()) {
    _qsShowDefaultResults();
    return;
  }
  _qsDebounce = setTimeout(function() {
    _qsSearch(val.trim());
  }, 120);
}

function _qsSearch(q) {
  var ql = q.toLowerCase();
  var results = [];

  // Search pages
  _qsPages.forEach(function(p) {
    if (p.label.toLowerCase().indexOf(ql) >= 0) {
      results.push({ icon: p.icon, label: p.label, category: p.category, action: p.action });
    }
  });

  // Search commands (local)
  if (typeof commands !== 'undefined' && Array.isArray(commands)) {
    commands.forEach(function(c) {
      var name = (c.name || c.label || '').toLowerCase();
      var body = (c.body || '').toLowerCase();
      if (name.indexOf(ql) >= 0 || body.indexOf(ql) >= 0) {
        results.push({
          icon: c.type === 'url' ? '🌐' : c.type === 'python' ? '🐍' : '📋',
          label: c.name || c.label || c.body,
          sub: c.body ? c.body.slice(0, 60) : '',
          category: 'Команди',
          action: (function(cmd){ return function(){ pyCall('run_command', JSON.stringify({type: cmd.type || 'shell', body: cmd.body, name: cmd.name})); closeQuickSearch(); }; })(c)
        });
      }
    });
  }

  // Search macros (local)
  if (typeof macros !== 'undefined' && Array.isArray(macros)) {
    macros.forEach(function(m) {
      var name = (m.name || m.label || '').toLowerCase();
      if (name.indexOf(ql) >= 0) {
        results.push({
          icon: '⚡',
          label: m.name || m.label,
          sub: m.command ? m.command.slice(0, 60) : '',
          category: 'Макроси',
          action: (function(mac){ return function(){ pyCall('run_macro', JSON.stringify(mac)); closeQuickSearch(); }; })(m)
        });
      }
    });
  }

  // Also ask Python for extended search (installed apps, etc.)
  pyCall('search_quick', JSON.stringify({ q: q }));

  _qsRenderResults(results, q);
}

// ── Render results ────────────────────────────────────────────────────────────
function _qsRenderResults(items, q) {
  _qsResults = items;
  _qsSelected = items.length > 0 ? 0 : -1;
  var list = R('qsList');
  if (!list) return;

  if (!items.length) {
    list.innerHTML = '<div class="qs-empty">Нічого не знайдено</div>';
    return;
  }

  // Group by category
  var groups = {};
  var order = [];
  items.forEach(function(item) {
    var cat = item.category || 'Інше';
    if (!groups[cat]) { groups[cat] = []; order.push(cat); }
    groups[cat].push(item);
  });

  var html = '';
  var globalIdx = 0;
  order.forEach(function(cat) {
    html += '<div class="qs-cat">' + cat + '</div>';
    groups[cat].forEach(function(item) {
      var idx = globalIdx++;
      var subHtml = item.sub ? '<div class="qs-result-sub">' + _escHtml(item.sub) + '</div>' : '';
      var hl = q ? _qsHighlight(_escHtml(item.label), q) : _escHtml(item.label);
      html += '<div class="qs-result' + (idx === 0 ? ' qs-selected' : '') + '" data-idx="' + idx + '" onclick="qsExecute(' + idx + ')" onmouseover="qsHover(' + idx + ')">'
        + '<span class="qs-result-icon">' + item.icon + '</span>'
        + '<div class="qs-result-body"><div class="qs-result-label">' + hl + '</div>' + subHtml + '</div>'
        + '</div>';
    });
  });

  list.innerHTML = html;
}

function _qsHighlight(text, q) {
  var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
  return text.replace(re, '<mark class="qs-mark">$1</mark>');
}

// ── Keyboard navigation ───────────────────────────────────────────────────────
function qsKeyDown(e) {
  if (e.key === 'Escape') { closeQuickSearch(); return; }
  if (e.key === 'ArrowDown') { e.preventDefault(); _qsMove(1); return; }
  if (e.key === 'ArrowUp')   { e.preventDefault(); _qsMove(-1); return; }
  if (e.key === 'Enter') { e.preventDefault(); qsExecute(_qsSelected); return; }
}

function _qsMove(dir) {
  if (!_qsResults.length) return;
  _qsSelected = (_qsSelected + dir + _qsResults.length) % _qsResults.length;
  _qsUpdateSelection();
}

function _qsUpdateSelection() {
  var items = document.querySelectorAll('#qsList .qs-result');
  items.forEach(function(el, i) {
    el.classList.toggle('qs-selected', i === _qsSelected);
    if (i === _qsSelected) el.scrollIntoView({ block: 'nearest' });
  });
}

function qsHover(idx) {
  _qsSelected = idx;
  _qsUpdateSelection();
}

function qsExecute(idx) {
  if (idx < 0 || idx >= _qsResults.length) return;
  var item = _qsResults[idx];
  if (item && typeof item.action === 'function') {
    closeQuickSearch();
    item.action();
  }
}

// ── Python push handler: search_results ─────────────────────────────────────
function handleQuickSearchResults(x) {
  if (!_qsOpen || !Array.isArray(x.results)) return;
  var inp = R('qsInput');
  var q = inp ? inp.value.trim() : '';
  // Merge python results into current
  var pyItems = x.results.map(function(r) {
    return {
      icon: r.icon || '🔎',
      label: r.label || r.name,
      sub: r.sub || r.body || '',
      category: r.category || 'Програми',
      action: (function(res){ return function(){
        if (res.page) showPage(res.page);
        else if (res.cmd) pyCall('run_command', JSON.stringify(res.cmd));
        else if (res.action) pyCall(res.action, JSON.stringify(res.data || {}));
        closeQuickSearch();
      }; })(r)
    };
  });
  var existing = _qsResults.filter(function(i){ return i.category !== 'Програми'; });
  _qsRenderResults(existing.concat(pyItems), q);
}

// ── Global keyboard shortcut ──────────────────────────────────────────────────
document.addEventListener('keydown', function(e) {
  if (e.ctrlKey && e.code === 'Space') {
    e.preventDefault();
    if (_qsOpen) closeQuickSearch();
    else openQuickSearch();
  }
}, true);
