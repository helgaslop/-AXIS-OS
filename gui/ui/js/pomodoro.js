/* AXIS OS — Pomodoro Timer */
(function () {
  'use strict';

  // ── Constants ────────────────────────────────────────────────────────────────
  var WORK_MIN  = 25;
  var SHORT_MIN = 5;
  var LONG_MIN  = 15;
  var LONG_AFTER = 4;  // long break after N pomodoros

  // ── State ────────────────────────────────────────────────────────────────────
  var _mode      = 'work';   // 'work' | 'short' | 'long'
  var _running   = false;
  var _remaining = WORK_MIN * 60;  // seconds
  var _total     = WORK_MIN * 60;
  var _interval  = null;
  var _session   = 0;  // completed pomodoros this boot
  var _todayCount   = 0;
  var _todayMinutes = 0;

  // Audio context (lazy-init)
  var _audioCtx = null;
  function _getAudioCtx() {
    if (!_audioCtx) {
      try { _audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e){}
    }
    return _audioCtx;
  }

  function _beep(freq, dur, vol) {
    var ctx = _getAudioCtx();
    if (!ctx) return;
    try {
      var osc  = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq || 880;
      osc.type = 'sine';
      gain.gain.setValueAtTime(vol || 0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + (dur || 0.6));
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + (dur || 0.6));
    } catch(e){}
  }

  function _playDone() {
    _beep(880, 0.4, 0.3);
    setTimeout(function(){ _beep(1100, 0.4, 0.25); }, 450);
    setTimeout(function(){ _beep(1320, 0.8, 0.2);  }, 900);
  }

  function _playTick() {
    _beep(440, 0.05, 0.03);
  }

  // ── Timer Logic ──────────────────────────────────────────────────────────────
  function _startTimer() {
    if (_running) return;
    _running = true;
    _updateUI();
    _interval = setInterval(function () {
      if (_remaining <= 0) {
        _onTimerEnd();
        return;
      }
      _remaining--;
      _updateUI();
    }, 1000);
  }

  function _pauseTimer() {
    _running = false;
    clearInterval(_interval);
    _interval = null;
    _updateUI();
  }

  function _resetTimer() {
    _pauseTimer();
    _setMode(_mode);
  }

  function _onTimerEnd() {
    _pauseTimer();
    _playDone();

    if (_mode === 'work') {
      _session++;
      _todayCount++;
      _todayMinutes += WORK_MIN;

      // Save to Python backend
      try {
        pyCall('save_pomodoro_stat', JSON.stringify({ minutes: WORK_MIN }));
      } catch(e){}

      _renderSessionDots();
      _renderStats();

      var nextMode = (_session % LONG_AFTER === 0) ? 'long' : 'short';
      var label = nextMode === 'long' ? 'Довга перерва (15 хв)' : 'Коротка перерва (5 хв)';
      showToast('🍅 Помодоро завершено! ' + label);
      _setMode(nextMode);
    } else {
      showToast('⏰ Перерва закінчилась — час працювати!');
      _setMode('work');
    }
  }

  function _setMode(mode) {
    _mode = mode;
    if (mode === 'work')  { _total = _remaining = WORK_MIN * 60; }
    if (mode === 'short') { _total = _remaining = SHORT_MIN * 60; }
    if (mode === 'long')  { _total = _remaining = LONG_MIN * 60; }
    _updateModeBtns();
    _updateUI();
  }

  // ── UI Rendering ─────────────────────────────────────────────────────────────
  function _fmt(secs) {
    var m = Math.floor(secs / 60);
    var s = secs % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function _updateUI() {
    var el;

    // Timer display
    el = R('pomTimerDisplay'); if (el) el.textContent = _fmt(_remaining);

    // SVG circular progress
    el = R('pomArc');
    if (el) {
      var pct = _total > 0 ? (_remaining / _total) : 1;
      var r   = 90;
      var circ = 2 * Math.PI * r;
      el.style.strokeDasharray  = circ;
      el.style.strokeDashoffset = circ * (1 - pct);
      // color by mode
      var col = _mode === 'work' ? 'var(--accent)' :
                _mode === 'short' ? 'var(--indigo)' : 'var(--orange)';
      el.style.stroke = col;
    }

    // Start/pause button
    el = R('pomStartBtn');
    if (el) {
      el.textContent = _running ? '⏸ Пауза' : '▶ Старт';
      el.style.background = _running ? 'rgba(99,102,241,.2)' : '';
    }

    // Mode label
    el = R('pomModeLabel');
    if (el) {
      var lbl = _mode === 'work' ? '🍅 Робота' :
                _mode === 'short' ? '☕ Перерва' : '🛋 Довга перерва';
      el.textContent = lbl;
    }

    // Task name reflection
    el = R('pomTaskReflect');
    var inp = R('pomTaskInput');
    if (el && inp) el.textContent = inp.value || '';
  }

  function _updateModeBtns() {
    ['work','short','long'].forEach(function(m) {
      var btn = R('pomMode_' + m);
      if (btn) btn.classList.toggle('active', m === _mode);
    });
  }

  function _renderSessionDots() {
    var el = R('pomSessionDots');
    if (!el) return;
    var html = '';
    for (var i = 0; i < LONG_AFTER; i++) {
      var done = (i < (_session % LONG_AFTER === 0 && _session > 0 ? LONG_AFTER : _session % LONG_AFTER));
      html += '<div style="width:12px;height:12px;border-radius:50%;border:2px solid var(--accent);background:'
            + (done ? 'var(--accent)' : 'transparent') + ';"></div>';
    }
    el.innerHTML = html;
  }

  function _renderStats() {
    var el;
    el = R('pomTodayCount');   if (el) el.textContent = _todayCount;
    el = R('pomTodayMinutes'); if (el) el.textContent = _todayMinutes + ' хв';
  }

  // ── Public API ───────────────────────────────────────────────────────────────
  window.pomStartPause = function () {
    if (_running) _pauseTimer();
    else          _startTimer();
  };

  window.pomReset = function () { _resetTimer(); };

  window.pomSetMode = function (mode) {
    _pauseTimer();
    _setMode(mode);
  };

  // Handle stats from Python
  window.handlePomodoroStats = function (d) {
    if (d && d.today) {
      _todayCount   = d.today.count   || 0;
      _todayMinutes = d.today.focus_minutes || 0;
      _renderStats();
    }
  };

  // ── Keyboard shortcut: Space ──────────────────────────────────────────────────
  document.addEventListener('keydown', function (e) {
    var page = R('page-pomodoro');
    if (!page || !page.classList.contains('active')) return;
    if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
      e.preventDefault();
      window.pomStartPause();
    }
  });

  // ── Init on page show ─────────────────────────────────────────────────────────
  function _initPomodoro() {
    _setMode('work');
    _renderSessionDots();
    _renderStats();
    try { pyCall('get_pomodoro_stats', '{}'); } catch(e){}
  }

  // Hook into showPage
  var _origShowPage = window.showPage;
  window.showPage = function (id) {
    _origShowPage && _origShowPage(id);
    if (id === 'pomodoro') {
      setTimeout(_initPomodoro, 50);
    }
  };

  // ── Public status getter ──────────────────────────────────────────────────────
  window.pomGetStatus = function () {
    return {
      mode: _mode, running: _running, remaining: _remaining,
      session: _session, todayCount: _todayCount, todayMinutes: _todayMinutes
    };
  };

  // Register axisPush handler
  var _origPush = window.axisPush;
  window.axisPush = function (type, jsonStr) {
    if (type === 'pomodoro_stats') {
      try { handlePomodoroStats(JSON.parse(jsonStr)); } catch(e){}
      return;
    }
    // ── Voice commands from Sphere ────────────────────────────────────────────
    if (type === 'pomodoro_voice_cmd') {
      try {
        var d = JSON.parse(jsonStr);
        var act = d.action;
        if (act === 'start') {
          if (!_running) { _setMode('work'); _startTimer(); }
          showToast('🍅 Помодоро запущено!');
        } else if (act === 'pause') {
          if (_running) _pauseTimer();
          showToast('⏸ Помодоро на паузі');
        } else if (act === 'stop') {
          _resetTimer();
          showToast('🔄 Помодоро скинуто');
        } else if (act === 'break_short') {
          _pauseTimer(); _setMode('short'); _startTimer();
          showToast('☕ Коротка перерва запущена');
        } else if (act === 'break_long') {
          _pauseTimer(); _setMode('long'); _startTimer();
          showToast('🛋 Довга перерва запущена');
        } else if (act === 'status') {
          var st = window.pomGetStatus();
          var modeLabel = st.mode === 'work' ? '🍅 Робота' : st.mode === 'short' ? '☕ Перерва' : '🛋 Довга перерва';
          var mins = Math.floor(st.remaining / 60);
          var secs = st.remaining % 60;
          var timeStr = (mins < 10 ? '0' : '') + mins + ':' + (secs < 10 ? '0' : '') + secs;
          showToast(modeLabel + ' · ' + timeStr + (st.running ? ' ▶' : ' ⏸'));
        }
      } catch(e){}
      return;
    }
    _origPush && _origPush(type, jsonStr);
  };

})();
