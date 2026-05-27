/* AXIS OS ? AI Generator */
// ═══ GENERATOR MODE SWITCH ═══
var _genMode = 'image';
function switchGenMode(el) {
  document.querySelectorAll('.gen-mode-tab').forEach(function(t){ t.classList.remove('active'); });
  el.classList.add('active');
  _genMode = el.dataset.mode;
  R('genModeCode').style.display  = (_genMode === 'code')  ? 'grid' : 'none';
  R('genModeImage').style.display = (_genMode === 'image') ? 'grid' : 'none';
  if (_genMode === 'code') {
    showToast('⚠ Генерація коду в розробці — результати можуть бути неточними');
  }
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

// ═══ SMART DESCRIPTION ENHANCER ═══
// Detects what the user wants and injects detailed technical requirements
function _enhanceDescription(desc, type) {
  var d = desc.toLowerCase();

  // ── CHESS / board games ──
  if (/шахмат|chess|шахи/.test(d)) {
    return desc + '\n\n[CHESS REQUIREMENTS — MANDATORY]\n' +
      'Draw board: 8x8 grid, alternating light/dark squares, coordinate labels a-h / 1-8.\n' +
      'Pieces rendered as Unicode symbols OR drawn with Canvas paths — large, clearly visible:\n' +
      '  King ♔♚, Queen ♕♛, Rook ♖♜, Bishop ♗♝, Knight ♘♞, Pawn ♙♟\n' +
      'Full move validation for EVERY piece type:\n' +
      '  Pawn: forward 1 (or 2 from start), diagonal capture, en passant, promotion to queen\n' +
      '  Knight: L-shape, can jump over pieces\n' +
      '  Bishop: diagonal unlimited\n' +
      '  Rook: horizontal/vertical unlimited\n' +
      '  Queen: rook + bishop combined\n' +
      '  King: 1 square any direction + castling (king-side and queen-side)\n' +
      'Check detection: highlight king in red when in check\n' +
      'Checkmate and stalemate detection with game-over popup\n' +
      'Highlight legal moves when piece is clicked (green dots or highlighted squares)\n' +
      'Turn indicator: "White to move" / "Black to move"\n' +
      'Simple AI for black pieces (pick random legal move, or minimax depth 2)\n' +
      'Captured pieces display\n' +
      'New game button';
  }

  // ── CHECKERS ──
  if (/шашки|checkers|draughts/.test(d)) {
    return desc + '\n\n[CHECKERS REQUIREMENTS — MANDATORY]\n' +
      'Draw 8x8 board. Pieces as filled circles with gradient.\n' +
      'Forced captures (jump over opponent). Multiple jumps in one turn.\n' +
      'King promotion when reaching last row (crown symbol on piece).\n' +
      'Highlight valid moves on click. AI opponent. Win detection.';
  }

  // ── TETRIS ──
  if (/тетріс|tetris|тетрис/.test(d)) {
    return desc + '\n\n[TETRIS REQUIREMENTS — MANDATORY]\n' +
      'All 7 tetrominoes: I, O, T, S, Z, J, L — each different color.\n' +
      'Rotation (clockwise and counter-clockwise). Wall kicks.\n' +
      'Line clear with animation. Score: 100/300/500/800 for 1/2/3/4 lines.\n' +
      'Speed increases every 10 lines (levels). Next piece preview box.\n' +
      'Hold piece feature. Ghost piece (shadow showing where it lands).\n' +
      'Game over detection. High score in localStorage.';
  }

  // ── SNAKE ──
  if (/зміїк|змійк|snake|snaky/.test(d)) {
    return desc + '\n\n[SNAKE REQUIREMENTS — MANDATORY]\n' +
      'Grid-based movement. Snake grows when eating food.\n' +
      'Wall collision AND self-collision = game over.\n' +
      'Arrow keys + WASD. Speed increases as snake grows.\n' +
      'Food placed randomly (never on snake). Score = length - 1.\n' +
      'Smooth visual: rounded segments, gradient colors from head to tail.\n' +
      'High score persistence in localStorage. Restart on press.';
  }

  // ── AK-47 / weapons ──
  if (/ак.?47|ак.?74|калашник|автомат|rifle|assault.?rif|ak47|ak74|carbine|m16|m4a1|gun|пістол|pistol|пушк|revolver|shotgun|sniper|снайп/.test(d)) {
    return desc + '\n\n[WEAPON DRAWING REQUIREMENTS — MANDATORY]\n' +
      'Draw on Canvas 900x400. Use ctx.beginPath(), lineTo(), bezierCurveTo(), arc() — NO simple rectangles.\n' +
      'AK-47 must have ALL these parts drawn as distinct Canvas shapes:\n' +
      '  1. Stock (приклад): wooden curved shape, right side\n' +
      '  2. Receiver/body (ствольна коробка): main rectangular body with details\n' +
      '  3. Magazine (магазин): curved banana magazine pointing down-forward\n' +
      '  4. Barrel (ствол): long thin cylinder extending left\n' +
      '  5. Gas tube (газова трубка): thin tube above barrel\n' +
      '  6. Front sight (мушка): small vertical post at barrel end\n' +
      '  7. Rear sight (приціл): folded sight near receiver\n' +
      '  8. Pistol grip (пістолетна рукоятка): curved grip below receiver\n' +
      '  9. Trigger guard (скоба): curved guard around trigger\n' +
      ' 10. Charging handle (затвор): small handle on right side of receiver\n' +
      ' 11. Dust cover: on top of receiver\n' +
      'Colors: dark steel #2a2a2a for metal, #5c3d1e for wood, accent highlights\n' +
      'Add technical label lines pointing to each part\n' +
      'Add rotation animation: gun slowly rotates 360° showing all angles\n' +
      'Bottom: display name "AK-47 / Автомат Калашникова" with specs text';
  }

  // ── VEHICLES: tanks, cars ──
  if (/танк|tank|броне|armou?r/.test(d)) {
    return desc + '\n\n[TANK DRAWING REQUIREMENTS — MANDATORY]\n' +
      'Draw on Canvas. Hull (hull body with track bogies), turret (rounded top with hatch), cannon barrel (long extending right).\n' +
      'Tracks: series of small rectangles below hull. Road wheels visible.\n' +
      'Colors: military green #4a5240 with dark shadows.\n' +
      'Add slow rotation or side-scrolling animation.';
  }
  if (/машин|автомобіл|car\b|auto\b|vehicle|спортивн.*авт/.test(d)) {
    return desc + '\n\n[CAR DRAWING REQUIREMENTS — MANDATORY]\n' +
      'Draw on Canvas. Full car silhouette with: body shape, roof, windows (windshield, side, rear), doors, hood, trunk.\n' +
      'Wheels: 2 circles with inner hub detail. Headlights and taillights.\n' +
      'Spoiler if sports car. Realistic proportions. Shadow under car.\n' +
      'Metallic gradient on body. Add slow idle animation (slight bounce).';
  }

  // ── HUMAN / CHARACTER ──
  if (/людин|персонаж|character|солдат|soldier|людська фігур|stick.?man|чоловічок/.test(d)) {
    return desc + '\n\n[CHARACTER DRAWING REQUIREMENTS — MANDATORY]\n' +
      'Draw full human figure with Canvas: head (circle), neck, torso (trapezoid), arms with elbow and wrist joints, hands (simplified), legs with knee joints, feet.\n' +
      'Clothing details drawn as filled shapes. Face: eyes, nose, mouth.\n' +
      'All body parts connected correctly. Proportional anatomy.\n' +
      'Add breathing or idle animation.';
  }

  // ── SOLAR SYSTEM / SPACE ──
  if (/сонячн.*систем|solar.?sys|planet|планет|космос|space\b|universe/.test(d)) {
    return desc + '\n\n[SPACE REQUIREMENTS — MANDATORY]\n' +
      'All 8 planets with correct relative sizes and colors: Mercury(grey), Venus(yellow), Earth(blue+green), Mars(red), Jupiter(orange bands), Saturn(golden+rings), Uranus(light blue), Neptune(dark blue).\n' +
      'Elliptical orbit paths drawn. Each planet orbits at correct relative speed. Sun in center with glow effect.\n' +
      'Stars background (200+ random dots). Moon orbiting Earth.\n' +
      'Planet name labels. Click planet to show info panel.';
  }

  // ── FIRE / PARTICLES ──
  if (/вогонь|fire\b|flame|полум|частинк|particle/.test(d)) {
    return desc + '\n\n[PARTICLE SYSTEM REQUIREMENTS — MANDATORY]\n' +
      '300+ particles. Each particle: position, velocity, life, color, size.\n' +
      'Fire: particles rise with random spread, fade from yellow→orange→red→transparent.\n' +
      'Physics: gravity, wind, turbulence. Glow effect using composite operations.\n' +
      '60fps with requestAnimationFrame. Interactive: click/move to spawn particles.';
  }

  // ── PIANO / MUSIC ──
  if (/піаніно|piano|keyboard.*music|клавіш.*муз/.test(d)) {
    return desc + '\n\n[PIANO REQUIREMENTS — MANDATORY]\n' +
      'Draw 3 full octaves (C3 to C6 = 37 white keys, 25 black keys) using Canvas or HTML elements.\n' +
      'White keys: 23px wide, 120px tall. Black keys: 14px wide, 80px tall, overlapping whites.\n' +
      'WebAudio API: each key plays its exact frequency (A4=440Hz, equal temperament).\n' +
      'Keyboard mapping: ASDFGHJK = white keys, WETYU = black keys.\n' +
      'Keys highlight on press/click. Hold key for sustained note.\n' +
      'Octave up/down buttons. Volume slider. Record and playback mode.';
  }

  // ── CLOCK ──
  if (/годинник|clock|watch|timer.*clock|аналогов.*час/.test(d)) {
    return desc + '\n\n[CLOCK REQUIREMENTS — MANDATORY]\n' +
      'Canvas analog clock: outer ring with 60 minute marks (larger at 5-min intervals), 12 hour numbers.\n' +
      'Three hands: hour (thick, short), minute (medium), second (thin, red with counterweight).\n' +
      'Smooth second hand (real-time Date()), or sweep animation.\n' +
      'Inner glow, metallic bezel effect. Dark luxury design.';
  }

  // ── FRACTAL / MATH VISUALIZATION ──
  if (/фрактал|fractal|mandelbrot|julia|sierpin/.test(d)) {
    return desc + '\n\n[FRACTAL REQUIREMENTS — MANDATORY]\n' +
      'Render on Canvas using iteration algorithm. Full color mapping (HSL based on escape speed).\n' +
      'Smooth infinite zoom: scroll to zoom in, drag to pan.\n' +
      'Show iteration count, zoom level, coordinates in status bar.\n' +
      'Web Worker for computation (non-blocking). Progressive rendering.';
  }

  // ── GENERIC VISUAL (no specific match) — force Canvas detail ──
  if (type === 'component' || /малюй|draw|намалюй|зобрази|render|відобрази|show me|display/.test(d)) {
    return desc + '\n\n[DRAWING REQUIREMENTS — MANDATORY]\n' +
      'Use HTML Canvas (900x500 minimum). Draw with ctx.beginPath(), bezierCurveTo(), arc() paths.\n' +
      'ABSOLUTELY NO simple colored rectangles as stand-ins for complex objects.\n' +
      'Every object has: proper silhouette, color gradients (createLinearGradient), shadows (shadowBlur), details.\n' +
      'Add animation if appropriate (requestAnimationFrame).';
  }

  return desc;
}

function generateProject() {
  if (_genRunning) return;
  var desc = (R('genDesc').value || '').trim();
  if (!desc) { R('genDesc').style.borderColor='var(--red)'; R('genDesc').focus(); return; }
  R('genDesc').style.borderColor = '';

  var provider   = R('genProvider').value;
  var complexity = R('genComplexity').value;

  // Auto-enhance description with detailed technical requirements
  var enhancedDesc = _enhanceDescription(desc, _genType);

  // ── Complexity expansions ──
  var complexExtra = {
    simple:  'Clean, functional. All features fully working.',
    medium:  'Polished UI, smooth animations, complete feature set, dark modern design.',
    complex: 'MAXIMUM quality. Stunning visuals, particle effects, 60fps animations, full feature set. Professional production level.',
  };

  // ── Type-specific mandatory requirements ──
  var typeRules = {
    game:
      'GAME RULES:\n' +
      '• ALL game mechanics fully coded — every rule, every edge case\n' +
      '• Board games: every piece type, legal move validation, special moves, check/checkmate\n' +
      '• Arcade games: requestAnimationFrame loop, collision detection, score, lives, level up\n' +
      '• Include simple AI opponent for 2-player games\n' +
      '• Keyboard + mouse controls. Score/timer always visible.',
    app:
      'APP RULES:\n' +
      '• Every button/feature fully implemented — nothing decorative or stub\n' +
      '• localStorage persistence. Input validation. Loading states.',
    site:
      'SITE RULES:\n' +
      '• All sections have real content. Navigation works. Forms validate.',
    component:
      'COMPONENT RULES:\n' +
      '• Fully interactive. All states handled. Smooth animations.',
  };

  var prompt =
    'Build this ' + _genType + ':\n\n' +
    enhancedDesc + '\n\n' +
    '════ COMPLEXITY: ' + complexity.toUpperCase() + ' ════\n' +
    complexExtra[complexity] + '\n\n' +
    (typeRules[_genType] || typeRules.app) + '\n\n' +
    '════ ABSOLUTE RULES — VIOLATING ANY = WRONG ANSWER ════\n' +
    '1. Single HTML file, embedded CSS+JS, zero CDN/external dependencies\n' +
    '2. Dark theme: background #0d0d0d or #111\n' +
    '3. ZERO stubs: no "// TODO", no "// implement", no placeholder functions\n' +
    '4. Canvas drawings use REAL paths (beginPath, bezierCurveTo, arc) — NOT colored rectangles\n' +
    '5. Every visual component drawn in full detail with gradients and shadows\n' +
    '6. Code runs error-free in browser\n' +
    '7. Output starts with <!DOCTYPE html> — nothing before it, nothing after </html>\n\n' +
    'START NOW:';

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
  if (console_) console_.textContent = '> Провайдер: ' + provider + '\n> Тип: ' + _genType + ' | Складність: ' + complexity + '\n> Промт розширено: ' + (enhancedDesc.length > desc.length ? 'ТАК' : 'НІ') + '\n> Генерую...\n';

  var modelEl = R('genModel');
  var model = modelEl ? (modelEl.value || _genModelDefaults[provider] || 'gpt-4o') : _genModelDefaults[provider] || 'gpt-4o';

  var systemPrompt =
    'You are a world-class creative developer who builds COMPLETE, STUNNING single-file HTML apps.\n' +
    'YOUR IRON RULES:\n' +
    '• Output ONLY raw HTML starting with <!DOCTYPE html>. Zero markdown. Zero explanation.\n' +
    '• Every feature described is FULLY implemented. Zero stubs. Zero TODOs.\n' +
    '• Canvas graphics: use real bezierCurveTo / arc paths for every shape. Never draw a gun as 2 boxes.\n' +
    '• Chess/board games: implement EVERY rule (castling, en passant, check, checkmate, AI).\n' +
    '• Arcade games: full physics loop, collision, scoring, game over, restart.\n' +
    '• Dark theme. Smooth animations. Professional look.\n' +
    '• You write 500-2000+ lines if needed. Completeness > brevity.';

  pyCall('ai_send_stream', JSON.stringify({
    id: _genReqId,
    provider: provider,
    model: model,
    messages: [{role:'user', content: prompt}],
    system: systemPrompt
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
  R('imgGenMsg').textContent = 'Надсилаю запит до ' + (provider==='openai'?'DALL·E 3':'FLUX (Pollinations)') + '...';

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

var _imgSavedPath = '';

function handleImageReady(d) {
  if ((d.id||'') !== _imgReqId) return;
  _imgRunning   = false;
  _imgResultB64 = d.b64 || '';
  _imgSavedPath = d.saved_path || '';

  var anim = R('imgGenAnim'); if (anim) anim.style.display='none';
  var img = R('imgResult');
  if (img && _imgResultB64) {
    // Detect JPEG vs PNG from base64 magic bytes (/9j/ = JPEG, iVBOR = PNG)
    var mime = _imgResultB64.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
    img.src = 'data:' + mime + ';base64,' + _imgResultB64;
    img.style.display = 'block';
  }

  var btn = R('imgGenBtn'); if (btn) { btn.disabled=false; btn.innerHTML='<span>🖼</span><span>Згенерувати зображення</span>'; }
  var dl = R('imgDownBtn'); if (dl) dl.style.display='inline-flex';
  var ur = R('imgUseAsRefBtn'); if (ur) ur.style.display='inline-flex';

  // Show where saved + source indicator
  var src = d.source || (d.via_proxy ? '🤗 FLUX (безкоштовно)' : '🔑 прямий запит');
  var fileName = _imgSavedPath ? _imgSavedPath.split('\\').pop() : '';
  var msg = fileName
    ? '💾 Збережено: Зображення/AXIS OS/' + fileName + ' · ' + src
    : '✓ Зображення згенеровано · ' + src;
  showToast(msg);

  // Update download button label if saved
  if (dl && _imgSavedPath) {
    dl.title = 'Збережено: ' + _imgSavedPath;
  }

  // Show source label under image
  var lbl = R('imgSourceLbl');
  if (lbl) { lbl.textContent = src; lbl.style.display='block'; }
}

function downloadGenImage() {
  // Open the saved file folder in Explorer
  if (_imgSavedPath) {
    pyCall('run_macro', JSON.stringify({command: 'explorer /select,"' + _imgSavedPath + '"', type: 'shell'}));
    showToast('📂 Відкриваю папку...');
    return;
  }
  // Fallback: download via browser
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

