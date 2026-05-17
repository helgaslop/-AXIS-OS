/* AXIS OS ? Notes */
// ═══ NOTES ═══
var _notes = JSON.parse(localStorage.getItem('axis_notes') || '[]');
var _noteActive = null;
var _notePreviewOn = false;

function notesInit() {
  if (!_notes.length) {
    _notes = [{id: Date.now(), title: 'Перша нотатка', body: '# Ласкаво просимо до Нотаток!\n\nТут можна зберігати будь-які записи.\n\n- Підтримується **Markdown**\n- Теги для категоризації\n- Автозбереження', tag: 'ідея', updatedAt: Date.now()}];
    notesPersist();
  }
  notesRenderList();
  if (_notes.length) notesOpen(_notes[0].id);
}

function notesRenderList() {
  var q = (R('notesSearch') ? R('notesSearch').value : '').toLowerCase();
  var el = R('notesList'); if (!el) return;
  var filtered = _notes.filter(function(n){
    return !q || (n.title+n.body).toLowerCase().includes(q);
  }).sort(function(a,b){ return b.updatedAt - a.updatedAt; });
  if (!filtered.length) {
    el.innerHTML = '<div class="notes-empty">Нічого не знайдено</div>'; return;
  }
  el.innerHTML = filtered.map(function(n){
    var active = _noteActive && _noteActive.id === n.id ? ' active' : '';
    var preview = n.body.replace(/[#*`\n]/g,' ').trim().slice(0,60);
    var tag = n.tag ? '<span class="note-tag">'+n.tag+'</span>' : '';
    var date = new Date(n.updatedAt).toLocaleDateString('uk-UA',{day:'2-digit',month:'2-digit'});
    return '<div class="note-item'+active+'" onclick="notesOpen('+n.id+')">'
      + '<div class="note-item-title">'+(n.title||'Без назви')+'</div>'
      + '<div class="note-item-preview">'+(preview||'Порожня нотатка')+'</div>'
      + '<div class="note-item-meta">'+tag+'<span class="note-date">'+date+'</span></div>'
      + '</div>';
  }).join('');
}

function notesOpen(id) {
  _noteActive = _notes.find(function(n){ return n.id === id; });
  if (!_noteActive) return;
  if (R('noteTitle'))  R('noteTitle').value = _noteActive.title || '';
  if (R('noteBody'))   R('noteBody').value  = _noteActive.body  || '';
  if (R('noteTag'))    R('noteTag').value   = _noteActive.tag   || '';
  notesUpdateMeta();
  notesRenderList();
  if (_notePreviewOn) notesRenderPreview();
}

function notesNew() {
  var n = {id: Date.now(), title: '', body: '', tag: '', updatedAt: Date.now()};
  _notes.unshift(n);
  notesPersist();
  notesOpen(n.id);
  setTimeout(function(){ if(R('noteTitle')) R('noteTitle').focus(); }, 50);
}

function notesSave() {
  if (!_noteActive) return;
  _noteActive.title     = R('noteTitle') ? R('noteTitle').value : '';
  _noteActive.body      = R('noteBody')  ? R('noteBody').value  : '';
  _noteActive.tag       = R('noteTag')   ? R('noteTag').value   : '';
  _noteActive.updatedAt = Date.now();
  notesPersist();
  notesUpdateMeta();
  notesRenderList();
}

function notesDelete() {
  if (!_noteActive) return;
  if (!confirm('Видалити нотатку «'+(_noteActive.title||'Без назви')+'»?')) return;
  _notes = _notes.filter(function(n){ return n.id !== _noteActive.id; });
  _noteActive = null;
  notesPersist();
  if (R('noteTitle')) R('noteTitle').value = '';
  if (R('noteBody'))  R('noteBody').value  = '';
  notesRenderList();
  if (_notes.length) notesOpen(_notes[0].id);
}

function notesCopy() {
  var text = (_noteActive ? _noteActive.body : '');
  if (!text) return;
  navigator.clipboard.writeText(text).then(function(){ showToast('📋 Скопійовано'); });
}

function notesTogglePreview() {
  _notePreviewOn = !_notePreviewOn;
  var p = R('notesPreview');
  var b = R('notePreviewBtn');
  if (p) p.style.display = _notePreviewOn ? 'block' : 'none';
  if (b) b.style.background = _notePreviewOn ? 'rgba(34,197,94,.12)' : '';
  if (_notePreviewOn) notesRenderPreview();
}

function notesAutoPreview() {
  if (_notePreviewOn) notesRenderPreview();
  notesUpdateMeta();
}

function notesRenderPreview() {
  var p = R('notesPreview'); if (!p) return;
  var body = R('noteBody') ? R('noteBody').value : '';
  p.innerHTML = typeof marked !== 'undefined' ? marked.parse(body) : body.replace(/\n/g,'<br>');
}

function notesUpdateMeta() {
  var body = R('noteBody') ? R('noteBody').value : '';
  var words = body.trim() ? body.trim().split(/\s+/).length : 0;
  if (R('notesWordCount')) R('notesWordCount').textContent = words + ' слів · ' + body.length + ' симв.';
  if (R('notesSavedAt') && _noteActive) {
    var d = new Date(_noteActive.updatedAt);
    R('notesSavedAt').textContent = 'Збережено ' + d.toLocaleTimeString('uk-UA',{hour:'2-digit',minute:'2-digit'});
  }
}

function notesPersist() {
  localStorage.setItem('axis_notes', JSON.stringify(_notes));
}
