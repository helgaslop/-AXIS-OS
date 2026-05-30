/* AXIS OS — Process Manager */
(function () {
  'use strict';

  var _procs        = [];
  var _sortBy       = 'cpu';
  var _sortAsc      = false;
  var _filter       = '';
  var _catFilter    = 'all';
  var _refreshTimer = null;
  var _loading      = false;

  var CAT_LABELS = {
    all:     '🌐 Всі',
    system:  '🖥 Система',
    browsers:'🌍 Браузери',
    games:   '🎮 Ігри',
    dev:     '💻 Dev Tools',
    other:   '📦 Інші',
  };

  // ── Fetch ────────────────────────────────────────────────────────────────────
  function _fetch() {
    if (_loading) return;
    _loading = true;
    try { pyCall('get_processes', '{}'); } catch(e) { _loading = false; }
  }

  window.handleProcessesData = function (data) {
    _loading = false;
    if (!Array.isArray(data)) return;
    _procs = data;
    _render();
  };

  // ── Sort + filter ────────────────────────────────────────────────────────────
  function _filtered() {
    var f = _filter.toLowerCase();
    return _procs.filter(function (p) {
      var catOk = _catFilter === 'all' || p.category === _catFilter;
      var txtOk = !f || p.name.toLowerCase().includes(f) || String(p.pid).includes(f);
      return catOk && txtOk;
    });
  }

  function _sorted(arr) {
    var by = _sortBy;
    return arr.slice().sort(function (a, b) {
      var av = a[by], bv = b[by];
      if (typeof av === 'string') av = av.toLowerCase();
      if (typeof bv === 'string') bv = bv.toLowerCase();
      if (av < bv) return _sortAsc ? -1 : 1;
      if (av > bv) return _sortAsc ? 1 : -1;
      return 0;
    });
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  function _render() {
    var tbody = R('procTableBody');
    if (!tbody) return;

    var rows = _sorted(_filtered());

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:24px 0;">Процесів не знайдено</td></tr>';
      _updateCount(0);
      return;
    }

    tbody.innerHTML = rows.map(function (p) {
      var highCpu = p.cpu > 50;
      var highRam = p.ram > 500;
      var highlight = (highCpu || highRam) ? 'color:var(--red);' : '';
      var cpuColor  = p.cpu > 50 ? 'color:var(--red)' : p.cpu > 20 ? 'color:var(--orange)' : 'color:var(--text2)';
      var ramColor  = p.ram > 500 ? 'color:var(--red)' : p.ram > 200 ? 'color:var(--orange)' : 'color:var(--text2)';
      var statusColor = p.status === 'running' ? 'var(--accent)' : p.status === 'sleeping' ? 'var(--text3)' : 'var(--orange)';
      var catLabel = CAT_LABELS[p.category] || p.category;

      return '<tr class="proc-tr" style="' + highlight + '">'
        + '<td style="font-family:var(--mono);font-size:11px;max-width:160px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + _escH(p.name) + '">' + _escH(p.name) + '</td>'
        + '<td style="color:var(--text3);font-size:11px;font-family:var(--mono);">' + p.pid + '</td>'
        + '<td style="' + cpuColor + ';font-size:12px;font-weight:700;font-family:var(--mono);">' + p.cpu.toFixed(1) + '%</td>'
        + '<td style="' + ramColor + ';font-size:11px;font-family:var(--mono);">' + p.ram.toFixed(1) + ' MB</td>'
        + '<td><span style="font-size:9px;font-weight:700;color:' + statusColor + ';background:' + statusColor + '22;padding:2px 7px;border-radius:10px;">' + p.status + '</span></td>'
        + '<td><span style="font-size:9px;color:var(--text3);">' + catLabel + '</span></td>'
        + '<td><button class="btn btn-sm btn-d" style="padding:2px 8px;font-size:10px;" onclick="procKill(' + p.pid + ',\'' + _escH(p.name) + '\')">Kill</button></td>'
        + '</tr>';
    }).join('');

    _updateCount(rows.length);
    _updateSortArrows();
  }

  function _updateCount(n) {
    var el = R('procCount');
    if (el) el.textContent = n + ' процесів';
  }

  function _updateSortArrows() {
    document.querySelectorAll('#procTable th[data-col]').forEach(function (th) {
      var col = th.dataset.col;
      var arrow = th.querySelector('.sort-arrow');
      if (!arrow) return;
      if (col === _sortBy) {
        arrow.textContent = _sortAsc ? ' ▲' : ' ▼';
      } else {
        arrow.textContent = '';
      }
    });
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function _escH(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Public API ────────────────────────────────────────────────────────────────
  window.procSortBy = function (col) {
    if (_sortBy === col) _sortAsc = !_sortAsc;
    else { _sortBy = col; _sortAsc = col === 'name'; }
    _render();
  };

  window.procFilter = function (val) {
    _filter = val;
    _render();
  };

  window.procSetCat = function (btn, cat) {
    _catFilter = cat;
    document.querySelectorAll('.proc-cat-btn').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    _render();
  };

  window.procKill = function (pid, name) {
    if (!confirm('Завершити процес "' + name + '" (PID: ' + pid + ')?')) return;
    try { pyCall('kill_process', JSON.stringify({ pid: pid })); } catch(e){}
    // Optimistic remove
    _procs = _procs.filter(function (p) { return p.pid !== pid; });
    _render();
  };

  window.procRefreshNow = function () {
    _fetch();
    showToast('↺ Оновлення процесів...');
  };

  // ── Auto-refresh every 3 s when page is active ────────────────────────────────
  function _startRefresh() {
    clearInterval(_refreshTimer); _refreshTimer = null;
    _fetch();
    _refreshTimer = setInterval(function () {
      var page = R('page-processes');
      if (page && page.classList.contains('active')) {
        _fetch();
      }
    }, 3000);
  }

  function _stopRefresh() {
    clearInterval(_refreshTimer);
    _refreshTimer = null;
  }

  // Hook axisPush
  var _origPush = window.axisPush;
  window.axisPush = function (type, jsonStr) {
    if (type === 'processes_data') {
      try { handleProcessesData(JSON.parse(jsonStr)); } catch(e){}
      return;
    }
    _origPush && _origPush(type, jsonStr);
  };

  // Hook showPage
  var _origShowPage = window.showPage;
  window.showPage = function (id) {
    _origShowPage && _origShowPage(id);
    if (id === 'processes') {
      _startRefresh();
    } else {
      _stopRefresh();
    }
  };

})();
