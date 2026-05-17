/* AXIS OS ? Core utilities & bridge */
// ═══════════════════════════════════════════════════
// PYTHON BRIDGE — axisPush receives data from Python
// pyCall sends commands to Python
// (pyCall itself is injected by Python; fallback below)
// ═══════════════════════════════════════════════════
if (typeof pyCall === 'undefined') {
  window.pyCall = function(cmd, data) { /* standalone fallback */ };
}

window.axisPush = function(type, jsonStr) {
  try {
    var d = JSON.parse(jsonStr);
    var map = {
      sys_stats:   handleSysStats,
      ai_response: handleAiResponse,
      ai_error:    handleAiError,
      toast:       function(x) { showToast(x.msg); },
      code_output:   handleCodeOutput,
      file_content:  handleFileContent,
      file_selected: handleFileSelected,
      tts_audio:   handleTtsAudio,
      tts_error:   function(x) { showToast('⚠ TTS: ' + x.error); if(liveSpeaking){ liveSpeaking=false; liveOnSpeakEnd(); } },
      stt_result:  handleSttResult,
      mic_devices: function(x) {
        var sel = R('micDeviceSel'); if (!sel) return;
        var devices = Array.isArray(x) ? x : [];
        sel.innerHTML = '<option value="-1">🎤 За замовчуванням</option>' +
          devices.map(function(d) {
            var sel_ = (_micSettings.deviceIndex === d.index) ? ' selected' : '';
            return '<option value="'+d.index+'"'+sel_+'>'+d.label+'</option>';
          }).join('');
        showToast('✓ Знайдено ' + devices.length + ' мікрофонів');
      },
      stt_error:   function(x) {
        isRecording = false;
        var btn = R('micBtn'); if(btn) btn.classList.remove('recording');
        showToast('⚠ Мікрофон: ' + x.error);
        if(liveMode) stopLiveMode();
      },
      sphere_config: function(x) {
        _savedCfg = x;
        if (x.api_keys) { _savedApiKeys = x.api_keys; updateGenKeyStatus(); if(R('acpProvidersList')) renderAcpProviders(); }
        loadSphereSettings(x);
        if (x.accent_color)  document.documentElement.style.setProperty('--accent', x.accent_color);
        if (x.accent_color2) document.documentElement.style.setProperty('--indigo', x.accent_color2);
        if (x.theme) loadSavedTheme(x.theme);
        if (x.ollama_url)    { var _ou=R('ollamaUrl'); if(_ou) _ou.value=x.ollama_url; }
        if (x.update_folder) { var _uf=R('updateFolderInp'); if(_uf) _uf.value=x.update_folder; }
        if (x.github_repo)   { var _gr=R('githubRepoInp');   if(_gr) _gr.value=x.github_repo; }
        var _auc=R('autoUpdateChk'); if(_auc) _auc.checked = (x.auto_update !== false);
        if (x.custom_system_prompt) { var _cs=R('customSystemPrompt'); if(_cs) _cs.value=x.custom_system_prompt; }
        var _ai=x.ai||{};
        if (_ai.default_provider) { var _dp=R('defaultProvider'); if(_dp) _dp.value=_ai.default_provider; }
        if (_ai.temperature!==undefined) { var _tp=R('aiTemperature'); if(_tp) _tp.value=_ai.temperature; }
        if (_ai.max_tokens!==undefined)  { var _mt=R('maxTokens');     if(_mt) _mt.value=_ai.max_tokens; }
        if (x.sphere_visual) {
          document.querySelectorAll('.viz-card').forEach(function(c){
            c.classList.toggle('active', c.dataset.viz === x.sphere_visual);
          });
        }
      },
      gen_result:    function(x) { handleGenResult(x); },
      ai_token:      function(x) {
        var id = x.id || '';
        if (id.startsWith('gen_'))  handleGenToken(x);
        else if (id.startsWith('acp_')) acpHandleToken && acpHandleToken(x);
        else handleChatToken && handleChatToken(x);   // chat streaming
      },
      ai_done:       function(x) {
        var id = x.id || '';
        if (id.startsWith('gen_'))  handleGenDone(x);
        else if (id.startsWith('acp_')) acpHandleDone && acpHandleDone(x);
        else handleChatDone && handleChatDone(x);     // chat streaming
      },
      image_ready:   function(x) { handleImageReady(x); },
      video_ready:   function(x) { handleVideoReady(x); },
      sphere_status: function(x) { updateSphereStatus(!!x.running); },
      ide_status:    function(x) { handleIdeStatus(x); },
      ide_config:    function(x) { if(x) ideApplyConfig(x); },
      autostart_status: function(x) {
        // Sync hidden checkboxes (for saveSphereSettings)
        var sa = R('sp_autostart'); if (sa) sa.checked = !!x.sphere;
        var aa = R('axis_autostart'); if (aa) aa.checked = !!x.axis;
        // Update visual cards
        setAutostartCard('axis_autostart_card',    'axis_autostart_badge',    !!x.axis);
        setAutostartCard('sphere_autostart_card',  'sphere_autostart_badge',  !!x.sphere);
        setAutostartCard('sphere_autostart_card2', 'sphere_autostart_badge2', !!x.sphere);
      },
      user_commands: function(x) { if(Array.isArray(x)){ commands=_normalizeCmds(x); sortAndRenderLib(); renderRecentCmds(); } },
      macros_data:   function(x) { if(Array.isArray(x)){ macros=x; initMacros(); } },
      file_saved:    function(x) { if(x.path) ideCurrentPath=x.path; },
      ollama_models: function(x) { if(Array.isArray(x)) loadOllamaChips(x); },
      navigate:    function(x) { if(x.page) showPage(x.page); },
      internal_cmd:function(x) {
        var c = x.cmd || '';
        if(c.startsWith('page:')) showPage(c.slice(5));
        else showToast('⚡ ' + c);
      },
      stt_status:  function(x) {
        if(x.status === 'listening') {
          var btn = R('micBtn'); if(btn) btn.classList.add('recording');
        } else if(x.status === 'no_speech' || x.status === 'timeout') {
          isRecording = false;
          var btn = R('micBtn'); if(btn) btn.classList.remove('recording');
        } else if(x.status === 'live_ready') {
          setLiveState('listening');
        }
      },
      clipboard_content: function(x) { handleClipboardContent(x); },
      api_status:      function(x) { if(typeof _renderApiStatus==='function') _renderApiStatus(x); },
      update_status:          function(x) { if(typeof handleUpdateStatus==='function') handleUpdateStatus(x); },
      github_update_status:   function(x) { if(typeof handleGithubUpdateStatus==='function') handleGithubUpdateStatus(x); },
      github_download_status: function(x) { if(typeof handleGithubDownloadStatus==='function') handleGithubDownloadStatus(x); },
      spotify_track:   function(x) { if(typeof handleSpotifyTrack==='function') handleSpotifyTrack(x); },
      spotify_search:  function(x) { if(typeof handleSpotifySearch==='function') handleSpotifySearch(x); },
      log_line:        function(x) { appendLog(x.level, x.msg); },
    };
    if (map[type]) map[type](d);
  } catch(e) { console.error('axisPush:', e); }
};

// ── Log viewer ────────────────────────────────────────────────────────────────
var _logLines = [];
var _logMax   = 500;

function appendLog(level, msg) {
  var ts = new Date().toLocaleTimeString('uk-UA', {hour12:false});
  _logLines.push({ts: ts, level: level, msg: msg});
  if (_logLines.length > _logMax) _logLines.shift();
  var el = document.getElementById('log-output');
  if (!el) return;
  var line = document.createElement('div');
  line.className = 'log-line log-' + (level || 'info');
  line.innerHTML = '<span class="log-ts">' + ts + '</span> ' +
    '<span class="log-msg">' + _escHtml(msg) + '</span>';
  el.appendChild(line);
  // auto-scroll if near bottom
  if (el.scrollHeight - el.scrollTop < el.clientHeight + 60) {
    el.scrollTop = el.scrollHeight;
  }
}

function clearLogs() {
  _logLines = [];
  var el = document.getElementById('log-output');
  if (el) el.innerHTML = '';
}

function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ═══ UTILS ═══
function showToast(msg, dur) {
  dur = dur || (_toastDuration ? _toastDuration * 1000 : 2800);
  var t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._t); t._t = setTimeout(function(){ t.classList.remove('show'); }, dur);
}
function R(id){ return document.getElementById(id); }

// ═══ CLOCK ═══
function updateClock(){
  var n = new Date();
  R('hTime').textContent = n.toLocaleTimeString('uk-UA',{hour12:false});
}
setInterval(updateClock, 1000); updateClock();

// ═══ SPLASH ═══
(function(){
  var bg = R('splashBg');
  for(var i=0;i<40;i++){
    var p=document.createElement('div');p.className='sp';
    p.style.cssText='left:'+Math.random()*100+'%;width:'+(1+Math.random()*2)+'px;height:'+(1+Math.random()*2)+'px;animation-duration:'+(4+Math.random()*8)+'s;animation-delay:'+(Math.random()*6)+'s;';
    bg.appendChild(p);
  }
  var bar=R('splashBar'), status=R('splashStatus');
  var steps=[
    [10,'Ініціалізація ядра AXIS...'],
    [25,'Завантаження AI модулів...'],
    [45,'Підключення Python bridge...'],
    [65,'Налаштування інтерфейсу...'],
    [85,'Перевірка конфігурації...'],
    [100,'Готово!']
  ];
  var i=0;
  function run(){
    if(i>=steps.length){
      setTimeout(function(){ R('splashScreen').classList.add('hide'); initApp(); },400);
      return;
    }
    bar.style.width=steps[i][0]+'%';
    status.textContent=steps[i][1];
    i++;
    setTimeout(run, 300+Math.random()*200);
  }
  setTimeout(run, 400);
})();

// ═══ NAVIGATION ═══
var pageTitles={dashboard:'Головна',monitor:'Системний монітор',agents:'AI Агенти',chat:'AI Чат',ide:'IDE',generator:'AI Генератор',music:'Музика',commands:'Команди',macros:'Автоматизація',network:'Нотатки',api:'API Ключі',settings:'Налаштування',logs:'Системні логи'};
var pageSubs={dashboard:'/ Огляд системи',monitor:'/ Продуктивність',agents:'/ Платформа для програмування',chat:'/ Діалог з AI',ide:'/ Розробка',generator:'/ Генерація проектів',music:'/ Spotify плеєр',commands:'/ Управління командами',macros:'/ Задачі та макроси',network:'/ Записи та ідеї',api:'/ Ключі доступу',settings:'/ Конфігурація',logs:'/ Python stdout & stderr'};

function showPage(id){
  document.querySelectorAll('.page,.page-flex').forEach(function(p){ p.classList.remove('active'); });
  var el=R('page-'+id); if(el) el.classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(function(b){ b.classList.remove('active'); });
  var nb=document.querySelector('[data-page="'+id+'"]'); if(nb) nb.classList.add('active');
  R('hTitle').textContent=pageTitles[id]||id;
  R('hBreadcrumb').textContent=pageSubs[id]||'';
  // Show/hide provider badge in header
  var hb = R('hdrModelBadge');
  if (hb) hb.style.display = (id === 'chat') ? 'flex' : 'none';
  if (id === 'commands') {
    if (R('cmdLibView') && R('cmdCreateView') && R('cmdCreateView').style.display === 'none') sortAndRenderLib();
  }
  if (id === 'music') {
    if (typeof onMusicPageShow === 'function') onMusicPageShow();
  } else {
    if (typeof onMusicPageHide === 'function') onMusicPageHide();
  }
}
document.querySelectorAll('.nav-btn[data-page]').forEach(function(b){
  b.onclick=function(){ showPage(b.dataset.page); };
});

// ═══ TABS ═══
function switchTab(el,id){
  el.parentElement.querySelectorAll('.tab').forEach(function(t){ t.classList.remove('active'); });
  el.classList.add('active');
  var container=el.parentElement.parentElement;
  container.querySelectorAll('.tab-content').forEach(function(c){ c.classList.remove('active'); });
  var tc=R(id); if(tc) tc.classList.add('active');
}
function showSSet(el, id) {
  // Nav highlight
  document.querySelectorAll('.snav-item').forEach(function(i){ i.classList.remove('active'); });
  el.classList.add('active');
  // Hide current with micro-fade, then show new
  var cur = document.querySelector('.sset.active');
  var next = R(id);
  if (!next || cur === next) return;
  if (cur) {
    cur.style.transition = 'opacity .1s';
    cur.style.opacity = '0';
    setTimeout(function() {
      cur.classList.remove('active');
      cur.style.transition = '';
      cur.style.opacity = '';
      next.classList.add('active');
      // Scroll content to top on section switch
      var sc = document.querySelector('.settings-content');
      if (sc) sc.scrollTop = 0;
    }, 100);
  } else {
    next.classList.add('active');
  }
}

function filterLogs(btn, filter) {
  document.querySelectorAll('.log-filter-btn').forEach(function(b){ b.classList.remove('active'); });
  btn.classList.add('active');
  document.querySelectorAll('#log-output .log-line').forEach(function(el){
    el.classList.toggle('hidden', filter !== 'all' && !el.classList.contains('log-' + filter));
  });
}

function copyAllLogs() {
  var text = _logLines.map(function(l){ return '['+l.ts+'] ['+l.level+'] '+l.msg; }).join('\n');
  navigator.clipboard.writeText(text).then(function(){ showToast('Логи скопійовано'); });
}
