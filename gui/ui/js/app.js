/* AXIS OS ? App init */
// ═══ SPHERE STATUS ═══
var _sphereRunning = false;

function updateSphereStatus(running) {
  _sphereRunning = running;
  var dot  = R('sphereDot');
  var lbl  = R('sphereStatusLbl');
  var btn  = R('sphereLaunchBtn');
  var btn2 = R('sphereLaunchBtn2');

  if (dot) {
    dot.className = 'sphere-dot ' + (running ? 'online' : 'offline');
  }
  if (lbl) {
    lbl.className = 'sphere-status-lbl ' + (running ? 'online' : 'offline');
    lbl.textContent = running ? '🔮 Sphere працює' : '○ Sphere вимкнена';
  }
  if (btn) {
    btn.className = 'launch-btn' + (running ? ' stop' : '');
    btn.innerHTML = running ? '⏹ Зупинити Sphere' : '⬡ Запустити Sphere';
  }
  if (btn2) {
    btn2.className = 'btn ' + (running ? 'btn-d' : 'btn-p');
    btn2.innerHTML = running ? '⏹ Зупинити сферу' : '⬡ Запустити сферу';
  }
}

function toggleSphere() {
  if (_sphereRunning) {
    pyCall('stop_sphere');
  } else {
    pyCall('launch_sphere');
    // Optimistically disable button while sphere starts
    var btn = R('sphereLaunchBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Запускається...'; }
    var btn2 = R('sphereLaunchBtn2');
    if (btn2) { btn2.disabled = true; btn2.innerHTML = '⏳ Запускається...'; }
    setTimeout(function() {
      if (btn)  btn.disabled = false;
      if (btn2) btn2.disabled = false;
    }, 3500);
  }
}

// Poll sphere status every 5 seconds
setInterval(function() { if (typeof pyCall !== 'undefined') pyCall('sphere_status'); }, 5000);

// Close clipboard panel when clicking outside
document.addEventListener('click', function(e) {
  var panel = R('clipPanel');
  if (!panel || panel.style.display === 'none') return;
  if (!panel.contains(e.target) && !e.target.closest('[onclick*="toggleClipPanel"]')) {
    panel.style.display = 'none';
  }
});

// ═══ INIT ═══
function _safeCall(fn, label) {
  try { fn(); } catch(e) { console.error('[AXIS] init error in ' + (label||fn.name||'?') + ':', e); }
}

function initApp(){
  _safeCall(loadCustomRoles,    'loadCustomRoles');
  _safeCall(initActivity,       'initActivity');
  _safeCall(fetchWeather,       'fetchWeather');
  setInterval(fetchWeather, 1800000);
  _safeCall(renderTodos,        'renderTodos');
  _safeCall(initMacros,         'initMacros');
  _safeCall(initApi,            'initApi');
  _safeCall(initChat,           'initChat');
  _safeCall(initCommands,       'initCommands');
  _safeCall(initVoice,          'initVoice');
  _safeCall(renderRolesList,    'renderRolesList');
  _safeCall(function(){ updateGenModels('openai'); }, 'updateGenModels');
  _safeCall(updateGenKeyStatus, 'updateGenKeyStatus');
  _safeCall(loadNotifSettings,  'loadNotifSettings');
  _safeCall(loadHotkeyInputs,   'loadHotkeyInputs');
  _safeCall(loadAutoSleepSettings, 'loadAutoSleepSettings');
  _safeCall(loadChatSettings,   'loadChatSettings');
  _safeCall(loadCmdExecSettings,'loadCmdExecSettings');
  _safeCall(loadAppVolumeUI,    'loadAppVolumeUI');
  _safeCall(applyUiLanguage,    'applyUiLanguage');
  _safeCall(notesInit,          'notesInit');
  _safeCall(renderStats,        'renderStats');
  _safeCall(resetSleepTimer,    'resetSleepTimer');
  _safeCall(_initClipboard,     '_initClipboard');
  _safeCall(_initMediaInfo,     '_initMediaInfo');
  _safeCall(renderRecentCmds,   'renderRecentCmds');
  // Load real Windows autostart state for both checkboxes
  pyCall('get_autostart_status');
  // Check if sphere is already running
  pyCall('sphere_status');
  if (window.speechSynthesis) {
    populateBrowserVoices();
    window.speechSynthesis.onvoiceschanged = function(){
      if (currentTtsProv === 'browser') populateBrowserVoices();
    };
  }
}