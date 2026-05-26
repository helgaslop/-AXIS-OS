/* AXIS OS ? AI Generator */
// ═══ GENERATOR MODE SWITCH ═══
var _genMode = 'code';
function switchGenMode(el) {
  document.querySelectorAll('.gen-mode-tab').forEach(function(t){ t.classList.remove('active'); });
  el.classList.add('active');
  _genMode = el.dataset.mode;
  R('genModeCode').style.display  = (_genMode === 'code')  ? 'grid' : 'none';
  R('genModeImage').style.display = (_genMode === 'image') ? 'grid' : 'none';
  R('genModeVideo').style.display = (_genMode === 'video') ? 'grid' : 'none';
}

// ═══ CODE GENERATOR — STREAMING ═══
var _genCode    = '';
var _genRunning = false;
var _genType    = 'game';
var _genTokens  = 0;
var _genReqId   = '';

var _genProviderModels = {
  openai:    [
    'gpt-5','gpt-5-mini',
    'gpt-4.5','gpt-4.5-mini',
    'gpt-4.1','gpt-4.1-mini','gpt-4.1-nano',
    'gpt-4o','gpt-4o-mini',
    'o3','o4-mini','o3-mini','o1','o1-mini',
  ],
  anthropic: ['claude-opus-4-5','claude-sonnet-4-5','claude-haiku-4-5'],
  google:    ['gemini-2.5-pro','gemini-2.5-flash','gemini-2.5-flash-lite','gemini-2.0-flash','gemini-1.5-pro'],
  perplexity: ['sonar-pro','sonar','sonar-reasoning-pro','sonar-reasoning','sonar-deep-research'],
  xai:        ['grok-3','grok-3-mini','grok-3-fast','grok-2'],
  ollama:     [],
};
var _genModelDefaults = {
  openai:'gpt-4o', anthropic:'claude-sonnet-4-5', google:'gemini-2.5-flash',
  perplexity:'sonar-pro', xai:'grok-3', ollama:'',
};

function updateGenModels(provider) {
  var sel = R('genModel'); if (!sel) return;
  var models = _genProviderModels[provider] || [];
  sel.innerHTML = '';
  if (!models.length) {
    var opt = document.createElement('option'); opt.value=''; opt.textContent='(введіть вручну)'; sel.appendChild(opt);
    sel.removeAttribute('disabled'); sel.style.color='var(--text3)'; return;
  }
  models.forEach(function(m) {
    var opt = document.createElement('option'); opt.value=m; opt.textContent=m; sel.appendChild(opt);
  });
  sel.value = _genModelDefaults[provider] || models[0];
}

function selectGenType(el) {
  document.querySelectorAll('#genTypeGrid .gen-type-btn').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
  _genType = el.dataset.type;
}

function switchGenTab(el, paneId) {
  el.closest('.gen-right-tabs').querySelectorAll('.gen-right-tab').forEach(function(t){ t.classList.remove('active'); });
  el.classList.add('active');
  document.querySelectorAll('.gen-pane').forEach(function(p){ p.classList.remove('active'); });
  var pane = R(paneId); if (pane) pane.classList.add('active');
}

function generateProject() {
  if (_genRunning) return;
  var desc = (R('genDesc').value || '').trim();
  if (!desc) { R('genDesc').style.borderColor='var(--red)'; R('genDesc').focus(); return; }
  R('genDesc').style.borderColor = '';

  var provider   = R('genProvider').value;
  var complexity = R('genComplexity').value;
  var typeLabels = {game:'гру',app:'застосунок',site:'сайт',component:'компонент'};
  var complexLabels = {
    simple:  'простий',
    medium:  'середнього рівня з гарним UI',
    complex: 'складний із анімаціями, ефектами та повним функціоналом'
  };

  var prompt = 'Згенеруй ' + complexLabels[complexity] + ' ' + typeLabels[_genType] + '.\n'
    + 'Опис: ' + desc + '\n\n'
    + 'Вимоги:\n'
    + '- Один HTML файл із вбудованим CSS та JavaScript\n'
    + '- Темний сучасний дизайн\n'
    + '- Повністю робочий код без зовнішніх залежностей\n'
    + '- Повернути ТІЛЬКИ HTML код без пояснень, починаючи з <!DOCTYPE html>';

  _genRunning = true;
  _genTokens  = 0;
  _genCode    = '';
  _genReqId   = 'gen_' + Date.now();

  // UI: show progress
  var btn = R('genBtn'); if (btn) { btn.disabled=true; btn.innerHTML='<span>⏳</span><span>Генерую...</span>'; }
  var pw = R('genProgressWrap'); if (pw) pw.style.display='block';
  var pb = R('genProgressBar'); if (pb) pb.style.width='5%';
  R('genProgressLabel').textContent = 'AI пише код...';
  R('genTokenCount').textContent = '0 токенів';

  // Show streaming animation in preview pane
  R('genPreviewEmpty').style.display = 'flex';
  R('genPreviewEmpty').querySelector('#genStreamAnim').style.display = 'flex';
  R('genStreamMsg').textContent = 'Підключаюсь до ' + provider + '...';
  var frame = R('genPreviewFrame'); if (frame) frame.style.display='none';

  // Switch to code pane to show live tokens
  var codeTab = document.querySelector('.gen-right-tab:nth-child(2)');
  if (codeTab) switchGenTab(codeTab, 'gen-pane-code');
  var area = R('genCodeArea'); if (area) area.textContent = '';

  var console_ = R('genConsole');
  if (console_) console_.textContent = '> Провайдер: ' + provider + '\n> Тип: ' + _genType + ' | Складність: ' + complexity + '\n> Генерую...\n';

  var modelEl = R('genModel');
  var model = modelEl ? (modelEl.value || _genModelDefaults[provider] || 'gpt-4o') : _genModelDefaults[provider] || 'gpt-4o';

  pyCall('ai_send_stream', JSON.stringify({
    id: _genReqId,
    provider: provider,
    model: model,
    messages: [{role:'user', content: prompt}],
    system: 'You are a code generator. Return ONLY clean, complete, working HTML code. No explanation, no markdown fences.'
  }));
}

function handleGenToken(d) {
  if ((d.id||'') !== _genReqId) return;
  var token = d.token || '';
  _genCode += token;
  _genTokens += token.length;

  // Live display in code pane
  var area = R('genCodeArea');
  if (area) {
    area.textContent = _genCode;
    area.scrollTop = area.scrollHeight;
  }

  // Update progress
  var count = R('genTokenCount');
  if (count) count.textContent = _genTokens + ' токенів';

  // Animate progress bar (simulate up to 90%)
  var pb = R('genProgressBar');
  if (pb) {
    var pct = Math.min(90, 5 + (_genTokens / 50));
    pb.style.width = pct + '%';
  }

  // Update stream message
  var lines = _genCode.split('\n').length;
  var cl = R('genCodeLines'); if (cl) cl.textContent = lines + ' рядків';
  var msg = R('genStreamMsg');
  if (msg) {
    if (_genCode.includes('<!DOCTYPE')) msg.textContent = 'Пишу HTML структуру...';
    if (_genCode.includes('<style'))    msg.textContent = 'Додаю стилі CSS...';
    if (_genCode.includes('<script'))   msg.textContent = 'Пишу JavaScript логіку...';
    if (_genCode.includes('function')) msg.textContent = 'Реалізую функції...';
  }
}

function handleGenDone(d) {
  if ((d.id||'') !== _genReqId) return;
  _genRunning = false;

  // Clean up markdown fences if AI added them
  var code = _genCode.replace(/^```html\s*/i,'').replace(/\s*```$/,'').trim();
  var match = code.match(/<!DOCTYPE html[\s\S]*/i) || code.match(/<html[\s\S]*/i);
  if (match) code = match[0];
  _genCode = code;

  // Finalize code area
  var area = R('genCodeArea'); if (area) area.textContent = code;

  // Update progress to 100%
  var pb = R('genProgressBar'); if (pb) { pb.style.width='100%'; }
  R('genProgressLabel').textContent = '✓ Готово!';
  var count = R('genTokenCount'); if (count) count.textContent = _genTokens + ' токенів';

  // Show preview
  var empty = R('genPreviewEmpty'); if (empty) empty.style.display='none';
  var frame = R('genPreviewFrame');
  if (frame && code) { frame.style.display='block'; frame.srcdoc=code; }

  // Switch to preview
  var firstTab = document.querySelector('.gen-right-tab');
  if (firstTab) switchGenTab(firstTab, 'gen-pane-preview');

  var btn = R('genBtn'); if (btn) { btn.disabled=false; btn.innerHTML='<span>✨</span><span>Згенерувати проект</span>'; }

  var lines = code.split('\n').length;
  var cl = R('genCodeLines'); if (cl) cl.textContent = lines + ' рядків';
  var console_ = R('genConsole');
  if (console_) console_.textContent += '> ✓ Згенеровано ' + _genTokens + ' токенів, ' + lines + ' рядків\n> Превью готове';

  // Hide progress after 2s
  setTimeout(function(){ var pw=R('genProgressWrap'); if(pw) pw.style.display='none'; }, 2000);
  showToast('✓ Проект згенеровано — ' + lines + ' рядків коду!');
}

function handleGenResult(data) {
  // Fallback for non-streaming response
  if ((data.id||'') !== _genReqId) return;
  _genCode = (data.text||'').replace(/^```html\s*/i,'').replace(/\s*```$/,'').trim();
  var match = _genCode.match(/<!DOCTYPE html[\s\S]*/i) || _genCode.match(/<html[\s\S]*/i);
  if (match) _genCode = match[0];
  handleGenDone({id: _genReqId});
}

function copyGenCode() {
  if (!_genCode) { showToast('⚠ Немає коду'); return; }
  _copyText(_genCode, '✓ Код скопійовано');
}

function saveGenToIde() {
  if (!_genCode) { showToast('⚠ Немає коду'); return; }
  showPage('ide');
  setTimeout(function(){
    var ed = R('ideEditor'); if (ed) { ed.value = _genCode; ideSetMode('html'); }
    showToast('✓ Код відкрито в IDE');
  }, 150);
}

// ═══ IMAGE GENERATOR ═══
var _imgStyle   = 'vivid';
var _imgRefB64  = '';
var _imgRunning = false;
var _imgReqId   = '';
var _imgResultB64 = '';

function selectImgStyle(el) {
  document.querySelectorAll('#imgStyleGrid .gen-type-btn').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
  _imgStyle = el.dataset.style;
}

function triggerImgRefInput() { var inp=R('imgRefInput'); if(inp) inp.click(); }

function imgRefSelected(inp) {
  var file = inp.files[0]; if (!file) return;
  var reader = new FileReader();
  reader.onload = function(e) {
    var dataUrl = e.target.result;
    _imgRefB64 = dataUrl.split(',')[1] || '';
    var preview = R('imgRefPreview');
    if (preview) { preview.src = dataUrl; preview.style.display='block'; }
    R('imgRefEmpty').style.display='none';
    R('imgRefActions').style.display='flex';
    R('imgRefDrop').style.minHeight='auto';
  };
  reader.readAsDataURL(file);
}

function imgDragOver(e) {
  e.preventDefault();
  R('imgRefDrop').classList.add('drag-over');
}

function imgDrop(e) {
  e.preventDefault();
  R('imgRefDrop').classList.remove('drag-over');
  var file = e.dataTransfer.files[0];
  if (!file || !file.type.startsWith('image/')) return;
  var fakeInput = {files:[file]};
  imgRefSelected(fakeInput);
}

function clearImgRef() {
  _imgRefB64 = '';
  var preview = R('imgRefPreview'); if (preview) { preview.style.display='none'; preview.src=''; }
  R('imgRefEmpty').style.display='flex';
  R('imgRefActions').style.display='none';
  var inp = R('imgRefInput'); if (inp) inp.value='';
}

function generateImage() {
  if (_imgRunning) return;
  var prompt = (R('imgPrompt').value || '').trim();
  if (!prompt) { R('imgPrompt').style.borderColor='var(--red)'; R('imgPrompt').focus(); return; }
  R('imgPrompt').style.borderColor = '';

  var provider = R('imgProvider').value;
  var size     = R('imgSize').value;
  var styleMap = {vivid:'vivid', natural:'natural', anime:'anime style', photo:'photorealistic', '3d':'3D render', sketch:'pencil sketch'};
  var fullPrompt = styleMap[_imgStyle] ? prompt + ', ' + styleMap[_imgStyle] + ' style' : prompt;

  _imgRunning = true;
  _imgReqId   = 'img_' + Date.now();

  var btn = R('imgGenBtn'); if (btn) { btn.disabled=true; btn.innerHTML='<span>⏳</span><span>Генерую...</span>'; }
  R('imgStatus').textContent = '';
  R('imgResultEmpty').style.display='none';
  R('imgResult').style.display='none';
  var anim = R('imgGenAnim'); if (anim) anim.style.display='flex';
  R('imgGenMsg').textContent = 'Надсилаю запит до ' + (provider==='openai'?'DALL·E 3':'Google Imagen') + '...';

  var messages = [
    {msg:'Аналізую промт...', delay:1500},
    {msg:'Генерую зображення...', delay:4000},
    {msg:'Опрацьовую деталі...', delay:8000},
    {msg:'Майже готово...', delay:15000}
  ];
  messages.forEach(function(m){
    setTimeout(function(){ if(_imgRunning && R('imgGenMsg')) R('imgGenMsg').textContent=m.msg; }, m.delay);
  });

  pyCall('generate_image', JSON.stringify({
    id:        _imgReqId,
    provider:  provider,
    prompt:    fullPrompt,
    size:      size,
    style:     (_imgStyle==='vivid'||_imgStyle==='natural') ? _imgStyle : 'vivid',
    ref_image: _imgRefB64
  }));
}

function handleImageReady(d) {
  if ((d.id||'') !== _imgReqId) return;
  _imgRunning  = false;
  _imgResultB64 = d.b64 || '';

  var anim = R('imgGenAnim'); if (anim) anim.style.display='none';
  var img = R('imgResult');
  if (img && _imgResultB64) {
    img.src = 'data:image/png;base64,' + _imgResultB64;
    img.style.display = 'block';
  }

  var btn = R('imgGenBtn'); if (btn) { btn.disabled=false; btn.innerHTML='<span>🖼</span><span>Згенерувати зображення</span>'; }
  var dl = R('imgDownBtn'); if (dl) dl.style.display='inline-flex';
  var ur = R('imgUseAsRefBtn'); if (ur) ur.style.display='inline-flex';
  showToast('✓ Зображення згенеровано!');
}

function downloadGenImage() {
  if (!_imgResultB64) return;
  var a = document.createElement('a');
  a.href = 'data:image/png;base64,' + _imgResultB64;
  a.download = 'axis_image_' + Date.now() + '.png';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  showToast('✓ Зображення завантажено');
}

function useImageAsRef() {
  if (!_imgResultB64) return;
  _imgRefB64 = _imgResultB64;
  var preview = R('imgRefPreview');
  if (preview) { preview.src = 'data:image/png;base64,' + _imgResultB64; preview.style.display='block'; }
  R('imgRefEmpty').style.display='none';
  R('imgRefActions').style.display='flex';
  showToast('✓ Зображення встановлено як референс');
}

// ═══ VIDEO GENERATOR (Luma AI) ═══
var _vidRunning = false;
var _vidRefB64  = '';
var _vidUrl     = '';
var _vidPollTimer = null;

function handleVidRefDrop(ev) {
  ev.preventDefault();
  R('vidRefZone').style.borderColor = 'var(--border)';
  var file = ev.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) loadVidRefFile(file);
}
function handleVidRefFile(inp) {
  var file = inp.files[0]; if (!file) return;
  loadVidRefFile(file);
}
function loadVidRefFile(file) {
  var reader = new FileReader();
  reader.onload = function(e) {
    _vidRefB64 = e.target.result.split(',')[1];
    var thumb = R('vidRefThumb');
    thumb.querySelector('img').src = e.target.result;
    thumb.style.display = 'block';
  };
  reader.readAsDataURL(file);
}

function generateVideo() {
  if (_vidRunning) return;
  var prompt = (R('vidPrompt').value || '').trim();
  if (!prompt) { R('vidPrompt').style.borderColor='var(--red)'; R('vidPrompt').focus(); return; }
  R('vidPrompt').style.borderColor = '';

  _vidRunning = true;
  var duration = R('vidDuration').value;
  var aspect   = R('vidAspect').value;

  var btn = R('vidGenBtn'); if (btn) { btn.disabled=true; btn.innerHTML='<span>⏳</span><span>Генерую...</span>'; }
  R('vidResultEmpty').style.display = 'none';
  R('vidResult').style.display = 'none';
  R('vidGenAnim').style.display = 'flex';
  R('vidStatus').textContent = '';
  if (R('vidDownloadBtn')) R('vidDownloadBtn').style.display = 'none';

  var vidReqId = 'vid_' + Date.now();
  pyCall('generate_video', JSON.stringify({
    id: vidReqId,
    prompt: prompt,
    duration: parseInt(duration),
    aspect_ratio: aspect,
    ref_image: _vidRefB64 || ''
  }));

  // Update status messages while waiting
  var msgs = [
    [3000,  'Запит прийнято, генерую відео...'],
    [15000, 'Генерую перші кадри...'],
    [40000, 'Рендеринг відео...'],
    [80000, 'Завершальна обробка...'],
  ];
  msgs.forEach(function(m) {
    setTimeout(function(){
      if (_vidRunning && R('vidStatusAnim')) R('vidStatusAnim').textContent = m[1];
    }, m[0]);
  });
}

function handleVideoReady(d) {
  _vidRunning = false;
  var btn = R('vidGenBtn'); if (btn) { btn.disabled=false; btn.innerHTML='<span>🎬</span><span>Згенерувати відео</span>'; }
  R('vidGenAnim').style.display = 'none';

  var url = d.url || d.video_url || '';
  if (!url) { R('vidStatus').textContent = '⚠ Немає URL відео'; return; }
  _vidUrl = url;

  var vid = R('vidResult');
  vid.style.display = 'block';
  if (R('vidDownloadBtn')) R('vidDownloadBtn').style.display = 'inline-flex';
  R('vidStatus').textContent = '✅ Відео готове! Збережено в Зображення/AXIS OS';
  showToast('🎬 Відео згенеровано!');
  if (_notifSettings.ai !== false) playNotifSound();

  if (d.local && url.startsWith('file://')) {
    // Load local file via fetch → Blob URL (avoids WebEngine file:// restrictions)
    fetch(url)
      .then(function(r) { return r.blob(); })
      .then(function(blob) {
        var blobUrl = URL.createObjectURL(blob);
        vid.src = blobUrl;
        _vidUrl = blobUrl;
      })
      .catch(function(e) {
        // Fallback: try direct src
        vid.src = url;
        console.warn('fetch fallback:', e);
      });
  } else {
    vid.src = url;
  }
}

function downloadVideo() {
  if (!_vidUrl) return;
  var a = document.createElement('a');
  a.href = _vidUrl;
  a.download = 'axis_video_' + Date.now() + '.mp4';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
