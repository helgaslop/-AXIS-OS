/* AXIS OS ? Sphere & TTS */
// ═══ SPHERE SETTINGS ═══
function loadSphereSettings(d) {
  function sv(id, val) { var el=R(id); if(el&&val!==undefined&&val!==null) el.value=val; }
  function sc(id, val) { var el=R(id); if(el) el.checked=!!val; }

  sv('sp_wake',            d.sphere_wake         || 'Aivon');
  sv('sp_mode',            d.sphere_mode         || 'smart');
  sv('sp_silent_phrase',   d.silent_phrase       || 'хватить слухати');
  sv('sp_mic_off_phrase',  d.mic_off_phrase      || 'вимкни мікрофон');
  var sizeLoadMap = {'Малий':'small','Середній':'medium','Великий':'large'};
  sv('sp_size', sizeLoadMap[d.sphere_size] || (d.sphere_size||'medium').toLowerCase());
  sv('sp_anim',          d.sphere_anim       || 'pulse');
  sv('sp_language',      d.language          || 'uk-UA');
  sv('sp_tts_prov',      d.tts_provider      || 'openai');
  sv('sp_tts_voice',     d.tts_voice         || 'onyx');

  // Edge voice: handle custom values not present in the hardcoded select options
  var edgeVoice = d.edge_voice || 'uk-UA-PolinaNeural';
  var edgeSel = R('sp_edge_voice');
  if (edgeSel) {
    edgeSel.value = edgeVoice;
    // If the value didn't stick (custom voice not in list), inject a temporary option
    if (edgeSel.value !== edgeVoice) {
      var customOpt = document.createElement('option');
      customOpt.value = edgeVoice;
      customOpt.textContent = edgeVoice + ' (збережений)';
      edgeSel.insertBefore(customOpt, edgeSel.firstChild);
      edgeSel.value = edgeVoice;
    }
  }

  // Sync runtime TTS state so speakText() uses the saved provider/voice immediately
  var savedProv  = d.tts_provider || 'browser';
  var savedVoice = d.tts_voice    || '';
  onTtsProviderChange(savedProv);
  // After onTtsProviderChange populates ttsVoiceSel, override with the saved voice
  if (savedVoice) {
    currentTtsVoice = savedVoice;
    var vSel = R('ttsVoiceSel');
    if (vSel) vSel.value = savedVoice;
  }
  // Also sync the VOICE tab provider dropdown
  var ttsProvSel = R('ttsProv');
  if (ttsProvSel) ttsProvSel.value = savedProv;
  sv('sp_ai_prov',       d.ai_provider       || 'openai');
  sv('sp_dialog_prov',   d.dialog_provider   || 'openai');
  sv('sp_weather_city',  d.weather_city      || 'Kyiv');

  // Position — map Ukrainian labels to values
  var pos = d.sphere_position || 'bottom-right';
  var posMap = {
    'Правий нижній кут':'bottom-right','Лівий нижній кут':'bottom-left',
    'По центру':'center','Правий верхній кут':'top-right'
  };
  sv('sp_position', posMap[pos] || pos);

  // Sliders
  var op = parseInt(d.sphere_opacity)||90;
  var as = parseInt(d.sphere_anim_speed)||5;
  var pc = parseInt(d.sphere_particle_count)||20;
  var ts = parseFloat(d.tts_speed)||1.2;
  var tv = parseInt(d.tts_volume)||80;
  var jv = parseInt(d.jarvis_volume)||70;
  sv('sp_opacity',        op); R('sp_opacity_val') && (R('sp_opacity_val').textContent=op);
  sv('sp_anim_speed',     as); R('sp_anim_speed_val') && (R('sp_anim_speed_val').textContent=as);
  sv('sp_particle_count', pc); R('sp_pcount_val') && (R('sp_pcount_val').textContent=pc);
  sv('sp_tts_speed',      ts); R('sp_tts_speed_val') && (R('sp_tts_speed_val').textContent=ts.toFixed(1));
  sv('sp_tts_volume',     tv); R('sp_tts_vol_val') && (R('sp_tts_vol_val').textContent=tv);
  sv('sp_jarvis_vol',     jv); R('sp_jarvis_vol_val') && (R('sp_jarvis_vol_val').textContent=jv);

  // Colors
  var c1 = d.sphere_color || '#00d4ff';
  var c2 = d.sphere_color2 || '#7b2cbf';
  sv('sp_color', c1);  R('sp_color_val')  && (R('sp_color_val').textContent  = c1);
  sv('sp_color2',c2);  R('sp_color2_val') && (R('sp_color2_val').textContent = c2);
  var cc1=R('sp_color'); if(cc1) cc1.oninput=function(){ R('sp_color_val').textContent=this.value; };
  var cc2=R('sp_color2');if(cc2) cc2.oninput=function(){ R('sp_color2_val').textContent=this.value; };

  // Checkboxes
  sc('sp_autostart',     d.sphere_autostart !== false);
  sc('sp_particles',     d.sphere_particles !== false);
  sc('sp_jarvis',        !!d.jarvis_sounds);
  sc('sp_hand_gestures', !!d.hand_gestures);
  // Gesture settings visibility
  var gs = R('gesture_settings'); if (gs) gs.style.display = d.hand_gestures ? 'block' : 'none';
  var gc = R('sp_gesture_camera');   if (gc && d.gesture_camera !== undefined)    gc.value = d.gesture_camera;
  var gcd= R('sp_gesture_cooldown'); if (gcd && d.gesture_cooldown !== undefined) gcd.value = d.gesture_cooldown;
  var gop= R('sp_gesture_open_palm');if (gop && d.gesture_open_palm) gop.value = d.gesture_open_palm;
  var gfi= R('sp_gesture_fist');     if (gfi && d.gesture_fist)      gfi.value = d.gesture_fist;
  var gtu= R('sp_gesture_thumbs_up');if (gtu && d.gesture_thumbs_up) gtu.value = d.gesture_thumbs_up;
  var gr = R('sp_gesture_right');    if (gr  && d.gesture_right)     gr.value  = d.gesture_right;
  var gl = R('sp_gesture_left');     if (gl  && d.gesture_left)      gl.value  = d.gesture_left;
  // STT provider
  var sttProv = R('sp_stt_provider');
  if (sttProv) {
    sttProv.value = d.stt_provider || 'google';
    var wo = R('whisper_opts');
    if (wo) wo.style.display = (d.stt_provider === 'whisper') ? 'contents' : 'none';
  }
  var wm = R('sp_whisper_model'); if (wm && d.whisper_model) wm.value = d.whisper_model;
  var pr=R('sp_pcount_row');    if(pr) pr.style.display=(d.sphere_particles!==false)?'flex':'none';
  var jr=R('sp_jarvis_vol_row');if(jr) jr.style.display=(d.jarvis_sounds)?'flex':'none';
  // Telegram
  sc('sp_telegram_enabled', !!d.telegram_enabled);
  var tgs = R('tg_settings'); if (tgs) tgs.style.display = d.telegram_enabled ? 'block' : 'none';
  sv('sp_telegram_token',       d.telegram_token       || '');
  sv('sp_telegram_allowed_ids', d.telegram_allowed_ids || '');
  // Telegram custom commands
  tgCmdLoad(d.telegram_commands || []);

  // Відновити активну viz-картку
  if (d.sphere_visual) {
    document.querySelectorAll('.viz-card').forEach(function(c){ c.classList.remove('active'); });
    var activeCard = document.querySelector('.viz-card[data-viz="'+d.sphere_visual+'"]');
    if (activeCard) {
      activeCard.classList.add('active');
      // Показати потрібний таб
      ['viz-round','viz-wave','viz-music'].forEach(function(tab){
        var el = R(tab); if(el) el.style.display='none';
      });
      var parent = activeCard.closest('.viz-grid');
      if (parent) parent.style.display='grid';
    }
  }
}

function saveSphereSettings() {
  var pos  = (R('sp_position')||{}).value || 'bottom-right';
  var size = (R('sp_size')||{}).value || 'medium';
  var data = {
    sphere_wake:          (R('sp_wake')||{}).value||'Aivon',
    sphere_mode:          (R('sp_mode')||{}).value||'smart',
    silent_phrase:        (R('sp_silent_phrase') ||{}).value||'хватить слухати',
    mic_off_phrase:       (R('sp_mic_off_phrase')||{}).value||'вимкни мікрофон',
    sphere_size:          size,
    sphere_position:      pos,
    sphere_color:         (R('sp_color')||{}).value||'#00d4ff',
    sphere_color2:        (R('sp_color2')||{}).value||'#7b2cbf',
    sphere_opacity:       parseInt((R('sp_opacity')||{}).value)||90,
    sphere_anim:          (R('sp_anim')||{}).value||'pulse',
    sphere_anim_speed:    parseInt((R('sp_anim_speed')||{}).value)||5,
    sphere_particles:     !!(R('sp_particles')||{}).checked,
    sphere_particle_count:parseInt((R('sp_particle_count')||{}).value)||20,
    sphere_autostart:     !!(R('sp_autostart')||{}).checked,
    language:             (R('sp_language')||{}).value||'uk-UA',
    tts_provider:         (R('sp_tts_prov')||{}).value||'openai',
    tts_voice:            (R('sp_tts_voice')||{}).value||'onyx',
    edge_voice:           (R('sp_edge_voice')||{}).value||'uk-UA-PolinaNeural',
    tts_speed:            parseFloat((R('sp_tts_speed')||{}).value)||1.2,
    tts_volume:           parseInt((R('sp_tts_volume')||{}).value)||80,
    jarvis_sounds:        !!(R('sp_jarvis')||{}).checked,
    jarvis_volume:        parseInt((R('sp_jarvis_vol')||{}).value)||70,
    hand_gestures:        !!(R('sp_hand_gestures')||{}).checked,
    gesture_camera:       parseInt((R('sp_gesture_camera')||{}).value)||0,
    gesture_cooldown:     parseInt((R('sp_gesture_cooldown')||{}).value)||2,
    gesture_open_palm:    (R('sp_gesture_open_palm')||{}).value||'stop_tts',
    gesture_fist:         (R('sp_gesture_fist')||{}).value||'hide',
    gesture_thumbs_up:    (R('sp_gesture_thumbs_up')||{}).value||'confirm',
    gesture_right:        (R('sp_gesture_right')||{}).value||'next_track',
    gesture_left:         (R('sp_gesture_left')||{}).value||'prev_track',
    stt_provider:         (R('sp_stt_provider')||{}).value || 'google',
    whisper_model:        (R('sp_whisper_model')||{}).value || 'small',
    ai_provider:          (R('sp_ai_prov')||{}).value||'openai',
    dialog_provider:      (R('sp_dialog_prov')||{}).value||'openai',
    weather_city:         (R('sp_weather_city')||{}).value||'Kyiv',
    // Telegram
    telegram_enabled:     !!(R('sp_telegram_enabled')||{}).checked,
    telegram_token:       (R('sp_telegram_token')||{}).value||'',
    telegram_allowed_ids: (R('sp_telegram_allowed_ids')||{}).value||'',
    telegram_commands:    tgCmdGetAll(),
  };
  pyCall('save_sphere', JSON.stringify(data));
  showToast('✓ Налаштування сфери збережено');
}

// ═══ TELEGRAM CUSTOM COMMANDS ═══
var _tgCmds = [];  // [{label, action}, ...]

var TG_DEFAULTS = [
  { label: '🎮 Ігри',         type: 'submenu_steam'    },
  { label: '🎬 Серіал',       type: 'submenu_watch'    },
  { label: '🔊 Гучність',     type: 'submenu_volume'   },
  { label: '🖥️ Система',     type: 'submenu_system'   },
  { label: '📋 Всі команди',  type: 'submenu_commands' },
  { label: '💻 Робота',       type: 'command', action: 'відкрий робочий процес' },
  { label: '🎵 Музика',       type: 'command', action: 'включи музику'          },
  { label: '📷 Скріншот',     type: 'command', action: 'зроби скріншот'         },
  { label: '🍅 Помодоро',     type: 'topic_pomodoro'                          },
  { label: '💤 Вимкнути ПК', type: 'topic_system2'                           },
];

var TG_TYPES = [
  { value: 'command',           label: '⚡ Команда'                  },
  // ── Тематичні меню (смарт-меню під тему) ─────────────────────────
  { value: 'topic_notes',       label: '📝 Тема: Нотатки'           },
  { value: 'topic_music',       label: '🎵 Тема: Музика / Spotify'  },
  { value: 'topic_tasks',       label: '✅ Тема: Задачі'            },
  { value: 'topic_habits',      label: '🏆 Тема: Звички'            },
  { value: 'topic_news',        label: '📰 Тема: Новини'            },
  { value: 'topic_reminders',   label: '⏰ Тема: Нагадування'       },
  { value: 'topic_weather',     label: '🌤 Тема: Погода'            },
  // ── Підменю (список з Sphere) ─────────────────────────────────────
  { value: 'topic_alarms',      label: '⏰ Тема: Будильники'         },
  { value: 'topic_focus',       label: '🎯 Тема: Фокус-режим'        },
  { value: 'topic_system2',     label: '🖥 Тема: Система+'            },
  { value: 'topic_pomodoro',    label: '🍅 Тема: Помодоро'            },
  // ── Підменю (динамічний список з Python) ──────────────────────────
  { value: 'submenu_steam',     label: '🎮 Підменю: Steam ігри'      },
  { value: 'submenu_watch',     label: '🎬 Підменю: Серіали/Відео'   },
  { value: 'submenu_volume',    label: '🔊 Підменю: Гучність'        },
  { value: 'submenu_system',    label: '🖥️ Підменю: Система'        },
  { value: 'submenu_commands',  label: '📋 Підменю: Всі мої команди' },
  { value: 'submenu_custom',    label: '✏️ Підменю: Своє'            },
];

function tgCmdGetAll() {
  return JSON.parse(JSON.stringify(_tgCmds));
}

function _tgTypeOpts(selected) {
  return TG_TYPES.map(function(t) {
    return '<option value="'+t.value+'"'+(t.value===selected?' selected':'')+'>'+t.label+'</option>';
  }).join('');
}

function tgCmdRender() {
  var list = R('tg_cmd_list');
  if (!list) return;
  list.innerHTML = '';
  _tgCmds.forEach(function(cmd, i) {
    var ctype  = cmd.type || 'command';
    var isCmd  = ctype === 'command';
    var isCust = ctype === 'submenu_custom';
    var row = document.createElement('div');
    row.className = 'tg-cmd-row';
    row.style.cssText = 'flex-direction:column;align-items:stretch;gap:6px;';
    row.innerHTML =
      // Рядок 1: назва + тип + видалити
      '<div style="display:flex;gap:6px;align-items:center;">' +
        '<span class="tg-cmd-lbl" style="white-space:nowrap;">Кнопка:</span>' +
        '<input type="text" placeholder="🎮 Ігри" value="'+_esc(cmd.label||'')+'" '+
          'oninput="_tgCmds['+i+'].label=this.value" style="flex:1;">' +
        '<select style="max-width:195px;font-size:11px;padding:4px 6px;border-radius:6px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.06);color:var(--text);" '+
          'onchange="_tgCmds['+i+'].type=this.value;tgCmdRender()">'+
          _tgTypeOpts(ctype) +
        '</select>' +
        '<button class="btn-icon" onclick="tgCmdRemove('+i+')" title="Видалити">✕</button>' +
      '</div>' +
      // Рядок 2: поле action (тільки для типу command)
      (isCmd ?
        '<div style="display:flex;gap:6px;align-items:center;padding-left:4px;">' +
          '<span class="tg-cmd-lbl" style="white-space:nowrap;">Дія:</span>' +
          '<input type="text" placeholder="що пограти / виключи пк / ..." '+
            'value="'+_esc(cmd.action||'')+'" '+
            'oninput="_tgCmds['+i+'].action=this.value" style="flex:1;">' +
        '</div>'
      : '') +
      // Рядок 3: textarea для custom підменю
      (isCust ?
        '<div style="padding-left:4px;">' +
          '<div style="font-size:10px;opacity:.5;margin-bottom:3px;">Свої пункти (кожен рядок: Назва | дія):</div>' +
          '<textarea rows="4" placeholder="🎮 GTA V | відкрий гта\n🎮 CS2 | відкрий кс" '+
            'style="width:100%;font-size:11px;font-family:monospace;padding:6px;border-radius:6px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.06);color:var(--text);resize:vertical;" '+
            'oninput="_tgCmds['+i+'].children=tgParseCustom(this.value)">'+
            tgSerializeCustom(cmd.children||[]) +
          '</textarea>' +
        '</div>'
      : '');
    list.appendChild(row);
  });
}

function tgParseCustom(text) {
  return text.split('\n').filter(function(l){ return l.trim(); }).map(function(l) {
    var parts = l.split('|');
    return { label: (parts[0]||'').trim(), action: (parts[1]||parts[0]||'').trim() };
  }).filter(function(c){ return c.label; });
}

function tgSerializeCustom(arr) {
  return (arr||[]).map(function(c){ return c.label + ' | ' + (c.action||c.label); }).join('\n');
}

function _esc(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
}

function tgCmdAdd() {
  _tgCmds.push({ label: '', action: '' });
  tgCmdRender();
  // Фокус на новому полі
  var rows = document.querySelectorAll('#tg_cmd_list .tg-cmd-row');
  if (rows.length) rows[rows.length-1].querySelector('input').focus();
}

function tgCmdRemove(i) {
  _tgCmds.splice(i, 1);
  tgCmdRender();
}

function tgCmdClear() {
  if (!confirm('Видалити всі кнопки?')) return;
  _tgCmds = [];
  tgCmdRender();
}

function tgCmdAddDefaults() {
  _tgCmds = JSON.parse(JSON.stringify(TG_DEFAULTS));
  tgCmdRender();
  showToast('📋 Стандартні кнопки додано');
}

function tgCmdLoad(arr) {
  _tgCmds = Array.isArray(arr) ? JSON.parse(JSON.stringify(arr)) : [];
  tgCmdRender();
}

function testTelegramBot() {
  var token = (R('sp_telegram_token')||{}).value||'';
  var res = R('tg_test_result');
  if (!token) { if(res) res.textContent = '⚠ Введіть токен'; return; }
  if(res) res.textContent = '🔄 Перевіряю...';
  fetch('https://api.telegram.org/bot' + token + '/getMe')
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(res) {
        if(d.ok) {
          var username = (d.result && d.result.username) ? d.result.username : 'bot';
          res.textContent = '✅ @' + username + ' — бот знайдено!';
        }
        else     res.textContent = '❌ Невірний токен: ' + (d.description||'');
      }
    })
    .catch(function(e){ if(res) res.textContent = '❌ Помилка мережі: ' + e.message; });
}

function setSttLang(lang) {
  sttLang = lang;
  localStorage.setItem('axis_stt_lang', lang);
  showToast('🎤 Мова STT: ' + lang);
}

function initVoice() {
  var sel = R('sttLangSel');
  if (sel) sel.value = sttLang;
  loadMicSettingsUI();
}

function toggleRecording() {
  if (isRecording) stopRecording();
  else startRecording();
}

function startRecording() {
  isRecording = true;
  var btn = R('micBtn');
  if (btn) { btn.classList.add('recording'); btn.title = 'Запис... (натисніть для зупинки)'; }
  pyCall('start_stt', JSON.stringify({mode: 'single', lang: sttLang, device_index: _micSettings.deviceIndex, sensitivity: _micSettings.sensitivity}));
}

function stopRecording() {
  isRecording = false;
  var btn = R('micBtn');
  if (btn) { btn.classList.remove('recording'); btn.title = 'Голосовий ввід'; }
  pyCall('stop_stt', '{}');
}

// Called by Python with recognized text
function handleSttResult(d) {
  var text = (d.text || '').trim();

  // Redirect to trigger-listen capture if active
  if (typeof _listenTriggerActive !== 'undefined' && _listenTriggerActive) {
    _handleTriggerListenResult(text);
    return;
  }

  if (!text) return;

  // Stop phrase
  var stopPh = (_cmdExecCfg.stopPhrase || '').toLowerCase().trim();
  if (stopPh && text.toLowerCase().includes(stopPh)) {
    showToast('⛔ Команду зупинено'); return;
  }

  if (d.mode === 'live') {
    if (!liveMode) return;
    if (liveSpeaking || pendingLiveId) return;
    if (STOP_WORDS.test(text)) { stopLiveMode(); return; }
    // Command chaining
    var parts = splitByChainWords(text);
    if (parts.length > 1) {
      parts.forEach(function(part, i) {
        setTimeout(function() {
          var m = matchCommand(part);
          if (m) { showCmdOverlay(m.name||m.trigger); pyCall('run_command', JSON.stringify({type:m.type,body:m.body,name:m.name||m.trigger})); _updateCmdStats(m.id,true); }
          else   { R('liveUserText').textContent='«'+part+'»'; liveSendMessage(part); }
        }, i * 700);
      });
      return;
    }
    R('liveUserText').textContent = '«' + text + '»';
    liveSendMessage(text);
  } else {
    // Single-shot
    isRecording = false;
    var btn = R('micBtn');
    if (btn) btn.classList.remove('recording');
    // Command chaining
    var parts = splitByChainWords(text);
    if (parts.length > 1 && parts.some(function(p){ return matchCommand(p); })) {
      parts.forEach(function(part, i) {
        setTimeout(function() {
          var m = matchCommand(part);
          if (m) { showCmdOverlay(m.name||m.trigger); pyCall('run_command', JSON.stringify({type:m.type,body:m.body,name:m.name||m.trigger})); _updateCmdStats(m.id,true); }
        }, i * 700);
      });
      return;
    }
    var inp = R('chatInput');
    if (inp) inp.value = text;
    sendChat();
  }
}

// ═══ TTS ENGINE ═══
var ttsEnabled      = false;
var currentTtsProv  = 'browser';  // 'browser' | 'openai' | 'google'
var currentTtsVoice = '';
var currentAudio    = null;

// OpenAI voices with Ukrainian labels
var OPENAI_VOICES = [
  {id:'onyx',    label:'Onyx — глибокий чоловічий'},
  {id:'echo',    label:'Echo — чоловічий'},
  {id:'ash',     label:'Ash — виразний чоловічий'},
  {id:'fable',   label:'Fable — молодий'},
  {id:'alloy',   label:'Alloy — нейтральний'},
  {id:'nova',    label:'Nova — жіночий'},
  {id:'shimmer', label:'Shimmer — ніжний жіночий'},
  {id:'coral',   label:'Coral — живий жіночий'},
  {id:'sage',    label:'Sage — спокійний нейтральний'},
];

// Google TTS voices (Cloud TTS, uses Google API key)
var GOOGLE_VOICES = [
  {id:'uk-UA-Wavenet-A', label:'uk-UA Wavenet A — жіночий (природній)'},
  {id:'uk-UA-Wavenet-B', label:'uk-UA Wavenet B — чоловічий (природній)'},
  {id:'uk-UA-Standard-A',label:'uk-UA Standard A — жіночий'},
  {id:'uk-UA-Standard-B',label:'uk-UA Standard B — чоловічий'},
  {id:'ru-RU-Wavenet-A', label:'ru-RU Wavenet A — жіночий'},
  {id:'ru-RU-Wavenet-D', label:'ru-RU Wavenet D — чоловічий'},
  {id:'en-US-Wavenet-D', label:'en-US Wavenet D — чоловічий'},
  {id:'en-US-Wavenet-F', label:'en-US Wavenet F — жіночий'},
];

function toggleTts() {
  ttsEnabled = !ttsEnabled;
  var btn = R('ttsBtn');
  if (btn) {
    btn.textContent = ttsEnabled ? '🔊' : '🔈';
    btn.title = ttsEnabled ? 'Голос увімкнено' : 'Голос AI вимкнено';
    btn.classList.toggle('v-active', ttsEnabled);
  }
  if (!ttsEnabled) {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  }
  showToast(ttsEnabled ? '🔊 Голос AI увімкнено (' + currentTtsProv + ')' : '🔈 Голос AI вимкнено');
}

// Main entry — routes to API or browser
function speakText(text) {
  if (!ttsEnabled) return;
  var clean = text.replace(/<[^>]+>/g,'').replace(/[*_`#>/]/g,'').trim().substring(0, 700);
  if (!clean) return;
  // Stop mic before speaking to prevent echo/feedback
  if (isRecording) stopRecording();
  if (currentTtsProv === 'openai' || currentTtsProv === 'google') {
    pyCall('tts_speak', JSON.stringify({
      text:     clean,
      provider: currentTtsProv,
      voice:    currentTtsVoice || (currentTtsProv === 'openai' ? 'onyx' : 'uk-UA-Wavenet-A'),
    }));
  } else {
    browserSpeak(clean);
  }
}

function browserSpeak(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  var utt = new SpeechSynthesisUtterance(text);
  utt.rate = 1.0; utt.pitch = 1.0; utt.volume = 1.0;
  if (currentTtsVoice) {
    var v = window.speechSynthesis.getVoices().find(function(x){ return x.name === currentTtsVoice; });
    if (v) utt.voice = v;
  } else {
    var voices = window.speechSynthesis.getVoices();
    utt.voice = voices.find(function(v){ return v.lang.startsWith('uk'); })
             || voices.find(function(v){ return v.lang.startsWith('ru'); })
             || voices.find(function(v){ return v.lang.startsWith('en'); })
             || voices[0];
  }
  utt.onend = utt.onerror = function(){ liveOnSpeakEnd(); };
  window.speechSynthesis.speak(utt);
}

// Handles MP3 base64 from Python (OpenAI / Google TTS)
function handleTtsAudio(d) {
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
  var audio = new Audio('data:audio/mp3;base64,' + d.audio_b64);
  currentAudio = audio;
  audio.onended = audio.onerror = function(){
    audio.src = '';  // release decoded PCM buffer
    currentAudio = null;
    liveOnSpeakEnd();
  };
  audio.play().catch(function(){ liveOnSpeakEnd(); });
}

function liveOnSpeakEnd() {
  if (!liveMode) return;
  liveSpeaking = false;
  R('liveUserText').textContent = '';
  liveRestartTimer = setTimeout(liveStartListening, 400);
}

// Settings: voice provider changed
function onTtsProviderChange(prov) {
  currentTtsProv = prov;
  currentTtsVoice = '';
  var sel  = R('ttsVoiceSel');
  if (!sel) {
    currentTtsProv  = prov;
    currentTtsVoice = '';
    return;
  }
  var note = R('ttsApiNote');
  var lbl  = R('ttsVoiceLabel');
  if (prov === 'openai') {
    sel.innerHTML = OPENAI_VOICES.map(function(v){
      return '<option value="'+v.id+'">'+v.label+'</option>';
    }).join('');
    currentTtsVoice = 'onyx';
    if (note) note.style.display = 'flex';
    if (lbl) lbl.textContent = 'Голос OpenAI';
  } else if (prov === 'xai') {
    sel.innerHTML = '<option value="grok-voice-think-fast-1">grok-voice-think-fast-1 — реалістичний</option>';
    currentTtsVoice = 'aurora';
    if (note) note.style.display = 'flex';
    if (lbl)  lbl.textContent = 'Голос xAI';
  } else if (prov === 'google') {
    sel.innerHTML = GOOGLE_VOICES.map(function(v){
      return '<option value="'+v.id+'">'+v.label+'</option>';
    }).join('');
    currentTtsVoice = 'uk-UA-Wavenet-A';
    if (note) note.style.display = 'flex';
    if (lbl) lbl.textContent = 'Голос Google TTS';
  } else {
    populateBrowserVoices();
    if (note) note.style.display = 'none';
    if (lbl) lbl.textContent = 'Системний голос';
  }
}

function populateBrowserVoices() {
  var sel = R('ttsVoiceSel'); if (!sel) return;
  var voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
  if (!voices.length) {
    sel.innerHTML = '<option value="">Голоси завантажуються...</option>';
    if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = populateBrowserVoices;
    return;
  }
  sel.innerHTML = '<option value="">(авто — найкращий доступний)</option>'
    + voices.map(function(v){
        return '<option value="'+v.name+'">'+v.name+' ('+v.lang+')</option>';
      }).join('');
}

function testTtsVoice() {
  var prev = ttsEnabled;
  ttsEnabled = true;
  var st = R('ttsStatus'); if(st) st.textContent = '▶ Відтворення...';
  speakText('Привіт! Це тест голосу AXIS. Hello, AXIS voice test.');
  setTimeout(function(){ ttsEnabled = prev; if(st) st.textContent = ''; }, 4000);
}

// ═══ LICENSE ══════════════════════════════════════════════════════════════════
// URL can be overridden in config via license_api_url key
var LICENSE_API_DEFAULT = 'https://helgaslop-axis-os.netlify.app/.netlify/functions/license-check';
var LICENSE_API = (typeof _savedCfg !== 'undefined' && _savedCfg && _savedCfg.license_api_url)
  ? _savedCfg.license_api_url
  : LICENSE_API_DEFAULT;

// Generate same device fingerprint as the website order form
function _licDeviceId() {
  var raw = [
    navigator.userAgent || '',
    screen.width + 'x' + screen.height + '@' + (screen.colorDepth || 0),
    (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : ''),
    navigator.language || '',
    navigator.platform || '',
    String(navigator.hardwareConcurrency || 0),
    String(navigator.deviceMemory || 0)
  ].join('|');
  var h = 5381;
  for (var i = 0; i < raw.length; i++) { h = (Math.imul(h, 33) ^ raw.charCodeAt(i)) >>> 0; }
  return h.toString(16).toUpperCase().padStart(8, '0');
}

// Load saved license key and check status with server
function checkLicenseStatus() {
  var ico  = R('lic-status-ico');
  var txt  = R('lic-status-text');
  var sub  = R('lic-status-sub');
  var inp  = R('licKeyInput');
  var msg  = R('lic-msg');
  if (!ico) return;

  // Refresh LICENSE_API in case config loaded after this variable was initialized
  if (typeof _savedCfg === 'object' && _savedCfg && _savedCfg.license_api_url) {
    LICENSE_API = _savedCfg.license_api_url;
  }
  var saved = (typeof _savedCfg === 'object' && _savedCfg !== null) ? (_savedCfg.license_key || '') : '';
  if (!saved) {
    ico.textContent = '⚠️'; txt.textContent = 'Ліцензія не активована';
    sub.textContent = 'Введіть ключ нижче щоб активувати';
    return;
  }

  if (inp) inp.value = saved;
  ico.textContent = '⏳'; txt.textContent = 'Перевірка ключа...'; sub.textContent = '';

  fetch(LICENSE_API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: saved, deviceId: _licDeviceId() })
  })
  .then(function(r){ return r.json(); })
  .then(function(d) {
    if (d.valid) {
      var planNames = { monthly:'Місячний', yearly:'Річний', lifetime:'Lifetime (Назавжди)' };
      ico.textContent  = '✅';
      txt.textContent  = 'Ліцензія активна';
      txt.style.color  = '#3fb950';
      var planDisplay0 = planNames[d.plan] || d.plan || '—';
      sub.textContent  = '📦 План: ' + planDisplay0 + (d.name ? '  |  👤 ' + d.name : '');
      if (msg) msg.textContent = '';
    } else {
      ico.textContent  = '❌';
      txt.textContent  = 'Ліцензія недійсна';
      txt.style.color  = '#f85149';
      sub.textContent  = d.error || '';
    }
  })
  .catch(function() {
    ico.textContent = '🌐'; txt.textContent = 'Немає з\'єднання'; txt.style.color = '';
    sub.textContent = 'Перевірку буде виконано при наступному підключенні';
  });
}

// Activate a new license key entered by the user
function activateLicense() {
  var inp = R('licKeyInput');
  var msg = R('lic-msg');
  var ico = R('lic-status-ico');
  var txt = R('lic-status-text');
  var sub = R('lic-status-sub');
  if (!inp) return;

  var key = inp.value.trim().toUpperCase();
  if (!/^AXIS-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(key)) {
    if (msg) { msg.textContent = '⚠️ Невірний формат. Очікується: AXIS-XXXX-XXXX-XXXX-XXXX'; msg.style.color = '#f0a83e'; }
    return;
  }

  if (msg) { msg.textContent = '⏳ Перевірка...'; msg.style.color = ''; }
  if (ico) ico.textContent = '⏳';

  fetch(LICENSE_API, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: key, deviceId: _licDeviceId() })
  })
  .then(function(r){ return r.json(); })
  .then(function(d) {
    if (d.valid) {
      // Save to config
      pyCall('save_config', JSON.stringify({ license_key: key, license_plan: d.plan }));
      var planNames = { monthly:'Місячний', yearly:'Річний', lifetime:'Lifetime (Назавжди)' };
      if (ico) { ico.textContent = '✅'; }
      if (txt) { txt.textContent = 'Ліцензія активована!'; txt.style.color = '#3fb950'; }
      var planDisplay1 = planNames[d.plan] || d.plan || '—';
      if (sub) sub.textContent = '📦 ' + planDisplay1;
      if (msg) { msg.textContent = '✅ Ключ прийнято і збережено'; msg.style.color = '#3fb950'; }
      var planDisplay2 = planNames[d.plan] || d.plan || '—';
      showToast('🔑 Ліцензію активовано: ' + planDisplay2);
    } else {
      if (ico) ico.textContent = '❌';
      if (txt) { txt.textContent = 'Ключ не прийнято'; txt.style.color = '#f85149'; }
      if (sub) sub.textContent = d.error || '';
      if (msg) { msg.textContent = '❌ ' + (d.error || 'Ключ недійсний'); msg.style.color = '#f85149'; }
    }
  })
  .catch(function() {
    if (msg) { msg.textContent = '🌐 Немає з\'єднання з сервером'; msg.style.color = '#f0a83e'; }
  });
}
