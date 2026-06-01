/* AXIS OS — Profile Page */
'use strict';

var _profileData = null;

var AVATARS = ['👤','🧑','👨‍💻','👩‍💻','🤖','🦊','🐉','🌟','⚡','🔮','🎯','🦁'];

// Field id → profile key mapping
var PF_FIELDS = [
  'last_name','first_name','middle_name','birth_date','language',
  'email','phone','telegram','website',
  'country','city','address','postal_code',
  'company','position','inn','edrpou','iban','bank','mfo',
  'doc_signatory','doc_basis',
];

function initProfilePage() {
  pyCall('get_profile', '{}');
}

// ── Push handler ──────────────────────────────────────────────────────────────
function handleProfileData(d) {
  _profileData = d;
  _renderProfile();
}

// ── Render ────────────────────────────────────────────────────────────────────
function _renderProfile() {
  var d = _profileData;
  if (!d) return;

  // Avatar
  var av = R('profileAvatar');
  if (av) av.textContent = d.avatar || '👤';

  // All text fields
  PF_FIELDS.forEach(function(key) {
    var el = R('pf_' + key);
    if (!el) return;
    if (el.tagName === 'SELECT') el.value = d[key] || '';
    else el.value = d[key] || '';
  });

  // Checkbox
  var stamp = R('pf_doc_stamp');
  if (stamp) stamp.checked = !!d.doc_stamp;

  // Avatar picker
  _renderAvatarPicker(d.avatar || '👤');

  // Full name display in avatar area
  var nameDisp = R('profileFullName');
  if (nameDisp) {
    var full = [d.last_name, d.first_name, d.middle_name].filter(Boolean).join(' ')
               || d.name || '—';
    nameDisp.textContent = full;
  }

  // Stats
  _renderStats(d.stats || {});

  // Member since
  var sinceEl = R('profileSince');
  if (sinceEl && d.created_at) {
    try {
      var dt = new Date(d.created_at);
      sinceEl.textContent = dt.toLocaleDateString('uk-UA',
        {year:'numeric', month:'long', day:'numeric'});
    } catch(e) {}
  }

  // License badge
  pyCall('get_license_status', '{}');
}

function _renderAvatarPicker(current) {
  var grid = R('avatarPickerGrid');
  if (!grid) return;
  grid.innerHTML = AVATARS.map(function(a) {
    return '<span class="av-opt' + (a === current ? ' av-opt-sel' : '') +
           '" onclick="selectAvatar(' + JSON.stringify(a) + ')">' + a + '</span>';
  }).join('');
}

function selectAvatar(emoji) {
  var av = R('profileAvatar');
  if (av) av.textContent = emoji;
  if (_profileData) _profileData.avatar = emoji;
  _renderAvatarPicker(emoji);
}

function _renderStats(st) {
  var items = [
    {id:'statAiReq',    val: st.ai_requests      || 0},
    {id:'statSphere',   val: st.sphere_queries    || 0},
    {id:'statPomodoro', val: st.pomodoro_sessions || 0},
    {id:'statNotes',    val: st.notes_created     || 0},
    {id:'statCommands', val: st.commands_run      || 0},
  ];
  items.forEach(function(item) {
    var el = R(item.id);
    if (el) el.textContent = item.val;
  });
  var lastEl = R('statLastActive');
  if (lastEl && st.last_active) {
    try {
      var d = new Date(st.last_active);
      lastEl.textContent = d.toLocaleString('uk-UA',
        {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
    } catch(e) {}
  }
}

// ── Save ──────────────────────────────────────────────────────────────────────
function saveProfile() {
  // Validate INN — 10 digits
  var inn = (R('pf_inn')||{}).value||'';
  if (inn && !/^\d{10}$/.test(inn.replace(/\s/g,''))) {
    showToast('⚠️ ІПН має містити 10 цифр'); return;
  }
  // Validate IBAN — starts with UA + 27 chars
  var iban = (R('pf_iban')||{}).value||'';
  if (iban && !/^UA\d{27}$/.test(iban.replace(/\s/g,''))) {
    showToast('⚠️ IBAN має починатись з UA та містити 29 символів'); return;
  }
  // Validate email if provided
  var email = (R('pf_email')||{}).value||'';
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    showToast('⚠️ Невірний формат email'); return;
  }

  var data = { avatar: (_profileData && _profileData.avatar) || '👤' };

  PF_FIELDS.forEach(function(key) {
    var el = R('pf_' + key);
    if (el) data[key] = el.tagName === 'SELECT' ? el.value : el.value.trim();
  });

  var stamp = R('pf_doc_stamp');
  data.doc_stamp = stamp ? stamp.checked : false;

  pyCall('save_profile', JSON.stringify(data));
}

// ── axisPush integration ──────────────────────────────────────────────────────
(function() {
  var _orig = window.axisPush;
  window.axisPush = function(type, jsonStr) {
    try {
      var d = JSON.parse(jsonStr);
      if (type === 'profile_data') { handleProfileData(d); return; }
      if (type === 'license_status') {
        var el = R('profileLicBadge');
        if (el) {
          el.textContent = (d.emoji || '') + ' ' + (d.name || d.tier);
          el.className   = 'lic-tier-badge lic-tier-' + d.tier;
        }
      }
    } catch(e) {}
    _orig && _orig(type, jsonStr);
  };
})();

// ── Hook into showPage ────────────────────────────────────────────────────────
(function() {
  var _orig = window.showPage;
  window.showPage = function(id) {
    _orig && _orig(id);
    if (id === 'profile') setTimeout(initProfilePage, 50);
  };
})();
