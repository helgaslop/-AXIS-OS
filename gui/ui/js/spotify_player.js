/* AXIS OS — Spotify Player */
var _spCurrentUri   = '';
var _spIsPlaying    = false;
var _spShuffle      = false;
var _spPollTimer    = null;
var _spIdleCount    = 0;
var _spFavorites    = JSON.parse(localStorage.getItem('axis_sp_fav') || '[]');

window.addEventListener('beforeunload', function() {
  if (typeof _spPollTimer !== 'undefined' && _spPollTimer) {
    clearInterval(_spPollTimer);
    _spPollTimer = null;
  }
});

// ── Ініціалізація ────────────────────────────────────────────────────────────
function initMusicPage() {
  spRenderFavorites();
}

// Викликається з showPage()
function onMusicPageShow() {
  spRefresh();
  if (_spPollTimer) clearInterval(_spPollTimer);
  _spPollTimer = setInterval(spRefresh, 5000);
}

function onMusicPageHide() {
  if (_spPollTimer) { clearInterval(_spPollTimer); _spPollTimer = null; }
}

// ── Оновити поточний трек ────────────────────────────────────────────────────
function spRefresh() {
  if (!_spIsPlaying) {
    _spIdleCount++;
    if (_spIdleCount > 12) { // ~1 minute idle at 5 s interval
      clearInterval(_spPollTimer);
      _spPollTimer = null;
      _spIdleCount = 0;
      return;
    }
  } else {
    _spIdleCount = 0;
  }
  pyCall('spotify_action', JSON.stringify({action: 'current'}));
}

// ── Обробник відповіді від Python ────────────────────────────────────────────
function handleSpotifyTrack(d) {
  var cover  = R('spCover');
  var idle   = R('spCoverIdle');
  var track  = R('spTrack');
  var artist = R('spArtist');
  var fill   = R('spProgressFill');
  var posEl  = R('spTimePos');
  var durEl  = R('spTimeDur');
  var playBtn= R('spPlayBtn');
  var volEl  = R('spVolume');
  var volVal = R('spVolVal');
  var shBtn  = R('spShuffleBtn');

  if (d.error || d.idle) {
    if (track)  track.textContent  = 'Нічого не грає';
    if (artist) artist.textContent = '—';
    if (cover)  { cover.src = ''; cover.style.display = 'none'; }
    if (idle)   idle.style.display = 'flex';
    if (fill)   fill.style.width = '0%';
    if (posEl)  posEl.textContent = '0:00';
    if (durEl)  durEl.textContent = '0:00';
    if (playBtn) playBtn.textContent = '▶';
    _spIsPlaying = false;
    return;
  }

  _spCurrentUri = d.uri  || '';
  _spIsPlaying  = !!d.is_playing;
  _spShuffle    = !!d.shuffle;

  if (track)  track.textContent  = d.name   || '';
  if (artist) artist.textContent = d.artist || '';

  if (cover && d.cover) {
    cover.src = d.cover;
    cover.style.display = 'block';
    if (idle) idle.style.display = 'none';
  }

  var pct = d.duration > 0 ? (d.progress / d.duration * 100) : 0;
  if (fill)  fill.style.width = pct.toFixed(1) + '%';
  if (posEl) posEl.textContent = _spFmtMs(d.progress  || 0);
  if (durEl) durEl.textContent = _spFmtMs(d.duration  || 0);

  if (playBtn) playBtn.textContent = _spIsPlaying ? '⏸' : '▶';

  if (volEl && d.volume !== undefined) {
    volEl.value = d.volume;
    if (volVal) volVal.textContent = d.volume + '%';
  }

  if (shBtn) shBtn.classList.toggle('active', _spShuffle);
}

function handleSpotifySearch(items) {
  var box = R('spSearchResults');
  if (!box) return;
  if (!items || !items.length) {
    box.innerHTML = '<div style="padding:10px;color:var(--text3);font-size:12px;">Нічого не знайдено</div>';
    return;
  }
  box.innerHTML = items.map(function(t) {
    return '<div class="sp-row" onclick="spPlayUri(\'' + _spEscUri(t.uri) + '\',\'' +
      _spEsc(t.name) + '\',\'' + _spEsc(t.artist) + '\')">'
      + (t.cover ? '<img src="'+_spEscUrl(t.cover)+'" class="sp-row-img">' : '<div class="sp-row-img sp-row-no-img">🎵</div>')
      + '<div class="sp-row-info"><div class="sp-row-name">' + _spEsc(t.name) + '</div>'
      + '<div class="sp-row-artist">' + _spEsc(t.artist) + '</div></div>'
      + '<div class="sp-row-dur">' + _spFmtMs(t.ms || 0) + '</div>'
      + '<button class="sp-fav-btn" onclick="event.stopPropagation();spAddFav(\'' + _spEscUri(t.uri) + '\',\'' +
        _spEsc(t.name) + '\',\'' + _spEsc(t.artist) + '\',\'' + _spEscUrl(t.cover||'') + '\')" title="В вибране">⭐</button>'
      + '</div>';
  }).join('');
}

// ── Дії ──────────────────────────────────────────────────────────────────────
function spAction(act) {
  pyCall('spotify_action', JSON.stringify({action: act}));
}

function spTogglePlay() {
  spAction(_spIsPlaying ? 'pause' : 'play');
}

function spToggleShuffle() {
  _spShuffle = !_spShuffle;
  pyCall('spotify_action', JSON.stringify({action: 'shuffle', state: _spShuffle}));
  var btn = R('spShuffleBtn');
  if (btn) btn.classList.toggle('active', _spShuffle);
}

function spSetVolume(val) {
  var v = R('spVolVal');
  if (v) v.textContent = val + '%';
  pyCall('spotify_action', JSON.stringify({action: 'volume', value: parseInt(val)}));
}

function spSearch() {
  var q = R('spSearchInput');
  if (!q || !q.value.trim()) return;
  var box = R('spSearchResults');
  if (box) box.innerHTML = '<div style="padding:10px;color:var(--text3);font-size:12px;">⟳ Шукаю...</div>';
  pyCall('spotify_action', JSON.stringify({action: 'search', query: q.value.trim()}));
}

function spPlayUri(uri, name, artist) {
  pyCall('spotify_action', JSON.stringify({action: 'play_uri', uri: uri}));
  showToast('🎵 ' + artist + ' — ' + name);
}

// ── Вибране ──────────────────────────────────────────────────────────────────
function spSaveCurrent() {
  if (!_spCurrentUri) { showToast('⚠ Зараз нічого не грає'); return; }
  var track  = R('spTrack');
  var artist = R('spArtist');
  var cover  = R('spCover');
  spAddFav(_spCurrentUri,
    track  ? track.textContent  : '?',
    artist ? artist.textContent : '?',
    cover  ? cover.src          : '');
}

function spAddFav(uri, name, artist, cover) {
  if (_spFavorites.find(function(f){ return f.uri === uri; })) {
    showToast('⭐ Вже у вибраному'); return;
  }
  _spFavorites.unshift({uri: uri, name: name, artist: artist, cover: cover || ''});
  if (_spFavorites.length > 50) _spFavorites.pop();
  localStorage.setItem('axis_sp_fav', JSON.stringify(_spFavorites));
  spRenderFavorites();
  showToast('⭐ Додано: ' + name);
}

function spRemoveFav(uri) {
  _spFavorites = _spFavorites.filter(function(f){ return f.uri !== uri; });
  localStorage.setItem('axis_sp_fav', JSON.stringify(_spFavorites));
  spRenderFavorites();
}

function spRenderFavorites() {
  var box = R('spFavorites');
  if (!box) return;
  if (!_spFavorites.length) {
    box.innerHTML = '<div style="padding:10px;color:var(--text3);font-size:12px;">Поки порожньо — додай треки через ⭐</div>';
    return;
  }
  box.innerHTML = _spFavorites.map(function(t) {
    return '<div class="sp-row" onclick="spPlayUri(\'' + _spEscUri(t.uri) + '\',\'' +
      _spEsc(t.name) + '\',\'' + _spEsc(t.artist) + '\')">'
      + (t.cover ? '<img src="'+_spEscUrl(t.cover)+'" class="sp-row-img">' : '<div class="sp-row-img sp-row-no-img">🎵</div>')
      + '<div class="sp-row-info"><div class="sp-row-name">' + _spEsc(t.name) + '</div>'
      + '<div class="sp-row-artist">' + _spEsc(t.artist) + '</div></div>'
      + '<button class="sp-fav-btn sp-fav-remove" onclick="event.stopPropagation();spRemoveFav(\'' + _spEscUri(t.uri) + '\')" title="Видалити">✕</button>'
      + '</div>';
  }).join('');
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function _spFmtMs(ms) {
  var s = Math.floor(ms / 1000);
  return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
}
function _spEsc(s) {
  return (s || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
function _spEscUri(s) {
  return String(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'").replace(/"/g,'&quot;');
}
function _spEscUrl(u) {
  return String(u||'').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
