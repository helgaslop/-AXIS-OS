/* AXIS OS ? Dashboard & system stats */
// ═══ SYSTEM STATS (from Python via axisPush) ═══
function handleSysStats(d) {
  // Dashboard
  var cpu = Math.round(d.cpu || 0);
  var cv = R('cpuVal'); if(cv){ cv.textContent=cpu+'%'; cv.style.color=cpu>80?'var(--red)':cpu>60?'var(--orange)':'var(--accent)'; }
  var cb = R('cpuBar'); if(cb) cb.style.width=cpu+'%';
  var rv = R('ramVal'); if(rv) rv.textContent=Math.round(d.ram||0)+'%';
  var rb = R('ramBar'); if(rb) rb.style.width=(d.ram||0)+'%';
  var dv = R('diskVal'); if(dv) dv.textContent=Math.round(d.disk||0)+'%';
  var db = R('diskBar'); if(db) db.style.width=(d.disk||0)+'%';
  var nv = R('netVal'); if(nv) nv.textContent=(d.net_recv||'—');

  var rs = R('ramSub'); if(rs && d.ram_used) rs.textContent=d.ram_used+' / '+d.ram_total;
  var ds = R('diskSub'); if(ds && d.disk_free) ds.textContent='Вільно: '+d.disk_free+' / '+d.disk_total;

  // Monitor gauges
  setGauge('cpuGaugeArc','cpuGaugeVal', cpu, '%');
  setGauge('ramGaugeArc','ramGaugeVal', Math.round(d.ram||0), '%');
  var rgs=R('ramGaugeSub'); if(rgs&&d.ram_used) rgs.textContent=d.ram_used+' / '+d.ram_total;

  if(d.gpu !== null && d.gpu !== undefined){
    setGauge('gpuGaugeArc','gpuGaugeVal', d.gpu, '%');
  }
  if(d.cpu_temp){
    var tp=Math.min(100, Math.max(0, Math.round(d.cpu_temp/100*100)));
    setGauge('tempGaugeArc','tempGaugeVal', tp, '°');
    R('tempGaugeVal').textContent=Math.round(d.cpu_temp)+'°';
  }

  // Sys info
  var si = R('sysInfoList');
  if(si) si.innerHTML=[
    ['ОС','Windows 11'],
    ['Uptime', d.uptime||'—'],
    ['Процеси', d.proc_count||'—'],
    ['CPU Temp', d.cpu_temp ? Math.round(d.cpu_temp)+'°C' : '—'],
    ['GPU Temp', d.gpu_temp ? d.gpu_temp+'°C' : '—'],
    ['AXIS OS','v1.0 · Активний'],
  ].map(function(r){ return '<div style="display:flex;justify-content:space-between;font-size:12px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.03)"><span style="color:var(--text3)">'+r[0]+'</span><span style="color:'+(r[0]==='AXIS OS'?'var(--accent)':'var(--text)')+'">'+r[1]+'</span></div>'; }).join('');

  // Disk info
  var di=R('diskInfoList');
  if(di && d.disks && d.disks.length){
    di.innerHTML=d.disks.map(function(dk){
      return '<div style="margin-bottom:10px;"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;"><span>'+_escDash(dk.device)+'</span><span style="color:var(--text3)">'+Math.round(dk.percent||0)+'% · '+_escDash(dk.total||'')+'</span></div><div class="prog"><div class="prog-bar prog-orange" style="width:'+Math.round(dk.percent||0)+'%"></div></div></div>';
    }).join('');
  }

  // Processes
  var pl=R('procList');
  if(pl && d.processes){
    var hdr='<div style="display:flex;font-size:10px;color:var(--text3);padding:4px 0;border-bottom:1px solid var(--border);margin-bottom:4px;font-weight:700;"><span style="flex:1">Процес</span><span style="min-width:60px;text-align:right">CPU</span><span style="min-width:80px;text-align:right">Пам\'ять</span></div>';
    pl.innerHTML=hdr+d.processes.map(function(p){
      return '<div class="proc-row"><span class="proc-name" style="font-family:var(--mono)">'+_escDash(p.name)+'</span><span class="proc-val">'+_escDash(String(p.cpu||0))+'%</span><span style="min-width:80px;text-align:right;font-size:11px;color:var(--text3)">'+_escDash(p.mem||'')+'</span></div>';
    }).join('');
  }

  // Disk detail
  var dl=R('diskDetailList');
  if(dl && d.disks){
    dl.innerHTML=d.disks.map(function(dk){
      return '<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.03);"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;"><span style="font-weight:600">'+_escDash(dk.device)+'</span><span class="badge badge-indigo">'+_escDash(dk.fstype||'')+'</span></div><div style="font-size:11px;color:var(--text3)">'+_escDash(dk.total||'')+' · Вільно: '+_escDash(dk.free||'')+'</div></div>';
    }).join('');
  }

  // Network page
  var nd=R('netDown'); if(nd) nd.textContent=d.net_recv||'—';
  var nu=R('netUp');   if(nu) nu.textContent=d.net_sent||'—';
  var nc=R('netConns'); if(nc) nc.textContent=d.proc_count||'—';

  var npl=R('netProcList');
  if(npl && d.processes){
    npl.innerHTML=d.processes.slice(0,5).map(function(p){
      return '<div class="conn-row"><div class="activity-dot" style="background:var(--accent)"></div><div style="flex:1;font-size:11px;font-family:var(--mono)">'+_escDash(p.name)+'</div><span style="color:var(--accent);font-size:11px;">'+_escDash(String(p.cpu||0))+'%</span></div>';
    }).join('');
  }

  var ndl=R('netDiskList');
  if(ndl && d.disks){
    ndl.innerHTML=d.disks.map(function(dk){
      return '<div class="conn-row"><span style="flex:1;font-size:11px;">'+dk.device+'</span><span style="font-size:11px;color:var(--text3)">'+dk.free+' вільно</span></div>';
    }).join('');
  }
}

function setGauge(arcId, valId, pct, unit){
  var arc=R(arcId); if(arc){ var c=201; arc.style.strokeDashoffset=c-(c*pct/100); }
  var val=R(valId); if(val) val.textContent=pct+unit;
}

// ═══ ACTIVITY FEED (реальний лог) ═══
var activities = JSON.parse(localStorage.getItem('axis_activity') || '[]');
if (!activities.length) {
  activities = [{title:'AXIS OS запущено', time: new Date().toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'}), color:'var(--accent)'}];
}

function addActivity(title, color) {
  color = color || 'var(--accent)';
  var time = new Date().toLocaleTimeString('uk-UA', {hour:'2-digit', minute:'2-digit'});
  activities.unshift({title: title.slice(0,60), time: time, color: color});
  if (activities.length > 30) activities = activities.slice(0, 30);
  try { localStorage.setItem('axis_activity', JSON.stringify(activities)); } catch(e){}
  initActivity();
}

function _escDash(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function initActivity(){
  var feed=R('activityFeed');
  if(!feed) return;
  var shown = activities.slice(0,8);
  feed.innerHTML=shown.map(function(a){
    // Sanitize color: only allow CSS variable refs or safe color values
    var safeColor = /^(var\(--[\w-]+\)|#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))$/.test(a.color||'') ? a.color : 'var(--accent)';
    return '<div class="activity-item"><div class="activity-dot" style="background:'+safeColor+'"></div><div><div class="activity-title">'+_escDash(a.title)+'</div><div class="activity-time">'+_escDash(a.time)+'</div></div></div>';
  }).join('');
}

// ═══ WEATHER ═══
var _weatherCache = null;
var _weatherTimer = null;

function fetchWeather() {
  try {
  var city = (typeof _savedCfg !== 'undefined' && _savedCfg && _savedCfg.weather_city)
             ? _savedCfg.weather_city
             : 'Kyiv';
  var el = R('weatherCity'); if(el) el.textContent = city;
  if (_weatherCache && _weatherCache.city === city && (Date.now() - _weatherCache.ts) < 1800000) {
    renderWeather(_weatherCache.data);
    return;
  }
  // Show loading state while fetching
  var tempEl = R('weatherTemp');   if(tempEl)  tempEl.textContent  = '…';
  var descEl = R('weatherDesc');   if(descEl)  descEl.textContent  = 'Завантаження…';
  var windEl = R('weatherWind');   if(windEl)  windEl.textContent  = '';
  var iconEl = R('weatherIcon');   if(iconEl)  iconEl.textContent  = '🌡️';

  fetch('https://wttr.in/' + encodeURIComponent(city) + '?format=j1')
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(d){
      _weatherCache = {city: city, data: d, ts: Date.now()};
      try { localStorage.setItem('axis_weather_cache', JSON.stringify(_weatherCache)); } catch(e){}
      renderWeather(d);
    })
    .catch(function(err){
      var eTemp = R('weatherTemp'); if(eTemp) eTemp.textContent = '—';
      var eDesc = R('weatherDesc'); if(eDesc) eDesc.textContent = 'Немає з\'єднання';
      var eWind = R('weatherWind'); if(eWind) eWind.textContent = '';
      var eIcon = R('weatherIcon'); if(eIcon) eIcon.textContent = '⚠';
      var eFc   = R('weatherForecast'); if(eFc) eFc.innerHTML = '';
      console.warn('fetchWeather failed:', err);
    });
  } catch(e) { console.warn('fetchWeather error:', e); }
}

function renderWeather(d) {
  try {
    var cur = d.current_condition[0];
    var temp = cur.temp_C + '°C';
    var desc = cur.lang_ua ? cur.lang_ua[0].value : cur.weatherDesc[0].value;
    var wind = 'Вітер: ' + cur.windspeedKmph + ' км/год';
    var wCode = parseInt(cur.weatherCode);
    var icon = weatherIcon(wCode);
    var el;
    el = R('weatherTemp'); if(el) el.textContent = temp;
    el = R('weatherDesc'); if(el) el.textContent = desc;
    el = R('weatherWind'); if(el) el.textContent = wind;
    el = R('weatherIcon'); if(el) el.textContent = icon;
    // 3-day forecast
    var fc = R('weatherForecast');
    if(fc && d.weather) {
      fc.innerHTML = d.weather.slice(0,3).map(function(day){
        var dayTemp = day.avgtempC + '°';
        var dayDate = day.date ? day.date.slice(5) : '';
        var dayIcon = weatherIcon(parseInt(day.hourly && day.hourly[4] ? day.hourly[4].weatherCode : 113));
        return '<div style="flex:1;text-align:center;background:var(--bg2);border-radius:8px;padding:4px 2px;">'
          + '<div style="font-size:16px;">' + dayIcon + '</div>'
          + '<div style="font-size:11px;font-weight:600;color:var(--accent);">' + dayTemp + '</div>'
          + '<div style="font-size:9px;color:var(--text3);">' + dayDate + '</div>'
          + '</div>';
      }).join('');
    }
    addActivity('Погода: ' + temp + ' ' + desc.slice(0,20), 'var(--cyan)');
  } catch(e) {
    var el2 = R('weatherDesc'); if(el2) el2.textContent = 'Помилка даних';
  }
}

function weatherIcon(code) {
  if(code===113) return '☀️';
  if(code===116) return '⛅';
  if(code===119||code===122) return '☁️';
  if(code===143||code===248||code===260) return '🌫️';
  if(code===176||code===185||code===263||code===266||code===281||code===284||code===293||code===296||code===299||code===302||code===305||code===308) return '🌧️';
  if(code===179||code===182||code===311||code===314||code===317||code===320||code===323||code===326||code===329||code===332||code===335||code===338||code===350||code===353||code===356||code===359||code===362||code===365||code===368||code===371||code===374||code===377) return '🌨️';
  if(code===200||code===386||code===389||code===392||code===395) return '⛈️';
  return '🌡️';
}

// ═══ TODO ═══
var todos = JSON.parse(localStorage.getItem('axis_todos') || '[]');

function renderTodos() {
  var list = R('todoList');
  if(!list) return;
  list.innerHTML = todos.map(function(t, i){
    return '<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);">'
      + '<input type="checkbox"' + (t.done?' checked':'') + ' onchange="toggleTodo('+i+')" style="cursor:pointer;accent-color:var(--accent);">'
      + '<span style="flex:1;font-size:12px;color:' + (t.done?'var(--text3)':'var(--text)') + ';' + (t.done?'text-decoration:line-through;':'') + '">' + _escDash(t.text) + '</span>'
      + '<button onclick="deleteTodo('+i+')" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:14px;padding:0 2px;" title="Видалити">×</button>'
      + '</div>';
  }).join('') || '<div style="color:var(--text3);font-size:12px;text-align:center;padding:8px;">Завдань немає 🎉</div>';
}

function addTodo() {
  var inp = R('todoInput');
  if(!inp || !inp.value.trim()) return;
  todos.unshift({text: inp.value.trim(), done: false});
  inp.value = '';
  saveTodos();
  renderTodos();
  addActivity('Завдання: ' + todos[0].text.slice(0,30), 'var(--indigo)');
}

function toggleTodo(i) {
  if(todos[i]) { todos[i].done = !todos[i].done; saveTodos(); renderTodos(); }
}

function deleteTodo(i) {
  todos.splice(i, 1);
  saveTodos();
  renderTodos();
}

function saveTodos() {
  try { localStorage.setItem('axis_todos', JSON.stringify(todos)); } catch(e){}
}

// ═══ STATISTICS ═══
var _stats = JSON.parse(localStorage.getItem('axis_stats') || '{"total":0,"tokens":0,"cmds":0,"providers":{}}');

function trackAiRequest(provider, tokens) {
  _stats.total++;
  _stats.tokens += (tokens || 0);
  _stats.providers[provider] = (_stats.providers[provider] || 0) + 1;
  localStorage.setItem('axis_stats', JSON.stringify(_stats));
}

function trackCmdRun() {
  _stats.cmds++;
  localStorage.setItem('axis_stats', JSON.stringify(_stats));
}

function resetStats() {
  if (!confirm('Скинути статистику?')) return;
  _stats = {total:0, tokens:0, cmds:0, providers:{}};
  localStorage.setItem('axis_stats', JSON.stringify(_stats));
  renderStats();
  showToast('↺ Статистику скинуто');
}

function renderStats() {
  var g = R('statsGrid'); var p = R('statsProviders');
  if (!g || !p) return;
  var totalReqs  = (_stats.total  || 0);
  var totalCmds  = (_stats.cmds   || 0);
  var totalToks  = (_stats.tokens || 0);
  var sessToday  = parseInt(localStorage.getItem('axis_sessions_today') || '0') || 0;
  var cards = [
    {label:'Всього запитів',  val: totalReqs,  ico:'🤖'},
    {label:'Команд виконано', val: totalCmds,  ico:'⚡'},
    {label:'~Токени',        val: totalToks > 1000 ? (totalToks/1000).toFixed(1)+'k' : totalToks, ico:'🔢'},
    {label:'Сесій сьогодні', val: sessToday, ico:'📅'},
  ];
  g.innerHTML = cards.map(function(c){
    return '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">'
      + '<div style="font-size:18px;margin-bottom:4px;">'+c.ico+'</div>'
      + '<div style="font-size:20px;font-weight:800;color:var(--accent);">'+c.val+'</div>'
      + '<div style="font-size:10px;color:var(--text3);margin-top:2px;">'+c.label+'</div>'
      + '</div>';
  }).join('');
  var provs = Object.entries(_stats.providers).sort(function(a,b){return b[1]-a[1];});
  p.innerHTML = provs.length ? '<div style="font-size:11px;font-weight:700;color:var(--text2);margin-bottom:6px;">По провайдерах:</div>'
    + provs.map(function(pr){
        var pct = _stats.total ? Math.round(pr[1]/_stats.total*100) : 0;
        return '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
          + '<span style="font-size:11px;min-width:90px;color:var(--text2);">'+pr[0]+'</span>'
          + '<div style="flex:1;height:5px;background:var(--bg3);border-radius:3px;overflow:hidden;">'
          + '<div style="height:100%;width:'+pct+'%;background:var(--accent);border-radius:3px;transition:width .5s;"></div></div>'
          + '<span style="font-size:10px;color:var(--text3);min-width:32px;">'+pr[1]+'</span>'
          + '</div>';
      }).join('') : '<div style="font-size:11px;color:var(--text3);">Ще немає даних</div>';
}

// ═══ MEDIA CONTROLS ═══
var _mediaSrc = 'yt';   // 'yt' | 'spt'

function switchMediaSrc(src) {
  _mediaSrc = src;
  document.querySelectorAll('.media-src-btn').forEach(function(b){ b.classList.remove('active'); });
  var btn = R('mediaSrc' + (src === 'yt' ? 'Yt' : 'Spt'));
  if (btn) btn.classList.add('active');
}

// Media key shortcuts via PowerShell (works system-wide, silent — no toast)
function _mediaSendKey(keyCode) {
  pyCall('run_macro', JSON.stringify({
    type:    'shell',
    silent:  true,
    command: 'powershell -c "(new-object -com wscript.shell).SendKeys([char]' + keyCode + ')"'
  }));
}

function mediaPlayPause() { _mediaSendKey(179); showToast('⏯ Грати / Пауза', 900); }
function mediaNext()      { _mediaSendKey(176); showToast('⏭ Наступний трек', 900); }
function mediaPrev()      { _mediaSendKey(177); showToast('⏮ Попередній трек', 900); }
function mediaVolUp()     { _mediaSendKey(175); showToast('🔊 Гучніше', 700); }
function mediaVolDown()   { _mediaSendKey(174); showToast('🔉 Тихіше', 700); }

function mediaOpenYt() {
  pyCall('run_macro', JSON.stringify({type:'shell', silent:true,
    command:'start https://youtube.com'}));
  showToast('▶ YouTube');
}
function mediaOpenSpotify() {
  // Try Spotify app first (registered as URI), fallback to web
  pyCall('run_macro', JSON.stringify({type:'shell', silent:true,
    command:'start spotify:'}));
  showToast('🎵 Spotify');
}
function mediaOpenYtMusic() {
  pyCall('run_macro', JSON.stringify({type:'shell', silent:true,
    command:'start https://music.youtube.com'}));
  showToast('🎶 YouTube Music');
}

// Poll media info via Windows Media Session (best effort — no API key needed)
function _initMediaInfo() {
  // Try to get currently playing track via PowerShell SMTC
  setInterval(function(){
    if (document.getElementById('page-dashboard') &&
        document.getElementById('page-dashboard').classList.contains('active')) {
      _fetchMediaInfo();
    }
  }, 5000);
}

function _fetchMediaInfo() {
  // Placeholder — full SMTC needs UWP bridge
  // Controls work via media keys regardless
}

// ═══ CLIPBOARD HISTORY ═══
var _clipHistory = [];
var _lastClipText = '';
var _CLIP_KEY = 'axis_clip_history';
var _MAX_CLIP = 20;

function _initClipboard() {
  try { _clipHistory = JSON.parse(localStorage.getItem(_CLIP_KEY) || '[]'); } catch(e) { _clipHistory = []; }
  // Poll system clipboard via Python every 4s
  setInterval(function() { if (typeof pyCall !== 'undefined') pyCall('get_clipboard'); }, 4000);
  // Intercept in-app copy events
  document.addEventListener('copy', function() {
    setTimeout(function() {
      var sel = window.getSelection ? window.getSelection().toString() : '';
      if (sel) _addClipItem(sel);
    }, 50);
  });
}

function _addClipItem(text) {
  text = (text || '').trim();
  if (!text || text === _lastClipText) return;
  _lastClipText = text;
  // Remove duplicate
  _clipHistory = _clipHistory.filter(function(i){ return i.text !== text; });
  _clipHistory.unshift({ text: text, ts: Date.now() });
  if (_clipHistory.length > _MAX_CLIP) _clipHistory.length = _MAX_CLIP;
  try { localStorage.setItem(_CLIP_KEY, JSON.stringify(_clipHistory)); } catch(e) {}
  _renderClipHistory();
}

function handleClipboardContent(d) {
  if (d && d.text) _addClipItem(d.text);
}

function _renderClipHistory() {
  var el = R('clipHistoryList'); if (!el) return;
  if (!_clipHistory.length) {
    el.innerHTML = '<div style="font-size:11px;color:var(--text3);text-align:center;padding:12px 0;">Буфер порожній</div>';
    return;
  }
  el.innerHTML = _clipHistory.map(function(item, i) {
    var preview = item.text.length > 60 ? item.text.slice(0,60) + '…' : item.text;
    var ago = _timeDiff ? _timeDiff(item.ts) : '';
    return '<div class="clip-item" onclick="clipPaste('+i+')" title="'+escH(item.text)+'">'
      + '<div class="clip-preview">'+escH(preview)+'</div>'
      + '<div class="clip-meta">'
      + '<span class="clip-ago">'+ago+'</span>'
      + '<button class="btn btn-sm" style="padding:2px 7px;font-size:9px;" onclick="event.stopPropagation();clipCopy('+i+')">📋</button>'
      + '<button class="btn btn-sm btn-d" style="padding:2px 7px;font-size:9px;" onclick="event.stopPropagation();clipDelete('+i+')">✕</button>'
      + '</div></div>';
  }).join('');
}

function clipPaste(i) {
  var item = _clipHistory[i]; if (!item) return;
  // Paste into focused input if any
  var active = document.activeElement;
  if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) {
    var start = active.selectionStart, end = active.selectionEnd;
    active.value = active.value.slice(0, start) + item.text + active.value.slice(end);
    active.selectionStart = active.selectionEnd = start + item.text.length;
  } else {
    // fallback: copy to clipboard
    clipCopy(i);
  }
}

function clipCopy(i) {
  var item = _clipHistory[i]; if (!item) return;
  pyCall('set_clipboard', JSON.stringify({text: item.text}));
  if (typeof _copyText === 'function') _copyText(item.text, '📋 Скопійовано');
  else showToast('📋 Скопійовано');
}

function clipDelete(i) {
  _clipHistory.splice(i, 1);
  try { localStorage.setItem(_CLIP_KEY, JSON.stringify(_clipHistory)); } catch(e) {}
  _renderClipHistory();
}

function clearClipHistory() {
  _clipHistory = [];
  _lastClipText = '';
  localStorage.removeItem(_CLIP_KEY);
  _renderClipHistory();
  showToast('🗑 Буфер очищено');
}

function toggleClipPanel() {
  var panel = R('clipPanel');
  if (!panel) return;
  var visible = panel.style.display !== 'none';
  panel.style.display = visible ? 'none' : 'flex';
  if (!visible) _renderClipHistory();
}
