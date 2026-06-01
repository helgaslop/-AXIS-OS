/* AXIS OS — Onboarding Wizard */
'use strict';

var _obStep    = 1;
var _obAvatar  = '👤';
var _obTotal   = 4;

var _OB_AVATARS = ['👤','🧑','👨‍💻','👩‍💻','🤖','🦊','🐉','🌟','⚡','🔮','🎯','🦁'];

// ── Init (called on app start) ────────────────────────────────────────────────
function checkOnboarding() {
  pyCall('get_onboarding_status', '{}');
}

function handleOnboardingStatus(d) {
  if (!d.done) {
    setTimeout(showOnboarding, 400);
  }
}

function showOnboarding() {
  var overlay = R('obOverlay');
  if (overlay) {
    overlay.style.display = 'flex';
    _goStep(1);
  }
}

// ── Navigation ────────────────────────────────────────────────────────────────
function obNext() {
  if (_obStep === 2) {
    var name = (R('obNameInput') || {}).value.trim();
    if (!name) { showToast('Введіть ваше ім\'я'); return; }
  }
  if (_obStep < _obTotal) _goStep(_obStep + 1);
}

function obBack() {
  if (_obStep > 1) _goStep(_obStep - 1);
}

function _goStep(n) {
  _obStep = n;
  // Hide all steps
  for (var i = 1; i <= _obTotal; i++) {
    var el = R('obStep' + i);
    if (el) el.style.display = i === n ? 'block' : 'none';
  }
  // Update progress dots
  var dots = R('obDots');
  if (dots) {
    dots.innerHTML = '';
    for (var j = 1; j <= _obTotal; j++) {
      var d = document.createElement('span');
      d.className = 'ob-dot' + (j === n ? ' ob-dot-active' : j < n ? ' ob-dot-done' : '');
      dots.appendChild(d);
    }
  }
  // Back button visibility
  var backBtn = R('obBackBtn');
  if (backBtn) backBtn.style.visibility = n > 1 ? 'visible' : 'hidden';
  // Next vs Finish
  var nextBtn = R('obNextBtn');
  if (nextBtn) nextBtn.textContent = n === _obTotal ? '🚀 Починати!' : 'Далі →';

  // Step-specific init
  if (n === 2) _renderObAvatars();
  if (n === 3) _initLicStep();
}

// ── Step 2: Avatar picker ─────────────────────────────────────────────────────
function _renderObAvatars() {
  var grid = R('obAvatarGrid');
  if (!grid) return;
  grid.innerHTML = _OB_AVATARS.map(function(a) {
    return '<span class="ob-av' + (a === _obAvatar ? ' ob-av-sel' : '') + '" onclick="obPickAvatar(\'' + a + '\')">' + a + '</span>';
  }).join('');
}

function obPickAvatar(emoji) {
  _obAvatar = emoji;
  var preview = R('obAvatarPreview');
  if (preview) preview.textContent = emoji;
  _renderObAvatars();
}

// ── Step 3: License ───────────────────────────────────────────────────────────
function _initLicStep() {
  // Show current trial status
  pyCall('get_license_status', '{}');
}

function obActivateLicense() {
  var inp = R('obLicKeyInput');
  if (!inp || !inp.value.trim()) return;
  pyCall('activate_license', JSON.stringify({ key: inp.value.trim() }));
}

function obStartTrial() {
  // Just proceed — trial starts automatically on first launch
  _goStep(4);
}

// ── Step 4: Finish ────────────────────────────────────────────────────────────
function obFinish() {
  var name  = (R('obNameInput')  || {}).value.trim();
  var email = (R('obEmailInput') || {}).value || '';
  email = email.trim();
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    showToast('⚠️ Невірний формат email');
    return;
  }
  pyCall('complete_onboarding', JSON.stringify({
    name: name, email: email, avatar: _obAvatar
  }));
}

function handleOnboardingComplete(d) {
  var overlay = R('obOverlay');
  if (overlay) overlay.style.display = 'none';
  showToast('🎉 Ласкаво просимо до AXIS OS!');
  // Start tooltips tour
  setTimeout(startTooltipsTour, 800);
}

// ── Tooltips tour ─────────────────────────────────────────────────────────────
var _tooltipItems = [
  { target: '[data-page="dashboard"]', text: '⬡ Головна — загальний огляд системи та швидкий доступ' },
  { target: '[data-page="chat"]',      text: '💬 AI Чат — розмова з GPT, Gemini, Claude та іншими' },
  { target: '[data-page="pomodoro"]',  text: '🍅 Помодоро — таймер фокусу + голосове керування' },
  { target: '[data-page="api"]',       text: '🔑 API Ключі — тут додайте ключі для AI' },
  { target: '[data-page="license"]',   text: '💳 Підписки — ліцензія і трекінг AI-витрат' },
];
var _tourIdx = 0;
var _tourEl  = null;

function startTooltipsTour() {
  _tourIdx = 0;
  _showTourTip();
}

function _showTourTip() {
  if (_tourEl) _tourEl.remove();
  if (_tourIdx >= _tooltipItems.length) return;

  var item   = _tooltipItems[_tourIdx];
  var target = document.querySelector(item.target);
  if (!target) { _tourIdx++; _showTourTip(); return; }

  var rect = target.getBoundingClientRect();
  var tip  = document.createElement('div');
  tip.className   = 'tour-tip';
  tip.innerHTML   = '<div class="tour-text">' + item.text + '</div>'
    + '<div class="tour-actions">'
    + '<button class="btn btn-sm" onclick="tourSkip()">Пропустити</button>'
    + '<button class="btn btn-sm btn-p" onclick="tourNext()">Далі →</button>'
    + '</div>';
  tip.style.cssText = 'position:fixed;left:' + (rect.right + 10) + 'px;top:' + rect.top + 'px;z-index:99999;';
  document.body.appendChild(tip);
  _tourEl = tip;

  // Highlight target
  target.classList.add('tour-highlight');
}

function tourNext() {
  var item = _tooltipItems[_tourIdx];
  var prev = document.querySelector(item.target);
  if (prev) prev.classList.remove('tour-highlight');
  _tourIdx++;
  _showTourTip();
}

function tourSkip() {
  if (_tourEl) _tourEl.remove();
  _tooltipItems.forEach(function(item) {
    var el = document.querySelector(item.target);
    if (el) el.classList.remove('tour-highlight');
  });
}

// ── axisPush integration ──────────────────────────────────────────────────────
(function() {
  var _orig = window.axisPush;
  window.axisPush = function(type, jsonStr) {
    try {
      var d = JSON.parse(jsonStr);
      if (type === 'onboarding_status')  { handleOnboardingStatus(d);  return; }
      if (type === 'onboarding_complete'){ handleOnboardingComplete(d); return; }
      if (type === 'license_status') {
        // Update license info in onboarding step 3
        var el = R('obLicStatus');
        if (el) {
          el.textContent = (d.emoji || '') + ' ' + (d.name || '') + ' — '
            + (d.tier === 'trial' ? d.days_left + ' дн. пробного' :
               d.tier === 'lifetime' ? 'Назавжди активна' : 'Активна');
          el.style.color = d.active ? 'var(--green)' : 'var(--orange)';
        }
      }
    } catch(e) {}
    _orig && _orig(type, jsonStr);
  };
})();

// ── Auto-check on load ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(checkOnboarding, 800);
});
