/* AXIS OS ? IDE & AI editor */
function _ideEscAttr(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
// ═══ IDE ═══
var ideEditor = null;
var ideCurrentPath = null;
var ideFiles = [
  {name:'main.py',lang:'python',ico:'🐍',code:'# AXIS OS — main\nimport sys\n\ndef main():\n    print("Hello from AXIS OS!")\n    return 0\n\nif __name__ == "__main__":\n    sys.exit(main())\n'},
  {name:'index.html',lang:'htmlmixed',ico:'🌐',code:'<!DOCTYPE html>\n<html lang="uk">\n<head>\n  <meta charset="UTF-8">\n  <title>AXIS OS</title>\n</head>\n<body>\n  <h1 style="color:#22c55e">Hello AXIS OS</h1>\n</body>\n</html>\n'},
  {name:'config.json',lang:'javascript',ico:'⚙',code:'{\n  "name": "AXIS OS",\n  "version": "1.0.0",\n  "ai": {\n    "default_model": "gpt-4o"\n  }\n}\n'},
];
var activeFileIdx = 0;

function initIde(){
  var tree = R('fileTree');
  if(tree) tree.innerHTML = ideFiles.map(function(f,i){
    return '<div class="ide-file'+(i===0?' active':'')+'" onclick="openIdeFile('+i+')"><span style="font-size:12px;margin-right:4px;">'+f.ico+'</span>'+f.name+'</div>';
  }).join('');
  var tabs = R('ideTabs');
  if(tabs) tabs.innerHTML = ideFiles.map(function(f,i){
    return '<div class="ide-tab'+(i===0?' active':'')+'" onclick="openIdeFile('+i+')">'+f.ico+' '+f.name+'</div>';
  }).join('');
  var wrap = R('ideEditorWrap');
  if(!wrap||ideEditor) return;
  ideEditor = CodeMirror(wrap,{
    value: ideFiles[0].code, mode:'python', theme:'material-darker',
    lineNumbers:true, matchBrackets:true, autoCloseBrackets:true,
    styleActiveLine:true, indentUnit:4, tabSize:4,
  });
  ideEditor.on('cursorActivity', function(){
    var c=ideEditor.getCursor();
    R('idePos').textContent='Ln '+(c.line+1)+', Col '+(c.ch+1);
  });
}

function openIdeFile(i){
  activeFileIdx=i;
  var f=ideFiles[i];
  document.querySelectorAll('.ide-file').forEach(function(el,j){ el.classList.toggle('active',j===i); });
  document.querySelectorAll('.ide-tab').forEach(function(el,j){ el.classList.toggle('active',j===i); });
  if(ideEditor){ ideEditor.setValue(f.code); ideEditor.setOption('mode',f.lang); }
  var langName = f.lang==='python'?'Python':f.lang==='htmlmixed'?'HTML':'JSON';
  R('ideLang').textContent=langName;
  R('ideLangFull').textContent=langName+' · UTF-8';
}

function runCode(){
  if(!ideEditor) return;
  var code=ideEditor.getValue();
  var f=ideFiles[activeFileIdx];
  if(f.lang==='python'){
    var out=R('ideTermOut');
    if(out) out.textContent='axis@os:~$ python '+f.name+'\n⏳ Виконується...\n';
    pyCall('run_code', JSON.stringify({code:code, lang:'python', file:f.name}));
  } else if(f.lang==='htmlmixed'){
    // Show HTML preview
    switchIdeRight(document.querySelector('.ide-right-tab'), 'preview');
    var frame=document.createElement('iframe');
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    frame.style.cssText='flex:1;border:none;width:100%;height:100%;';
    var pane=R('ide-pane-preview'); pane.innerHTML='';
    pane.appendChild(frame);
    frame.srcdoc=code;
    showToast('HTML завантажено у перегляд');
  }
}

function handleCodeOutput(d){
  var out=R('ideTermOut');
  if(out) out.textContent='axis@os:~$ python '+ideFiles[activeFileIdx].name+'\n'+(d.output||'')+'\naxis@os:~$ _';
  var op=R('ide-pane-output');
  if(op) op.textContent=d.output||'';
}
function handleFileContent(d){
  if(!ideEditor || d.content===undefined) return;
  ideEditor.setValue(d.content);
  if(d.path){
    ideCurrentPath = d.path;
    var fname = d.path.split(/[\\/]/).pop();
    var ext   = fname.split('.').pop().toLowerCase();
    var modeMap = {py:'python',js:'javascript',html:'htmlmixed',htm:'htmlmixed',css:'css',json:'javascript',md:'python',ts:'javascript',jsx:'javascript',tsx:'javascript'};
    var mode = modeMap[ext] || 'python';
    ideEditor.setOption('mode', mode);
    var langMap = {python:'Python',javascript:'JS/JSON',htmlmixed:'HTML',css:'CSS'};
    var langName = langMap[mode] || 'Text';
    R('ideLang')     && (R('ideLang').textContent     = langName);
    R('ideLangFull') && (R('ideLangFull').textContent = langName + ' · ' + fname);
    // Track in recent files sidebar
    if(typeof ideAddRecentFile === 'function') ideAddRecentFile(d.path, fname);
    showPage('agents');
  }
}
function ideSave(){
  if(!ideEditor) return;
  if(ideCurrentPath) pyCall('save_file', JSON.stringify({path:ideCurrentPath, content:ideEditor.getValue()}));
  else               ideSaveAs();
}
function ideSaveAs(){
  if(!ideEditor) return;
  pyCall('save_file_as', JSON.stringify({content:ideEditor.getValue()}));
}
function clearTerm(){ var o=R('ideTermOut'); if(o) o.textContent='axis@os:~$ _'; }

function switchIdeRight(el, id){
  document.querySelectorAll('.ide-right-tab').forEach(function(t){ t.classList.remove('active'); });
  if(el) el.classList.add('active');
  ['preview','output','ai'].forEach(function(p){
    var pe=R('ide-pane-'+p); if(pe) pe.style.display=(p===id)?'flex':'none';
  });
}

function sendIdeAi(){
  var inp=R('ideAiInput'); var msg=inp.value.trim(); if(!msg) return;
  var chat=R('ideAiChat');
  var msgDiv=document.createElement('div');
  msgDiv.style.cssText='background:rgba(34,197,94,.07);border-radius:8px;padding:8px;margin-bottom:6px;font-size:12px;';
  msgDiv.textContent=msg;  // safe: textContent never executes HTML
  chat.appendChild(msgDiv);
  chat.scrollTop=chat.scrollHeight;
  inp.value='';
  var code=ideEditor?ideEditor.getValue():'';
  var reqId='ide_'+Date.now();
  chat.innerHTML+='<div id="'+reqId+'" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:8px;margin-bottom:6px;font-size:12px;color:var(--text2);">⏳ Аналізую...</div>';
  chat.scrollTop=chat.scrollHeight;
  pyCall('ai_send', JSON.stringify({
    id: reqId,
    provider: currentProvider, model: currentModel,
    messages:[{role:'user',content:'Контекст коду:\n```\n'+code.slice(0,2000)+'\n```\n\nПитання: '+msg}],
    system:'Ти AI помічник для написання коду. Відповідай по-українськи, конкретно.'
  }));
}
function ideAiKey(e){ if(e.key==='Enter') sendIdeAi(); }

// ═══ IDE INLINE AI EDIT SYSTEM (Claude Code–style) ═══
var _pendingEdits    = null;   // [{old, new}] waiting to be applied
var _ideEditReqId    = null;   // request ID for current edit
var _ideNewFileReqId = null;   // request ID for new file creation

var _IDE_EDIT_SYSTEM = 'You are a precise code editor. The user provides a FULL file and a change request.\n'
  + 'Return ONLY valid JSON — no markdown, no explanation outside the JSON:\n'
  + '{"description":"brief summary of changes","edits":[{"old":"EXACT text from file","new":"replacement text"}]}\n'
  + 'Rules:\n'
  + '- "old" must be an EXACT substring found verbatim in the file (copy it precisely)\n'
  + '- Keep edits minimal and targeted — do not rewrite the whole file unless asked\n'
  + '- Multiple independent changes = multiple entries in the edits array\n'
  + '- If nothing needs to change: {"description":"No changes needed","edits":[]}\n'
  + '- For a brand new file: [{"old":"__NEW_FILE__","new":"full file content"}]\n'
  + 'Do NOT wrap output in ```json or any code fence.';

var _IDE_NEWFILE_SYSTEM = 'You are a code generator. The user describes a file to create.\n'
  + 'Return ONLY valid JSON (no markdown, no code fence):\n'
  + '{"filename":"name.ext","description":"what it does","content":"full file content"}\n'
  + 'Use the appropriate language for the filename extension.';

/* ── Show/hide Ctrl+K AI bar ─────────────────────────────── */
function toggleIdeAiBar(){
  var bar = R('ideAiBar');
  if(!bar) return;
  var visible = bar.style.display !== 'none';
  bar.style.display = visible ? 'none' : 'flex';
  if(!visible){ var inp = R('ideAiBarInput'); if(inp){ inp.value=''; inp.focus(); } }
}
function ideAiBarKey(e){ if(e.key==='Enter') ideAiEditRequest(); if(e.key==='Escape') toggleIdeAiBar(); }

/* ── Step / status helpers ───────────────────────────────── */
function ideShowStep(txt){
  var el=R('ideAiSteps'), tx=R('ideAiStepText');
  if(!el||!tx) return;
  if(txt){ el.style.display='block'; tx.textContent=txt; }
  else   { el.style.display='none';  tx.textContent=''; }
}
function ideSetStatusBar(txt, color){
  var e1=R('ideAiStatusBar'); if(e1){ e1.textContent=txt; e1.style.color=color||'var(--indigo)'; }
  var e2=R('ideAiStatus');    if(e2){ e2.textContent=txt; e2.style.color=color||'var(--indigo)'; }
}

/* ── Main edit request ───────────────────────────────────── */
function ideAiEditRequest(){
  var inp     = R('ideAiBarInput');
  var userReq = inp ? inp.value.trim() : '';
  if(!userReq){ if(inp) inp.focus(); return; }
  if(!ideEditor){ showToast('Спочатку відкрийте файл'); return; }

  var fullCode = ideEditor.getValue();
  var fname    = (ideFiles[activeFileIdx]&&ideFiles[activeFileIdx].name) || (ideCurrentPath?ideCurrentPath.split(/[\\/]/).pop():'file');
  var ext      = fname.split('.').pop().toLowerCase();

  _ideEditReqId = 'idedit_' + Date.now();

  var btn = R('ideAiBarBtn');
  if(btn){ btn.textContent='⏳ Аналізую...'; btn.disabled=true; }
  ideRejectEdits();
  ideShowStep('🔍 Читаю: ' + fname);
  ideSetStatusBar('⏳ AI аналізує...', 'var(--indigo)');

  var _steps = ['🔍 Читаю: '+fname, '🧠 Аналізую структуру...', '✏️ Генерую правки...'];
  var _si = 0;
  var _st = setInterval(function(){ _si=(_si+1)%_steps.length; ideShowStep(_steps[_si]); }, 1400);
  window['_ideStepT'] = _st;

  pyCall('ai_send', JSON.stringify({
    id: _ideEditReqId,
    provider: currentProvider, model: currentModel,
    messages:[{role:'user', content:'File: '+fname+'\n\n```'+ext+'\n'+fullCode+'\n```\n\nChange request: '+userReq}],
    system: _IDE_EDIT_SYSTEM
  }));
}

/* ── Parse AI edit response → render diff ────────────────── */
function _ideHandleEditResponse(text){
  clearInterval(window['_ideStepT']);
  ideShowStep('');
  var btn=R('ideAiBarBtn'); if(btn){ btn.textContent='✦ Аналіз і правка'; btn.disabled=false; }

  var raw = text.trim().replace(/^```json\s*/i,'').replace(/\s*```$/,'').trim();
  var parsed = null;
  try { parsed = JSON.parse(raw); } catch(e){
    var m = raw.match(/\{[\s\S]*\}/);
    if(m){ try { parsed = JSON.parse(m[0]); } catch(e2){} }
  }

  if(!parsed || !parsed.edits){
    ideSetStatusBar('⚠ Формат відповіді AI неправильний', 'var(--red)');
    showToast('⚠ AI відповів некоректно', 2500);
    var chat=R('ideAiChat');
    if(chat) chat.innerHTML+='<div style="background:var(--bg2);border:1px solid rgba(239,68,68,.3);border-radius:8px;padding:8px;margin-bottom:6px;font-size:11px;color:var(--text2);white-space:pre-wrap;">⚠ Не вдалося розпізнати правки. Відповідь AI:\n\n'+_escHtml(text)+'</div>';
    return;
  }

  _pendingEdits = parsed.edits;
  var desc = parsed.description || '';

  if(!_pendingEdits.length){
    ideSetStatusBar('✓ Змін не потрібно', 'var(--accent)');
    showToast('✓ ' + (desc || 'Код вже правильний'));
    return;
  }
  ideSetStatusBar('✦ ' + _pendingEdits.length + ' правок готово — натисніть Застосувати', 'var(--indigo)');
  _ideRenderDiff(_pendingEdits, desc);
}

/* ── Render diff panel ───────────────────────────────────── */
function _ideRenderDiff(edits, description){
  var panel=R('ideAiDiffPanel'), body=R('ideAiDiffBody'), summ=R('ideAiDiffSummary');
  if(!panel||!body) return;
  if(summ) summ.textContent = (description?description+' · ':'')+edits.length+' зміна(и)';

  var html='';
  edits.forEach(function(edit, i){
    if(edit.old==='__NEW_FILE__'){
      html+='<div style="margin-bottom:10px;">'
        +'<div style="font-size:9px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">+ Новий файл</div>'
        +'<div style="background:rgba(34,197,94,.07);border-left:3px solid var(--accent);padding:6px 10px;white-space:pre-wrap;color:#86efac;border-radius:0 4px 4px 0;max-height:120px;overflow-y:auto;">'
        +_escHtml(edit.new.slice(0,800))+(edit.new.length>800?'\n…':'')
        +'</div></div>';
      return;
    }
    html+='<div style="margin-bottom:10px;">'
      +'<div style="font-size:9px;color:var(--red);text-transform:uppercase;letter-spacing:1px;margin-bottom:2px;">− Було ('+( i+1)+')</div>'
      +'<div style="background:rgba(239,68,68,.07);border-left:3px solid var(--red);padding:5px 10px;white-space:pre-wrap;color:#fca5a5;border-radius:0 4px 4px 0;max-height:80px;overflow-y:auto;">'
      +_escHtml(edit.old)+'</div>'
      +'<div style="font-size:9px;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin:3px 0 2px;">+ Стане</div>'
      +'<div style="background:rgba(34,197,94,.07);border-left:3px solid var(--accent);padding:5px 10px;white-space:pre-wrap;color:#86efac;border-radius:0 4px 4px 0;max-height:80px;overflow-y:auto;">'
      +_escHtml(edit.new)+'</div></div>';
  });
  body.innerHTML=html;
  panel.style.display='block';
}

function _escHtml(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

/* ── Apply edits to CodeMirror ───────────────────────────── */
function ideApplyEdits(){
  if(!_pendingEdits||!ideEditor) return;
  var content=ideEditor.getValue(), failed=0, applied=0;
  _pendingEdits.forEach(function(edit){
    if(edit.old==='__NEW_FILE__'){ content=edit.new; applied++; return; }
    if(content.indexOf(edit.old)===-1){ failed++; console.warn('[IDE] Edit not found:',edit.old.slice(0,60)); }
    else { content=content.replace(edit.old, edit.new); applied++; }
  });
  ideEditor.setValue(content);
  if(ideFiles[activeFileIdx]) ideFiles[activeFileIdx].code=content;
  ideRejectEdits();
  _pendingEdits=null;
  var msg='✓ Застосовано '+applied+' правок'+(failed?' ('+failed+' не знайдено)':'');
  ideSetStatusBar(msg, failed?'var(--orange)':'var(--accent)');
  showToast(msg, 2200);
  if(ideCurrentPath) ideSave();
}

/* ── Reject / hide diff panel ────────────────────────────── */
function ideRejectEdits(){
  var p=R('ideAiDiffPanel'); if(p) p.style.display='none';
  var b=R('ideAiDiffBody');  if(b) b.innerHTML='';
  _pendingEdits=null;
}

/* ── AI: create new file from scratch ────────────────────── */
function ideAiNewFile(){
  var desc = prompt('Опишіть файл для створення:\n(напр. "Python клас User з login/logout" або "HTML сторінка з формою входу")');
  if(!desc||!desc.trim()) return;
  _ideNewFileReqId = 'idenew_'+Date.now();
  ideSetStatusBar('✨ Генерую файл...','var(--indigo)');
  ideShowStep('✨ AI створює файл...');
  pyCall('ai_send', JSON.stringify({
    id: _ideNewFileReqId,
    provider: currentProvider, model: currentModel,
    messages:[{role:'user', content: desc.trim()}],
    system: _IDE_NEWFILE_SYSTEM
  }));
}

function _ideHandleNewFileResponse(text){
  ideShowStep('');
  var raw=text.trim().replace(/^```json\s*/i,'').replace(/\s*```$/,'').trim();
  var parsed=null;
  try { parsed=JSON.parse(raw); } catch(e){ var m=raw.match(/\{[\s\S]*\}/); if(m){ try{parsed=JSON.parse(m[0]);}catch(e2){} } }
  if(!parsed||!parsed.content){ showToast('⚠ AI не зміг створити файл',2200); ideSetStatusBar('⚠ Помилка','var(--red)'); return; }

  var fname=parsed.filename||('new_file_'+Date.now()+'.py');
  var ext=fname.split('.').pop().toLowerCase();
  var modeMap={py:'python',js:'javascript',ts:'javascript',jsx:'javascript',tsx:'javascript',html:'htmlmixed',htm:'htmlmixed',css:'css',json:'javascript',md:'python'};
  var icoMap ={py:'🐍',js:'📜',ts:'💙',jsx:'⚛',tsx:'⚛',html:'🌐',htm:'🌐',css:'🎨',json:'⚙',md:'📄'};
  var newFile={name:fname, lang:modeMap[ext]||'python', ico:icoMap[ext]||'📄', code:parsed.content};
  ideFiles.push(newFile);
  var ni=ideFiles.length-1;
  var tree=R('fileTree');
  if(tree) tree.innerHTML=ideFiles.map(function(f,i){ return '<div class="ide-file'+(i===ni?' active':'')+'" onclick="openIdeFile('+i+')"><span style="font-size:12px;margin-right:4px;">'+f.ico+'</span>'+f.name+'</div>'; }).join('');
  var tabs=R('ideTabs');
  if(tabs) tabs.innerHTML=ideFiles.map(function(f,i){ return '<div class="ide-tab'+(i===ni?' active':'')+'" onclick="openIdeFile('+i+')">'+f.ico+' '+f.name+'</div>'; }).join('');
  openIdeFile(ni);
  showToast('✨ '+fname+' створено AI');
  ideSetStatusBar('✨ '+fname,'var(--accent)');
}

/* ── Quick AI actions (Explain, Bugs, Optimize…) ─────────── */
function ideQuick(prompt){
  var inp=R('ideAiInput'); if(inp) inp.value=prompt;
  sendIdeAi();
}

/* ── Run in terminal ─────────────────────────────────────── */
function ideRunInTerm(){
  if(!ideEditor) return;
  var f=ideFiles[activeFileIdx]; if(!f) return;
  var out=R('ideTermOut');
  if(out) out.textContent='axis@os:~$ '+f.name+'\n⏳ Виконується...\n';
  if(f.lang==='python'){
    pyCall('run_code', JSON.stringify({code:ideEditor.getValue(), lang:'python', file:f.name}));
  } else if(f.lang==='javascript'){
    // SECURITY: never eval() editor content in renderer context
    // Send to Python for execution in a subprocess instead
    pyCall('ide_run_code', JSON.stringify({
      code: ideEditor.getValue(),
      lang: 'js',
      filename: f.name
    }));
    // Show result in terminal when Python responds via axisPush
  } else { if(out) out.textContent='axis@os:~$ '+f.name+'\n⚠ Запуск підтримується для Python та JS\naxis@os:~$ _'; }
}

/* ── Recent files sidebar ────────────────────────────────── */
var _ideRecentHistory = (function(){ try{return JSON.parse(localStorage.getItem('axis_ide_recent')||'[]');}catch(e){return [];} })();
function ideAddRecentFile(path, fname){
  _ideRecentHistory=_ideRecentHistory.filter(function(r){return r.path!==path;});
  _ideRecentHistory.unshift({path:path, name:fname||path.split(/[\\/]/).pop()});
  if(_ideRecentHistory.length>8) _ideRecentHistory=_ideRecentHistory.slice(0,8);
  localStorage.setItem('axis_ide_recent',JSON.stringify(_ideRecentHistory));
  _ideRenderRecentFiles();
}
function _ideRenderRecentFiles(){
  var el=R('ideRecentFiles'); if(!el) return;
  if(!_ideRecentHistory.length){ el.innerHTML='<div style="font-size:10px;color:var(--text3);padding:4px 2px;">Немає файлів</div>'; return; }
  var icoMap={py:'🐍',js:'📜',ts:'💙',html:'🌐',css:'🎨',json:'⚙',md:'📄',jsx:'⚛',tsx:'⚛'};
  el.innerHTML=_ideRecentHistory.map(function(r){
    var ext=r.name.split('.').pop().toLowerCase();
    return '<div class="ide-file" style="font-size:10px;padding:3px 6px;" onclick="pyCall(\'open_file_path\',JSON.stringify({path:'+JSON.stringify(r.path)+'}));" title="'+_ideEscAttr(r.path)+'">'+(icoMap[ext]||'📄')+' '+r.name+'</div>';
  }).join('');
}
_ideRenderRecentFiles();

/* ── Ctrl+K keyboard shortcut ────────────────────────────── */
document.addEventListener('keydown',function(e){
  if(e.ctrlKey && e.key==='k'){
    var pg=R('page-agents'); if(pg && pg.classList.contains('active')){ e.preventDefault(); toggleIdeAiBar(); }
  }
});

// Route AI responses: Live → IDE edit → IDE new file → IDE pane chat → normal chat
var _origAiResponse = handleAiResponse;
window.handleAiResponse = function(d){
  // Live voice mode
  if (liveMode && d.id === pendingLiveId) {
    liveHandleResponse(d.text || '');
    addChatMsg('user', R('liveUserText') ? R('liveUserText').textContent.replace(/^«|»$/g,'') : '…', 'Ви (Live)');
    addChatMsg('ai', d.text || '', 'AXIS Live · ' + currentModel);
    return;
  }
  // IDE Edit mode (returns JSON edits)
  if (d.id && d.id === _ideEditReqId) { _ideHandleEditResponse(d.text || ''); return; }
  // IDE New File mode
  if (d.id && d.id === _ideNewFileReqId) { _ideHandleNewFileResponse(d.text || ''); return; }
  // IDE AI chat pane (regular assist)
  var ide = R(d.id);
  if (ide) { ide.textContent = d.text || ''; return; }
  _origAiResponse(d);
};

// ═══ IDE CONTROL PANEL ═══
// ─── IDE Control Panel ────────────────────────────────────────────
var _ideRunning = false;
var _ideConfig = {provider:'openai', model:'gpt-4o', privacy_mode:false, recent_projects:[]};

function ideInit(){
  // Load IDE config via bridge
  pyCall('get_ide_status');
}
function initAgents(){ ideInit(); }

function ideApplyConfig(cfg){
  _ideConfig = Object.assign(_ideConfig, cfg);
  var prov = document.getElementById('ideProvider');
  var mod  = document.getElementById('ideModel');
  var priv = document.getElementById('idePrivacy');
  if(prov) prov.value = cfg.provider || 'openai';
  if(mod)  mod.value  = cfg.model    || 'gpt-4o';
  if(priv) priv.checked = !!cfg.privacy_mode;
  ideTogglePrivacyBadge(!!cfg.privacy_mode);
  ideRenderRecent(cfg.recent_projects || []);
}

function ideTogglePrivacyBadge(on){
  var b = document.getElementById('idePrivacyBadge');
  if(b) b.style.display = on ? 'block' : 'none';
}

function ideSaveSettings(){
  var prov = (document.getElementById('ideProvider')||{}).value || 'openai';
  var mod  = (document.getElementById('ideModel')||{}).value   || 'gpt-4o';
  var priv = !!(document.getElementById('idePrivacy')||{}).checked;
  _ideConfig.provider     = prov;
  _ideConfig.model        = mod;
  _ideConfig.privacy_mode = priv;
  ideTogglePrivacyBadge(priv);
  pyCall('save_ide_config', JSON.stringify({provider:prov, model:mod, privacy_mode:priv}));
}

function ideSetStatus(running){
  _ideRunning = running;
  var pill  = document.getElementById('ideStatusPill');
  var dot   = document.getElementById('ideDot');
  var txt   = document.getElementById('ideStatusText');
  var lbtn  = document.getElementById('ideLaunchBtn');
  var sbtn  = document.getElementById('ideStopBtn');
  if(pill){
    pill.className = 'idectl-status-pill' + (running ? ' running' : '');
  }
  if(dot)  dot.className  = 'idectl-dot' + (running ? ' on' : '');
  if(txt)  txt.textContent = running ? 'Запущено' : 'Остановлено';
  if(lbtn) lbtn.style.display = running ? 'none'  : '';
  if(sbtn) sbtn.style.display = running ? '' : 'none';
}

function ideLaunch(){
  pyCall('launch_ide');
  showToast('IDE запускается...');
  setTimeout(function(){ pyCall('get_ide_status'); }, 2500);
}

function ideStop(){
  pyCall('stop_ide');
  setTimeout(function(){ pyCall('get_ide_status'); }, 800);
}

function ideLaunchWithFolder(){
  pyCall('launch_ide', JSON.stringify({open_folder:true}));
  showToast('IDE запускается...');
  setTimeout(function(){ pyCall('get_ide_status'); }, 2500);
}

function ideRenderRecent(list){
  var el = document.getElementById('ideRecentList');
  if(!el) return;
  if(!list || !list.length){
    el.innerHTML = '<div style="font-size:11px;color:var(--text3);text-align:center;padding:16px 0;">Нет недавних проектов</div>';
    return;
  }
  el.innerHTML = list.slice(0,6).map(function(p){
    var name = p.split(/[\/\\]/).pop() || p;
    return '<div class="idectl-recent-item" onclick="ideLaunchProject('+JSON.stringify(p)+')">'
      + '<span style="font-size:14px;">📁</span>'
      + '<span class="idectl-recent-path" title="'+p+'">'+name+'</span>'
      + '<span class="idectl-recent-open">Открыть</span></div>';
  }).join('');
}

function ideLaunchProject(path){
  pyCall('launch_ide', JSON.stringify({project_path: path}));
  showToast('Открываю: ' + (path.split(/[\/\\]/).pop() || path));
  setTimeout(function(){ pyCall('get_ide_status'); }, 2500);
}

function ideNewProject(template){
  if(!_ideRunning){
    pyCall('launch_ide');
    setTimeout(function(){
      pyCall('ide_new_project', JSON.stringify({template: template}));
    }, 3000);
  } else {
    pyCall('ide_new_project', JSON.stringify({template: template}));
  }
  showToast('Создаю проект: ' + template);
}

// ─── IDE push events ──────────────────────────────────────────────
function handleIdeStatus(d){
  ideSetStatus(d.running);
  if(d.config) ideApplyConfig(d.config);
}
