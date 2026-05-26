/* AXIS OS ? Settings & API keys */
// ═══ API KEYS ═══
var apiProviders = {
  ai: [
    {ico:'🟢', name:'OpenAI',    desc:'GPT-4.1, o4-mini, DALL·E 3',      color:'#1e3a2e', dot:'#10a37f', id:'openai'},
    {ico:'🟠', name:'Anthropic', desc:'Claude Opus / Sonnet / Haiku',     color:'#3a2a1e', dot:'#cc785c', id:'anthropic'},
    {ico:'🔵', name:'Google AI', desc:'Gemini 2.5 Pro / Flash + Imagen',  color:'#1e2842', dot:'#4285f4', id:'google'},
    {ico:'⚫', name:'xAI',       desc:'Grok-3, Grok-3-mini',              color:'#1a1a2e', dot:'#888',    id:'xai'},
    {ico:'🌊', name:'DeepSeek',  desc:'DeepSeek-Chat, DeepSeek-Reasoner', color:'#0d1e3a', dot:'#1e90ff', id:'deepseek'},
    {ico:'🔍', name:'Perplexity',desc:'Sonar Pro — AI пошук в інтернеті', color:'#0d2a2a', dot:'#20b2aa', id:'perplexity'},
  ],
  media: [
    {ico:'🎬', name:'Luma AI',   desc:'Dream Machine — генерація відео',  color:'#1a0a2e', dot:'#9b59b6', id:'luma'},
  ],
  search: [
    {ico:'🌐', name:'Serper',    desc:'Google Search API — веб-пошук для AI', color:'#1a2e1a', dot:'#27ae60', id:'serper'},
    {ico:'🔎', name:'Tavily',    desc:'AI Search API — розумний пошук',    color:'#2e1a1a', dot:'#e67e22', id:'tavily'},
    {ico:'☁',  name:'OpenWeather',desc:'Реальна погода для сфери та панелі',color:'#1a2a3a', dot:'#3498db', id:'openweather'},
  ],
  services: [
    {ico:'🎵', name:'Spotify',   desc:'Client ID',     color:'#1a2e1a', dot:'#1db954', id:'spotify_client_id',     ph:'Client ID'},
    {ico:'🎵', name:'Spotify',   desc:'Client Secret', color:'#1a2e1a', dot:'#1db954', id:'spotify_client_secret', ph:'Client Secret'},
  ],
};

// ── API STATUS PANEL ──────────────────────────────────────────────────────
var _apiStatusMap = {
  openai:      {name:'OpenAI',       ico:'🟢', dot:'#10a37f'},
  anthropic:   {name:'Anthropic',    ico:'🟠', dot:'#cc785c'},
  google:      {name:'Google AI',    ico:'🔵', dot:'#4285f4'},
  xai:         {name:'xAI',          ico:'⚫', dot:'#aaa'},
  deepseek:    {name:'DeepSeek',     ico:'🌊', dot:'#1e90ff'},
  perplexity:  {name:'Perplexity',   ico:'🔍', dot:'#20b2aa'},
  luma:        {name:'Luma AI',      ico:'🎬', dot:'#9b59b6'},
  serper:      {name:'Serper',       ico:'🌐', dot:'#27ae60'},
  tavily:      {name:'Tavily',       ico:'🔎', dot:'#e67e22'},
  openweather: {name:'OpenWeather',  ico:'☁',  dot:'#3498db'},
  spotify:     {name:'Spotify',      ico:'🎵', dot:'#1db954'},
};

function checkApiStatus() {
  // Показуємо "перевірка..." на всіх
  var items = document.querySelectorAll('.asp-item');
  items.forEach(function(el) {
    el.querySelector('.asp-badge').textContent = '⟳';
    el.querySelector('.asp-badge').style.background = 'rgba(255,255,255,.06)';
    el.querySelector('.asp-badge').style.color = 'var(--text3)';
  });
  pyCall('check_api_status', '{}');
}

function _renderApiStatus(results) {
  var panel = R('apiStatusList');
  if (!panel) return;
  var html = '';
  Object.keys(_apiStatusMap).forEach(function(id) {
    var info = _apiStatusMap[id];
    var st = results[id] || 'missing';
    var badge, bdColor, dotColor;
    if (st === 'token') {
      badge = '✓ Активний'; bdColor = 'rgba(34,197,94,.15)'; dotColor = '#22c55e';
    } else if (st === 'set') {
      badge = '✓ Ключ задано'; bdColor = 'rgba(34,197,94,.1)'; dotColor = '#86efac';
    } else {
      badge = '✗ Не задано'; bdColor = 'rgba(239,68,68,.08)'; dotColor = '#ef4444';
    }
    html += '<div class="asp-item">'
      + '<span style="width:20px;text-align:center;flex-shrink:0;">'+info.ico+'</span>'
      + '<span class="asp-name">'+info.name+'</span>'
      + '<span class="asp-badge" style="background:'+bdColor+';color:'+(st==='missing'?'#f87171':'#86efac')+'">'+badge+'</span>'
      + '<span class="asp-dot" style="background:'+dotColor+'"></span>'
      + '</div>';
  });
  panel.innerHTML = html;
}

function initApi(){
  var list = R('apiList');
  if (!list) return;

  // ── Панель статусу підключень ──────────────────────────────────────────
  var statusPanel = '<div style="margin-bottom:18px;">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">'
    + '<span style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.08em;text-transform:uppercase;">🔗 Підключені сервіси</span>'
    + '<button class="btn btn-sm" onclick="checkApiStatus()" style="font-size:10px;padding:3px 10px;">🔄 Перевірити</button>'
    + '</div>'
    + '<div id="apiStatusList" style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">'
    + Object.keys(_apiStatusMap).map(function(id){
        var info = _apiStatusMap[id];
        return '<div class="asp-item">'
          + '<span style="width:20px;text-align:center;flex-shrink:0;">'+info.ico+'</span>'
          + '<span class="asp-name">'+info.name+'</span>'
          + '<span class="asp-badge" style="background:rgba(255,255,255,.04);color:var(--text3);">· · ·</span>'
          + '<span class="asp-dot" style="background:#333;"></span>'
          + '</div>';
      }).join('')
    + '</div></div>';

  function section(title, ico, items, footer) {
    var rows = items.map(function(a) {
      var ph = a.ph || 'sk-••••••••••••••••';
      return '<div class="api-row">'
        + '<div class="api-ico" style="background:'+a.color+'">'+a.ico+'</div>'
        + '<div class="api-info"><div class="api-name">'+a.name+'</div><div class="api-desc">'+a.desc+'</div></div>'
        + '<div class="api-dot" style="background:'+a.dot+'"></div>'
        + '<input type="password" id="key_'+a.id+'" placeholder="'+ph+'" style="max-width:230px;font-size:11px;">'
        + '<button class="btn btn-sm btn-p" onclick="saveApiKey(\''+a.id+'\',\''+a.name+'\')">💾</button>'
        + '<button class="btn btn-sm" onclick="toggleKeyVis(\'key_'+a.id+'\')" title="Показати/сховати">👁</button>'
        + '</div>';
    }).join('');
    return '<div style="margin-top:16px;">'
      + '<div style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px;">'+ico+' '+title+'</div>'
      + rows
      + (footer || '')
      + '</div>';
  }

  var spotifyConnect = '<div style="margin-top:8px;padding:10px 12px;border-radius:10px;'
    + 'border:1px solid rgba(29,185,84,.3);background:rgba(29,185,84,.07);'
    + 'display:flex;align-items:center;justify-content:space-between;gap:12px;">'
    + '<div>'
    + '<div style="font-size:12px;font-weight:700;color:#1db954;">🎵 Авторизація Spotify</div>'
    + '<div style="font-size:10px;color:var(--text3);margin-top:2px;">Збережи ключі вище, потім натисни Підключити</div>'
    + '</div>'
    + '<button class="btn btn-sm" style="background:rgba(29,185,84,.18);border-color:rgba(29,185,84,.5);'
    + 'color:#1db954;font-weight:700;font-size:12px;padding:6px 16px;white-space:nowrap;" '
    + 'onclick="pyCall(\'connect_spotify\',\'{}\')">'
    + '🔗 Підключити</button>'
    + '</div>';

  list.innerHTML = statusPanel
    + section('AI Провайдери',  '🤖', apiProviders.ai)
    + section('Медіа генерація','🎨', apiProviders.media)
    + section('Пошук та погода','🌐', apiProviders.search)
    + section('Сервіси',        '⚙',  apiProviders.services, spotifyConnect)
    + _buildTestPanel();

  // Автоматично перевіряємо при відкритті
  setTimeout(checkApiStatus, 400);
}

// ── UPDATER (local folder) ────────────────────────────────────────────────────
var _pendingUpdate = null;

function saveUpdateFolder() {
  var inp = R('updateFolderInp');
  if (!inp) return;
  pyCall('save_update_folder', JSON.stringify({folder: inp.value.trim()}));
}

function checkUpdate() {
  var inp = R('updateFolderInp');
  var lbl = R('updateStatusLbl');
  var btn = R('checkUpdateBtn');
  if (lbl) lbl.textContent = '⟳ Перевіряю...';
  if (btn) btn.disabled = true;
  var folder = inp ? inp.value.trim() : '';
  pyCall('check_update', JSON.stringify({folder: folder}));
}

function applyUpdate() {
  if (!_pendingUpdate) return;
  var btn = R('applyUpdateBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⟳ Встановлюю...'; }
  pyCall('apply_update', JSON.stringify(_pendingUpdate));
}

function handleUpdateStatus(d) {
  var lbl  = R('updateStatusLbl');
  var card = R('updateAvailableCard');
  var info = R('updateVerInfo');
  var btn  = R('checkUpdateBtn');
  var verLbl = R('appVerLbl');
  if (btn) btn.disabled = false;
  if (verLbl && d.current) verLbl.textContent = d.current;
  if (d.status === 'available') {
    _pendingUpdate = d;
    if (lbl)  lbl.textContent = '';
    if (card) card.style.display = 'block';
    if (info) info.textContent = 'Поточна: ' + d.current + '  →  Нова: ' + d.version;
  } else if (d.status === 'up_to_date') {
    _pendingUpdate = null;
    if (card) card.style.display = 'none';
    if (lbl)  lbl.textContent = '✓ Версія актуальна (' + d.current + ')';
  } else if (d.status === 'no_folder') {
    if (lbl) lbl.textContent = '⚠ Вкажіть папку оновлень';
  }
}

// ── UPDATER (GitHub Releases) ─────────────────────────────────────────────────
var _ghPending = null;
var _ghChangelogVisible = false;

function ghRepoChanged() {
  // скидаємо картку при зміні репо
  var card = R('ghAvailCard'); if (card) card.style.display = 'none';
  var err  = R('ghErrorCard'); if (err)  err.style.display  = 'none';
  var lbl  = R('ghStatusLbl'); if (lbl)  lbl.textContent    = '';
  _ghPending = null;
}

function saveAutoUpdate(enabled) {
  pyCall('save_config', JSON.stringify({auto_update: enabled}));
  showToast(enabled ? '🔔 Авто-перевірка увімкнена' : '🔕 Авто-перевірка вимкнена');
}

function checkGithubUpdate() {
  var inp = R('githubRepoInp');
  var repo = inp ? inp.value.trim() : '';
  if (!repo) {
    showToast('⚠ Введіть репозиторій (owner/repo)');
    return;
  }
  var lbl = R('ghStatusLbl');
  var btn = R('ghCheckBtn');
  if (lbl) lbl.textContent = '⟳ Перевіряю GitHub...';
  if (btn) btn.disabled = true;
  var card = R('ghAvailCard'); if (card) card.style.display = 'none';
  var err  = R('ghErrorCard'); if (err)  err.style.display  = 'none';
  pyCall('check_github_update', JSON.stringify({repo: repo}));
}

function toggleGhChangelog() {
  _ghChangelogVisible = !_ghChangelogVisible;
  var el  = R('ghChangelog');
  var btn = R('ghChangelogBtn');
  if (el)  el.style.display = _ghChangelogVisible ? 'block' : 'none';
  if (btn) btn.textContent  = _ghChangelogVisible ? '📋 Сховати' : '📋 Зміни';
}

function handleGithubUpdateStatus(d) {
  var lbl  = R('ghStatusLbl');
  var btn  = R('ghCheckBtn');
  var card = R('ghAvailCard');
  var errC = R('ghErrorCard');
  var errM = R('ghErrorMsg');
  var verLbl = R('appVerLbl');
  if (btn) btn.disabled = false;
  if (verLbl && d.current) verLbl.textContent = d.current;

  if (d.status === 'available') {
    _ghPending = d;
    if (lbl)  lbl.textContent = '';
    if (errC) errC.style.display = 'none';
    if (card) card.style.display = 'block';

    // Badge на кнопці "Налаштування" в сайдбарі
    var navSettings = document.querySelector('.nav-btn[data-page="settings"]');
    if (navSettings && !navSettings.querySelector('.update-badge')) {
      var badge = document.createElement('span');
      badge.className = 'update-badge';
      badge.title = 'Доступне оновлення v' + d.version;
      badge.style.cssText = 'display:inline-block;width:8px;height:8px;border-radius:50%;' +
        'background:#34d399;margin-left:6px;box-shadow:0 0 6px #34d399;flex-shrink:0;';
      navSettings.appendChild(badge);
    }

    // Якщо авто-перевірка — показуємо тост
    if (d._auto) {
      showToast('🆕 Доступне оновлення v' + d.version + ' — зайди в Налаштування', 5000);
    }

    var verInfo = R('ghVerInfo');
    if (verInfo) verInfo.textContent = 'Поточна: v' + d.current + '  →  Нова: v' + d.version;

    var dateInfo = R('ghDateInfo');
    if (dateInfo && d.published_at) {
      var dt = new Date(d.published_at);
      dateInfo.textContent = '📅 Опубліковано: ' + dt.toLocaleDateString('uk-UA');
    }

    var link = R('ghReleaseLink');
    if (link && d.release_url) link.href = d.release_url;

    var log = R('ghChangelog');
    if (log) {
      log.textContent = d.body || '(немає опису)';
      log.style.display = 'none';
    }
    _ghChangelogVisible = false;
    var logBtn = R('ghChangelogBtn');
    if (logBtn) logBtn.textContent = '📋 Зміни';

    // Кнопки завантаження для кожного asset
    var wrap = R('ghAssetsWrap');
    if (wrap) {
      var assets = d.assets || [];
      if (assets.length === 0) {
        // Немає assets — тільки посилання на реліз
        wrap.innerHTML = '<span style="font-size:11px;color:var(--text3);">Асети відсутні — відкрийте сторінку релізу</span>';
      } else {
        var html = '';
        assets.forEach(function(a) {
          var sizeMb = a.size ? (a.size / 1024 / 1024).toFixed(1) + ' MB' : '';
          html += '<button class="btn btn-sm btn-p" onclick="downloadGhAsset(' +
            JSON.stringify(a.url) + ',' + JSON.stringify(a.name) + ')">' +
            '⬇ ' + escH(a.name) + (sizeMb ? ' <span style="opacity:.6;font-size:10px;">(' + sizeMb + ')</span>' : '') +
            '</button>';
        });
        wrap.innerHTML = html;
      }
    }
    R('ghProgressWrap').style.display = 'none';

  } else if (d.status === 'up_to_date') {
    _ghPending = null;
    if (card) card.style.display = 'none';
    if (errC) errC.style.display = 'none';
    if (lbl)  lbl.textContent = '✅ Версія актуальна (v' + d.current + ')';

  } else if (d.status === 'no_repo') {
    if (lbl) lbl.textContent = '⚠ Вкажіть репозиторій';

  } else if (d.status === 'error') {
    if (card) card.style.display = 'none';
    if (errC) { errC.style.display = 'block'; }
    if (errM) errM.textContent = '❌ ' + (d.error || 'Невідома помилка');
    if (lbl)  lbl.textContent = '';
  }
}

function downloadGhAsset(url, name) {
  if (!url) return;
  var pw = R('ghProgressWrap');
  var pb = R('ghProgressBar');
  var pl = R('ghProgressLbl');
  if (pw) pw.style.display = 'block';
  if (pb) pb.style.width = '0%';
  if (pl) pl.textContent = '⬇ Завантажую ' + name + '...';
  // Блокуємо кнопки assets
  var wrap = R('ghAssetsWrap');
  if (wrap) wrap.querySelectorAll('button').forEach(function(b){ b.disabled = true; });
  pyCall('download_github_update', JSON.stringify({url: url, version: _ghPending ? _ghPending.version : ''}));
}

function handleGithubDownloadStatus(d) {
  var pb = R('ghProgressBar');
  var pl = R('ghProgressLbl');
  var pw = R('ghProgressWrap');

  if (d.status === 'downloading') {
    if (pw) pw.style.display = 'block';
    var pct = d.pct || 0;
    if (pb) { pb.style.width = pct + '%'; pb.style.background = 'var(--accent)'; }
    var done  = d.done  ? (d.done  / 1024 / 1024).toFixed(1) + ' MB' : '';
    var total = d.total ? (d.total / 1024 / 1024).toFixed(1) + ' MB' : '';
    if (pl) pl.textContent = (d.label ? d.label + '  ' : '') +
        (done && total ? done + ' / ' + total + ' (' + pct + '%)' : (pct ? pct + '%' : ''));

  } else if (d.status === 'applying') {
    if (pb) { pb.style.width = '100%'; pb.style.background = 'var(--accent)'; }
    if (pl) pl.textContent = d.label || '📂 Копіюю файли...';

  } else if (d.status === 'pip') {
    if (pb) { pb.style.width = '100%'; pb.style.background = '#a78bfa'; }
    if (pl) pl.textContent = d.label || '📦 Встановлюю нові пакети...';

  } else if (d.status === 'restarting') {
    if (pb) { pb.style.width = '100%'; pb.style.background = '#34d399'; }
    if (pl) pl.textContent = '✅ Готово! Перезапускаю AXIS OS...';

  } else if (d.status === 'error') {
    if (pl) pl.textContent = '❌ ' + (d.error || 'Помилка завантаження');
    if (pb) { pb.style.width = '0%'; pb.style.background = '#ef4444'; }
    var wrap = R('ghAssetsWrap');
    if (wrap) wrap.querySelectorAll('button').forEach(function(b){ b.disabled = false; });
  }
}

function toggleKeyVis(id) {
  var inp = R(id);
  if (!inp) return;
  inp.type = (inp.type === 'password') ? 'text' : 'password';
}

function saveApiKey(provider, name){
  var key = R('key_'+provider);
  if (!key || !key.value.trim()) { showToast('Введіть ключ для ' + name); return; }
  pyCall('save_api_key', JSON.stringify({provider: provider, key: key.value.trim()}));
  showToast('✓ ' + name + ' ключ збережено');
  key.value = '';
  // Refresh status panel — show "checking" immediately
  var items = document.querySelectorAll('.asp-item');
  items.forEach(function(el) {
    var badge = el.querySelector('.asp-badge');
    if (badge) { badge.textContent = '⟳'; badge.style.background='rgba(255,255,255,.06)'; badge.style.color='var(--text3)'; }
  });
}

// ═══ ACCENT ═══
function setAccent(a, b){
  document.documentElement.style.setProperty('--accent',a);
  document.documentElement.style.setProperty('--indigo',b);
  pyCall('save_config', JSON.stringify({accent_color: a, accent_color2: b}));
  showToast('Колір змінено');
}

// ═══ SPHERE VISUALIZATION PICKER ═══
function switchVizTab(el, id) {
  el.closest('.sgroup').querySelectorAll('.viz-tab').forEach(function(t){ t.classList.remove('active'); });
  el.classList.add('active');
  ['viz-round','viz-wave','viz-music'].forEach(function(k){
    var el2 = R(k); if (el2) el2.style.display = (k === id) ? 'grid' : 'none';
  });
}

// Кольори для кожного стилю сфери
var VIZ_COLORS = {
  'plasma':         ['#00d4ff', '#0369a1'],
  'energy':         ['#a855f7', '#4c1d95'],
  'neon':           ['#00ffff', '#0ea5e9'],
  'fire':           ['#f97316', '#7c2d12'],
  'galaxy':         ['#818cf8', '#1e1b4b'],
  'matrix_viz':     ['#4ade80', '#052e16'],
  'holo':           ['#94d8fb', '#1e293b'],
  'dark':           ['#ef4444', '#450a0a'],
  'wave-ocean':     ['#06b6d4', '#0c4a6e'],
  'wave-forest':    ['#22c55e', '#14532d'],
  'wave-aurora':    ['#a855f7', '#4c1d95'],
  'wave-sunset':    ['#f97316', '#991b1b'],
  'music-bars':     ['#22c55e', '#064e3b'],
  'music-pulse':    ['#a855f7', '#1e1b4b'],
  'music-spectrum': ['#06b6d4', '#4f46e5'],
  'music-sine':     ['#22c55e', '#06070d'],
};

function selectViz(card) {
  document.querySelectorAll('.viz-card').forEach(function(c){ c.classList.remove('active'); });
  card.classList.add('active');
  var viz = card.dataset.viz;
  var cols = VIZ_COLORS[viz] || ['#00d4ff', '#7b2cbf'];
  // Оновити пікери кольорів
  var c1el = R('sp_color'), c2el = R('sp_color2');
  var v1el = R('sp_color_val'), v2el = R('sp_color2_val');
  if (c1el) { c1el.value = cols[0]; if(v1el) v1el.textContent = cols[0]; }
  if (c2el) { c2el.value = cols[1]; if(v2el) v2el.textContent = cols[1]; }
  // Зберегти стиль + кольори в sphere_config.json через save_sphere
  pyCall('save_sphere', JSON.stringify({
    sphere_visual: viz,
    sphere_color:  cols[0],
    sphere_color2: cols[1]
  }));
  showToast('✓ Стиль «' + card.querySelector('.viz-name').textContent + '» застосовано');
}

// ═══ PANEL THEMES ═══
var THEMES = {
  cyberneon: {bg:'#04050a', bg2:'#0a0f1e', accent:'#22c55e', indigo:'#6366f1', text:'#e2e8f0', border:'rgba(255,255,255,.07)'},
  aurora:    {bg:'#07040f', bg2:'#0f0a1e', accent:'#a855f7', indigo:'#ec4899', text:'#e2e8f0', border:'rgba(255,255,255,.07)'},
  matrix:    {bg:'#020702', bg2:'#030d03', accent:'#22c55e', indigo:'#4ade80', text:'#dcfce7', border:'rgba(34,197,94,.1)'},
  minimal:   {bg:'#141414', bg2:'#1e1e1e', accent:'#9ca3af', indigo:'#6b7280', text:'#d1d5db', border:'rgba(255,255,255,.08)'},
  sunset:    {bg:'#0f0602', bg2:'#1a0e04', accent:'#f97316', indigo:'#ec4899', text:'#fed7aa', border:'rgba(249,115,22,.1)'},
  ocean:     {bg:'#020810', bg2:'#030d1a', accent:'#06b6d4', indigo:'#0ea5e9', text:'#bae6fd', border:'rgba(6,182,212,.1)'},
  volcano:   {bg:'#0f0202', bg2:'#1a0304', accent:'#ef4444', indigo:'#f97316', text:'#fecaca', border:'rgba(239,68,68,.1)'},
  forest:    {bg:'#020702', bg2:'#040d04', accent:'#4ade80', indigo:'#22c55e', text:'#dcfce7', border:'rgba(74,222,128,.1)'},
  galaxy:    {bg:'#07060f', bg2:'#0f0a1e', accent:'#6366f1', indigo:'#a855f7', text:'#e0e7ff', border:'rgba(99,102,241,.1)'},
  candy:     {bg:'#0f0209', bg2:'#1a0514', accent:'#ec4899', indigo:'#f97316', text:'#fce7f3', border:'rgba(236,72,153,.1)'},
  darkpro:   {bg:'#0a0a0a', bg2:'#111111', accent:'#64748b', indigo:'#475569', text:'#cbd5e1', border:'rgba(255,255,255,.06)'},
  ice:       {bg:'#f0f9ff', bg2:'#e0f2fe', accent:'#0891b2', indigo:'#0e7490', text:'#0c4a6e', border:'rgba(8,145,178,.15)'}
};
var _activeTheme = 'cyberneon';

function applyTheme(card) {
  var theme = card.dataset.theme;
  var t = THEMES[theme]; if (!t) return;
  _activeTheme = theme;
  document.querySelectorAll('#themeGrid .theme-card').forEach(function(c){ c.classList.remove('active'); });
  card.classList.add('active');
  var root = document.documentElement;
  root.style.setProperty('--bg',     t.bg);
  root.style.setProperty('--bg2',    t.bg2);
  root.style.setProperty('--accent', t.accent);
  root.style.setProperty('--indigo', t.indigo);
  root.style.setProperty('--text',   t.text);
  root.style.setProperty('--border', t.border);
  pyCall('save_config', JSON.stringify({theme: theme, accent_color: t.accent, accent_color2: t.indigo}));
  showToast('✓ Тема «' + card.querySelector('.theme-name').textContent + '» застосована');
}

function loadSavedTheme(themeName) {
  if (!themeName || !THEMES[themeName]) return;
  _activeTheme = themeName;
  var t = THEMES[themeName];
  var root = document.documentElement;
  root.style.setProperty('--bg',     t.bg);
  root.style.setProperty('--bg2',    t.bg2);
  root.style.setProperty('--accent', t.accent);
  root.style.setProperty('--indigo', t.indigo);
  root.style.setProperty('--text',   t.text);
  root.style.setProperty('--border', t.border);
  var card = document.querySelector('#themeGrid .theme-card[data-theme="'+themeName+'"]');
  if (card) {
    document.querySelectorAll('#themeGrid .theme-card').forEach(function(c){ c.classList.remove('active'); });
    card.classList.add('active');
  }
}

// ═══ MIC DEVICE + STT SENSITIVITY ═══
var _micSettings = JSON.parse(localStorage.getItem('axis_mic') || '{"deviceIndex":-1,"deviceLabel":"","sensitivity":50}');

function loadMicDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
    pyCall('list_mic_devices', '{}');
    return;
  }
  navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){
    stream.getTracks().forEach(function(t){t.stop();});
    return navigator.mediaDevices.enumerateDevices();
  }).then(function(devices){
    var sel = R('micDeviceSel'); if (!sel) return;
    var inputs = devices.filter(function(d){ return d.kind === 'audioinput'; });
    sel.innerHTML = '<option value="-1">🎤 За замовчуванням</option>' +
      inputs.map(function(d,i){
        var label = d.label || ('Мікрофон ' + (i+1));
        var sel_ = (_micSettings.deviceLabel && d.label === _micSettings.deviceLabel) ? ' selected' : '';
        return '<option value="'+i+'"'+sel_+'>'+label+'</option>';
      }).join('');
    if (_micSettings.deviceIndex >= 0) sel.value = _micSettings.deviceIndex;
    showToast('✓ Знайдено ' + inputs.length + ' мікрофонів');
  }).catch(function(){ pyCall('list_mic_devices', '{}'); });
}

function saveMicSettings() {
  var sel  = R('micDeviceSel');
  var sens = R('sttSensitivity');
  _micSettings = {
    deviceIndex: sel  ? parseInt(sel.value)  : -1,
    deviceLabel: sel  ? (sel.options[sel.selectedIndex]||{}).text||'' : '',
    sensitivity: sens ? parseInt(sens.value) : 50,
  };
  localStorage.setItem('axis_mic', JSON.stringify(_micSettings));
}

function loadMicSettingsUI() {
  var sens = R('sttSensitivity');
  if (sens) { sens.value = _micSettings.sensitivity || 50; R('sttSensVal').textContent = sens.value; }
  loadMicDevices();
}

// ═══ APP VOLUME ═══
var _appVolume = parseInt(localStorage.getItem('axis_app_volume') || '100');

function setAppVolume(val) {
  _appVolume = parseInt(val);
  R('appVolVal').textContent = val;
  localStorage.setItem('axis_app_volume', String(_appVolume));
  document.querySelectorAll('audio,video').forEach(function(el){ el.volume = _appVolume/100; });
}

function loadAppVolumeUI() {
  var sl = R('appVolume');
  if (sl) { sl.value = _appVolume; R('appVolVal').textContent = _appVolume; }
}

// ═══ UI LANGUAGE ═══
var _UI_LANGS = {
  uk: {settings:'НАЛАШТУВАННЯ',general:'Загальні',ai:'AI',sphere:'🔮 Сфера',appear:'Вигляд',about:'Про систему'},
  en: {settings:'SETTINGS',general:'General',ai:'AI',sphere:'🔮 Sphere',appear:'Appearance',about:'About'},
  ru: {settings:'НАСТРОЙКИ',general:'Основные',ai:'AI',sphere:'🔮 Сфера',appear:'Вид',about:'О системе'},
};
var _uiLang = localStorage.getItem('axis_ui_lang') || 'uk';

function applyUiLanguage(lang) {
  _uiLang = lang || _uiLang;
  localStorage.setItem('axis_ui_lang', _uiLang);
  var L = _UI_LANGS[_uiLang] || _UI_LANGS.uk;
  var tabs = document.querySelectorAll('#settingsPage .tabs .tab');
  var keys = ['general','ai','sphere','appear','about'];
  tabs.forEach(function(t,i){ if(keys[i] && L[keys[i]]) t.textContent = L[keys[i]]; });
  var title = document.querySelector('#settingsPage .page-title');
  if (title) title.textContent = L.settings;
  if (R('uiLang')) R('uiLang').value = _uiLang;
}

// ═══ COMMAND EXECUTION SETTINGS ═══
var _cmdExecCfg = JSON.parse(localStorage.getItem('axis_cmd_exec') || '{"chainWords":"і,та,потім,затем,then,and","confirmPhrases":"так,правильно,підтверджую,yes","cancelPhrases":"ні,відміна,скасувати,no","stopPhrase":"зупини команду","autoCancel":30,"overlay":true,"overlayPos":"tl"}');

function saveCmdExecSettings() {
  _cmdExecCfg = {
    chainWords:     (R('cmdChainWords')    ||{}).value || 'і,та,потім,затем',
    confirmPhrases: (R('cmdConfirmPhrases')||{}).value || 'так,правильно,підтверджую',
    cancelPhrases:  (R('cmdCancelPhrases') ||{}).value || 'ні,відміна,скасувати',
    stopPhrase:     (R('cmdStopPhrase')    ||{}).value || 'зупини команду',
    autoCancel:     parseInt((R('cmdAutoCancel')||{}).value) || 30,
    overlay:        R('cmdOverlayEnabled') ? R('cmdOverlayEnabled').checked : true,
    overlayPos:     _cmdExecCfg.overlayPos || 'tl',
  };
  localStorage.setItem('axis_cmd_exec', JSON.stringify(_cmdExecCfg));
}

function loadCmdExecSettings() {
  if (R('cmdChainWords'))     R('cmdChainWords').value     = _cmdExecCfg.chainWords     || 'і,та,потім,затем';
  if (R('cmdConfirmPhrases')) R('cmdConfirmPhrases').value = _cmdExecCfg.confirmPhrases || 'так,правильно,підтверджую';
  if (R('cmdCancelPhrases'))  R('cmdCancelPhrases').value  = _cmdExecCfg.cancelPhrases  || 'ні,відміна,скасувати';
  if (R('cmdStopPhrase'))     R('cmdStopPhrase').value     = _cmdExecCfg.stopPhrase     || 'зупини команду';
  if (R('cmdAutoCancel'))     R('cmdAutoCancel').value     = _cmdExecCfg.autoCancel     || 30;
  if (R('cmdOverlayEnabled')) R('cmdOverlayEnabled').checked = _cmdExecCfg.overlay !== false;
  // restore active pos button
  document.querySelectorAll('.overlay-pos-btn').forEach(function(b){
    b.classList.toggle('active', b.dataset.pos === (_cmdExecCfg.overlayPos||'tl'));
  });
  toggleOverlayPosRow();
}

function selectOverlayPos(btn) {
  document.querySelectorAll('.overlay-pos-btn').forEach(function(b){ b.classList.remove('active'); });
  btn.classList.add('active');
  _cmdExecCfg.overlayPos = btn.dataset.pos;
  localStorage.setItem('axis_cmd_exec', JSON.stringify(_cmdExecCfg));
}

function toggleOverlayPosRow() {
  var row = R('cmdOverlayPosRow');
  if (row) row.style.display = (R('cmdOverlayEnabled') && R('cmdOverlayEnabled').checked) ? 'flex' : 'none';
}

// ═══ AUTO-SLEEP ═══
var _autoSleepCfg = JSON.parse(localStorage.getItem('axis_autosleep') || '{"enabled":false,"timeout":5,"dim":true,"wakeClick":true}');
var _sleepTimer = null;
var _dimOverlay = null;

function saveAutoSleep() {
  _autoSleepCfg = {
    enabled:   R('autoSleepEnabled') ? R('autoSleepEnabled').checked : false,
    timeout:   R('autoSleepTimeout') ? parseInt(R('autoSleepTimeout').value) : 5,
    dim:       R('autoSleepDim')     ? R('autoSleepDim').checked     : true,
    wakeClick: R('autoSleepWakeClick') ? R('autoSleepWakeClick').checked : true,
  };
  localStorage.setItem('axis_autosleep', JSON.stringify(_autoSleepCfg));
  resetSleepTimer();
}

function loadAutoSleepSettings() {
  if (R('autoSleepEnabled'))   R('autoSleepEnabled').checked    = !!_autoSleepCfg.enabled;
  if (R('autoSleepTimeout'))   R('autoSleepTimeout').value      = _autoSleepCfg.timeout || 5;
  if (R('autoSleepDim'))       R('autoSleepDim').checked        = _autoSleepCfg.dim !== false;
  if (R('autoSleepWakeClick')) R('autoSleepWakeClick').checked  = _autoSleepCfg.wakeClick !== false;
}

function resetSleepTimer() {
  clearTimeout(_sleepTimer);
  if (!_autoSleepCfg.enabled) return;
  _sleepTimer = setTimeout(function() {
    if (_autoSleepCfg.dim) showDimOverlay();
    else pyCall('minimize_window', '{}');
  }, _autoSleepCfg.timeout * 60 * 1000);
}

function showDimOverlay() {
  if (_dimOverlay) return;
  _dimOverlay = document.createElement('div');
  _dimOverlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:99999;display:flex;align-items:center;justify-content:center;cursor:pointer;backdrop-filter:blur(8px);';
  _dimOverlay.innerHTML = '<div style="text-align:center;color:rgba(255,255,255,.3);"><div style="font-size:32px;margin-bottom:8px;">🌙</div><div style="font-size:13px;">AXIS OS — сплячий режим</div><div style="font-size:11px;margin-top:4px;opacity:.6;">Натисніть або рухайте мишу для пробудження</div></div>';
  if (_autoSleepCfg.wakeClick) _dimOverlay.addEventListener('click', wakeFromSleep);
  document.body.appendChild(_dimOverlay);
}

function wakeFromSleep() {
  if (_dimOverlay) { document.body.removeChild(_dimOverlay); _dimOverlay = null; }
  resetSleepTimer();
}

['mousemove','keydown','click','touchstart'].forEach(function(ev) {
  document.addEventListener(ev, function() { if (_autoSleepCfg.enabled) resetSleepTimer(); }, {passive:true});
});

// ═══ IMPORT / EXPORT ═══
function exportAllData() {
  var data = {
    version: '1.0',
    exported: new Date().toISOString(),
    settings: JSON.parse(localStorage.getItem('axis_config') || '{}'),
    commands: JSON.parse(localStorage.getItem('axis_commands') || '[]'),
    roles:    JSON.parse(localStorage.getItem('axis_roles')    || '[]'),
    macros:   JSON.parse(localStorage.getItem('axis_macros')   || '[]'),
    notif:    _notifSettings,
    hotkeys:  _hotkeys,
    autosleep: _autoSleepCfg,
    chat_cfg: _chatSettings,
  };
  var blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'axis_backup_' + new Date().toISOString().slice(0,10) + '.json';
  a.click();
  showToast('✓ Дані експортовано');
}

function exportChatHistory() {
  if (!chatMessages.length) { showToast('⚠ Чат порожній'); return; }
  var text = chatMessages.map(function(m) {
    return '[' + m.role.toUpperCase() + ']\n' + m.content;
  }).join('\n\n---\n\n');
  var blob = new Blob([text], {type:'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'axis_chat_' + new Date().toISOString().slice(0,10) + '.txt';
  a.click();
  showToast('✓ Чат збережено');
}

function importAllData(input) {
  var file = input.files[0]; if (!file) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    try {
      var data = JSON.parse(e.target.result);
      if (data.commands) localStorage.setItem('axis_commands', JSON.stringify(data.commands));
      if (data.roles)    localStorage.setItem('axis_roles',    JSON.stringify(data.roles));
      if (data.macros)   localStorage.setItem('axis_macros',   JSON.stringify(data.macros));
      if (data.notif)    { _notifSettings = data.notif; localStorage.setItem('axis_notif', JSON.stringify(data.notif)); loadNotifSettings(); }
      if (data.hotkeys)  { _hotkeys = data.hotkeys; localStorage.setItem('axis_hotkeys', JSON.stringify(data.hotkeys)); loadHotkeyInputs(); }
      if (data.autosleep){ _autoSleepCfg = data.autosleep; localStorage.setItem('axis_autosleep', JSON.stringify(data.autosleep)); loadAutoSleepSettings(); }
      showToast('✓ Дані імпортовано. Перезапустіть для повного застосування.');
    } catch(ex) { showToast('⚠ Помилка читання файлу'); }
  };
  reader.readAsText(file);
  input.value = '';
}

function clearAllData() {
  if (!confirm('Видалити ВСІ дані? Команди, ролі, налаштування будуть стерті.')) return;
  ['axis_commands','axis_roles','axis_macros','axis_notif','axis_hotkeys','axis_autosleep','axis_config','axis_chat_settings','axis_stats','axis_chat_history','axis_clip_history','axis_activity','axis_todos'].forEach(function(k){ localStorage.removeItem(k); });
  showToast('🗑 Всі дані видалено. Перезапустіть.');
}

// ═══ AUTOSTART ═══
function setAutostartCard(cardId, badgeId, enabled) {
  var card  = R(cardId);
  var badge = R(badgeId);
  if (card)  { card.classList.toggle('on', enabled); }
  if (badge) {
    badge.className = 'autostart-badge ' + (enabled ? 'on' : 'off');
    badge.textContent = enabled ? '● УВІМКНЕНО' : '○ ВИМКНЕНО';
  }
}

function toggleAxisAutostart() {
  var cur = R('axis_autostart_card') && R('axis_autostart_card').classList.contains('on');
  pyCall('toggle_axis_autostart', JSON.stringify({enabled: !cur}));
}

function toggleSphereAutostart() {
  var cur = R('sphere_autostart_card') && R('sphere_autostart_card').classList.contains('on');
  pyCall('toggle_sphere_autostart', JSON.stringify({enabled: !cur}));
}

// ═══ LIVE API KEY TESTS ═══════════════════════════════════════════════════════
var _apiTestRunning = false;

function runApiTests() {
  if (_apiTestRunning) return;
  _apiTestRunning = true;
  var btn = R('runApiTestsBtn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Перевіряю...'; }
  // Reset all rows to "waiting"
  document.querySelectorAll('.api-test-row').forEach(function(row) {
    row.querySelector('.atr-status').innerHTML = '<span class="atr-dot atr-wait"></span>';
    row.querySelector('.atr-msg').textContent = '—';
  });
  pyCall('run_api_tests', '{}');
}

function handleApiTestResult(d) {
  var row = R('atr_' + d.id);
  if (!row) {
    // Row might not exist if API was added later — insert it
    _ensureTestRow(d.id, d.name, d.ico);
    row = R('atr_' + d.id);
  }
  if (!row) return;

  var statusEl = row.querySelector('.atr-status');
  var msgEl    = row.querySelector('.atr-msg');

  var dotClass, icon;
  if      (d.status === 'ok')      { dotClass = 'atr-ok';      icon = '✅'; }
  else if (d.status === 'error')   { dotClass = 'atr-err';     icon = '❌'; }
  else if (d.status === 'no_key')  { dotClass = 'atr-nokey';   icon = '⚪'; }
  else if (d.status === 'testing') { dotClass = 'atr-testing'; icon = '⏳'; }
  else                             { dotClass = 'atr-wait';    icon = '—'; }

  statusEl.innerHTML = '<span class="atr-dot ' + dotClass + '"></span>' + icon;
  msgEl.textContent  = d.msg || '';
}

function handleApiTestsDone() {
  _apiTestRunning = false;
  var btn = R('runApiTestsBtn');
  if (btn) { btn.disabled = false; btn.textContent = '🔬 Запустити тести'; }
  showToast('✅ Тести завершено');
}

function _ensureTestRow(id, name, ico) {
  var tbody = R('apiTestsTbody');
  if (!tbody || R('atr_' + id)) return;
  var tr = document.createElement('tr');
  tr.id = 'atr_' + id;
  tr.className = 'api-test-row';
  tr.innerHTML = '<td class="atr-ico">' + (ico||'🔑') + '</td>'
    + '<td class="atr-name">' + _escHtml(name||id) + '</td>'
    + '<td class="atr-status"><span class="atr-dot atr-wait"></span>—</td>'
    + '<td class="atr-msg">—</td>';
  tbody.appendChild(tr);
}

// Build the test panel HTML
function _buildTestPanel() {
  var rows = [
    {id:'openai',      name:'OpenAI GPT',        ico:'🤖'},
    {id:'anthropic',   name:'Anthropic Claude',  ico:'🔵'},
    {id:'google',      name:'Google Gemini',     ico:'✨'},
    {id:'xai',         name:'xAI Grok',          ico:'⚡'},
    {id:'perplexity',  name:'Perplexity',        ico:'🌐'},
    {id:'tavily',      name:'Tavily Search',     ico:'🔍'},
    {id:'serper',      name:'Google Serper',     ico:'🔎'},
    {id:'openweather', name:'OpenWeather',       ico:'🌤'},
    {id:'ollama',      name:'Ollama (local)',    ico:'🖥'},
  ].map(function(r) {
    return '<tr id="atr_' + r.id + '" class="api-test-row">'
      + '<td class="atr-ico">' + r.ico + '</td>'
      + '<td class="atr-name">' + r.name + '</td>'
      + '<td class="atr-status"><span class="atr-dot atr-wait"></span>—</td>'
      + '<td class="atr-msg">Не перевірено</td>'
      + '</tr>';
  }).join('');

  return '<div class="api-tests-panel" style="margin-top:24px;">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">'
    + '<span style="font-size:11px;font-weight:700;color:var(--text3);letter-spacing:.08em;text-transform:uppercase;">🧪 Тестування ключів</span>'
    + '<button id="runApiTestsBtn" class="btn btn-sm btn-p" onclick="runApiTests()">🔬 Запустити тести</button>'
    + '</div>'
    + '<table class="api-tests-table"><tbody id="apiTestsTbody">' + rows + '</tbody></table>'
    + '<div style="font-size:10px;color:var(--text3);margin-top:8px;">Кожен ключ перевіряється реальним запитом до API</div>'
    + '</div>';
}

// Inject axisPush handler for test results
(function() {
  var _orig = window.axisPush;
  window.axisPush = function(type, jsonStr) {
    try {
      var d = JSON.parse(jsonStr);
      if (type === 'api_test_result') { handleApiTestResult(d); return; }
      if (type === 'api_tests_done')  { handleApiTestsDone();   return; }
    } catch(e) {}
    _orig && _orig(type, jsonStr);
  };
})();
