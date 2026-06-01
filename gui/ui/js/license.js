/* AXIS OS — License & AI Subscriptions */
'use strict';

// ── AI Providers config ───────────────────────────────────────────────────────
var AI_PROVIDERS = [
  { id: 'OpenAI',     icon: '🤖', name: 'OpenAI',     url: 'https://platform.openai.com/account/billing', plans: ['Pay-as-you-go', 'ChatGPT Plus', 'ChatGPT Pro'] },
  { id: 'Gemini',     icon: '✨', name: 'Google Gemini', url: 'https://aistudio.google.com/', plans: ['Free', 'Gemini Advanced'] },
  { id: 'Claude',     icon: '🔵', name: 'Anthropic Claude', url: 'https://console.anthropic.com/settings/billing', plans: ['Pay-as-you-go', 'Claude Pro'] },
  { id: 'xAI',        icon: '⚡', name: 'xAI Grok',   url: 'https://console.x.ai/billing', plans: ['Pay-as-you-go'] },
  { id: 'Perplexity', icon: '🌐', name: 'Perplexity', url: 'https://www.perplexity.ai/settings/account', plans: ['Free', 'Pro'] },
];

var _licenseData  = null;
var _aiSubs       = {};
var _aiStatuses   = {};
var _editProvider = null;

// Provider icons for spending breakdown
var PROV_ICONS = { openai: '🤖', anthropic: '🔵', google: '✨', xai: '⚡', deepseek: '🔮', perplexity: '🌐' };
var PROV_NAMES = { openai: 'OpenAI', anthropic: 'Claude', google: 'Gemini', xai: 'Grok', deepseek: 'DeepSeek', perplexity: 'Perplexity' };

// ── Init ──────────────────────────────────────────────────────────────────────
function initLicensePage() {
  pyCall('get_license_status', '{}');
  pyCall('get_ai_subscriptions', '{}');
  licRefreshStats();
  // Restore saved budget display
  var saved = localStorage.getItem('axis_budget_usd');
  if (saved) { var inp = R('spendBudgetInput'); if (inp) inp.value = saved; }
}

// ── Push handlers ─────────────────────────────────────────────────────────────
function handleLicenseStatus(d) {
  _licenseData = d;
  _renderLicense();
}

function handleLicenseResult(d) {
  var el = R('licActivateMsg');
  if (el) {
    el.textContent = d.message || '';
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  }
  if (d.ok) {
    var inp = R('licKeyInput2');
    if (inp) inp.value = '';
    showToast(d.message || '✅ Активовано');
  }
}

function handleAiSubscriptions(d) {
  _aiSubs = d || {};
  _renderAiCards();
}

function handleAiKeyStatuses(d) {
  _aiStatuses = d || {};
  _renderAiCards();
}

// ── Proxy stats ───────────────────────────────────────────────────────────────
function licRefreshStats() {
  var loading = R('proxyStatsLoading');
  var content = R('proxyStatsContent');
  if (loading) loading.style.display = 'block';
  if (content) content.style.display = 'none';
  pyCall('get_proxy_stats', '{}');
}

function licSaveBudget() {
  var inp = R('spendBudgetInput');
  var amount = parseFloat((inp && inp.value) || '0') || 0;
  localStorage.setItem('axis_budget_usd', amount);
  pyCall('set_budget', JSON.stringify({ amount: amount }));
}

function handleProxyStats(d) {
  var loading = R('proxyStatsLoading');
  var content = R('proxyStatsContent');

  if (d.error) {
    if (loading) { loading.textContent = '⚠️ ' + d.error; loading.style.display = 'block'; }
    if (content) content.style.display = 'none';
    return;
  }

  if (loading) loading.style.display = 'none';
  if (content) content.style.display = 'block';

  var budget   = d.budget_usd   || 0;
  var spent    = d.total_cost_usd || 0;
  var remain   = d.remaining_usd != null ? d.remaining_usd : Math.max(0, budget - spent);
  var reqs     = d.total_requests || 0;
  var pct      = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;

  // Update budget input if server returned it
  var inp = R('spendBudgetInput');
  if (inp && budget > 0 && !inp.value) inp.value = budget;

  _setText('spendTotalReqs', reqs.toLocaleString());
  _setText('spendTotalCost', '≈ $' + spent.toFixed(3));
  _setText('spendBudgetDisplay', '$' + budget.toFixed(2));
  _setText('spendRemain', '$' + remain.toFixed(2));

  var bar = R('spendTotalBar');
  if (bar) {
    bar.style.width = pct.toFixed(1) + '%';
    bar.className = 'spend-bar-fill' + (pct > 80 ? ' warn' : '');
  }
  var remEl = R('spendRemain');
  if (remEl) remEl.className = 'spend-remain-val' + (remain < budget * 0.2 && budget > 0 ? ' low' : '') + (remain <= 0 && budget > 0 ? ' empty' : '');

  // Breakdown
  var bd = d.breakdown || [];
  // Safe: use reduce instead of spread to avoid stack overflow on large arrays
  var maxCost = bd.reduce(function(acc, item) { return Math.max(acc, item.cost_usd || 0); }, 0) || 1;
  var html = bd.map(function(item) {
    var barW = maxCost > 0 ? (item.cost_usd / maxCost * 100).toFixed(1) : 0;
    var icon = PROV_ICONS[item.provider] || '🔗';
    var name = PROV_NAMES[item.provider] || item.provider;
    return '<div class="spend-prov-row">'
      + '<span class="spend-prov-ico">' + icon + '</span>'
      + '<span class="spend-prov-name">' + name + '</span>'
      + '<div class="spend-prov-bar-wrap"><div class="spend-prov-bar" style="width:' + barW + '%"></div></div>'
      + '<span class="spend-prov-reqs">' + item.requests.toLocaleString() + ' req</span>'
      + '<span class="spend-prov-cost">$' + item.cost_usd.toFixed(3) + '</span>'
      + '</div>';
  }).join('');
  var bdEl = R('spendBreakdown');
  if (bdEl) bdEl.innerHTML = html || '<div style="font-size:12px;color:var(--text3);text-align:center;padding:8px">Ще немає запитів цього місяця</div>';
}

function _setText(id, val) { var el = R(id); if (el) el.textContent = val; }

function handleAiCostStats(d) {
  var el = R('aiCostStats');
  if (!el || !d) return;
  var bd = d.breakdown || [];
  if (!bd.length) { el.style.display = 'none'; return; }

  var rows = bd.map(function(item) {
    var usdStr = item.usd != null ? '<span class="cost-usd">≈ $' + item.usd.toFixed(2) + '/міс</span>' : '';
    return '<div class="cost-row"><span class="cost-name">' + _escHtml(item.name) + '</span>'
      + '<span class="cost-raw">' + _escHtml(item.cost) + '</span>' + usdStr + '</div>';
  }).join('');

  var totalStr = d.total_usd > 0
    ? '<div class="cost-total">💸 Загалом: <strong>~$' + d.total_usd.toFixed(2) + '</strong> / місяць</div>'
    : '';

  el.innerHTML = totalStr + rows;
  el.style.display = 'block';
}

// ── License render ────────────────────────────────────────────────────────────
function _renderLicense() {
  var d = _licenseData;
  if (!d) return;

  // Badge
  var badge = R('licTierBadge');
  if (badge) {
    badge.textContent = (d.emoji || '') + ' ' + (d.name || d.tier);
    badge.className = 'lic-tier-badge lic-tier-' + d.tier;
  }

  // Status message
  var msg = R('licStatusMsg');
  if (msg) {
    if (d.tier === 'lifetime') {
      msg.textContent = '♾️ Довічна ліцензія активна';
      msg.style.color = 'var(--green)';
    } else if (!d.active) {
      msg.textContent = '⛔ Термін дії закінчився — активуйте ключ';
      msg.style.color = 'var(--red)';
    } else if (d.tier === 'trial') {
      msg.textContent = '⏳ Пробний період: ' + d.days_left + ' дн. залишилось';
      msg.style.color = d.days_left <= 2 ? 'var(--orange)' : 'var(--accent)';
    } else {
      msg.textContent = '✅ Активно · ' + d.days_left + ' дн. до поновлення';
      msg.style.color = 'var(--green)';
    }
  }

  // Trial bar
  var bar = R('licTrialBar');
  var barFill = R('licTrialBarFill');
  if (bar && barFill) {
    if (d.tier === 'trial') {
      bar.style.display = 'block';
      var pct = Math.min(100, Math.round((d.days_left / 7) * 100));
      barFill.style.width = pct + '%';
      barFill.style.background = pct > 40 ? 'var(--green)' : pct > 15 ? 'var(--orange)' : 'var(--red)';
    } else {
      bar.style.display = 'none';
    }
  }

  // Active key display
  var keyEl = R('licActiveKey');
  if (keyEl) {
    keyEl.textContent = d.key ? d.key : '—';
    keyEl.style.opacity = d.key ? '1' : '0.4';
  }

  // Show/hide activation section
  var actSection = R('licActivateSection');
  if (actSection) {
    actSection.style.display = (d.tier === 'lifetime') ? 'none' : 'block';
  }
}

// ── AI Cards render ───────────────────────────────────────────────────────────
function _renderAiCards() {
  var container = R('aiSubsCards');
  if (!container) return;

  var html = '';
  AI_PROVIDERS.forEach(function(p) {
    var st  = _aiStatuses[p.id] || {};
    var sub = _aiSubs[p.id]     || {};
    var statusClass = st.status === 'ok' ? 'ai-dot-ok' : st.status === 'error' ? 'ai-dot-err' : 'ai-dot-none';
    var statusLabel = st.label || 'Перевірка...';

    html += '<div class="ai-sub-card" id="aiCard_' + p.id + '">'
      + '<div class="ai-sub-hdr">'
      +   '<span class="ai-sub-icon">' + p.icon + '</span>'
      +   '<div class="ai-sub-info">'
      +     '<div class="ai-sub-name">' + p.name + '</div>'
      +     '<div class="ai-sub-status"><span class="ai-dot ' + statusClass + '"></span>' + _escHtml(statusLabel) + '</div>'
      +   '</div>'
      +   '<div class="ai-sub-actions">'
      +     '<button class="btn btn-xs" onclick="aiSubEdit(\'' + p.id + '\')" title="Редагувати">✏️</button>'
      +     '<button class="btn btn-xs" onclick="window.__axisOpenUrl(\'' + p.url + '\')" title="Управляти">↗</button>'
      +   '</div>'
      + '</div>';

    if (sub.plan || sub.renewal || sub.cost) {
      html += '<div class="ai-sub-meta">';
      if (sub.plan)    html += '<span class="ai-meta-chip">📦 ' + _escHtml(sub.plan) + '</span>';
      if (sub.cost)    html += '<span class="ai-meta-chip">💰 ' + _escHtml(sub.cost) + '</span>';
      if (sub.renewal) html += '<span class="ai-meta-chip">📅 ' + _escHtml(sub.renewal) + '</span>';
      html += '</div>';
    }

    html += '</div>';
  });

  container.innerHTML = html;
}

// ── Edit provider modal ───────────────────────────────────────────────────────
function aiSubEdit(providerId) {
  _editProvider = providerId;
  var p   = AI_PROVIDERS.find(function(x){ return x.id === providerId; }) || {};
  var sub = _aiSubs[providerId] || {};

  var modal = R('aiSubModal');
  if (!modal) return;

  R('aiSubModalTitle').textContent  = (p.icon || '') + ' ' + (p.name || providerId);
  R('aiSubPlanInput').value         = sub.plan    || '';
  R('aiSubCostInput').value         = sub.cost    || '';
  R('aiSubRenewalInput').value      = sub.renewal || '';
  R('aiSubNotesInput').value        = sub.notes   || '';

  // Populate plan options
  var planSel = R('aiSubPlanInput');
  if (p.plans && planSel.tagName === 'SELECT') {
    planSel.innerHTML = '<option value="">— оберіть —</option>'
      + p.plans.map(function(pl){ return '<option value="'+pl+'"'+(sub.plan===pl?' selected':'')+'>'+pl+'</option>'; }).join('');
  }

  modal.style.display = 'flex';
}

function aiSubModalClose() {
  var modal = R('aiSubModal');
  if (modal) modal.style.display = 'none';
  _editProvider = null;
}

function aiSubModalSave() {
  if (!_editProvider) return;
  var data = {
    provider: _editProvider,
    plan:     (R('aiSubPlanInput')   || {}).value || '',
    cost:     (R('aiSubCostInput')   || {}).value || '',
    renewal:  (R('aiSubRenewalInput')|| {}).value || '',
    notes:    (R('aiSubNotesInput')  || {}).value || '',
  };
  _aiSubs[_editProvider] = data;
  pyCall('save_ai_subscription', JSON.stringify(data));
  aiSubModalClose();
  _renderAiCards();
}

// ── License activation ────────────────────────────────────────────────────────
function licActivate() {
  var inp = document.getElementById('licKeyInput') || document.getElementById('licKeyInput2');
  if (!inp) return;
  var key = inp.value.trim().toUpperCase();
  if (!key) return;
  // Validate format: AXIS-XXXX-XXXX-XXXX-XXXX
  if (!/^AXIS-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(key)) {
    showToast('⚠️ Невірний формат ключа. Очікується: AXIS-XXXX-XXXX-XXXX-XXXX');
    return;
  }
  inp.value = key; // normalize to uppercase
  pyCall('activate_license', JSON.stringify({ key: key }));
}

function licCheckKeys() {
  // Reset statuses to "checking"
  _aiStatuses = {};
  _renderAiCards();
  pyCall('check_ai_keys', '{}');
  showToast('🔍 Перевіряю ключі...');
}

// ── Plans info ────────────────────────────────────────────────────────────────
function showAxisPlans() {
  var modal = R('axisPlansModal');
  if (modal) modal.style.display = 'flex';
}
function axisPlansClose() {
  var modal = R('axisPlansModal');
  if (modal) modal.style.display = 'none';
}

// Helper: open URL via Python
window.__axisOpenUrl = function(url) {
  try { pyCall('open_file_path', JSON.stringify({ path: url })); } catch(e) {}
};

// ── axisPush integration ──────────────────────────────────────────────────────
(function() {
  var _orig = window.axisPush;
  window.axisPush = function(type, jsonStr) {
    try {
      var d = JSON.parse(jsonStr);
      if (type === 'license_status')   { handleLicenseStatus(d);   return; }
      if (type === 'license_result')   { handleLicenseResult(d);   return; }
      if (type === 'ai_subscriptions') { handleAiSubscriptions(d); return; }
      if (type === 'ai_key_statuses')  { handleAiKeyStatuses(d);   return; }
      if (type === 'ai_cost_stats')    { handleAiCostStats(d);     return; }
      if (type === 'proxy_stats')      { handleProxyStats(d);      return; }
    } catch(e) {}
    _orig && _orig(type, jsonStr);
  };
})();

// ── Hook into showPage ────────────────────────────────────────────────────────
(function() {
  var _orig = window.showPage;
  window.showPage = function(id) {
    _orig && _orig(id);
    if (id === 'license') {
      setTimeout(initLicensePage, 50);
    }
  };
})();
