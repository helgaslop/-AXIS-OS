/* AXIS OS ? Commands & macros */
// ═══ MACROS ═══
var macros = [
  {ico:'🚀',name:'Запустити скрипт',key:'Ctrl+F5',command:'python main.py',type:'shell'},
  {ico:'🧹',name:'Очистити кеш',key:'Ctrl+Shift+Del',command:'clear_cache',type:'internal'},
  {ico:'📊',name:'Звіт системи',key:'Ctrl+Shift+R',command:'system_report',type:'internal'},
];

function initMacros(){
  var list=R('macroList');
  if(!list) return;
  list.innerHTML=macros.map(function(m){
    return '<div class="macro-card"><div class="macro-ico">'+m.ico+'</div><div class="macro-info"><div class="macro-name">'+m.name+'</div><div class="macro-key"><span class="hotkey">'+m.key+'</span></div></div><button class="btn btn-sm" onclick="event.stopPropagation();runMacro(this)" data-cmd="'+m.command+'" data-type="'+m.type+'" data-name="'+m.name+'">▶</button></div>';
  }).join('');
}

function runMacro(btn){
  pyCall('run_macro', JSON.stringify({command:btn.dataset.cmd, type:btn.dataset.type}));
  showToast('▶ '+btn.dataset.name);
}

function openMacroModal(){ R('macroModal').classList.add('show'); }
function closeMacroModal(){ R('macroModal').classList.remove('show'); }
function saveMacro(){
  var n=R('macroName').value.trim(), k=R('macroKey').value.trim(), c=R('macroCmd').value.trim();
  if(n && c){
    macros.push({ico:'⚡',name:n,key:k||'—',command:c,type:'shell'});
    initMacros(); showToast('Макрос «'+n+'» збережено');
    pyCall('save_macros', JSON.stringify({macros: macros}));
  }
  closeMacroModal();
}

// ═══ COMMAND PALETTE ═══
var palCmds=[
  {ico:'⬡',label:'Головна',fn:function(){showPage('dashboard');}},
  {ico:'📊',label:'Системний монітор',fn:function(){showPage('monitor');}},
  {ico:'🤖',label:'Агенти',fn:function(){showPage('agents');}},
  {ico:'💬',label:'AI Чат',fn:function(){showPage('chat');}},
  {ico:'💻',label:'IDE',fn:function(){showPage('ide');}},
  {ico:'📋',label:'Команди',fn:function(){showPage('commands');}},
  {ico:'⚡',label:'Автоматизація',fn:function(){showPage('macros');}},
  {ico:'➕',label:'Створити команду',fn:function(){showPage('commands');openCmdModal();}},
  {ico:'🌐',label:'Мережа',fn:function(){showPage('network');}},
  {ico:'🔑',label:'API Ключі',fn:function(){showPage('api');}},
  {ico:'⚙',label:'Налаштування',fn:function(){showPage('settings');}},
  {ico:'🧹',label:'Очистити чат',fn:clearChat},
];
var palIdx=0, palFiltered=palCmds;

function showPalette(){
  R('paletteOverlay').classList.add('show');
  R('paletteInput').value='';
  renderPalette(palCmds);
  setTimeout(function(){ R('paletteInput').focus(); },50);
}
function closePalette(e){ if(e.target===R('paletteOverlay')) R('paletteOverlay').classList.remove('show'); }
function renderPalette(items){
  palFiltered=items; palIdx=0;
  R('paletteList').innerHTML=items.map(function(c,i){
    return '<div class="palette-item'+(i===0?' pal-active':'')+'" onclick="runPalCmd('+palCmds.indexOf(c)+')"><span class="palette-item-ico">'+c.ico+'</span>'+c.label+'</div>';
  }).join('');
}
function filterPalette(q){
  renderPalette(palCmds.filter(function(c){ return c.label.toLowerCase().includes(q.toLowerCase()); }));
}
function runPalCmd(i){ palCmds[i].fn(); R('paletteOverlay').classList.remove('show'); }
function paletteNav(e){
  if(e.key==='Escape'){ R('paletteOverlay').classList.remove('show'); return; }
  if(e.key==='Enter' && palFiltered.length){ palFiltered[palIdx].fn(); R('paletteOverlay').classList.remove('show'); }
}

// ═══ KEYBOARD ═══
document.addEventListener('keydown',function(e){
  if((e.ctrlKey||e.metaKey)&&e.key==='k'){ e.preventDefault(); showPalette(); }
  if((e.ctrlKey||e.metaKey)&&e.key==='s'){ e.preventDefault(); ideSave(); }
  if(e.key==='F5'){ e.preventDefault(); runCode(); }
  if(e.key==='Escape') R('paletteOverlay').classList.remove('show');
});

// ═══ COMMANDS ═══
var cmdTypeLabels = {shell:'Shell',python:'Python',url:'URL',internal:'Внутрішня'};
var activeCmdType = 'all';
var cmdEditIdx = -1;
var _savedApiKeys = {};
var _savedCfg = {};

// ── Command format normalizer (old sphere format ↔ new panel format) ─────────
// Sphere uses: phrase, action, icon, alts[]
// Panel uses:  name, trigger, body, ico, trigger_alts (string)
// We keep BOTH field sets so sphere & panel stay in sync.
function _normalizeCmd(c, idx) {
  if (!c || typeof c !== 'object') return null;
  // Map old → new if new fields are missing
  if (!c.name)    c.name    = c.response || c.phrase || '?';
  if (!c.trigger) c.trigger = c.phrase   || '';
  if (!c.body)    c.body    = c.action   || '';
  if (!c.ico)     c.ico     = c.icon     || '❓';
  if (c.trigger_alts === undefined) {
    c.trigger_alts = Array.isArray(c.alts) ? c.alts.join(', ') : (c.alts || '');
  }
  // Ensure old fields are also present so sphere still works
  if (!c.phrase)  c.phrase  = c.trigger;
  if (!c.action)  c.action  = c.body;
  if (!c.icon)    c.icon    = c.ico;
  if (!Array.isArray(c.alts)) {
    c.alts = (c.trigger_alts || '').split(',').map(function(s){ return s.trim(); }).filter(Boolean);
  }
  // Ensure id exists
  if (!c.id) c.id = Date.now() + (idx || 0);
  if (!c.created_at) c.created_at = c.id;
  return c;
}

function _normalizeCmds(arr) {
  return (Array.isArray(arr) ? arr : []).map(function(c, i){ return _normalizeCmd(c, i); }).filter(Boolean);
}

var commands = [];

// ═══ ВКЛАДКИ: МОЇ / ВБУДОВАНІ ═══
var _cmdCurrentTab = 'my';
function showCmdTab(tab) {
  _cmdCurrentTab = tab;
  var myBtn = R('cmdTabMy'), biBtn = R('cmdTabBuiltin');
  var myPanel = R('cmdMyPanel'), biPanel = R('cmdBuiltinPanel');
  if (!myBtn || !biBtn) return;
  if (tab === 'my') {
    myPanel.style.display = ''; biPanel.style.display = 'none';
    myBtn.className = 'btn btn-p'; myBtn.style.fontSize = '12px';
    biBtn.className = 'btn btn-sm'; biBtn.style.fontSize = '12px';
  } else {
    myPanel.style.display = 'none'; biPanel.style.display = '';
    myBtn.className = 'btn btn-sm'; myBtn.style.fontSize = '12px';
    biBtn.className = 'btn btn-p'; biBtn.style.fontSize = '12px';
    renderBuiltinCmds('');
  }
}

// ═══ ВБУДОВАНІ КОМАНДИ (вшиті в сферу) ═══
var BUILTIN_COMMANDS = [
  // ── 🎮 Steam / Ігри ──
  {cat:'🎮 Steam / Ігри', ph:'запусти гру {назва}', ex:'запусти гру BeamNG.drive', desc:'Запустити гру з локальної Steam бібліотеки'},
  {cat:'🎮 Steam / Ігри', ph:'які ігри / що є в стімі', desc:'Список всіх встановлених Steam ігор'},
  {cat:'🎮 Steam / Ігри', ph:'що пограти / порекомендуй гру', desc:'Випадкова рекомендація з бібліотеки'},
  // ── 🔊 Звук / Гучність ──
  {cat:'🔊 Звук', ph:'гучність {0–100}', ex:'гучність 60', desc:'Встановити гучність у відсотках'},
  {cat:'🔊 Звук', ph:'гучніше / тихіше', desc:'Гучність +10% або -10%'},
  {cat:'🔊 Звук', ph:'без звуку / мут', desc:'Вимкнути звук (mute)'},
  {cat:'🔊 Звук', ph:'включи звук', desc:'Увімкнути звук назад'},
  // ── 🖥️ Система ──
  {cat:'🖥️ Система', ph:'виключи пк / вимкни компʼютер', desc:'Вимкнення ПК (shutdown)'},
  {cat:'🖥️ Система', ph:'перезавантаж пк', desc:'Перезавантаження ПК'},
  {cat:'🖥️ Система', ph:'сплячий режим / сон', desc:'Сплячий режим Windows'},
  {cat:'🖥️ Система', ph:'заблокуй екран', desc:'Заблокувати екран Windows'},
  {cat:'🖥️ Система', ph:'стан системи / стан пк', desc:'CPU, RAM, диск — поточний стан'},
  {cat:'🖥️ Система', ph:'що зараз запущено / процеси', desc:'Список активних процесів'},
  {cat:'🖥️ Система', ph:'закрий {назва вікна}', ex:'закрий chrome', desc:'Закрити процес по імені'},
  {cat:'🖥️ Система', ph:'скільки пам\'яті / диску', desc:'Використання RAM і дисків'},
  {cat:'🖥️ Система', ph:'мій ip / ip адреса', desc:'Показати локальну IP адресу'},
  {cat:'🖥️ Система', ph:'wifi пароль / покажи пароль wifi', desc:'Показати збережений пароль WiFi'},
  // ── 📷 Скріншот / Екран ──
  {cat:'📷 Скріншот', ph:'зроби скріншот', desc:'Скріншот всього екрану → файл'},
  {cat:'📷 Скріншот', ph:'скріншот активного вікна', desc:'Тільки поточне вікно'},
  {cat:'📷 Скріншот', ph:'проаналізуй екран / що на екрані', desc:'AI опис поточного екрану'},
  {cat:'📷 Скріншот', ph:'проаналізуй буфер / що в буфері', desc:'AI аналіз скопійованого тексту'},
  // ── 🌐 Браузер / Сайти ──
  {cat:'🌐 Браузер', ph:'відкрий {сайт}', ex:'відкрий youtube / відкрий google', desc:'Відкрити популярний сайт'},
  {cat:'🌐 Браузер', ph:'загугли {запит}', ex:'загугли погода Київ', desc:'Пошук в Google'},
  {cat:'🌐 Браузер', ph:'знайди в ютубі {запит}', desc:'Пошук відео на YouTube'},
  {cat:'🌐 Браузер', ph:'відкрий пошту / gmail', desc:'Відкрити Gmail'},
  {cat:'🌐 Браузер', ph:'відкрий телеграм', desc:'Відкрити Telegram Web'},
  // ── 🎬 Відео / Серіали ──
  {cat:'🎬 Відео', ph:'включи {назва серіалу}', ex:'включи вікінги / включи зоряні війни', desc:'Знайти і запустити в браузері'},
  {cat:'🎬 Відео', ph:'продовж дивитися / що я дивився', desc:'Продовжити останній переглянутий контент'},
  // ── 🎵 Музика ──
  {cat:'🎵 Музика', ph:'включи музику / відкрий музику', desc:'Відкрити YouTube Music / Spotify'},
  {cat:'🎵 Музика', ph:'далі / наступний трек', desc:'Наступний трек'},
  {cat:'🎵 Музика', ph:'назад / попередній трек', desc:'Попередній трек'},
  {cat:'🎵 Музика', ph:'пауза / пауза музики', desc:'Пауза / продовжити'},
  // ── ⏰ Час / Дата ──
  {cat:'⏰ Час і дата', ph:'котра година / який час', desc:'Поточний час'},
  {cat:'⏰ Час і дата', ph:'яке сьогодні число / яка дата', desc:'Поточна дата'},
  {cat:'⏰ Час і дата', ph:'постав таймер на {X} хвилин', ex:'постав таймер на 10 хвилин', desc:'Таймер зі сповіщенням'},
  {cat:'⏰ Час і дата', ph:'нагадай через {X} хвилин {що}', desc:'Нагадування'},
  // ── 🌤️ Погода ──
  {cat:'🌤️ Погода', ph:'яка погода / погода сьогодні', desc:'Погода в твоєму місті'},
  {cat:'🌤️ Погода', ph:'погода {місто}', ex:'погода Київ', desc:'Погода у вказаному місті'},
  // ── 📁 Файли ──
  {cat:'📁 Файли', ph:'знайди файл {назва}', ex:'знайди файл commands.json', desc:'Пошук файлу на диску'},
  {cat:'📁 Файли', ph:'відкрий провідник / відкрий папку', desc:'Відкрити Провідник Windows'},
  {cat:'📁 Файли', ph:'відкрий завантаження', desc:'Відкрити папку Downloads'},
  // ── 🤖 AI ──
  {cat:'🤖 AI / Діалог', ph:'давай поговоримо / режим діалогу', desc:'Увімкнути режим розмови з AI'},
  {cat:'🤖 AI / Діалог', ph:'запитай {AI} {питання}', ex:'запитай гемені що таке квантовий компʼютер', desc:'Запит до конкретного AI'},
  {cat:'🤖 AI / Діалог', ph:'створи команду {опис}', ex:'створи команду відкрий телеграм', desc:'AI автоматично створює нову команду'},
  {cat:'🤖 AI / Діалог', ph:'що ти можеш / список команд', desc:'Список можливостей сфери'},
  // ── 💻 Програми ──
  {cat:'💻 Програми', ph:'відкрий {назва}', ex:'відкрий блокнот / відкрий steam', desc:'Запустити програму за назвою'},
  {cat:'💻 Програми', ph:'закрий {назва}', ex:'закрий chrome', desc:'Закрити програму'},
  {cat:'💻 Програми', ph:'відкрий код / vs code', desc:'Відкрити Visual Studio Code'},
  {cat:'💻 Програми', ph:'відкрий термінал / cmd', desc:'Відкрити командний рядок'},
  // ── 📱 Telegram ──
  {cat:'📱 Telegram', ph:'/start або /menu', desc:'Головне меню бота'},
  {cat:'📱 Telegram', ph:'/status', desc:'Стан ПК через Telegram'},
  {cat:'📱 Telegram', ph:'будь-яка фраза з команд', desc:'Всі команди працюють через Telegram текстом'},
];

function renderBuiltinCmds(q) {
  var container = R('cmdBuiltinGroups');
  if (!container) return;
  q = (q || '').toLowerCase().trim();
  // Групуємо по категорії
  var grouped = {};
  BUILTIN_COMMANDS.forEach(function(c) {
    if (q && c.ph.toLowerCase().indexOf(q) < 0 && c.cat.toLowerCase().indexOf(q) < 0 && (c.desc||'').toLowerCase().indexOf(q) < 0) return;
    if (!grouped[c.cat]) grouped[c.cat] = [];
    grouped[c.cat].push(c);
  });
  var cats = Object.keys(grouped);
  if (!cats.length) { container.innerHTML = '<div style="color:var(--text3);padding:20px;text-align:center;">Нічого не знайдено</div>'; return; }
  container.innerHTML = cats.map(function(cat) {
    var items = grouped[cat].map(function(c) {
      return '<div style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);">' +
        '<div style="flex:1;min-width:0;">' +
          '<div style="font-size:13px;color:var(--text);font-family:monospace;background:rgba(0,212,255,.08);padding:2px 8px;border-radius:5px;display:inline-block;margin-bottom:3px;">' + c.ph + '</div>' +
          (c.ex ? '<div style="font-size:11px;color:#a78bfa;margin-bottom:2px;">Приклад: <i>' + c.ex + '</i></div>' : '') +
          '<div style="font-size:12px;color:var(--text3);">' + (c.desc||'') + '</div>' +
        '</div>' +
        '<button class="btn btn-sm" style="font-size:10px;flex-shrink:0;" onclick="copyBuiltin(\''+c.ph.replace(/'/g,"\\'")+'\')" title="Скопіювати фразу">📋</button>' +
      '</div>';
    }).join('');
    return '<div style="margin-bottom:16px;">' +
      '<div style="font-size:13px;font-weight:600;color:var(--accent);margin-bottom:8px;padding:6px 10px;background:rgba(0,212,255,.06);border-radius:8px;border-left:3px solid var(--accent);">' + cat + ' <span style="font-size:11px;font-weight:400;opacity:.6">(' + grouped[cat].length + ')</span></div>' +
      '<div style="padding:0 4px;">' + items + '</div>' +
    '</div>';
  }).join('');
}

function copyBuiltin(phrase) {
  navigator.clipboard.writeText(phrase).then(function(){ showToast('📋 Скопійовано: ' + phrase.slice(0,30)); });
}

var _newCmdType = 'shell';
var CMD_BROWSERS = /chrome|firefox|edge|msedge|opera|brave|vivaldi|chromium/i;
var CMD_CATS = {
  browsers: {ico:'🔍', name:'Браузери'},
  sites:    {ico:'🌐', name:'Веб-сайти'},
  apps:     {ico:'⚙',  name:'Програми'},
  python:   {ico:'🐍', name:'Python скрипти'},
  system:   {ico:'🔧', name:'Система'}
};
var CMD_CAT_ORDER = ['browsers','sites','apps','python','system'];

function getCmdCategory(c) {
  if (c.type === 'url')      return 'sites';
  if (c.type === 'python')   return 'python';
  if (c.type === 'internal') return 'system';
  if (CMD_BROWSERS.test(c.body) || CMD_BROWSERS.test(c.name)) return 'browsers';
  return 'apps';
}
function getCmdTypeIco(type) {
  return {shell:'⚙', python:'🐍', url:'🌐', internal:'🔧'}[type] || '⚡';
}

// ── View switching ──────────────────────────────────────────────────────────
function showCmdLib() {
  R('cmdLibView').style.display = '';
  R('cmdCreateView').style.display = 'none';
  sortAndRenderLib();
}
function showCmdCreate(id) {
  R('cmdLibView').style.display = 'none';
  R('cmdCreateView').style.display = '';
  _resetCmdForm(id);
  renderCmdListPanel('');
}
function openCmdModal(id) { showPage('commands'); showCmdCreate(id); }
function closeCmdModal()  { showCmdLib(); }

function _resetCmdForm(id) {
  cmdEditIdx = id || -1;
  _newCmdType = 'shell';
  R('cmdEditId').value    = id || '';
  R('cmdTrigger').value   = '';
  R('cmdTriggerAlts').value = '';
  R('cmdName').value      = '';
  R('cmdIcon').value      = '';
  R('cmdDesc').value      = '';
  R('cmdBody').value      = '';
  R('cmdHotkey').value    = '';
  R('cmdCreateTitle').textContent = 'Створення команди';
  var fi = R('cmdFileInfo'); if (fi) fi.style.display = 'none';
  document.querySelectorAll('#cmdTypeSelect .cmd-type-radio-btn').forEach(function(c){ c.classList.remove('active'); });
  var first = document.querySelector('#cmdTypeSelect .cmd-type-radio-btn[data-type="shell"]');
  if (first) first.classList.add('active');
  updateCmdBodyLabel('shell');

  if (id) {
    var cmd = commands.find(function(c){ return c.id === id; });
    if (cmd) {
      R('cmdCreateTitle').textContent = 'Редагування: ' + cmd.name;
      R('cmdName').value      = cmd.name || '';
      R('cmdIcon').value      = cmd.ico  || '';
      R('cmdDesc').value      = cmd.desc || '';
      R('cmdBody').value      = cmd.body || '';
      R('cmdHotkey').value    = cmd.hotkey || '';
      R('cmdTrigger').value   = cmd.trigger || '';
      R('cmdTriggerAlts').value = cmd.trigger_alts || '';
      _newCmdType = cmd.type || 'shell';
      document.querySelectorAll('#cmdTypeSelect .cmd-type-radio-btn').forEach(function(c){
        c.classList.toggle('active', c.dataset.type === _newCmdType);
      });
      updateCmdBodyLabel(_newCmdType);
    }
  }
  setTimeout(function(){ var n=R('cmdTrigger'); if(n) n.focus(); }, 80);
}

// ── Library render ──────────────────────────────────────────────────────────
function sortAndRenderLib() {
  var tc = R('cmdTotalCount'); if (tc) tc.textContent = '(' + commands.length + ')';
  var sort = (R('cmdSortSelect') || {value:'date_desc'}).value;
  var sorted = commands.slice();
  if      (sort === 'date_desc') sorted.sort(function(a,b){ return (b.created_at||b.id)-(a.created_at||a.id); });
  else if (sort === 'date_asc')  sorted.sort(function(a,b){ return (a.created_at||a.id)-(b.created_at||b.id); });
  else if (sort === 'name_asc')  sorted.sort(function(a,b){ return (a.name||'').localeCompare(b.name||'','uk'); });
  else if (sort === 'name_desc') sorted.sort(function(a,b){ return (b.name||'').localeCompare(a.name||'','uk'); });
  else if (sort === 'type')      sorted.sort(function(a,b){ return (a.type||'').localeCompare(b.type||''); });
  renderCmdLibGroups(sorted);
}

function renderCmdLibGroups(list) {
  var el = R('cmdLibGroups'); if (!el) return;
  if (!list.length) {
    el.innerHTML = '<div style="text-align:center;padding:60px 0;color:var(--text3);"><div style="font-size:48px;margin-bottom:12px;opacity:.3;">📋</div><div style="font-size:14px;margin-bottom:8px;">Команд не знайдено</div><button class="btn btn-p" onclick="showCmdCreate()">+ Додати першу команду</button></div>';
    return;
  }
  var groups = {};
  list.forEach(function(c){ var k=getCmdCategory(c); if(!groups[k]) groups[k]=[]; groups[k].push(c); });
  var html = '';
  CMD_CAT_ORDER.forEach(function(key) {
    if (!groups[key]) return;
    var items = groups[key], cat = CMD_CATS[key];
    html += '<div class="cmd-group">';
    html += '<div class="cmd-group-hdr"><span style="font-size:16px;">'+cat.ico+'</span><span class="cmd-group-name">'+cat.name+'</span><span class="cmd-group-count">'+items.length+'</span></div>';
    html += '<div class="cmd-grid">';
    items.forEach(function(c) {
      var ico    = c.ico || getCmdTypeIco(c.type);
      var label  = {shell:'П',python:'Py',url:'С',internal:'Sys'}[c.type]||'?';
      var phrase = c.trigger || c.body || '';
      var on     = c.enabled !== false;
      var uses   = c.use_count || 0;
      var lastOk = c.last_run_ok;
      var lastAt = c.last_run_at ? _timeAgo(c.last_run_at) : '';
      var statusHtml = '';
      if (lastAt) statusHtml = lastOk
        ? '<span class="cmd-status-ok">✓ '+lastAt+'</span>'
        : '<span class="cmd-status-err">✗ '+lastAt+'</span>';
      html += '<div class="cmd-lib-card'+(on?'':' disabled')+'" id="cmd-card-'+c.id+'">';
      html += '<div class="cmd-lib-card-actions">';
      html += '<button class="btn btn-sm" style="padding:3px 7px;font-size:10px;" onclick="editCmd('+c.id+')" title="Редагувати">✏</button>';
      html += '<button class="btn btn-sm" style="padding:3px 7px;font-size:10px;" onclick="duplicateCmd('+c.id+')" title="Дублювати">⎘</button>';
      html += '<button class="btn btn-sm btn-d" style="padding:3px 7px;font-size:10px;" onclick="deleteCmd('+c.id+')" title="Видалити">🗑</button>';
      html += '</div>';
      html += '<div class="cmd-toggle '+(on?'on':'off')+'" onclick="toggleCmdEnabled('+c.id+')" title="'+(on?'Вимкнути':'Увімкнути')+'"></div>';
      var srcBadge = c.source === 'sphere'
        ? '<span title="Створила сфера автоматично" style="font-size:10px;background:rgba(0,212,255,.12);color:var(--accent);padding:1px 5px;border-radius:4px;margin-left:4px;">🤖</span>'
        : '<span title="Створено в панелі" style="font-size:10px;background:rgba(139,92,246,.12);color:#a78bfa;padding:1px 5px;border-radius:4px;margin-left:4px;">👤</span>';
      html += '<div class="cmd-lib-card-name">'+ico+' '+escH(c.name)+srcBadge+'</div>';
      html += '<div class="cmd-lib-card-phrase">"'+escH(phrase)+'"</div>';
      html += '<div class="cmd-lib-card-foot">';
      html += '<span class="cmd-type-badge cmd-type-'+c.type+'">'+label+'</span>';
      html += '<span class="cmd-use-badge">▶'+uses+'</span>';
      html += statusHtml;
      html += '<div style="flex:1;min-width:0;"></div>';
      html += '<div class="cmd-run-btn" onclick="quickTestCmd('+c.id+')" title="Запустити зараз">▶</div>';
      html += '</div></div>';
    });
    html += '</div></div>';
  });
  el.innerHTML = html;
}

function escH(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ── Create panel — right list ───────────────────────────────────────────────
function renderCmdListPanel(q) {
  var el = R('cmdListItems'); if (!el) return;
  var lc = R('cmdListCount'); if (lc) lc.textContent = '(' + commands.length + ')';
  var filtered = commands.filter(function(c){
    return !q || (c.name||'').toLowerCase().includes(q.toLowerCase()) || (c.trigger||'').toLowerCase().includes(q.toLowerCase()) || (c.body||'').toLowerCase().includes(q.toLowerCase());
  });
  if (!filtered.length) { el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text3);font-size:12px;">Команд не знайдено</div>'; return; }
  el.innerHTML = filtered.map(function(c){
    var ico = c.ico || getCmdTypeIco(c.type);
    var phrase = c.trigger || c.body || '';
    return '<div class="cmd-list-item">'
      + '<div class="cmd-list-ico">'+ico+'</div>'
      + '<div style="flex:1;min-width:0;">'
      +   '<div class="cmd-list-name">'+escH(c.name)+'</div>'
      +   '<div class="cmd-list-phrase">'+escH(phrase)+'</div>'
      + '</div>'
      + '<div style="display:flex;gap:4px;">'
      +   '<button class="btn btn-sm" style="padding:3px 8px;font-size:10px;" onclick="editCmd('+c.id+')">✏</button>'
      +   '<button class="btn btn-sm btn-d" style="padding:3px 8px;font-size:10px;" onclick="deleteCmd('+c.id+')">🗑</button>'
      + '</div></div>';
  }).join('');
}

// ── Init / compat ───────────────────────────────────────────────────────────
function initCommands() { sortAndRenderLib(); }
function renderCmds()   { sortAndRenderLib(); }
function filterCmds()   { sortAndRenderLib(); }
function setCmdType()   { sortAndRenderLib(); }

// ── 1. Toggle enable/disable ────────────────────────────────────────────────
function toggleCmdEnabled(id) {
  var c = commands.find(function(x){ return x.id === id; });
  if (!c) return;
  c.enabled = c.enabled === false ? true : false;
  pyCall('save_commands', JSON.stringify({commands: commands}));
  sortAndRenderLib();
  showToast(c.enabled ? '✓ Команду увімкнено' : '○ Команду вимкнено');
}

// ── 2. Duplicate ─────────────────────────────────────────────────────────────
function duplicateCmd(id) {
  var c = commands.find(function(x){ return x.id === id; });
  if (!c) return;
  var copy = JSON.parse(JSON.stringify(c));
  copy.id = Date.now();
  copy.name = copy.name + ' (копія)';
  copy.use_count = 0;
  delete copy.last_run_at;
  delete copy.last_run_ok;
  commands.push(copy);
  pyCall('save_commands', JSON.stringify({commands: commands}));
  sortAndRenderLib();
  showToast('⎘ Команду дубльовано');
}

// ── 3. Quick test from card ──────────────────────────────────────────────────
function quickTestCmd(id) {
  var c = commands.find(function(x){ return x.id === id; });
  if (!c) return;
  pyCall('run_command', JSON.stringify({type: c.type, body: c.body, name: c.name}));
  _updateCmdStats(id, true);
}

// ── Recent commands widget ───────────────────────────────────────────────────
function renderRecentCmds() {
  var el = R('recentCmdsList'); if (!el) return;
  var recent = commands.filter(function(c){ return !!c.last_run_at; });
  recent.sort(function(a,b){ return (b.last_run_at||0) - (a.last_run_at||0); });
  recent = recent.slice(0, 6);
  if (!recent.length) {
    el.innerHTML = '<div style="font-size:11px;color:var(--text3);padding:6px 0;">Ще немає запусків — використайте команди</div>';
    return;
  }
  el.innerHTML = recent.map(function(c) {
    var ico = c.ico || '▶';
    var ago = c.last_run_at ? _timeAgo(c.last_run_at) : '';
    var ok  = c.last_run_ok !== false;
    return '<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;background:var(--bg3);border-radius:8px;border:1px solid var(--border);">'
      + '<span style="font-size:14px;flex-shrink:0;">'+ico+'</span>'
      + '<div style="flex:1;min-width:0;">'
      +   '<div style="font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+escH(c.name)+'</div>'
      +   '<div style="font-size:10px;color:'+(ok?'var(--accent)':'var(--red)')+';">'+(ok?'✓':'✗')+' '+ago+'</div>'
      + '</div>'
      + '<button class="btn btn-sm" style="font-size:10px;padding:3px 9px;flex-shrink:0;" onclick="quickTestCmd('+c.id+')" title="Запустити">▶</button>'
      + '</div>';
  }).join('');
}

// ── 4 & 5. Stats: usage count + last run ────────────────────────────────────
function _updateCmdStats(id, ok) {
  var c = commands.find(function(x){ return x.id === id; });
  if (!c) return;
  c.use_count = (c.use_count || 0) + 1;
  c.last_run_at = Date.now();
  c.last_run_ok = ok;
  trackCmdRun();
  pyCall('save_commands', JSON.stringify({commands: commands}));
  renderRecentCmds();
  addActivity((c.ico||'▶') + ' ' + c.name, ok ? 'var(--accent)' : 'var(--red)');
  var card = R('cmd-card-' + id);
  if (card) {
    var badge = card.querySelector('.cmd-use-badge');
    if (badge) badge.textContent = '▶' + c.use_count;
    var old = card.querySelector('.cmd-status-ok, .cmd-status-err');
    if (old) old.remove();
    var foot = card.querySelector('.cmd-lib-card-foot');
    if (foot) {
      var sp = document.createElement('span');
      sp.className = ok ? 'cmd-status-ok' : 'cmd-status-err';
      sp.textContent = ok ? '✓ щойно' : '✗ щойно';
      foot.insertBefore(sp, foot.querySelector('.cmd-run-btn'));
    }
  }
}

function _timeAgo(ts) {
  var s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60)  return s + 'с';
  if (s < 3600) return Math.floor(s/60) + 'хв';
  if (s < 86400) return Math.floor(s/3600) + 'г';
  return Math.floor(s/86400) + 'д';
}

// ── AI Command Creator ───────────────────────────────────────────────────────
var _cmdAiSystem = 'You are a command assistant for an AI OS on Windows. The user describes what they want a command to do. Return ONLY a JSON object, no explanation:\n{\n  "trigger": "main Ukrainian phrase to say/type",\n  "alts": "alternative phrases comma separated in Ukrainian",\n  "type": "shell or url or python",\n  "name": "short display name",\n  "body": "executable name or full path or URL",\n  "icon": "one relevant emoji",\n  "hotkey": "",\n  "desc": "one line description"\n}\nExamples: "відкрий телеграм" → body="Telegram.exe" type="shell"; "відкрий ютуб" → body="https://youtube.com" type="url"';

function _sendCmdAiRequest(desc) {
  var reqId = 'cmdai_' + Date.now();
  pyCall('ai_send', JSON.stringify({
    id: reqId,
    provider: currentProvider || 'openai',
    model: currentModel || 'gpt-4o',
    messages: [{role:'user', content: desc}],
    system: _cmdAiSystem
  }));
  return reqId;
}

function aiAutoFillCmd() {
  var desc = (R('cmdAiDesc').value || '').trim();
  if (!desc) { R('cmdAiDesc').focus(); return; }
  var btn = R('cmdAiBtn');
  if (btn) { btn.textContent = '⏳...'; btn.disabled = true; }
  _sendCmdAiRequest(desc);
}

function createCmdFromChat() {
  var inp = R('chatCmdInput');
  var desc = (inp ? inp.value : '').trim();
  if (!desc) { if(inp) inp.focus(); return; }
  if (inp) inp.value = '';
  showToast('⏳ AI створює команду...');
  _sendCmdAiRequest(desc);
}

function handleCmdAiResult(d) {
  // Reset AI fill button
  var btn = R('cmdAiBtn');
  if (btn) { btn.textContent = '✨ Заповнити'; btn.disabled = false; }

  var text = d.text || '';
  var match = text.match(/\{[\s\S]*?\}/);
  if (!match) { showToast('⚠ AI не розпізнав команду, спробуйте інакше'); return; }

  var cmd;
  try { cmd = JSON.parse(match[0]); }
  catch(e) { showToast('⚠ Помилка відповіді AI'); return; }

  // Navigate to create form and fill it
  showPage('commands');
  showCmdCreate();
  setTimeout(function() {
    if (cmd.trigger) R('cmdTrigger').value = cmd.trigger;
    if (cmd.alts)    R('cmdTriggerAlts').value = cmd.alts;
    if (cmd.name)    R('cmdName').value = cmd.name;
    if (cmd.body)    R('cmdBody').value = cmd.body;
    if (cmd.icon)    R('cmdIcon').value = cmd.icon;
    if (cmd.hotkey)  R('cmdHotkey').value = cmd.hotkey;
    if (cmd.desc)    R('cmdDesc').value = cmd.desc;
    if (cmd.type) {
      var typeBtn = document.querySelector('#cmdTypeSelect [data-type="'+cmd.type+'"]');
      if (typeBtn) selectCmdType(typeBtn, cmd.type);
    }
    // Highlight the trigger field so user sees it
    var tf = R('cmdTrigger');
    if (tf) { tf.style.borderColor='var(--accent)'; tf.style.boxShadow='0 0 0 3px rgba(34,197,94,.15)'; }
    showToast('✓ AI заповнив форму — перевірте і збережіть');
  }, 200);
}

// ── File browse ─────────────────────────────────────────────────────────────
function browseFile() { pyCall('open_file_dialog'); }

function handleFileSelected(d) {
  // Guard: reject data: URLs that come from drag-drop rather than real file dialog
  var body = d.body || '';
  if (body.startsWith('data:') || body.length > 2000) {
    showToast('⚠ Використайте кнопку 📁 для вибору файлу через діалог');
    return;
  }
  var info = R('cmdFileInfo');
  if (info) { info.style.display='block'; info.innerHTML='📁 <b>'+escH(d.filename||d.name||'')+'</b> — поля заповнено автоматично'; }
  if (d.name)  R('cmdName').value = d.name;
  if (d.ico)   { var ic=R('cmdIcon'); if(ic) ic.value=d.ico; }
  if (d.desc)  R('cmdDesc').value = d.desc;
  if (d.body)  R('cmdBody').value = d.body;
  // Also pre-fill trigger phrase if empty
  var tr = R('cmdTrigger');
  if (tr && !tr.value && d.name) tr.value = 'відкрий ' + d.name.toLowerCase();
  _newCmdType = d.type || 'shell';
  document.querySelectorAll('#cmdTypeSelect .cmd-type-radio-btn').forEach(function(c){
    c.classList.toggle('active', c.dataset.type === _newCmdType);
  });
  updateCmdBodyLabel(_newCmdType);
  showToast('✓ ' + (d.filename||d.name||'файл') + ' — поля заповнено');
}

// ── Type selector ────────────────────────────────────────────────────────────
function selectCmdType(el, type) {
  document.querySelectorAll('#cmdTypeSelect .cmd-type-radio-btn').forEach(function(c){ c.classList.remove('active'); });
  el.classList.add('active');
  _newCmdType = type;
  updateCmdBodyLabel(type);
}

function updateCmdBodyLabel(type) {
  var labels = { shell:'Шлях до дії *', python:'Python код *', url:'URL адреса *', internal:'Внутрішня команда *' };
  var placeholders = { shell:'chrome\nnotepad\nC:\\Program Files\\App\\app.exe', python:'import os\nprint(os.getcwd())', url:'https://example.com', internal:'system_report' };
  var hints = { shell:'Назва програми або повний шлях до .exe файлу', python:'Код виконається напряму через Python', url:'Сайт або локальний HTML-файл, відкриється у браузері', internal:'Внутрішня дія AXIS: system_report, clear_cache тощо' };
  var lbl = R('cmdBodyLabel'); if(lbl) lbl.textContent = labels[type] || 'Шлях до дії *';
  var inp = R('cmdBody');      if(inp) inp.placeholder  = placeholders[type] || '';
  var h   = R('cmdBodyHint');  if(h)   h.textContent    = hints[type] || '';
}

// ── Save / delete ────────────────────────────────────────────────────────────
function saveCmd() {
  var name = R('cmdName').value.trim();
  var body = R('cmdBody').value.trim();
  if (!name) { R('cmdName').style.borderColor='var(--red)'; R('cmdName').focus(); return; }
  if (!body) { R('cmdBody').style.borderColor='var(--red)'; R('cmdBody').focus(); return; }
  R('cmdName').style.borderColor='';
  R('cmdBody').style.borderColor='';

  var editId = parseInt(R('cmdEditId').value) || -1;
  var trigger = R('cmdTrigger').value.trim();
  var trigAlts = R('cmdTriggerAlts').value.trim();
  var ico = R('cmdIcon').value || getCmdTypeIco(_newCmdType);
  var obj = {
    // Panel format fields
    id:           editId > 0 ? editId : Date.now(),
    ico:          ico,
    name:         name,
    desc:         R('cmdDesc').value.trim(),
    type:         _newCmdType,
    body:         body,
    hotkey:       R('cmdHotkey').value.trim(),
    trigger:      trigger,
    trigger_alts: trigAlts,
    created_at:   editId > 0 ? ((commands.find(function(c){return c.id===editId;})||{}).created_at || Date.now()) : Date.now(),
    // Sphere-compatible fields (so sphere can still read the file)
    phrase:       trigger || name,
    action:       body,
    icon:         ico,
    response:     name,
    alts:         trigAlts ? trigAlts.split(',').map(function(s){ return s.trim(); }).filter(Boolean) : [],
  };

  if (editId > 0) {
    var idx = commands.findIndex(function(c){ return c.id === editId; });
    if (idx > -1) { commands[idx] = obj; showToast('✓ Команду «'+name+'» оновлено'); }
  } else {
    commands.push(obj);
    showToast('✓ Команду «'+name+'» створено');
  }
  pyCall('save_commands', JSON.stringify({commands: commands}));
  _resetCmdForm();
  renderCmdListPanel('');
  var lc=R('cmdListCount'); if(lc) lc.textContent='('+commands.length+')';
  var tc=R('cmdTotalCount'); if(tc) tc.textContent='('+commands.length+')';
}

function testNewCmd() {
  var body = R('cmdBody').value.trim();
  if (!body) { showToast('⚠ Введіть шлях до дії'); return; }
  if (_newCmdType === 'url') {
    pyCall('run_macro', JSON.stringify({command:'start '+body, type:'shell'}));
    showToast('🌐 Тест: відкриваю '+body);
  } else if (_newCmdType === 'shell') {
    pyCall('run_macro', JSON.stringify({command:body, type:'shell'}));
    showToast('▶ Тест: '+body);
  } else {
    showToast('ℹ Тест для Python/Система — натисніть Зберегти та запустіть з бібліотеки');
  }
}

function showCmdStats() {
  var counts = {};
  commands.forEach(function(c){ counts[c.type]=(counts[c.type]||0)+1; });
  var lines = Object.keys(counts).map(function(t){ return cmdTypeLabels[t]+': '+counts[t]; });
  showToast('📊 '+commands.length+' команд — '+lines.join(', '));
}

function loadExampleCmds() {
  var examples = [
    {id:Date.now()+1,  ico:'🌐', name:'Chrome',     desc:'', type:'shell',    body:'chrome',              hotkey:'', trigger:'відкрий chrome',     trigger_alts:'запусти chrome',       created_at:Date.now()},
    {id:Date.now()+2,  ico:'🦊', name:'Firefox',    desc:'', type:'shell',    body:'firefox',             hotkey:'', trigger:'відкрий firefox',    trigger_alts:'запусти firefox',      created_at:Date.now()},
    {id:Date.now()+3,  ico:'📝', name:'Блокнот',    desc:'', type:'shell',    body:'notepad',             hotkey:'', trigger:'відкрий блокнот',    trigger_alts:'відкрий нотатки',      created_at:Date.now()},
    {id:Date.now()+4,  ico:'📺', name:'YouTube',    desc:'', type:'url',      body:'https://youtube.com', hotkey:'', trigger:'відкрий ютуб',       trigger_alts:'youtube',              created_at:Date.now()},
    {id:Date.now()+5,  ico:'📧', name:'Gmail',      desc:'', type:'url',      body:'https://gmail.com',   hotkey:'', trigger:'відкрий пошту',      trigger_alts:'відкрий gmail',        created_at:Date.now()},
    {id:Date.now()+6,  ico:'🔍', name:'Google',     desc:'', type:'url',      body:'https://google.com',  hotkey:'', trigger:'відкрий гугл',       trigger_alts:'відкрий google',       created_at:Date.now()},
    {id:Date.now()+7,  ico:'🧮', name:'Калькулятор',desc:'', type:'shell',    body:'calc',                hotkey:'', trigger:'відкрий калькулятор',trigger_alts:'калькулятор',          created_at:Date.now()},
    {id:Date.now()+8,  ico:'📊', name:'Системний звіт',desc:'Статистика системи',type:'internal',body:'system_report',hotkey:'',trigger:'системний звіт',trigger_alts:'покажи систему', created_at:Date.now()},
  ];
  var added = 0;
  examples.forEach(function(ex){
    if (!commands.find(function(c){ return c.name===ex.name; })) { commands.push(ex); added++; }
  });
  pyCall('save_commands', JSON.stringify({commands: commands}));
  sortAndRenderLib();
  showToast('✓ Додано ' + added + ' прикладів');
}

function runCmd(id) {
  var cmd = commands.find(function(c){ return c.id === id; });
  if (!cmd) return;
  if (cmd.type === 'shell') {
    pyCall('run_macro', JSON.stringify({command: cmd.body, type:'shell'}));
    showToast('▶ ' + cmd.name);
  } else if (cmd.type === 'python') {
    pyCall('run_code', JSON.stringify({code: cmd.body, lang:'python'}));
    showPage('ide');
    showToast('▶ Python: ' + cmd.name);
  } else if (cmd.type === 'url') {
    pyCall('run_macro', JSON.stringify({command: 'start ' + cmd.body, type:'shell'}));
    showToast('🌐 Відкриваю: ' + cmd.body);
  } else {
    showToast('⚡ ' + cmd.name);
  }
}

function editCmd(id) {
  showPage('commands');
  showCmdCreate(id);
}

function deleteCmd(id) {
  var cmd = commands.find(function(c){ return c.id === id; });
  if (!cmd) return;
  if (confirm('Видалити команду «' + cmd.name + '»?')) {
    commands = commands.filter(function(c){ return c.id !== id; });
    sortAndRenderLib();
    renderCmdListPanel('');
    showToast('🗑 Команду видалено');
    pyCall('save_commands', JSON.stringify({commands: commands}));
  }
}

// ═══ EXPORT / IMPORT COMMANDS ═══
function exportCmds() {
  var data = JSON.stringify(commands, null, 2);
  var blob = new Blob([data], {type: 'application/json'});
  var url  = URL.createObjectURL(blob);
  var a    = document.createElement('a');
  a.href = url; a.download = 'axis_commands.json';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('✓ Експортовано ' + commands.length + ' команд');
}

function importCmds() {
  var inp = document.createElement('input');
  inp.type = 'file'; inp.accept = '.json';
  inp.onchange = function(e) {
    var file = e.target.files[0]; if (!file) return;
    var reader = new FileReader();
    reader.onload = function(ev) {
      try {
        var arr = JSON.parse(ev.target.result);
        if (!Array.isArray(arr)) { showToast('⚠ Невірний формат'); return; }
        var added = 0;
        arr.forEach(function(c) {
          if (c.name && c.body && !commands.find(function(x){ return x.id === c.id; })) {
            commands.push(c); added++;
          }
        });
        pyCall('save_commands', JSON.stringify({commands: commands}));
        sortAndRenderLib();
        showToast('✓ Імпортовано ' + added + ' команд');
      } catch(e) { showToast('⚠ Помилка імпорту JSON'); }
    };
    reader.readAsText(file);
  };
  inp.click();
}

// ═══ COMMAND TEMPLATES ═══
var CMD_TEMPLATES = [
  { cat:'🌐 Браузери та сайти', ico:'🎬', name:'YouTube',        desc:'Відкрити YouTube',          type:'url',    body:'https://youtube.com',         trigger:'відкрий ютуб' },
  { cat:'🌐 Браузери та сайти', ico:'🔍', name:'Google',         desc:'Пошук Google',              type:'url',    body:'https://google.com',          trigger:'відкрий гугл' },
  { cat:'🌐 Браузери та сайти', ico:'🤖', name:'ChatGPT',        desc:'Відкрити ChatGPT',          type:'url',    body:'https://chat.openai.com',     trigger:'відкрий chatgpt' },
  { cat:'🌐 Браузери та сайти', ico:'💻', name:'GitHub',         desc:'Відкрити GitHub',           type:'url',    body:'https://github.com',          trigger:'відкрий github' },
  { cat:'🌐 Браузери та сайти', ico:'📺', name:'Twitch',         desc:'Відкрити Twitch',           type:'url',    body:'https://twitch.tv',           trigger:'відкрий твіч' },
  { cat:'🌐 Браузери та сайти', ico:'📸', name:'Instagram',      desc:'Відкрити Instagram',        type:'url',    body:'https://instagram.com',       trigger:'відкрий інстаграм' },
  { cat:'🌐 Браузери та сайти', ico:'✈️', name:'Telegram Web',   desc:'Відкрити Telegram',         type:'url',    body:'https://web.telegram.org',    trigger:'відкрий телеграм' },

  { cat:'📁 Програми',          ico:'📁', name:'Провідник',      desc:'Відкрити файловий менеджер',type:'shell',  body:'explorer.exe',                trigger:'відкрий провідник' },
  { cat:'📁 Програми',          ico:'📝', name:'Блокнот',        desc:'Відкрити Notepad',          type:'shell',  body:'notepad.exe',                 trigger:'відкрий блокнот' },
  { cat:'📁 Програми',          ico:'🧮', name:'Калькулятор',    desc:'Відкрити калькулятор',      type:'shell',  body:'calc.exe',                    trigger:'відкрий калькулятор' },
  { cat:'📁 Програми',          ico:'⚙',  name:'Диспетчер задач',desc:'Task Manager',              type:'shell',  body:'taskmgr.exe',                 trigger:'відкрий диспетчер' },
  { cat:'📁 Програми',          ico:'📊', name:'Excel',          desc:'Microsoft Excel',           type:'shell',  body:'excel.exe',                   trigger:'відкрий excel' },
  { cat:'📁 Програми',          ico:'📄', name:'Word',           desc:'Microsoft Word',            type:'shell',  body:'winword.exe',                 trigger:'відкрий word' },
  { cat:'📁 Програми',          ico:'📧', name:'Outlook',        desc:'Microsoft Outlook',         type:'shell',  body:'outlook.exe',                 trigger:'відкрий пошту' },
  { cat:'📁 Програми',          ico:'🎮', name:'Steam',          desc:'Відкрити Steam',            type:'shell',  body:'steam://open/main',           trigger:'відкрий стім' },
  { cat:'📁 Програми',          ico:'💬', name:'Discord',        desc:'Відкрити Discord',          type:'shell',  body:'discord://',                  trigger:'відкрий дискорд' },

  { cat:'⌨️ Клавіатура',        ico:'🖥',  name:'Робочий стіл',  desc:'Win+D — показати стіл',     type:'python', body:'import pyautogui; pyautogui.hotkey("win","d")',                   trigger:'показати стіл' },
  { cat:'⌨️ Клавіатура',        ico:'🔄', name:'Alt+Tab',        desc:'Переключити вікно',         type:'python', body:'import pyautogui; pyautogui.hotkey("alt","tab")',                 trigger:'переключи вікно' },
  { cat:'⌨️ Клавіатура',        ico:'📸', name:'Скріншот',       desc:'Зробити скріншот',          type:'python', body:'import pyautogui; pyautogui.screenshot().save("screenshot.png"); import os; os.startfile("screenshot.png")', trigger:'зроби скріншот' },
  { cat:'⌨️ Клавіатура',        ico:'📋', name:'Копіювати',      desc:'Ctrl+C',                    type:'python', body:'import pyautogui; pyautogui.hotkey("ctrl","c")',                  trigger:'скопіювати' },
  { cat:'⌨️ Клавіатура',        ico:'📌', name:'Вставити',       desc:'Ctrl+V',                    type:'python', body:'import pyautogui; pyautogui.hotkey("ctrl","v")',                  trigger:'вставити' },
  { cat:'⌨️ Клавіатура',        ico:'↩',  name:'Відмінити',      desc:'Ctrl+Z',                    type:'python', body:'import pyautogui; pyautogui.hotkey("ctrl","z")',                  trigger:'відмінити' },
  { cat:'⌨️ Клавіатура',        ico:'❌', name:'Закрити вікно',  desc:'Alt+F4',                    type:'python', body:'import pyautogui; pyautogui.hotkey("alt","f4")',                  trigger:'закрити вікно' },
  { cat:'⌨️ Клавіатура',        ico:'🔍', name:'Пошук Windows',  desc:'Відкрити пошук Win',        type:'python', body:'import pyautogui; pyautogui.hotkey("win","s")',                   trigger:'відкрий пошук' },

  { cat:'🔊 Звук та медіа',     ico:'🔇', name:'Мут',            desc:'Вимкнути звук',             type:'shell',  body:'powershell -c "(New-Object -com WScript.Shell).SendKeys([char]173)"',   trigger:'вимкни звук' },
  { cat:'🔊 Звук та медіа',     ico:'🔊', name:'Зняти мут',      desc:'Увімкнути звук',            type:'shell',  body:'powershell -c "(New-Object -com WScript.Shell).SendKeys([char]173)"',   trigger:'увімкни звук' },
  { cat:'🔊 Звук та медіа',     ico:'🔉', name:'Гучність -',     desc:'Гучність -5 кроків',        type:'shell',  body:'powershell -c "1..5|%{(New-Object -com WScript.Shell).SendKeys([char]174)}"', trigger:'тихіше' },
  { cat:'🔊 Звук та медіа',     ico:'🔈', name:'Гучність +',     desc:'Гучність +5 кроків',        type:'shell',  body:'powershell -c "1..5|%{(New-Object -com WScript.Shell).SendKeys([char]175)}"', trigger:'гучніше' },
  { cat:'🔊 Звук та медіа',     ico:'⏭',  name:'Наступний трек', desc:'Media Next',                type:'shell',  body:'powershell -c "(New-Object -com WScript.Shell).SendKeys([char]176)"',   trigger:'наступна пісня' },
  { cat:'🔊 Звук та медіа',     ico:'⏮',  name:'Попередній трек',desc:'Media Previous',            type:'shell',  body:'powershell -c "(New-Object -com WScript.Shell).SendKeys([char]177)"',   trigger:'попередня пісня' },
  { cat:'🔊 Звук та медіа',     ico:'⏯',  name:'Пауза / Пуск',  desc:'Media Play/Pause',          type:'shell',  body:'powershell -c "(New-Object -com WScript.Shell).SendKeys([char]179)"',   trigger:'пауза' },

  { cat:'🖥️ Система',           ico:'🔒', name:'Заблокувати ПК', desc:'Блокування екрану',         type:'shell',  body:'rundll32.exe user32.dll,LockWorkStation',                trigger:'заблокуй комп' },
  { cat:'🖥️ Система',           ico:'😴', name:'Сон',            desc:'Режим сну',                 type:'shell',  body:'rundll32.exe powrprof.dll,SetSuspendState 0,1,0',        trigger:'увімкни сон' },
  { cat:'🖥️ Система',           ico:'🔄', name:'Перезавантажити',desc:'Перезавантаження (30с)',    type:'shell',  body:'shutdown /r /t 30',                                      trigger:'перезавантаж' },
  { cat:'🖥️ Система',           ico:'⛔', name:'Вимкнути ПК',    desc:'Вимкнення (30 сек)',        type:'shell',  body:'shutdown /s /t 30',                                      trigger:'вимкни комп' },
  { cat:'🖥️ Система',           ico:'✅', name:'Скасувати вимкн.',desc:'Зупинити countdown',       type:'shell',  body:'shutdown /a',                                            trigger:'скасуй вимкнення' },
  { cat:'🖥️ Система',           ico:'🗑', name:'Очист. кошик',   desc:'Очистити кошик',            type:'python', body:'import subprocess; subprocess.run(["powershell","-c","Clear-RecycleBin -Force"],capture_output=True)', trigger:'очисти кошик' },
  { cat:'🖥️ Система',           ico:'📋', name:'Очист. буфер',   desc:'Очистити clipboard',        type:'shell',  body:'powershell -c "Set-Clipboard -Value $null"',             trigger:'очисти буфер' },
  { cat:'🖥️ Система',           ico:'⚡', name:'Режим енергії',  desc:'Переключити план живлення', type:'shell',  body:'powercfg /setactive scheme_min',                         trigger:'режим продуктивності' },

  { cat:'🐍 Python скрипти',    ico:'🕐', name:'Поточний час',   desc:'Показати час',              type:'python', body:'from datetime import datetime; print(datetime.now().strftime("%H:%M:%S %d.%m.%Y"))', trigger:'який час' },
  { cat:'🐍 Python скрипти',    ico:'🌐', name:'Мій IP',         desc:'Показати IP адресу',        type:'python', body:'import socket; print("IP:", socket.gethostbyname(socket.gethostname()))', trigger:'який мій ip' },
  { cat:'🐍 Python скрипти',    ico:'💾', name:'Вільне місце',   desc:'Показати місце на диску',   type:'python', body:'import shutil; t,u,f=shutil.disk_usage("/"); print(f"Диск: {f//2**30}GB вільно з {t//2**30}GB")', trigger:'вільне місце' },
  { cat:'🐍 Python скрипти',    ico:'📊', name:'RAM використання',desc:'Показати RAM',             type:'python', body:'import psutil; m=psutil.virtual_memory(); print(f"RAM: {m.used//1024**2}MB / {m.total//1024**2}MB ({m.percent}%)")', trigger:'скільки оперативки' },
  { cat:'🐍 Python скрипти',    ico:'📁', name:'Список файлів',  desc:'Файли в поточній папці',    type:'python', body:'import os; files=os.listdir("."); print("\\n".join(files[:20]))', trigger:'список файлів' },
  { cat:'🐍 Python скрипти',    ico:'🔔', name:'Нотифікація',    desc:'Показати сповіщення',       type:'python', body:'from plyer import notification; notification.notify(title="AXIS OS", message="Готово!", timeout=5)', trigger:'покажи сповіщення' },

  { cat:'⚙ Внутрішні AXIS',     ico:'📊', name:'Системний звіт', desc:'Статистика CPU/RAM',        type:'internal', body:'system_report',  trigger:'системний звіт' },
  { cat:'⚙ Внутрішні AXIS',     ico:'⚙',  name:'Налаштування',   desc:'Відкрити налаштування',     type:'internal', body:'open_settings',  trigger:'відкрий налаштування' },
  { cat:'⚙ Внутрішні AXIS',     ico:'🗑', name:'Очистити чат',   desc:'Очистити повідомлення',     type:'internal', body:'clear_chat',     trigger:'очисти чат' },
];

function openCmdTemplates() {
  R('tplSearch').value = '';
  renderTemplates(CMD_TEMPLATES);
  R('cmdTplModal').style.display = 'flex';
  setTimeout(function(){ R('tplSearch').focus(); }, 100);
}

function closeCmdTemplates() {
  R('cmdTplModal').style.display = 'none';
}

function filterTemplates(q) {
  if (!q.trim()) { renderTemplates(CMD_TEMPLATES); return; }
  var lq = q.toLowerCase();
  renderTemplates(CMD_TEMPLATES.filter(function(t){
    return (t.name+t.desc+t.cat+t.trigger).toLowerCase().includes(lq);
  }));
}

var _tplFiltered = [];

function renderTemplates(list) {
  var body = R('tplBody'); if (!body) return;
  _tplFiltered = list;
  if (!list.length) { body.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text3);">Нічого не знайдено</div>'; return; }

  var cats = {};
  var idxMap = {};
  list.forEach(function(t, i){
    if (!cats[t.cat]) cats[t.cat] = [];
    cats[t.cat].push({t:t, i:i});
  });

  body.innerHTML = Object.keys(cats).map(function(cat, ci) {
    var items = cats[cat].map(function(entry){
      return '<div class="tpl-item" data-tpl-idx="'+entry.i+'">'
        + '<div class="tpl-item-ico">'+entry.t.ico+'</div>'
        + '<div style="min-width:0;">'
        +   '<div class="tpl-item-name">'+entry.t.name+'</div>'
        +   '<div class="tpl-item-desc">'+entry.t.desc+'</div>'
        +   '<span class="tpl-item-type">'+entry.t.type+'</span>'
        + '</div></div>';
    }).join('');
    var isFirst = ci === 0;
    return '<div class="tpl-cat">'
      + '<div class="tpl-cat-hdr'+(isFirst?' open':'')+'" onclick="toggleTplCat(this)">'
      + cat+'<span class="tpl-arrow">▼</span></div>'
      + '<div class="tpl-cat-items'+(isFirst?'':' hidden')+'">'+items+'</div>'
      + '</div>';
  }).join('');

  body.querySelectorAll('.tpl-item').forEach(function(el){
    el.addEventListener('click', function(){
      applyTemplate(_tplFiltered[parseInt(this.dataset.tplIdx)]);
    });
  });
}

function toggleTplCat(hdr) {
  var items = hdr.nextElementSibling;
  var open = !items.classList.contains('hidden');
  if (open) { items.classList.add('hidden'); hdr.classList.remove('open'); }
  else       { items.classList.remove('hidden'); hdr.classList.add('open'); }
}

function applyTemplate(t) {
  // Fill type
  var typeBtns = document.querySelectorAll('.cmd-type-radio-btn');
  typeBtns.forEach(function(b){ b.classList.toggle('active', b.dataset.type === t.type); });
  _newCmdType = t.type;
  updateCmdBodyLabel(t.type);
  // Fill fields
  if (R('cmdName'))    R('cmdName').value    = t.name;
  if (R('cmdBody'))    R('cmdBody').value    = t.body;
  if (R('cmdIcon'))    R('cmdIcon').value    = t.ico;
  if (R('cmdTrigger') && !R('cmdTrigger').value) R('cmdTrigger').value = t.trigger;
  closeCmdTemplates();
  showToast('✓ Шаблон «' + t.name + '» застосовано');
}

// ═══ COMMAND OVERLAY ═══
var _cmdOverlayEl = null;
var _cmdOverlayTimer = null;

function showCmdOverlay(name) {
  if (!_cmdExecCfg.overlay) return;
  if (!_cmdOverlayEl) {
    _cmdOverlayEl = document.createElement('div');
    _cmdOverlayEl.className = 'cmd-overlay';
    _cmdOverlayEl.innerHTML = '<span class="cmd-overlay-dot"></span><span id="cmdOverlayText"></span>';
    document.body.appendChild(_cmdOverlayEl);
  }
  var pos = _cmdExecCfg.overlayPos || 'tl';
  var posMap = {
    tl:'top:20px;left:20px',  tc:'top:20px;left:50%;transform:translateX(-50%)',  tr:'top:20px;right:20px',
    bl:'bottom:20px;left:20px',bc:'bottom:20px;left:50%;transform:translateX(-50%)',br:'bottom:20px;right:20px',
  };
  _cmdOverlayEl.style.cssText = (_cmdOverlayEl.style.cssText || '') + ';position:fixed;' + (posMap[pos]||posMap.tl);
  _cmdOverlayEl.querySelector('#cmdOverlayText').textContent = '▶ ' + name;
  _cmdOverlayEl.classList.add('show');
  clearTimeout(_cmdOverlayTimer);
  _cmdOverlayTimer = setTimeout(function(){ if(_cmdOverlayEl) _cmdOverlayEl.classList.remove('show'); }, 2500);
}

// ═══ COMMAND CHAINING ═══
function splitByChainWords(text) {
  var words = (_cmdExecCfg.chainWords || 'і,та,потім,затем').split(',').map(function(w){ return w.trim().toLowerCase(); }).filter(Boolean);
  if (!words.length) return [text];
  var pattern = new RegExp('\\b(' + words.map(function(w){ return w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); }).join('|') + ')\\b', 'gi');
  return text.split(pattern).map(function(s){ return s.trim(); }).filter(function(s){ return s && !words.includes(s.toLowerCase()); });
}

// ═══ NOTIFICATIONS ═══
var _notifSettings = JSON.parse(localStorage.getItem('axis_notif') || '{"ai":true,"cmd":true,"err":true,"sound":"ding","toastDur":4}');
var _toastDuration = _notifSettings.toastDur || 4;

function saveNotifSettings() {
  _notifSettings = {
    ai:       R('notifAiSound')  ? R('notifAiSound').checked  : true,
    cmd:      R('notifCmdSound') ? R('notifCmdSound').checked : true,
    err:      R('notifErrSound') ? R('notifErrSound').checked : true,
    sound:    R('notifSoundType') ? R('notifSoundType').value : 'ding',
    toastDur: R('toastDuration') ? parseInt(R('toastDuration').value) : 4,
  };
  _toastDuration = _notifSettings.toastDur;
  localStorage.setItem('axis_notif', JSON.stringify(_notifSettings));
}

function loadNotifSettings() {
  if (R('notifAiSound'))   R('notifAiSound').checked   = _notifSettings.ai !== false;
  if (R('notifCmdSound'))  R('notifCmdSound').checked  = _notifSettings.cmd !== false;
  if (R('notifErrSound'))  R('notifErrSound').checked  = _notifSettings.err !== false;
  if (R('notifSoundType')) R('notifSoundType').value   = _notifSettings.sound || 'ding';
  if (R('toastDuration'))  { R('toastDuration').value  = _notifSettings.toastDur || 4; R('toastDurVal').textContent = _notifSettings.toastDur || 4; }
}

function previewNotifSound() { playNotifSound('ding'); }

function playNotifSound(type) {
  var t = type || (_notifSettings.sound || 'ding');
  if (t === 'none') return;
  try {
    var ctx = new (window.AudioContext || window.webkitAudioContext)();
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    var freqs = {ding:[880,0.15], chime:[1047,0.25], pop:[400,0.08], beep:[600,0.1]};
    var f = freqs[t] || freqs.ding;
    osc.frequency.value = f[0];
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + f[1]);
    osc.start(); osc.stop(ctx.currentTime + f[1]);
  } catch(e) {}
}

// ═══ HOTKEYS ═══
var _hotkeys = JSON.parse(localStorage.getItem('axis_hotkeys') || '{}');
var _hotkeyCapturing = null;

function loadHotkeyInputs() {
  document.querySelectorAll('.hotkey-input').forEach(function(inp) {
    var action = inp.dataset.action;
    inp.value = _hotkeys[action] || '';
    inp.placeholder = {mic:'Ctrl+Shift+M', live:'Ctrl+Shift+L', clear_chat:'Ctrl+Shift+D', settings:'Ctrl+,', new_chat:'Ctrl+N'}[action] || '';
  });
}

function captureHotkey(inp) {
  if (_hotkeyCapturing) { _hotkeyCapturing.classList.remove('recording'); }
  _hotkeyCapturing = inp;
  inp.classList.add('recording');
  inp.value = 'Натисніть клавіші...';
  inp.dataset.listening = '1';
}

function clearHotkey(inp) {
  var action = inp.dataset.action;
  delete _hotkeys[action];
  inp.value = '';
  localStorage.setItem('axis_hotkeys', JSON.stringify(_hotkeys));
  showToast('Клавішу скинуто');
}

function resetHotkeys() {
  _hotkeys = {};
  localStorage.setItem('axis_hotkeys', JSON.stringify(_hotkeys));
  loadHotkeyInputs();
  showToast('↺ Гарячі клавіші скинуто');
}

document.addEventListener('keydown', function(e) {
  // Capture mode
  if (_hotkeyCapturing && _hotkeyCapturing.dataset.listening === '1') {
    e.preventDefault();
    var parts = [];
    if (e.ctrlKey)  parts.push('Ctrl');
    if (e.shiftKey) parts.push('Shift');
    if (e.altKey)   parts.push('Alt');
    var k = e.key;
    if (!['Control','Shift','Alt','Meta'].includes(k)) {
      if (k === ',') k = ',';
      parts.push(k.length === 1 ? k.toUpperCase() : k);
      var combo = parts.join('+');
      _hotkeyCapturing.value = combo;
      _hotkeys[_hotkeyCapturing.dataset.action] = combo;
      localStorage.setItem('axis_hotkeys', JSON.stringify(_hotkeys));
      _hotkeyCapturing.classList.remove('recording');
      _hotkeyCapturing.dataset.listening = '0';
      _hotkeyCapturing = null;
      showToast('✓ Клавішу збережено: ' + combo);
    }
    return;
  }
  // Execute hotkeys
  var combo = (e.ctrlKey?'Ctrl+':'') + (e.shiftKey?'Shift+':'') + (e.altKey?'Alt+':'') + (e.key.length===1?e.key.toUpperCase():e.key);
  combo = combo.replace(/\+$/,'');
  for (var action in _hotkeys) {
    if (_hotkeys[action] === combo) {
      e.preventDefault();
      if (action === 'mic')        { toggleRecording(); }
      else if (action === 'live')  { startLiveMode(); }
      else if (action === 'clear_chat') { clearChat(); }
      else if (action === 'settings')   { showPage('settings'); }
      else if (action === 'new_chat')   { clearChat(); showPage('chat'); }
      break;
    }
  }
});
