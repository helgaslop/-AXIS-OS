/* AXIS OS — Notification Center */
// ═══════════════════════════════════════════════════

var _notifications = [];
var _notifMax = 50;
var _notifUnread = 0;
var _notifPanelOpen = false;
var _NOTIF_STORAGE_KEY = 'axis_notifications_v2';

// ── localStorage persistence ──────────────────────────────────────────────────
function _saveNotifs() {
  try {
    localStorage.setItem(_NOTIF_STORAGE_KEY, JSON.stringify(_notifications.slice(0, _notifMax)));
  } catch(e) {}
}
function _loadNotifs() {
  try {
    var saved = JSON.parse(localStorage.getItem(_NOTIF_STORAGE_KEY) || '[]');
    if (Array.isArray(saved) && saved.length) {
      _notifications = saved;
      _notifUnread = saved.filter(function(n){ return !n.read; }).length;
    }
  } catch(e) {}
}
_loadNotifs();

// Category config
var _notifCats = {
  info:    { icon: 'ℹ', color: '#6366f1' },
  ok:      { icon: '✓', color: '#22c55e' },
  error:   { icon: '✕', color: '#ef4444' },
  warning: { icon: '⚠', color: '#f59e0b' },
  ai:      { icon: '🤖', color: '#6366f1' },
  update:  { icon: '🔄', color: '#3b82f6' },
  system:  { icon: '⚙', color: '#8b5cf6' },
};

// ── Add a notification ────────────────────────────────────────────────────────
function addNotification(msg, category) {
  category = category || 'info';
  var now = new Date();
  var ts = now.toLocaleTimeString('uk-UA', { hour12: false, hour: '2-digit', minute: '2-digit' });
  var notif = {
    id: Date.now() + Math.random(),
    msg: msg,
    category: category,
    ts: ts,
    read: false,
    date: now.toLocaleDateString('uk-UA'),
  };
  _notifications.unshift(notif);
  if (_notifications.length > _notifMax) _notifications.pop();
  _notifUnread++;
  _updateNotifBadge();
  if (_notifPanelOpen) _renderNotifList();
  _saveNotifs();
}

// ── Badge ─────────────────────────────────────────────────────────────────────
function _updateNotifBadge() {
  var badge = R('notifBadge');
  if (!badge) return;
  if (_notifUnread > 0) {
    badge.textContent = _notifUnread > 99 ? '99+' : String(_notifUnread);
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }
}

// ── Toggle panel ──────────────────────────────────────────────────────────────
function toggleNotifPanel() {
  var panel = R('notifPanel');
  if (!panel) return;
  _notifPanelOpen = !_notifPanelOpen;
  if (_notifPanelOpen) {
    panel.style.display = 'flex';
    // Mark all as read
    _notifications.forEach(function(n) { n.read = true; });
    _notifUnread = 0;
    _updateNotifBadge();
    _renderNotifList();
    // Close on outside click
    setTimeout(function() {
      document.addEventListener('click', _notifOutsideClick);
    }, 0);
  } else {
    panel.style.display = 'none';
    document.removeEventListener('click', _notifOutsideClick);
  }
}

function _notifOutsideClick(e) {
  var panel = R('notifPanel');
  var btn   = R('notifBellBtn');
  if (!panel) return;
  if (!panel.contains(e.target) && (!btn || !btn.contains(e.target))) {
    _notifPanelOpen = false;
    panel.style.display = 'none';
    document.removeEventListener('click', _notifOutsideClick);
  }
}

// ── Render list ───────────────────────────────────────────────────────────────
function _renderNotifList() {
  var list = R('notifList');
  if (!list) return;

  if (!_notifications.length) {
    list.innerHTML = '<div class="notif-empty">Сповіщень немає</div>';
    return;
  }

  var html = '';
  _notifications.forEach(function(n) {
    var cat = _notifCats[n.category] || _notifCats.info;
    // Sanitise values that come from localStorage / untrusted sources
    var safeId  = parseFloat(n.id) || 0;
    var safeCat = /^[a-z_]+$/.test(n.category) ? n.category : 'info';
    var safeTs  = _escHtml(String(n.ts || ''));
    html += '<div class="notif-item' + (n.read ? '' : ' notif-unread') + '" data-id="' + safeId + '">'
      + '<div class="notif-cat-dot" style="background:' + cat.color + '">' + cat.icon + '</div>'
      + '<div class="notif-body">'
      + '<div class="notif-msg">' + _escHtml(n.msg) + '</div>'
      + '<div class="notif-meta"><span class="notif-badge notif-cat-' + safeCat + '">' + safeCat + '</span><span class="notif-ts">' + safeTs + '</span></div>'
      + '</div>'
      + '<button class="notif-del" onclick="deleteNotif(' + safeId + ',event)" title="Видалити">✕</button>'
      + '</div>';
  });

  list.innerHTML = html;
}

// ── Delete single ─────────────────────────────────────────────────────────────
function deleteNotif(id, e) {
  if (e) e.stopPropagation();
  id = parseFloat(id);
  _notifications = _notifications.filter(function(n) { return parseFloat(n.id) !== id; });
  _saveNotifs();
  _renderNotifList();
}

// ── Clear all ─────────────────────────────────────────────────────────────────
function clearAllNotifs() {
  _notifications = [];
  _notifUnread = 0;
  _updateNotifBadge();
  _saveNotifs();
  _renderNotifList();
}

// ── Intercept showToast to also store notifications ──────────────────────────
(function() {
  var _origShowToast = window.showToast;
  window.showToast = function(msg, dur) {
    _origShowToast && _origShowToast(msg, dur);
    if (!msg) return;
    // Filter out short/trivial toasts from notification center
    var _skipPrefixes = ['🔊','🔈','🔇','📋 Скопійовано','🎵','▶','⏸','⏭'];
    var isNoise = msg.length < 20 || _skipPrefixes.some(function(p){ return String(msg).startsWith(p); });
    if (isNoise) { return; }
    // Determine category from emoji prefix
    var cat = 'info';
    if (/^[✓✔☑]/.test(msg) || /^✓/.test(msg)) cat = 'ok';
    else if (/^[⚠⛔❌✗]/.test(msg) || /error|помилка|fail/i.test(msg)) cat = 'warning';
    else if (/^🤖|^AI|^GPT|^Claude|^Gemini/i.test(msg)) cat = 'ai';
    else if (/^🔄|оновлен/i.test(msg)) cat = 'update';
    addNotification(msg, cat);
  };
})();

// ── Also intercept ai_response, ai_error push events ────────────────────────
// These are handled through the map in axisPush — we extend it after load
document.addEventListener('DOMContentLoaded', function() {
  // nothing to do here — _wrapAxisPush is called inline below
});

// Wrap axisPush to capture additional push events
(function() {
  var _origPush = window.axisPush;
  window.axisPush = function(type, jsonStr) {
    _origPush && _origPush(type, jsonStr);
    try {
      var d = JSON.parse(jsonStr);
      if (type === 'ai_error') {
        addNotification('AI помилка: ' + (d.error || d.msg || ''), 'error');
      } else if (type === 'update_status' && d.status === 'available') {
        addNotification('🔄 Оновлення доступне: v' + d.version, 'update');
      } else if (type === 'github_update_status' && d.status === 'available') {
        addNotification('🐙 GitHub оновлення: v' + (d.version || d.tag || ''), 'update');
      } else if (type === 'search_results') {
        handleQuickSearchResults && handleQuickSearchResults(d);
      }
    } catch(e) { /* ignore */ }
  };
})();
