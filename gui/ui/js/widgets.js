/* AXIS OS — Dashboard Widget System (drag & drop, minimize, refresh) */
(function () {
  'use strict';

  // ── Layout storage ────────────────────────────────────────────────────────────
  var LAYOUT_KEY = 'axis_widget_layout';
  var MINIMIZED_KEY = 'axis_widget_minimized';

  var _layout    = JSON.parse(localStorage.getItem(LAYOUT_KEY)    || 'null') || null;
  var _minimized = JSON.parse(localStorage.getItem(MINIMIZED_KEY) || '{}');

  function _saveLayout() {
    var grid = R('widgetGrid');
    if (!grid) return;
    var order = [];
    grid.querySelectorAll('.widget-card').forEach(function (w) {
      order.push(w.dataset.widget);
    });
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(order));
  }

  function _saveMinimized() {
    localStorage.setItem(MINIMIZED_KEY, JSON.stringify(_minimized));
  }

  // ── Quick Notes widget ────────────────────────────────────────────────────────
  var _notesTimer = null;

  window.widgetNoteInput = function (el) {
    clearTimeout(_notesTimer);
    _notesTimer = setTimeout(function () {
      try { pyCall('save_quick_notes', JSON.stringify({ text: el.value })); } catch(e){}
    }, 800);
  };

  window.handleQuickNotes = function (d) {
    var el = R('widgetNoteArea');
    if (el && d && d.text !== undefined) el.value = d.text;
  };

  // ── Clock widget ──────────────────────────────────────────────────────────────
  function _updateWidgetClock() {
    var n = new Date();
    var el;
    el = R('wClockTime');
    if (el) el.textContent = n.toLocaleTimeString('uk-UA', { hour12: false });
    el = R('wClockDate');
    if (el) el.textContent = n.toLocaleDateString('uk-UA', { weekday:'long', day:'numeric', month:'long' });
    el = R('wClockGreet');
    if (el) {
      var h = n.getHours();
      var g = h < 6 ? '🌙 Доброї ночі' : h < 12 ? '🌅 Доброго ранку' : h < 18 ? '☀️ Доброго дня' : '🌆 Доброго вечора';
      el.textContent = g;
    }
  }
  setInterval(_updateWidgetClock, 1000);

  // ── Recent Commands widget ─────────────────────────────────────────────────────
  var _recentCmdsWidget = JSON.parse(localStorage.getItem('axis_recent_cmds_widget') || '[]');

  window.addRecentCmdWidget = function (name, type, body) {
    _recentCmdsWidget = _recentCmdsWidget.filter(function(c){ return c.name !== name; });
    _recentCmdsWidget.unshift({ name: name, type: type, body: body, ts: Date.now() });
    if (_recentCmdsWidget.length > 5) _recentCmdsWidget.length = 5;
    try { localStorage.setItem('axis_recent_cmds_widget', JSON.stringify(_recentCmdsWidget)); } catch(e){}
    _renderRecentCmdsWidget();
  };

  function _renderRecentCmdsWidget() {
    var el = R('wRecentCmds');
    if (!el) return;
    if (!_recentCmdsWidget.length) {
      el.innerHTML = '<div style="font-size:11px;color:var(--text3);text-align:center;padding:12px 0;">Ще немає команд</div>';
      return;
    }
    el.innerHTML = _recentCmdsWidget.map(function (c, i) {
      return '<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);">'
        + '<span style="font-size:11px;flex:1;font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + _escH(c.name) + '</span>'
        + '<button class="btn btn-sm" style="padding:2px 8px;font-size:9px;flex-shrink:0;" onclick="widgetReRunCmd(' + i + ')">▶</button>'
        + '</div>';
    }).join('');
  }

  window.widgetReRunCmd = function (i) {
    var c = _recentCmdsWidget[i];
    if (!c) return;
    try {
      pyCall('run_command', JSON.stringify({ type: c.type, body: c.body, name: c.name }));
      showToast('▶ ' + c.name);
    } catch(e){}
  };

  function _escH(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── Widget minimize toggle ────────────────────────────────────────────────────
  window.toggleWidgetMinimize = function (id) {
    _minimized[id] = !_minimized[id];
    _saveMinimized();
    var body = document.querySelector('[data-widget="' + id + '"] .widget-body');
    if (body) body.style.display = _minimized[id] ? 'none' : '';
    var btn = document.querySelector('[data-widget="' + id + '"] .widget-min-btn');
    if (btn) btn.textContent = _minimized[id] ? '▼' : '▲';
  };

  // ── Widget refresh buttons ─────────────────────────────────────────────────────
  window.widgetRefresh = function (id) {
    if (id === 'sysmonitor') {
      showToast('↺ Оновлення системи...');
      // Stats come from the periodic push — just show toast
    } else if (id === 'weather') {
      showToast('↺ Оновлення погоди...');
      fetchWeather && fetchWeather();
    } else if (id === 'quicknotes') {
      try { pyCall('get_quick_notes', '{}'); } catch(e){}
    } else if (id === 'recentcmds') {
      _renderRecentCmdsWidget();
    }
  };

  // ── Drag & Drop ───────────────────────────────────────────────────────────────
  var _dragSrc = null;

  function _initDragDrop() {
    var grid = R('widgetGrid');
    if (!grid) return;

    grid.querySelectorAll('.widget-card').forEach(function (card) {
      card.setAttribute('draggable', 'true');

      card.addEventListener('dragstart', function (e) {
        _dragSrc = card;
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      card.addEventListener('dragend', function () {
        card.classList.remove('dragging');
        grid.querySelectorAll('.widget-card').forEach(function (c) {
          c.classList.remove('drag-over');
        });
        _saveLayout();
      });

      card.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (card !== _dragSrc) {
          card.classList.add('drag-over');
        }
      });

      card.addEventListener('dragleave', function () {
        card.classList.remove('drag-over');
      });

      card.addEventListener('drop', function (e) {
        e.preventDefault();
        card.classList.remove('drag-over');
        if (_dragSrc && _dragSrc !== card) {
          // Swap positions
          var parent = grid;
          var srcIdx = Array.from(parent.children).indexOf(_dragSrc);
          var dstIdx = Array.from(parent.children).indexOf(card);
          if (srcIdx < dstIdx) {
            parent.insertBefore(_dragSrc, card.nextSibling);
          } else {
            parent.insertBefore(_dragSrc, card);
          }
          _saveLayout();
        }
      });
    });
  }

  // ── Apply saved layout order ───────────────────────────────────────────────────
  function _applyLayout() {
    var grid = R('widgetGrid');
    if (!grid || !_layout || !_layout.length) return;
    _layout.forEach(function (id) {
      var el = grid.querySelector('[data-widget="' + id + '"]');
      if (el) grid.appendChild(el);
    });
  }

  // ── Apply minimized states ────────────────────────────────────────────────────
  function _applyMinimized() {
    Object.keys(_minimized).forEach(function (id) {
      if (_minimized[id]) {
        var body = document.querySelector('[data-widget="' + id + '"] .widget-body');
        if (body) body.style.display = 'none';
        var btn = document.querySelector('[data-widget="' + id + '"] .widget-min-btn');
        if (btn) btn.textContent = '▼';
      }
    });
  }

  // ── Init on dashboard page show ───────────────────────────────────────────────
  function _initWidgets() {
    _applyLayout();
    _applyMinimized();
    _initDragDrop();
    _updateWidgetClock();
    _renderRecentCmdsWidget();
    try { pyCall('get_quick_notes', '{}'); } catch(e){}
  }

  // Wrap axisPush to handle quick_notes
  var _prevPush2 = window.axisPush;
  window.axisPush = function (type, jsonStr) {
    if (type === 'quick_notes') {
      try { handleQuickNotes(JSON.parse(jsonStr)); } catch(e){}
      return;
    }
    _prevPush2 && _prevPush2(type, jsonStr);
  };

  // Wrap showPage
  var _prevShowPage2 = window.showPage;
  window.showPage = function (id) {
    _prevShowPage2 && _prevShowPage2(id);
    if (id === 'dashboard') {
      setTimeout(_initWidgets, 80);
    }
  };

  // Also init on first load (dashboard is default active page)
  document.addEventListener('DOMContentLoaded', function () {
    setTimeout(_initWidgets, 400);
  });

})();
